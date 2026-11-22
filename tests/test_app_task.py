# -*- coding: utf-8 -*-
import base64
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, new_test_user, tagged

PNG = base64.b64encode(b'\x89PNG\r\n\x1a\n-dl-task-proof').decode()


@tagged('post_install', '-at_install')
class TestAppTask(HttpCase):
    """Employee tasks: access, notifications, photos, repeats, reminders, the app API and create_for()."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.boss = new_test_user(cls.env, 'dl_task_boss', password='dl_task_boss1',
                                 groups='base.group_user,donialink_app.group_task_manager')
        cls.ali = new_test_user(cls.env, 'dl_task_ali', password='dl_task_ali1', groups='base.group_portal')
        cls.omar = new_test_user(cls.env, 'dl_task_omar', password='dl_task_omar1', groups='base.group_portal')
        cls.Task = cls.env['donialink.app.task']
        cls.Message = cls.env['donialink.app.message']

    def _messages(self, kind, user=None):
        domain = [('kind_code', '=', kind)]
        if user:
            domain.append(('user_id', '=', user.id))
        return self.Message.search(domain)

    def _task(self, **vals):
        return self.Task.with_user(self.boss).create(dict({
            'name': 'Clean the fryer', 'user_ids': [(6, 0, self.ali.ids)]}, **vals))

    def test_assign_notifies_and_access(self):
        task = self._task(deadline=fields.Datetime.now() + timedelta(hours=3))
        message = self._messages('task_assigned', self.ali)
        self.assertEqual(len(message), 1)
        self.assertEqual(message.url, '#task-%s' % task.id)
        self.assertTrue(task.with_user(self.ali).name, 'the assignee reads it')
        with self.assertRaises(AccessError):
            task.with_user(self.omar).check_access('read')
        task.write({'user_ids': [(4, self.omar.id)]})
        self.assertEqual(len(self._messages('task_assigned', self.omar)), 1, 'a new assignee is told')
        other = self.Task.create({'name': 'Not mine', 'user_ids': [(6, 0, self.omar.ids)]})
        self.assertNotIn(other, self.Task.with_user(self.ali).search([]))
        self.assertIn(other, self.Task.with_user(self.boss).search([]), 'managers see the tasks of their companies')
        with self.assertRaises(AccessError):
            other.with_user(self.ali).action_start()

    def test_done_with_photo(self):
        task = self._task(photo_required=True, line_ids=[(0, 0, {'name': 'Oil out'}), (0, 0, {'name': 'Wipe'})])
        mine = task.with_user(self.ali)
        mine.action_start()
        self.assertEqual(task.state, 'progress')
        with self.assertRaises(UserError):
            mine.action_done(note='ok')
        mine.action_done(note='All clean', photos=[('fryer.jpg', b'\x89PNG-proof', 'image/png')])
        self.assertEqual((task.state, task.done_by_id, task.done_note), ('done', self.ali, 'All clean'))
        self.assertEqual(len(task.photo_ids), 1)
        done = self._messages('task_done')
        self.assertIn(self.boss, done.user_id, 'the creator is told')
        self.assertNotIn(self.ali, done.user_id)
        with self.assertRaises(AccessError):
            task.with_user(self.omar).action_cancel()

    def test_repeat(self):
        deadline = datetime(2026, 11, 20, 9, 0)
        daily = self._task(repeat='daily', deadline=deadline, line_ids=[(0, 0, {'name': 'Count'})])
        daily.with_user(self.ali).action_done()
        nxt = self.Task.search([('previous_id', '=', daily.id)])
        self.assertEqual(nxt.deadline, deadline + timedelta(days=1))
        self.assertEqual((nxt.state, len(nxt.line_ids), nxt.line_ids.done), ('todo', 1, False))
        self.assertTrue(daily.next_created)
        # weekly on Monday and Thursday: from Friday 20 Nov the next is Monday 23 Nov
        weekly = self._task(repeat='weekly', repeat_weekdays='0,3', deadline=deadline)
        weekly._create_next()
        self.assertEqual(self.Task.search([('previous_id', '=', weekly.id)]).deadline, datetime(2026, 11, 23, 9, 0))

    def test_reminders_and_badge(self):
        soon = self._task(name='Soon', deadline=fields.Datetime.now() + timedelta(minutes=30))
        late = self._task(name='Late', deadline=fields.Datetime.now() - timedelta(hours=2))
        self.assertEqual(self.Task.with_user(self.ali).dl_app_task_badge(), 2)
        self.Task._cron_reminders()
        self.assertTrue(soon.reminder_sent and late.overdue_sent)
        self.assertEqual(len(self._messages('task_due', self.ali)), 2)
        self.assertIn(self.boss, self._messages('task_due').user_id, 'the creator hears about overdue tasks')
        self.Task._cron_reminders()
        self.assertEqual(len(self._messages('task_due', self.ali)), 2, 'once only')
        self.assertTrue(late.is_overdue)
        self.assertIn(late, self.Task.search([('is_overdue', '=', True)]))

    def test_create_for(self):
        task = self.Task.create_for(self.ali | self.omar, 'Explain the difference', description='POS/0042',
                                    lines=['Count again'], origin='expense_cash_control',
                                    res_model='res.users', res_id=self.ali.id)
        self.assertEqual((task.user_ids, task.origin, len(task.line_ids)), (self.ali | self.omar, 'expense_cash_control', 1))
        with self.assertRaises(UserError):
            self.Task.create_for(self.env['res.users'], 'Nobody')

    def api(self, endpoint, **params):
        response = self.url_open('/dl/app/api/%s' % endpoint, data=json.dumps({'params': params}),
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        return response.json()['result']

    def test_app_api(self):
        task = self._task(line_ids=[(0, 0, {'name': 'Check gas'})])
        self.authenticate('dl_task_ali', 'dl_task_ali1')
        self.assertEqual([t['id'] for t in self.api('tasks_mine')['tasks']], [task.id])
        detail = self.api('task', task_id=task.id)['task']
        self.assertEqual(detail['checklist'][0]['name'], 'Check gas')
        self.api('task_line', line_id=detail['checklist'][0]['id'], done=True)
        self.api('task_comment', task_id=task.id, body='On it')
        done = self.api('task_do', task_id=task.id, step='done', note='Fine',
                        photos=[{'content_b64': PNG, 'filename': 'gas.png', 'mimetype': 'image/png'}])['task']
        self.assertEqual((done['state'], len(done['photos'])), ('done', 1))
        self.assertEqual(self.api('tasks_team')['error'], 'refused', 'staff do not manage the team')
        other = self.Task.create({'name': 'Omar only', 'user_ids': [(6, 0, self.omar.ids)]})
        self.assertEqual(self.api('task', task_id=other.id)['error'], 'refused')
        self.authenticate('dl_task_boss', 'dl_task_boss1')
        created = self.api('task_create', name='Close the shop', user_ids=[self.omar.id], lines=['Lights', 'Door'],
                           repeat='weekly', repeat_weekdays='4')['task']
        self.assertEqual((created['lines'], created['repeat']), (2, 'weekly'))
        team = self.api('tasks_team', user_id=self.omar.id)
        self.assertIn(created['id'], [t['id'] for t in team['tasks']])

    def test_dashboard_card(self):
        admin = new_test_user(self.env, 'dl_task_admin', groups='base.group_user,donialink_app.group_app_manager')
        Admin = self.env['donialink.app.admin'].with_user(admin)

        def overdue():
            return next(s for s in Admin.get_data()['sections'] if s['key'] == 'tasks')['numbers'][1]['value']
        before = overdue()
        self._task(deadline=fields.Datetime.now() - timedelta(hours=1))
        self.assertEqual(overdue(), before + 1, 'one more overdue')

    def test_assignee_can_not_edit_directly(self):
        """Assignees work through the actions only: no direct state, deadline, people or done_by changes."""
        task = self._task(photo_required=True, deadline=fields.Datetime.now() + timedelta(days=1),
                          line_ids=[(0, 0, {'name': 'Oil out'})])
        mine = task.with_user(self.ali)
        for vals in ({'state': 'done'}, {'deadline': fields.Datetime.now() + timedelta(days=9)},
                     {'user_ids': [(4, self.omar.id)]}, {'done_by_id': self.omar.id}, {'priority': '2'}):
            with self.assertRaises(AccessError):
                mine.write(vals)
        line = mine.line_ids
        with self.assertRaises(AccessError):
            line.write({'name': 'Something else'})
        with self.assertRaises(AccessError):
            self.env['donialink.app.task.line'].with_user(self.ali).create({'task_id': task.id, 'name': 'Extra'})
        line.done = True
        self.assertTrue(line.done, 'ticking is allowed')
        mine.action_start()
        with self.assertRaises(UserError):
            mine.action_done()
        mine.action_done(photos=[('p.jpg', b'\x89PNG', 'image/png')])
        self.assertEqual((task.state, task.done_by_id), ('done', self.ali))
        # the creator and managers still edit
        task.with_user(self.boss).write({'priority': '2'})
        self.assertEqual(task.priority, '2')

    def test_portal_staff_of_another_company(self):
        """A portal person sees his tasks even when the task's company is not one he can read."""
        other = self.env['res.company'].create({'name': 'DL Task Other Co'})
        self.ali.company_ids |= other
        task = self.Task.create({'name': 'Other shop', 'user_ids': [(6, 0, self.ali.ids)], 'company_id': other.id})
        self.ali.write({'company_ids': [(6, 0, self.env.company.ids)], 'company_id': self.env.company.id})
        self.authenticate('dl_task_ali', 'dl_task_ali1')
        mine = self.api('tasks_mine')
        self.assertNotIn('error', mine, mine.get('message'))
        self.assertIn(task.id, [t['id'] for t in mine['tasks']])
        self.assertEqual(next(t for t in mine['tasks'] if t['id'] == task.id)['company'], 'DL Task Other Co')
        self.assertEqual(self.api('task', task_id=task.id)['task']['id'], task.id)

    def test_assigned_notification_in_their_language(self):
        """The new-task notification reaches each assignee in his language; internal ones also in Odoo."""
        self.env['res.lang']._activate_lang('ar_001')
        self.ali.lang = 'ar_001'
        task = self.Task.with_user(self.boss).create({'name': 'Fryer', 'user_ids': [(6, 0, (self.ali | self.boss).ids)],
                                                      'deadline': fields.Datetime.now() + timedelta(hours=5)})
        arabic = self._messages('task_assigned', self.ali)
        self.assertTrue(arabic.title.startswith('مهمة جديدة'), arabic.title)
        self.assertEqual(arabic.url, '#task-%s' % task.id)
        self.assertTrue(self._messages('task_assigned', self.boss).title.startswith('New task'))
        notified = self.env['mail.message'].search([('model', '=', task._name), ('res_id', '=', task.id),
                                                    ('message_type', '=', 'user_notification')])
        self.assertIn(self.boss.partner_id, notified.partner_ids, 'the internal assignee is told in Odoo too')
        self.assertNotIn(self.ali.partner_id, notified.partner_ids)


@tagged('post_install', '-at_install')
class TestAppTaskCompany(HttpCase):

    def test_task_goes_to_the_company_chosen_in_the_app(self):
        branch = self.env['res.company'].create({'name': 'DL Task Branch'})
        boss = new_test_user(self.env, 'dl_tc_boss', password='dl_tc_boss1',
                             groups='base.group_user,donialink_app.group_task_manager',
                             company_ids=[(6, 0, (self.env.company | branch).ids)])
        self.authenticate('dl_tc_boss', 'dl_tc_boss1')
        self.opener.cookies['cids'] = str(self.env.company.id)   # Odoo's own switcher on the main company
        call = lambda endpoint, **p: self.url_open('/dl/app/api/%s' % endpoint, data=json.dumps({'params': p}),
                                                    headers={'Content-Type': 'application/json'}).json()['result']
        self.assertEqual(call('company_set', company_id=branch.id)['company_id'], branch.id)
        result = call('task_create', name='Clean the fryer', user_ids=[boss.id])
        self.assertEqual(self.env['donialink.app.task'].browse(result['task']['id']).company_id, branch, result)
