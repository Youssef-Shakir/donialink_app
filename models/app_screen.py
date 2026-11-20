# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class DonialinkAppScreen(models.Model):
    """A tile on the app's home page. Either a screen drawn by the app's JavaScript (a module registers it with
    ``DLApp.screen('<key>', {...})`` in the ``donialink_app.assets_app`` bundle), or a link (``url``)."""
    _name = 'donialink.app.screen'
    _description = 'DoniaLink App: Screen'
    _order = 'sequence, id'

    key = fields.Char(required=True, index=True, help='The key the JavaScript screen registers with.')
    name = fields.Char(required=True, translate=True)
    description = fields.Char(translate=True)
    icon = fields.Char(default='box')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    url = fields.Char('Link', help='Opens this address instead of an app screen, e.g. /odoo for the full Odoo.')
    group_ids = fields.Many2many('res.groups', string='Only For',
                                 help='Empty: everyone who uses the app. Otherwise only members of these groups.')
    user_ids = fields.Many2many('res.users', 'donialink_app_screen_user_rel', 'screen_id', 'user_id',
                                string='Only For People', help='Also shown to these people (with Only For groups).')
    role_ids = fields.Many2many('donialink.app.role', 'donialink_app_role_screen_rel', 'screen_id', 'role_id',
                                string='Roles', help='Also shown to the people with these roles.')
    on_home = fields.Boolean('Tile on Home', default=True)
    requires_model = fields.Char('Needs Model', help='The screen is only offered when this model exists (a soft '
                                                     'dependency, e.g. donialink.agent.tools for the summary).')
    badge_model = fields.Char('Badge Model', help='Model whose method gives the number shown on the tile.')
    badge_method = fields.Char('Badge Method', help='Method of the badge model named dl_app_…, called as the '
                                                    'user with no arguments, returning a number (0: no badge).')

    _sql_constraints = [('key_unique', 'unique(key)', 'A screen with this key already exists.')]

    @api.model
    def _for_user(self, user=None):
        user = user or self.env.user
        screens = self.sudo().search([])
        roles = user.sudo().dl_app_role_ids
        return screens.filtered(lambda s: (not (s.group_ids or s.user_ids) or user in s.user_ids
                                           or (s.group_ids & user.groups_id) or (s.role_ids & roles))
                                and (not s.requires_model or s.requires_model in self.env))

    def _badge(self, user):
        """The number on the tile, computed as ``user``; 0 when it can't be computed."""
        self.ensure_one()
        # only methods named dl_app_* : a screen record can't call an arbitrary method
        if not self.badge_model or not (self.badge_method or '').startswith('dl_app_'):
            return 0
        if self.badge_model not in self.env:
            return 0
        try:
            with self.env.cr.savepoint():
                value = getattr(self.env[self.badge_model].with_user(user), self.badge_method)()
            return int(value or 0)
        except Exception as e:  # noqa: BLE001 - a badge never breaks the home page
            _logger.warning('DoniaLink App: badge of screen %s failed: %s', self.key, e)
            return 0

    def _to_app(self, user):
        return [{
            'key': s.key, 'name': s.name, 'description': s.description or '', 'icon': s.icon or 'box',
            'url': s.url or '', 'home': s.on_home, 'badge': s._badge(user),
        } for s in self]
