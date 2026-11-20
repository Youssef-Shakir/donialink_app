# -*- coding: utf-8 -*-
"""The app's admin dashboard (a backend client action for App Managers): people, creating users, who receives
what, who sees what, activity, broadcast. Every method checks the App Manager group.

Other modules add a card to the dashboard by extending ``_dl_app_admin_sections``::

    class DonialinkAppAdmin(models.AbstractModel):
        _inherit = 'donialink.app.admin'

        def _dl_app_admin_sections(self):
            return super()._dl_app_admin_sections() + [{
                'key': 'cashbox', 'title': _('Cash boxes'), 'icon': 'cash', 'sequence': 20,
                'numbers': [{'label': _('Expenses to review'), 'value': 3, 'warn': True}],
                'action': 'expense_cash_control_telegram.action_ecc_owner_move_review',  # xml id or None
            }]

Richer cards: register an OWL component in registry.category('donialink_app.admin_sections') under the same key.
"""
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

TARGETS = ('role', 'group', 'user')


class DonialinkAppAdmin(models.AbstractModel):
    _name = 'donialink.app.admin'
    _description = 'DoniaLink App: Admin Dashboard'

    @api.model
    def _check(self):
        if not self.env.user.has_group('donialink_app.group_app_manager'):
            raise AccessError(_('Only App Managers can use the DoniaLink App dashboard.'))

    @api.model
    def _people(self):
        """Everyone who can use the app: active and archived internal and portal users (not the bots)."""
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        excluded = self.env.ref('base.user_root') | self.env.ref('base.public_user')
        agent = self.env.ref('donialink_agent.user_agent', raise_if_not_found=False)
        if agent:
            excluded |= agent
        # Odoo's templates for new users are not people
        excluded |= self.env.ref('base.default_user', raise_if_not_found=False) or Users
        template = self.env['ir.config_parameter'].sudo().get_param('base.template_portal_user_id')
        if template and template.isdigit():
            excluded |= Users.browse(int(template))
        portal = self.env.ref('base.group_portal')
        return Users.search(['|', ('share', '=', False), ('groups_id', 'in', portal.ids),
                             ('id', 'not in', excluded.ids), ('company_ids', 'in', self.env.user.company_ids.ids)],
                            order='active desc, name')

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    @api.model
    def get_data(self):
        self._check()
        people = self._people()
        Role = self.env['donialink.app.role'].sudo()
        Kind = self.env['donialink.app.kind'].sudo()
        Screen = self.env['donialink.app.screen'].sudo()
        roles = Role.search([])
        kinds = Kind.search([])
        screens = Screen.search([])
        groups = (kinds.recipient_group_ids | screens.group_ids | roles.group_ids).sorted('full_name')
        sections = sorted(self._dl_app_admin_sections(), key=lambda s: s.get('sequence', 50))
        return {
            'people': [{
                'id': u.id, 'name': u.name, 'login': u.login, 'active': u.active,
                'type': 'portal' if u.share else 'internal',
                'roles': u.dl_app_role_ids.ids,
                'companies': u.company_ids.mapped('name'),
                'phones': u.dl_app_phone_count, 'unread': u.dl_app_unread,
                'last_seen': fields.Datetime.to_string(u.dl_app_last_seen) if u.dl_app_last_seen else False,
            } for u in people],
            'roles': [{'id': r.id, 'name': r.name, 'type': r.user_type, 'default': r.is_default,
                       'description': r.description or '', 'count': len(r.user_ids)} for r in roles],
            'groups': [{'id': g.id, 'name': g.full_name} for g in groups],
            'companies': [{'id': c.id, 'name': c.name} for c in self.env.user.company_ids],
            'kinds': [{
                'id': k.id, 'code': k.code, 'name': k.name, 'icon': k.icon or 'bell', 'push': k.push,
                'active': k.active, 'roles': k.role_ids.ids, 'groups': k.recipient_group_ids.ids,
                'users': k.recipient_ids.ids, 'muted': k.muted_user_ids.ids,
            } for k in kinds],
            'screens': [{
                'id': s.id, 'key': s.key, 'name': s.name, 'icon': s.icon or 'box',
                'open': not (s.group_ids or s.user_ids), 'roles': s.role_ids.ids, 'groups': s.group_ids.ids,
                'users': s.user_ids.ids,
            } for s in screens],
            'activity': self._activity(kinds, people),
            'sections': sections,
        }

    @api.model
    def _activity(self, kinds, people):
        Message = self.env['donialink.app.message'].sudo()
        now = fields.Datetime.now()
        today = fields.Datetime.to_datetime(fields.Date.context_today(self))
        week = now - timedelta(days=7)
        rows = []
        for kind in kinds:
            rows.append({
                'kind': kind.name,
                'today': Message.search_count([('kind_id', '=', kind.id), ('create_date', '>=', today)]),
                'week': Message.search_count([('kind_id', '=', kind.id), ('create_date', '>=', week)]),
                'not_pushed': Message.search_count([('kind_id', '=', kind.id), ('create_date', '>=', week),
                                                    ('pushed', '=', 0)]),
            })
        week_messages = Message.search([('create_date', '>=', week)])
        return {
            'kinds': rows,
            'today': Message.search_count([('create_date', '>=', today)]),
            'week': len(week_messages),
            'pushes': sum(week_messages.mapped('pushed')),
            'not_pushed': len(week_messages.filtered(lambda m: not m.pushed)),
            'no_phone': [{'id': u.id, 'name': u.name} for u in people.filtered(
                lambda u: u.active and not u.dl_app_phone_count)],
        }

    @api.model
    def _dl_app_admin_sections(self):
        """Cards other modules add to the dashboard (see the module docstring)."""
        return []

    # ------------------------------------------------------------------
    # People
    # ------------------------------------------------------------------

    @api.model
    def _person(self, user_id, manage=False):
        """An app user of the manager's companies. ``manage``: also one the manager may change: a manager who is not a
        system administrator only manages people whose access is part of their own (never an administrator)."""
        user = self._people().filtered(lambda u: u.id == int(user_id))
        if not user:
            raise UserError(_('This person is not an app user of your companies.'))
        if manage and not self.env.user.has_group('base.group_system'):
            admins = self.env.ref('base.group_system') | self.env.ref('base.group_erp_manager')
            base = self.env.ref('base.group_portal') | self.env.ref('base.group_public')
            if (user.groups_id & admins) or (user.groups_id - self.env.user.groups_id - base):
                raise AccessError(_('%s has more access than you: ask an administrator.', user.name))
        return user

    @api.model
    def create_user(self, name, login, password=None, role_ids=None, company_ids=None):
        """One step: the person, the login, the password (generated when empty, returned once), the roles. Portal
        (free) unless a role needs an internal user."""
        self._check()
        name, login = (name or '').strip(), (login or '').strip()
        if not name or not login:
            raise UserError(_('Give a name and a phone number or login.'))
        Users = self.env['res.users'].sudo().with_context(active_test=False, no_reset_password=True)
        if Users.search_count([('login', '=', login)]):
            raise UserError(_('The login %s is already used.', login))
        roles = self.env['donialink.app.role'].sudo().browse([int(r) for r in (role_ids or [])]).exists()
        if not roles:
            roles = self.env['donialink.app.role'].sudo().search([('is_default', '=', True)], limit=1)
        self.env['donialink.app.role']._dl_check_grant(roles.group_ids)
        internal = any(r.user_type == 'internal' for r in roles)
        allowed = self.env.user.company_ids
        companies = allowed.browse([int(c) for c in (company_ids or [])]) & allowed if company_ids else (
            (roles.company_ids & allowed) or self.env.company)
        generated = not password
        password = password or secrets.token_urlsafe(9)
        user = Users.create({
            'name': name, 'login': login, 'password': password,
            'groups_id': [(6, 0, [self.env.ref('base.group_user' if internal else 'base.group_portal').id])],
            'company_ids': [(6, 0, companies.ids)], 'company_id': companies[:1].id,
            'dl_app_role_ids': [(6, 0, roles.ids)],
        })
        return {'user_id': user.id, 'login': login, 'password': password if generated else False,
                'type': 'internal' if internal else 'portal'}

    @api.model
    def set_roles(self, user_id, role_ids):
        self._check()
        user = self._person(user_id, manage=True)
        roles = self.env['donialink.app.role'].sudo().browse([int(r) for r in role_ids or []]).exists()
        self.env['donialink.app.role']._dl_check_grant(roles.group_ids)
        user.sudo().dl_app_role_ids = [(6, 0, roles.ids)]
        return True

    @api.model
    def send_test(self, user_id):
        self._check()
        user = self._person(user_id)
        self.env['donialink.app.message'].sudo().send(
            title=_('Test notification'), body=_('Notifications from %s reach this phone.', self.env.company.name),
            users=user, sender=self.env.user.name, origin='test', push=True)
        return {'phones': user.dl_app_phone_count}

    @api.model
    def reset_password(self, user_id, password=None):
        self._check()
        user = self._person(user_id, manage=True)
        new = password or secrets.token_urlsafe(9)
        user.sudo().password = new
        return {'password': new}

    @api.model
    def set_active(self, user_id, active):
        self._check()
        user = self._person(user_id, manage=True)
        if user == self.env.user:
            raise UserError(_('You can not archive yourself.'))
        user.sudo().active = bool(active)
        return True

    # ------------------------------------------------------------------
    # Who receives / sees what
    # ------------------------------------------------------------------

    @api.model
    def _target_field(self, target):
        if target not in TARGETS:
            raise UserError(_('Unknown target.'))
        return target

    @api.model
    def toggle_kind(self, kind_id, target, target_id, on):
        """Add or remove a role, a group or a person as recipients of a kind."""
        self._check()
        kind = self.env['donialink.app.kind'].sudo().browse(int(kind_id)).exists()
        field = {'role': 'role_ids', 'group': 'recipient_group_ids', 'user': 'recipient_ids'}[self._target_field(target)]
        kind.write({field: [(4 if on else 3, int(target_id))]})
        return True

    @api.model
    def set_kind_push(self, kind_id, push):
        self._check()
        self.env['donialink.app.kind'].sudo().browse(int(kind_id)).exists().push = bool(push)
        return True

    @api.model
    def test_kind(self, kind_id):
        """A test of this kind, to me (as its recipients would get it)."""
        self._check()
        kind = self.env['donialink.app.kind'].sudo().browse(int(kind_id)).exists()
        messages = self.env['donialink.app.message'].sudo().send(
            kind=kind, title=_('Test: %s', kind.name), body=_('This is how "%s" reaches you.', kind.name),
            users=self.env.user, sender=self.env.user.name, origin='test')
        return {'sent': len(messages)}

    @api.model
    def toggle_screen(self, screen_id, target, target_id, on):
        self._check()
        screen = self.env['donialink.app.screen'].sudo().browse(int(screen_id)).exists()
        field = {'role': 'role_ids', 'group': 'group_ids', 'user': 'user_ids'}[self._target_field(target)]
        screen.write({field: [(4 if on else 3, int(target_id))]})
        return True

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    @api.model
    def broadcast(self, title, body, role_ids=None, group_ids=None, user_ids=None):
        self._check()
        Users = self.env['res.users'].sudo()
        users = (self.env['donialink.app.role'].sudo().browse([int(r) for r in role_ids or []]).user_ids
                 | self.env['res.groups'].sudo().browse([int(g) for g in group_ids or []]).users
                 | Users.browse([int(u) for u in user_ids or []]))
        users = users & self._people()
        if not users:
            raise UserError(_('Choose who receives the message.'))
        messages = self.env['donialink.app.message'].sudo().send(
            kind='general', title=title, body=body, users=users, sender=self.env.user.name, origin='broadcast')
        return {'sent': len(messages)}
