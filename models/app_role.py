# -*- coding: utf-8 -*-
"""Roles of the app: a bundle of access groups, app screens, notification kinds and companies given to people in
one step (Owner, Manager, Accountant, Staff...). Modules add or extend roles with data XML.

Assigning a role adds the groups the person did not have yet (remembered as given by roles); removing it takes
back only those, and only when no other role of the person still gives them. Screens and kinds are not copied:
the role's members are read when the app lists screens and when a kind looks for its recipients."""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class DonialinkAppRole(models.Model):
    _name = 'donialink.app.role'
    _description = 'DoniaLink App: Role'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    description = fields.Char(translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    user_type = fields.Selection([('portal', 'Portal (free, app only)'), ('internal', 'Internal (also Odoo)')],
                                 required=True, default='portal',
                                 help='Portal users are free and use the app only; internal users also open Odoo.')
    group_ids = fields.Many2many('res.groups', 'donialink_app_role_group_rel', 'role_id', 'group_id',
                                 string='Access Groups')
    screen_ids = fields.Many2many('donialink.app.screen', 'donialink_app_role_screen_rel', 'role_id', 'screen_id',
                                  string='Screens')
    kind_ids = fields.Many2many('donialink.app.kind', 'donialink_app_role_kind_rel', 'role_id', 'kind_id',
                                string='Receives')
    company_ids = fields.Many2many('res.company', 'donialink_app_role_company_rel', 'role_id', 'company_id',
                                   string='Companies', default=lambda self: self.env.company,
                                   help='Companies given to the people created with this role.')
    is_default = fields.Boolean('Default for New Users')
    user_ids = fields.Many2many('res.users', 'donialink_app_role_user_rel', 'role_id', 'user_id', string='People',
                                context={'active_test': False})
    user_count = fields.Integer(compute='_compute_user_count')

    def _compute_user_count(self):
        for role in self:
            role.user_count = len(role.user_ids)

    @api.model
    def _dl_check_grant(self, groups):
        """Nobody gives access they don't have: a role may only carry the groups of the person acting, unless they
        are a system administrator (data loading, as superuser, is exempt)."""
        if self.env.su or self.env.user.has_group('base.group_system'):
            return
        extra = groups - self.env.user.groups_id
        if extra:
            raise AccessError(_('You can not give access you do not have yourself: %s',
                                ', '.join(extra.mapped('full_name'))))

    @api.model_create_multi
    def create(self, vals_list):
        roles = super().create(vals_list)
        for role in roles:
            self._dl_check_grant(role.group_ids)
            role._grant(role.user_ids)
        return roles

    def write(self, vals):
        if 'group_ids' in vals or 'user_ids' in vals:
            for role in self:
                self._dl_check_grant(role.group_ids)
        before = {role.id: role.user_ids for role in self}
        old_groups = {role.id: role.group_ids for role in self}
        result = super().write(vals)
        if 'group_ids' in vals:
            self._dl_check_grant(self.group_ids)
        for role in self:
            added = role.user_ids - before[role.id]
            removed = before[role.id] - role.user_ids
            if added:
                role._grant(added)
            if removed:
                role._take_back(removed, old_groups[role.id])
            if 'group_ids' in vals:
                kept = role.user_ids - added
                role._grant(kept)
                gone = old_groups[role.id] - role.group_ids
                if gone:
                    role._take_back(kept, gone, still_member=True)
        return result

    def unlink(self):
        for role in self:
            role._take_back(role.user_ids, role.group_ids)
        return super().unlink()

    # ------------------------------------------------------------------

    def _grant(self, users):
        """Add the role's groups the people don't have yet, remembering they came from a role."""
        self.ensure_one()
        internal = self.env.ref('base.group_user')
        for user in users.sudo():
            missing = self.group_ids - user.groups_id
            if not missing:
                continue
            if user.share and any(internal in (g | g.trans_implied_ids) for g in missing):
                raise UserError(_('%(user)s is a portal user: the role "%(role)s" needs an internal user.',
                                  user=user.name, role=self.name))
            user.with_context(dl_app_no_role_sync=True).write({
                'groups_id': [(4, g.id) for g in missing],
                'dl_app_role_group_ids': [(4, g.id) for g in missing]})

    def _take_back(self, users, groups, still_member=False):
        """Remove ``groups`` given by roles, unless another role of the person still gives them."""
        self.ensure_one()
        for user in users.sudo():
            others = user.dl_app_role_ids if still_member else user.dl_app_role_ids - self
            back = (groups & user.dl_app_role_group_ids) - others.group_ids
            if back:
                user.with_context(dl_app_no_role_sync=True).write({
                    'groups_id': [(3, g.id) for g in back],
                    'dl_app_role_group_ids': [(3, g.id) for g in back]})

    def action_open_users(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': self.name, 'res_model': 'res.users',
                'view_mode': 'list,form', 'domain': [('id', 'in', self.user_ids.ids)],
                'context': {'active_test': False}}
