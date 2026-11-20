# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    dl_app_message_ids = fields.One2many('donialink.app.message', 'user_id', string='App Messages')
    dl_app_unread = fields.Integer('Unread in the App', compute='_compute_dl_app_unread')
    dl_app_phone_count = fields.Integer('Phones with App Notifications', compute='_compute_dl_app_phone_count')
    dl_app_role_ids = fields.Many2many('donialink.app.role', 'donialink_app_role_user_rel', 'user_id', 'role_id',
                                       string='App Roles')
    dl_app_role_group_ids = fields.Many2many('res.groups', 'donialink_app_user_role_group_rel', 'user_id', 'group_id',
                                             string='Groups Given by App Roles', readonly=True)
    dl_app_last_seen = fields.Datetime('Last Time in the App', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        for user in users.filtered('dl_app_role_ids'):
            for role in user.dl_app_role_ids:
                role._grant(user)
        return users

    def write(self, vals):
        if 'dl_app_role_ids' not in vals or self.env.context.get('dl_app_no_role_sync'):
            return super().write(vals)
        before = {user.id: user.dl_app_role_ids for user in self}
        result = super().write(vals)
        self.env['donialink.app.role']._dl_check_grant(
            (self.dl_app_role_ids - self.env['donialink.app.role'].browse(
                [r.id for roles in before.values() for r in roles])).group_ids)
        for user in self:
            for role in user.dl_app_role_ids - before[user.id]:
                role._grant(user)
            for role in before[user.id] - user.dl_app_role_ids:
                role._take_back(user, role.group_ids)
        return result

    def _compute_dl_app_unread(self):
        data = dict(self.env['donialink.app.message'].sudo()._read_group(
            [('user_id', 'in', self.ids), ('is_read', '=', False)], ['user_id'], ['__count']))
        for user in self:
            user.dl_app_unread = data.get(user, 0)

    def _compute_dl_app_phone_count(self):
        data = dict(self.env['mail.push.device'].sudo()._read_group(
            [('partner_id', 'in', self.partner_id.ids)], ['partner_id'], ['__count']))
        for user in self:
            user.dl_app_phone_count = data.get(user.partner_id, 0)

    def action_dl_app_test(self):
        """Send a test notification to this person's app."""
        self.ensure_one()
        self.env['donialink.app.message'].send(
            title=_('Test notification'), body=_('Notifications from %s reach this phone.', self.env.company.name),
            users=self, sender=self.env.user.name, origin='test', push=True)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': _('Sent to %(name)s (%(count)s phone(s)).', name=self.name,
                                            count=self.dl_app_phone_count)}}
