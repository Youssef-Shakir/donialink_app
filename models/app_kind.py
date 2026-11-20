# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DonialinkAppKind(models.Model):
    """A kind of notification (reports from DoniaLink, POS session closed, …) and who receives it.

    Modules add their kinds in data files; the recipients are chosen here (or by the DoniaLink Platform for its
    reports). A person can switch a kind off in the app when ``user_can_mute`` is set."""
    _name = 'donialink.app.kind'
    _description = 'DoniaLink App: Notification Kind'
    _order = 'sequence, id'

    code = fields.Char(required=True, index=True, help='Technical key used by the code that sends, e.g. "report".')
    name = fields.Char(required=True, translate=True)
    description = fields.Char(translate=True, help='Shown to people under the kind in the app settings.')
    icon = fields.Char(default='bell', help='Icon name in the app (bell, report, cash, receipt, chart, alert, '
                                            'box, card, info).')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    push = fields.Boolean('Push to Phones', default=True,
                          help='Off: the message only goes to the inbox, without a phone notification.')
    user_can_mute = fields.Boolean('People Can Switch It Off', default=True)
    recipient_ids = fields.Many2many(
        'res.users', 'donialink_app_kind_recipient_rel', 'kind_id', 'user_id', string='Recipients',
        help='Who receives this kind when the sender does not name the people.')
    recipient_group_ids = fields.Many2many(
        'res.groups', 'donialink_app_kind_recipient_group_rel', 'kind_id', 'group_id', string='Recipient Groups',
        help='The members of these groups receive this kind too.')
    role_ids = fields.Many2many('donialink.app.role', 'donialink_app_role_kind_rel', 'kind_id', 'role_id',
                                string='Roles', help='The people with these roles receive this kind too.')
    muted_user_ids = fields.Many2many(
        'res.users', 'donialink_app_kind_muted_rel', 'kind_id', 'user_id', string='Switched Off By',
        help='People who switched this kind off in the app.')
    message_count = fields.Integer(compute='_compute_message_count')

    _sql_constraints = [('code_unique', 'unique(code)', 'A notification kind with this code already exists.')]

    def _compute_message_count(self):
        data = dict(self.env['donialink.app.message'].sudo()._read_group(
            [('kind_id', 'in', self.ids)], ['kind_id'], ['__count']))
        for kind in self:
            kind.message_count = data.get(kind, 0)

    @api.model
    def _get(self, code):
        """The kind with this code (archived ones too); an empty record when it doesn't exist."""
        if not code:
            return self.browse()
        if isinstance(code, models.BaseModel):
            return code
        return self.sudo().with_context(active_test=False).search([('code', '=', code)], limit=1)

    def _wanted_by(self, users):
        """``users`` minus the people who switched this kind off (when they may)."""
        self.ensure_one()
        if not self.user_can_mute:
            return users
        return users - self.muted_user_ids

    def _recipients(self, company=None):
        """The people who receive this kind (for ``company``): the people chosen, the members of the recipient
        groups and of the roles that include it; active, with access to the company, and who didn't switch it off."""
        self.ensure_one()
        users = (self.recipient_ids | self.recipient_group_ids.users | self.role_ids.user_ids).filtered('active')
        if company:
            users = users.filtered(lambda u: company in u.company_ids)
        return self._wanted_by(users)

    def action_open_messages(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('donialink_app.action_app_message')
        action['domain'] = [('kind_id', '=', self.id)]
        action['context'] = {}
        return action
