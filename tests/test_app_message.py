# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAppMessage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Message = cls.env['donialink.app.message']
        cls.owner = new_test_user(cls.env, 'dl_owner', groups='base.group_user', name='Ali Owner')
        cls.cashier = new_test_user(cls.env, 'dl_cashier', groups='base.group_portal', name='Omar Cashier')
        cls.kind = cls.env['donialink.app.kind'].create({
            'code': 'test_kind', 'name': 'Test kind', 'recipient_ids': [(6, 0, (cls.owner | cls.cashier).ids)]})

    def test_send_to_kind_recipients(self):
        messages = self.Message.send('test_kind', 'Session closed', 'POS/0012 closed with 150,000 IQD')
        self.assertEqual(messages.user_id, self.owner | self.cashier)
        self.assertEqual(messages[0].preview, 'POS/0012 closed with 150,000 IQD')
        self.assertTrue(all(not m.is_read for m in messages))

    def test_muted_people_are_left_out(self):
        self.kind.muted_user_ids = self.cashier
        self.assertEqual(self.Message.send('test_kind', 'Hello').user_id, self.owner)
        # named people too
        self.assertEqual(self.Message.send('test_kind', 'Hello', users=self.cashier), self.Message)
        # unless the kind can't be switched off
        self.kind.user_can_mute = False
        self.assertEqual(self.Message.send('test_kind', 'Hello', users=self.cashier).user_id, self.cashier)

    def test_company_filter(self):
        other = self.env['res.company'].create({'name': 'Branch 2'})
        self.owner.write({'company_ids': [(4, other.id)]})
        self.assertEqual(self.Message.send('test_kind', 'Branch 2 report', company=other).user_id, self.owner)

    def test_file_is_kept_once(self):
        messages = self.Message.send('test_kind', 'Weekly report', file=('weekly.pdf', b'%PDF-1.4 test', 'application/pdf'))
        self.assertEqual(len(messages.attachment_id), 1)
        self.assertEqual(messages.attachment_id.res_model, 'donialink.app.message')

    def test_push_rows(self):
        self.env['mail.push.device'].sudo().create({
            'partner_id': self.owner.partner_id.id, 'endpoint': 'https://push.example.com/abc',
            'keys': '{"p256dh": "x", "auth": "y"}'})
        message = self.Message.send(title='Hi', users=self.owner)
        self.assertEqual(message.pushed, 1)
        push = self.env['mail.push'].sudo().search([('mail_push_device_id.partner_id', '=', self.owner.partner_id.id)])
        self.assertIn('/dl/app#msg-%s' % message.id, push.payload)
        # no push for a kind that doesn't push
        self.kind.push = False
        self.assertEqual(self.Message.send('test_kind', 'Quiet', users=self.owner).pushed, 0)

    def test_needs_title_and_people(self):
        with self.assertRaises(UserError):
            self.Message.send('test_kind', '')
        with self.assertRaises(UserError):
            self.Message.send(None, 'No one')

    def test_people_see_only_their_messages(self):
        self.Message.send('test_kind', 'For both')
        self.assertEqual(self.Message.with_user(self.cashier).search([]).user_id, self.cashier)
        self.assertEqual(self.Message.with_user(self.owner).search([]).user_id, self.owner)
