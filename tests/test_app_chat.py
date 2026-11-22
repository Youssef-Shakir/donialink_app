# -*- coding: utf-8 -*-
import base64
import json
from unittest.mock import patch

from odoo.tests import HttpCase, new_test_user, tagged

PNG = base64.b64encode(b'\x89PNG\r\n\x1a\n-dl-chat').decode()


@tagged('post_install', '-at_install')
class TestAppChat(HttpCase):
    """Chat on Odoo Discuss: portal and internal people of the same companies, members only."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ali = new_test_user(cls.env, 'dl_chat_ali', password='dl_chat_ali1', groups='base.group_portal')
        cls.boss = new_test_user(cls.env, 'dl_chat_boss', password='dl_chat_boss1', groups='base.group_user')
        cls.omar = new_test_user(cls.env, 'dl_chat_omar', password='dl_chat_omar1', groups='base.group_portal')
        other = cls.env['res.company'].create({'name': 'DL Chat Other Co'})
        cls.far = new_test_user(cls.env, 'dl_chat_far', password='dl_chat_far1', groups='base.group_portal',
                                company_id=other.id, company_ids=[(6, 0, other.ids)])

    def api(self, endpoint, **params):
        response = self.url_open('/dl/app/api/%s' % endpoint, data=json.dumps({'params': params}),
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        return response.json()['result']

    def test_direct_chat(self):
        self.env['mail.push.device'].sudo().create({
            'partner_id': self.boss.partner_id.id, 'endpoint': 'https://push.example.com/dl-chat',
            'keys': json.dumps({'p256dh': 'x', 'auth': 'y'})})
        self.env['mail.push.device'].sudo().get_web_push_vapid_public_key()   # keys exist
        sent_pushes = []
        patcher = patch('odoo.addons.mail.models.mail_thread.push_to_end_point',
                        side_effect=lambda **kw: sent_pushes.append(json.loads(kw['payload'])))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.authenticate('dl_chat_ali', 'dl_chat_ali1')
        people = [p['id'] for p in self.api('chat_people')['people']]
        self.assertIn(self.boss.id, people)
        self.assertNotIn(self.far.id, people, 'only the people of my companies')
        self.assertNotIn(self.ali.id, people)
        self.assertEqual(self.api('chat_open', user_id=self.far.id)['error'], 'refused')
        chat_id = self.api('chat_open', user_id=self.boss.id)['chat_id']
        self.assertEqual(self.api('chat_open', user_id=self.boss.id)['chat_id'], chat_id, 'one chat per pair')
        sent = self.api('chat_send', chat_id=chat_id, body='Gas is finished <b>now</b>')['message']
        self.assertTrue(sent['mine'])
        self.assertIn('&lt;b&gt;', sent['body'], 'text is escaped')
        channel = self.env['discuss.channel'].browse(chat_id)
        self.assertEqual(channel.channel_type, 'chat')
        self.assertTrue(sent_pushes, 'Odoo pushes the message to the phone')
        self.assertEqual(sent_pushes[-1]['options']['data']['model'], 'discuss.channel')
        self.assertEqual(sent_pushes[-1]['options']['data']['res_id'], chat_id)

        self.authenticate('dl_chat_boss', 'dl_chat_boss1')
        chats = self.api('chats')['chats']
        row = next(c for c in chats if c['id'] == chat_id)
        self.assertEqual((row['name'], row['unread']), (self.ali.name, 1))
        self.assertEqual(self.env['discuss.channel'].with_user(self.boss).dl_app_chat_badge(), 1)
        thread = self.api('chat_messages', chat_id=chat_id)
        self.assertEqual([m['mine'] for m in thread['messages']], [False])
        self.assertEqual(self.env['discuss.channel'].with_user(self.boss).dl_app_chat_badge(), 0, 'read')
        reply = self.api('chat_send', chat_id=chat_id, body='Coming')['message']
        self.assertEqual(self.api('chat_messages', chat_id=chat_id, after=sent['id'])['messages'][0]['id'], reply['id'])

        self.authenticate('dl_chat_omar', 'dl_chat_omar1')
        self.assertEqual(self.api('chat_messages', chat_id=chat_id)['error'], 'refused', 'not a member')
        self.assertEqual(self.api('chat_send', chat_id=chat_id, body='hi')['error'], 'refused')

    def test_group_with_photo(self):
        self.authenticate('dl_chat_boss', 'dl_chat_boss1')
        chat_id = self.api('chat_group', name='Kitchen', user_ids=[self.ali.id, self.omar.id])['chat_id']
        channel = self.env['discuss.channel'].browse(chat_id)
        self.assertEqual(channel.channel_type, 'group')
        self.assertEqual(set(channel.channel_member_ids.partner_id.ids),
                         {self.boss.partner_id.id, self.ali.partner_id.id, self.omar.partner_id.id})
        message = self.api('chat_send', chat_id=chat_id, files=[{'content_b64': PNG, 'filename': 'fryer.png',
                                                                 'mimetype': 'image/png'}])['message']
        url = message['files'][0]['url']
        self.authenticate('dl_chat_ali', 'dl_chat_ali1')
        self.assertIn('Kitchen', [c['name'] for c in self.api('chats')['chats']])
        self.assertEqual(self.url_open(url).status_code, 200, 'members open the photo')
        self.authenticate('dl_chat_far', 'dl_chat_far1')
        self.assertEqual(self.url_open(url).status_code, 404, 'others do not')
        self.assertEqual(self.api('chat_group', name='X', user_ids=[self.ali.id])['error'], 'refused')
