# -*- coding: utf-8 -*-
import json

from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAppHttp(HttpCase):

    def setUp(self):
        super().setUp()
        self.owner = new_test_user(self.env, 'dl_http_owner', password='dl_http_owner1', groups='base.group_user')
        self.other = new_test_user(self.env, 'dl_http_other', password='dl_http_other1', groups='base.group_portal')
        self.Message = self.env['donialink.app.message']

    def api(self, action, **params):
        response = self.url_open('/dl/app/api/%s' % action, data=json.dumps({'params': params}),
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        return response.json()['result']

    def test_page_needs_login(self):
        response = self.url_open('/dl/app', allow_redirects=False)
        self.assertIn('/web/login', response.headers.get('Location', ''))
        self.authenticate('dl_http_owner', 'dl_http_owner1')
        response = self.url_open('/dl/app')
        self.assertEqual(response.status_code, 200)
        self.assertIn('/dl/app/manifest.webmanifest', response.text)

    def test_manifest_and_worker(self):
        manifest = self.url_open('/dl/app/manifest.webmanifest').json()
        self.assertEqual(manifest['scope'], '/dl/app')
        worker = self.url_open('/dl/app/sw.js')
        self.assertEqual(worker.headers['Service-Worker-Allowed'], '/dl/app')
        self.assertNotIn('{{', worker.text)

    def test_inbox_read_and_kinds(self):
        message = self.Message.send('report', 'Weekly report', 'Sales up 12%', users=self.owner,
                                    file=('w.pdf', b'%PDF-1.4', 'application/pdf'))
        self.Message.send('report', 'Not yours', users=self.other)
        self.authenticate('dl_http_owner', 'dl_http_owner1')
        session = self.api('session')
        self.assertEqual(session['unread'], 1)
        self.assertIn('inbox', [s['key'] for s in session['screens']])
        self.assertIn('odoo', [s['key'] for s in session['screens']])  # internal user: Open Odoo
        self.assertTrue(session['push_key'])
        inbox = self.api('inbox')
        self.assertEqual([m['id'] for m in inbox['messages']], [message.id])
        detail = self.api('message', message_id=message.id)
        self.assertEqual(detail['unread'], 0)
        self.assertIn('Sales up 12%', detail['message']['body'])
        self.assertTrue(self.url_open('/dl/app/file/%s' % message.id).content.startswith(b'%PDF'))
        kinds = self.api('kind_set', code='report', on=False)['kinds']
        self.assertFalse([k for k in kinds if k['code'] == 'report'][0]['on'])
        self.assertIn(self.owner, self.env.ref('donialink_app.kind_report').muted_user_ids)

    def test_other_people_messages_are_hidden(self):
        theirs = self.Message.send('report', 'Theirs', users=self.other,
                                   file=('t.pdf', b'%PDF-1.4', 'application/pdf'))
        self.authenticate('dl_http_owner', 'dl_http_owner1')
        self.assertEqual(self.api('message', message_id=theirs.id).get('error'), 'not_found')
        self.assertEqual(self.url_open('/dl/app/file/%s' % theirs.id).status_code, 404)
        self.api('read', all=True)
        self.assertFalse(theirs.is_read)

    def test_portal_user_and_push_subscribe(self):
        self.authenticate('dl_http_other', 'dl_http_other1')
        session = self.api('session')
        self.assertNotIn('odoo', [s['key'] for s in session['screens']])  # portal: no Open Odoo tile
        answer = self.api('push_subscribe', vapid_key=session['push_key'], subscription={
            'endpoint': 'https://push.example.com/portal', 'keys': {'p256dh': 'p', 'auth': 'a'}})
        self.assertTrue(answer['push'])
        device = self.env['mail.push.device'].sudo().search([('endpoint', '=', 'https://push.example.com/portal')])
        self.assertEqual(device.partner_id, self.other.partner_id)
        self.assertEqual(self.api('push_subscribe', vapid_key='old', subscription={})['error'], 'push_key')
        self.api('push_unsubscribe', endpoint='https://push.example.com/portal')
        self.assertFalse(device.exists())

    def test_client_branding(self):
        """The app carries the client's name and logo, not DoniaLink's."""
        import base64
        import io
        from PIL import Image
        company = self.owner.company_id
        company.name = 'Cafe Baghdad'
        buf = io.BytesIO()
        Image.new('RGB', (300, 120), (200, 30, 30)).save(buf, format='PNG')
        company.logo = base64.b64encode(buf.getvalue())
        self.authenticate('dl_http_owner', 'dl_http_owner1')
        manifest = self.url_open('/dl/app/manifest.webmanifest').json()
        self.assertEqual(manifest['name'], 'Cafe Baghdad')
        self.assertTrue(all(i['src'].startswith('/dl/app/icon/') for i in manifest['icons']))
        icon = self.url_open('/dl/app/icon/192.png')
        self.assertEqual(icon.headers['Content-Type'], 'image/png')
        image = Image.open(io.BytesIO(icon.content))
        self.assertEqual(image.size, (192, 192))
        self.assertEqual(image.getpixel((96, 96))[:3], (200, 30, 30), 'the logo is in the middle')
        self.assertIn('Cafe Baghdad', self.url_open('/dl/app').text)
        self.assertEqual(self.api('session')['logo'], '/dl/app/icon/192.png')
        company.logo = False
        self.assertEqual(self.url_open('/dl/app/icon/512.png').status_code, 200, 'falls back to the default icon')

    def test_change_password(self):
        """People change their own password in the app and stay logged in."""
        self.authenticate('dl_http_other', 'dl_http_other1')
        self.assertEqual(self.api('password', old='wrong-one', new='New-pass-123')['error'], 'refused')
        self.assertEqual(self.api('password', old='dl_http_other1', new='short')['error'], 'refused')
        self.assertTrue(self.api('password', old='dl_http_other1', new='New-pass-123')['ok'])
        self.assertIn('unread', self.api('session'), 'the session stays open')
        self.authenticate('dl_http_other', 'New-pass-123')
        self.assertIn('unread', self.api('session'))

    def test_language(self):
        self.authenticate('dl_http_other', 'dl_http_other1')
        self.assertEqual(self.api('lang_set', lang='ar')['lang'], 'ar_001')
        self.assertEqual(self.other.lang, 'ar_001')
        self.assertEqual(self.url_open('/dl/app').text.count('dir="rtl"'), 1, 'the app opens right to left')
        self.assertEqual(self.api('lang_set', lang='en')['lang'], 'en_US')
        self.assertEqual(self.api('lang_set', lang='fr')['error'], 'bad_request')
