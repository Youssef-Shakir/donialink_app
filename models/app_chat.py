# -*- coding: utf-8 -*-
"""Chat in the DoniaLink App is Odoo Discuss (direct chats and groups): the same conversations are in Odoo's
Discuss for internal users; portal users chat from the app. Odoo pushes new messages to every phone."""
from odoo import api, models


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    @api.model
    def dl_app_chat_badge(self):
        """Unread chat messages of the person (the badge of the Chat tile)."""
        members = self.env['discuss.channel.member'].sudo().search([
            ('partner_id', '=', self.env.user.partner_id.id), ('channel_id.channel_type', 'in', ('chat', 'group'))])
        return sum(members.mapped('message_unread_counter'))
