# -*- coding: utf-8 -*-
"""Employee tasks of the app: a light model (staff are often portal users, so not project.task).

Assignees see and do their tasks in the app ("My tasks"); the creator and the task managers see and assign all the
tasks of their companies ("Team tasks"). Notifications: task_assigned (to the assignees), task_due (reminder
and overdue), task_done (to the creator and the task managers). A task can repeat daily or on chosen weekdays.

Other modules create tasks with ``env['donialink.app.task'].create_for(users, title, ...)``."""
import base64
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

WEEKDAYS = [('0', 'Monday'), ('1', 'Tuesday'), ('2', 'Wednesday'), ('3', 'Thursday'), ('4', 'Friday'),
            ('5', 'Saturday'), ('6', 'Sunday')]
MANAGER_GROUP = 'donialink_app.group_task_manager'


class DonialinkAppTask(models.Model):
    _name = 'donialink.app.task'
    _description = 'DoniaLink App: Task'
    _inherit = ['mail.thread']
    _order = 'state_sequence, deadline, priority desc, id desc'

    name = fields.Char('Task', required=True, tracking=True)
    description = fields.Text()
    user_ids = fields.Many2many('res.users', 'donialink_app_task_user_rel', 'task_id', 'user_id', string='Assigned To',
                                required=True, tracking=True)
    creator_id = fields.Many2one('res.users', 'Created By', default=lambda self: self.env.user, readonly=True,
                                 index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    deadline = fields.Datetime('Due', tracking=True, index=True)
    priority = fields.Selection([('0', 'Normal'), ('1', 'High'), ('2', 'Urgent')], default='0', required=True)
    state = fields.Selection([('todo', 'To Do'), ('progress', 'In Progress'), ('done', 'Done'),
                              ('cancelled', 'Cancelled')], default='todo', required=True, tracking=True, index=True)
    state_sequence = fields.Integer(compute='_compute_state_sequence', store=True)
    line_ids = fields.One2many('donialink.app.task.line', 'task_id', string='Checklist', copy=True)
    photo_required = fields.Boolean('Photo Required to Finish')
    photo_ids = fields.Many2many('ir.attachment', 'donialink_app_task_photo_rel', 'task_id', 'attachment_id',
                                 string='Proof Photos')
    done_note = fields.Text('Note When Done')
    done_by_id = fields.Many2one('res.users', 'Done By', readonly=True)
    done_date = fields.Datetime('Done On', readonly=True)
    is_overdue = fields.Boolean(compute='_compute_is_overdue', search='_search_is_overdue')
    # repeat
    repeat = fields.Selection([('none', 'Once'), ('daily', 'Every day'), ('weekly', 'On chosen days')],
                              default='none', required=True)
    repeat_weekdays = fields.Char('Repeat On', help='Weekdays, 0 = Monday … 6 = Sunday, e.g. "0,2,4".')
    next_created = fields.Boolean(readonly=True, copy=False)
    previous_id = fields.Many2one('donialink.app.task', 'Repeats', readonly=True, copy=False, ondelete='set null')
    # reminders
    reminder_sent = fields.Boolean(readonly=True, copy=False)
    overdue_sent = fields.Boolean(readonly=True, copy=False)
    # where it comes from
    origin = fields.Char(help='What created it (a module, "platform", …).')
    res_model = fields.Char('Related Model')
    res_id = fields.Many2oneReference('Related Record', model_field='res_model')

    @api.depends('state')
    def _compute_state_sequence(self):
        order = {'progress': 0, 'todo': 1, 'done': 2, 'cancelled': 3}
        for task in self:
            task.state_sequence = order.get(task.state, 9)

    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for task in self:
            task.is_overdue = bool(task.deadline and task.deadline < now and task.state in ('todo', 'progress'))

    def _search_is_overdue(self, operator, value):
        now = fields.Datetime.now()
        if (operator == '=') == bool(value):
            return [('deadline', '<', now), ('state', 'in', ('todo', 'progress'))]
        return ['|', '|', ('deadline', '=', False), ('deadline', '>=', now), ('state', 'not in', ('todo', 'progress'))]

    # ------------------------------------------------------------------
    # Access helpers
    # ------------------------------------------------------------------

    @api.model
    def _is_manager(self, user=None):
        return (user or self.env.user).has_group(MANAGER_GROUP)

    def _can_do(self, user=None):
        """Assignees, the creator and the managers may work on it."""
        user = user or self.env.user
        return all(user in t.user_ids or user == t.creator_id or self._is_manager(user) for t in self)

    # ------------------------------------------------------------------
    # Create / assign
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        for task in tasks:
            task._notify('task_assigned', task.user_ids)
        return tasks

    def _check_edit(self):
        """Only task managers and the creator edit a task directly; assignees work through the actions (start,
        done with its photo rule, checklist ticks, comments), which write with sudo after their own checks."""
        if self.env.su or self._is_manager():
            return
        if any(task.creator_id != self.env.user for task in self):
            raise AccessError(_('Use Start and Done to work on a task; only its creator or a manager edits it.'))

    def write(self, vals):
        self._check_edit()
        before = {t.id: t.user_ids for t in self} if 'user_ids' in vals else {}
        result = super().write(vals)
        for task in self:
            added = task.user_ids - before.get(task.id, task.user_ids)
            if added:
                task._notify('task_assigned', added)
        return result

    @api.model
    def create_for(self, users, title, description=None, deadline=None, priority='0', company=None, lines=None,
                   photo_required=False, origin=None, res_model=None, res_id=None, repeat='none',
                   repeat_weekdays=None):
        """Create a task for ``users`` (res.users) from code. ``lines``: checklist names. Returns the task."""
        if not users:
            raise UserError(_('A task needs someone to do it.'))
        return self.sudo().create({
            'name': title, 'description': description or False, 'user_ids': [(6, 0, users.ids)],
            'deadline': deadline or False, 'priority': str(priority or '0'),
            'company_id': (company or self.env.company).id, 'photo_required': bool(photo_required),
            'line_ids': [(0, 0, {'name': name}) for name in (lines or [])],
            'origin': origin or False, 'res_model': res_model or False, 'res_id': res_id or False,
            'repeat': repeat or 'none', 'repeat_weekdays': repeat_weekdays or False,
        })

    # ------------------------------------------------------------------
    # Work
    # ------------------------------------------------------------------

    def action_start(self):
        self._check_can_do()
        self.filtered(lambda t: t.state == 'todo').sudo().write({'state': 'progress'})
        return True

    def action_done(self, note=None, photos=None):
        """Finish: ``photos`` [(filename, bytes, mimetype)] are attached as proof (required when the task says)."""
        self._check_can_do()
        for task in self:
            if task.state in ('done', 'cancelled'):
                continue
            attachments = self.env['ir.attachment'].sudo()
            for filename, content, mimetype in photos or []:
                attachments |= attachments.create({'name': filename or 'photo.jpg', 'raw': content,
                                                   'mimetype': mimetype or 'image/jpeg',
                                                   'res_model': task._name, 'res_id': task.id})
            if task.photo_required and not (task.photo_ids or attachments):
                raise UserError(_('Take a photo to finish "%s".', task.name))
            task.sudo().write({'state': 'done', 'done_by_id': self.env.user.id, 'done_date': fields.Datetime.now(),
                               'done_note': note or task.done_note or False,
                               'photo_ids': [(4, a.id) for a in attachments]})
            task._notify('task_done', task._done_audience())
            if task.repeat != 'none':
                task._create_next()
        return True

    def action_cancel(self):
        if not all(self.env.user == t.creator_id or self._is_manager() for t in self):
            raise AccessError(_('Only the creator or a task manager can cancel a task.'))
        self.sudo().write({'state': 'cancelled'})
        return True

    def action_reset(self):
        self._check_can_do()
        self.sudo().write({'state': 'todo', 'done_by_id': False, 'done_date': False})
        return True

    def _check_can_do(self):
        if not self._can_do():
            raise AccessError(_('This task is not yours.'))

    def _done_audience(self):
        self.ensure_one()
        managers = self.env.ref(MANAGER_GROUP).sudo().users.filtered(lambda u: self.company_id in u.company_ids)
        return (self.creator_id | managers) - self.env.user

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def _notify(self, kind, users, overdue=False):
        """The app message of ``kind`` to ``users``, each group in its own language and time zone (a tap opens the
        task). Internal assignees also get it in Odoo's notifications."""
        self.ensure_one()
        self = self.sudo()   # noqa: PLW0642 - reading the recipients' language and time zone (portal actors too)
        users = users.sudo().filtered('active')
        messages = self.env['donialink.app.message']
        for lang in set(users.mapped(lambda u: u.lang or 'en_US')):
            group = users.filtered(lambda u: (u.lang or 'en_US') == lang)
            task = self.with_context(lang=lang, tz=group[:1].tz or self.env.user.tz or 'UTC')
            env = task.env
            if kind == 'task_assigned':
                title = env._('New task: %s', task.name)
            elif kind == 'task_done':
                title = env._('Task done: %s', task.name)
            else:
                title = env._('Overdue: %s', task.name) if overdue else env._('Task due: %s', task.name)
            if kind == 'task_done':
                lines = [env._('%(who)s finished it.', who=task.done_by_id.name or ''), task.done_note or '']
            else:
                lines = [task.description or '']
                if task.deadline:
                    when = fields.Datetime.context_timestamp(task, task.deadline).strftime('%Y-%m-%d %H:%M')
                    lines.append(env._('Due %s', when))
                if task.line_ids:
                    lines.append(env._('%s points to tick', len(task.line_ids)))
            messages |= self.env['donialink.app.message'].sudo().with_context(lang=lang).send(
                kind=kind, title=title, body='\n'.join(filter(None, lines)), users=group,
                company=self.company_id, url='#task-%s' % self.id, sender=self.creator_id.name,
                origin='task', data={'task_id': self.id})
        if kind == 'task_assigned':
            internal = users.filtered(lambda u: not u.share)
            if internal:
                self.sudo().message_notify(
                    partner_ids=internal.partner_id.ids, subject=_('New task: %s', self.name),
                    body=_('%(creator)s gave you a task: %(task)s', creator=self.creator_id.name or '',
                           task=self.name), model_description=_('Task'))
        return messages

    @api.model
    def _cron_reminders(self):
        """Hourly: a reminder in the hour before the deadline, and once when it is overdue."""
        now = fields.Datetime.now()
        soon = self.sudo().search([('state', 'in', ('todo', 'progress')), ('reminder_sent', '=', False),
                                   ('deadline', '>', now), ('deadline', '<=', now + timedelta(hours=1))])
        for task in soon:
            task._notify('task_due', task.user_ids)
            task.reminder_sent = True
        late = self.sudo().search([('state', 'in', ('todo', 'progress')), ('overdue_sent', '=', False),
                                   ('deadline', '<', now)])
        for task in late:
            task._notify('task_due', task.user_ids | task.creator_id, overdue=True)
            task.overdue_sent = True
        # repeating tasks whose day is over without being done: the next one is created anyway
        for task in self.sudo().search([('repeat', '!=', 'none'), ('next_created', '=', False),
                                        ('deadline', '<', now - timedelta(hours=12))]):
            task._create_next()

    # ------------------------------------------------------------------
    # Repeat
    # ------------------------------------------------------------------

    def _next_deadline(self):
        self.ensure_one()
        tz = pytz.timezone(self.creator_id.tz or self.env.user.tz or 'UTC')
        base = self.deadline or fields.Datetime.now()
        local = pytz.utc.localize(base).astimezone(tz)
        days = sorted({int(d) for d in (self.repeat_weekdays or '').split(',') if d.strip().isdigit()})
        step = 1
        if self.repeat == 'weekly' and days:
            step = min(((d - local.weekday()) % 7) or 7 for d in days)
        nxt = local + timedelta(days=step)
        return nxt.astimezone(pytz.utc).replace(tzinfo=None)

    def _create_next(self):
        for task in self.sudo().filtered(lambda t: t.repeat != 'none' and not t.next_created):
            task.next_created = True
            task.copy({
                'deadline': task._next_deadline(), 'state': 'todo', 'previous_id': task.id,
                'line_ids': [(0, 0, {'name': line.name}) for line in task.line_ids],
                'photo_ids': False, 'done_note': False, 'creator_id': task.creator_id.id,
            })

    # ------------------------------------------------------------------
    # App
    # ------------------------------------------------------------------

    @api.model
    def dl_app_task_badge(self):
        """Open tasks of the person due today or overdue (the tile badge)."""
        end = datetime.combine(fields.Date.context_today(self) + timedelta(days=1), time.min)
        return self.search_count([('user_ids', 'in', self.env.user.id), ('state', 'in', ('todo', 'progress')),
                                  ('deadline', '<', end)])

    def _to_app(self, full=False):
        values = []
        user = self.env.user
        for t in self:
            value = {
                'id': t.id, 'name': t.name, 'state': t.state, 'priority': t.priority,
                'deadline': fields.Datetime.to_string(t.deadline) if t.deadline else False,
                'overdue': t.is_overdue, 'users': [{'id': u.id, 'name': u.name} for u in t.user_ids],
                'creator': t.creator_id.name or '', 'company': t.company_id.name,
                'lines': len(t.line_ids), 'lines_done': len(t.line_ids.filtered('done')),
                'photo_required': t.photo_required, 'repeat': t.repeat,
                'mine': user in t.user_ids,
            }
            if full:
                value.update({
                    'description': t.description or '', 'done_note': t.done_note or '',
                    'done_by': t.done_by_id.name or '', 'done_date': fields.Datetime.to_string(t.done_date) if t.done_date else False,
                    'checklist': [{'id': line.id, 'name': line.name, 'done': line.done} for line in t.line_ids],
                    'photos': [{'id': a.id, 'name': a.name, 'url': '/web/image/%s' % a.id} for a in t.photo_ids],
                    'comments': [{'author': m.author_id.name or '', 'body': m.body or '',
                                  'date': fields.Datetime.to_string(m.date)}
                                 for m in t.message_ids.filtered(lambda m: m.message_type == 'comment')],
                    'can_cancel': user == t.creator_id or self._is_manager(user),
                })
            values.append(value)
        return values


class DonialinkAppTaskLine(models.Model):
    _name = 'donialink.app.task.line'
    _description = 'DoniaLink App: Task Checklist Line'
    _order = 'sequence, id'

    task_id = fields.Many2one('donialink.app.task', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    done = fields.Boolean()

    def _editor(self, tasks):
        return self.env.su or self.env['donialink.app.task']._is_manager() or all(
            t.creator_id == self.env.user for t in tasks)

    @api.model_create_multi
    def create(self, vals_list):
        tasks = self.env['donialink.app.task'].browse([v.get('task_id') for v in vals_list if v.get('task_id')])
        if not self._editor(tasks):
            raise AccessError(_('Only the creator or a manager changes the checklist.'))
        return super().create(vals_list)

    def write(self, vals):
        # assignees only tick lines
        if set(vals) - {'done'} and not self._editor(self.task_id):
            raise AccessError(_('Only the creator or a manager changes the checklist.'))
        self.task_id._check_can_do()
        return super().write(vals)

    def unlink(self):
        if not self._editor(self.task_id):
            raise AccessError(_('Only the creator or a manager changes the checklist.'))
        return super().unlink()


class DonialinkAppAdmin(models.AbstractModel):
    _inherit = 'donialink.app.admin'

    def _dl_app_admin_sections(self):
        Task = self.env['donialink.app.task'].sudo()
        companies = self.env.user.company_ids.ids
        domain = [('company_id', 'in', companies)]
        today = datetime.combine(fields.Date.context_today(self), time.min)
        open_tasks = Task.search(domain + [('state', 'in', ('todo', 'progress'))])
        by_person = {}
        for task in open_tasks:
            for user in task.user_ids:
                by_person[user.name] = by_person.get(user.name, 0) + 1
        top = sorted(by_person.items(), key=lambda kv: -kv[1])[:3]
        return super()._dl_app_admin_sections() + [{
            'key': 'tasks', 'title': _('Tasks'), 'icon': 'check', 'sequence': 10,
            'numbers': [
                {'label': _('Open'), 'value': len(open_tasks)},
                {'label': _('Overdue'), 'value': len(open_tasks.filtered('is_overdue')), 'warn': True},
                {'label': _('Done today'), 'value': Task.search_count(domain + [('done_date', '>=', today)])},
            ] + [{'label': name, 'value': count} for name, count in top],
            'action': 'donialink_app.action_app_task', 'button': _('Assign'),
        }]
