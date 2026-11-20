# -*- coding: utf-8 -*-
import base64
import json
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext, is_html_empty, plaintext2html

_logger = logging.getLogger(__name__)

APP_PATH = '/dl/app'
ICON = '/donialink_app/static/img/icon-192.png'
BADGE = '/donialink_app/static/img/favicon-32.png'
_TAG = re.compile(r'<[a-zA-Z/][^>]*>')


class DonialinkAppMessage(models.Model):
    """One message in a person's app inbox: a notification, a report (with its PDF), a reminder.

    Other modules send with ``env['donialink.app.message'].send(...)``: the message lands in each person's inbox
    and, when the kind pushes, as a notification on each phone where they turned notifications on."""
    _name = 'donialink.app.message'
    _description = 'DoniaLink App: Message'
    _order = 'id desc'
    _rec_name = 'title'

    user_id = fields.Many2one('res.users', 'To', required=True, index=True, ondelete='cascade')
    kind_id = fields.Many2one('donialink.app.kind', 'Kind', index=True, ondelete='set null')
    kind_code = fields.Char(related='kind_id.code', store=True, string='Kind Code')
    title = fields.Char(required=True)
    body = fields.Html(sanitize=True)
    preview = fields.Char(compute='_compute_preview', store=True, help='The body as one line of text.')
    attachment_id = fields.Many2one('ir.attachment', 'File', ondelete='set null')
    url = fields.Char('Opens', help='Where a tap leads: "#<screen key>" (an app screen), "/odoo/…" or https://… '
                                    'Empty: the message itself.')
    company_id = fields.Many2one('res.company', index=True)
    sender = fields.Char(help='Shown under the title, e.g. "DoniaLink" or the name of the person who sent it.')
    origin = fields.Char(help='What sent it (a module, "platform", …).')
    data = fields.Json(help='Extra values for the screen that opens it.')
    is_read = fields.Boolean('Read', default=False, index=True)
    read_date = fields.Datetime(readonly=True)
    pushed = fields.Integer('Phones Notified', readonly=True)

    @api.depends('body')
    def _compute_preview(self):
        for message in self:
            text = '' if is_html_empty(message.body) else html2plaintext(message.body or '')
            message.preview = ' '.join(text.split())[:300]

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    @api.model
    def send(self, kind=None, title='', body='', users=None, company=None, file=None, attachment=None, url=None,
             data=None, sender=None, origin=None, push=None):
        """Put a message in each person's inbox and notify their phones. Returns the messages created.

        :param kind: a kind code ("report") or record; without ``users``, its recipients receive it.
        :param title: the notification title (required).
        :param body: plain text or HTML.
        :param users: res.users to send to (a kind still removes the people who switched it off).
        :param company: res.company the message is about; people without access to it are left out.
        :param file: (filename, bytes, mimetype) to attach (stored once for everyone), or use ``attachment``.
        :param url: where a tap leads (see the ``url`` field).
        :param push: force (True) or skip (False) the phone notification; default: the kind's setting.
        """
        title = (title or '').strip()
        if not title:
            raise UserError(_('A DoniaLink App message needs a title.'))
        kind = self.env['donialink.app.kind']._get(kind)
        if users is None:
            if not kind:
                raise UserError(_('Name the people to send to, or a kind that has recipients.'))
            users = kind._recipients(company)
        else:
            users = users.sudo().filtered('active')
            if company:
                users = users.filtered(lambda u: company in u.company_ids)
            if kind:
                users = kind._wanted_by(users)
        if not users:
            return self.browse()
        if body and not _TAG.search(body):
            body = plaintext2html(body)
        if file and not attachment:
            filename, content, mimetype = (tuple(file) + (None,))[:3]
            attachment = self.env['ir.attachment'].sudo().create({
                'name': filename or 'file', 'raw': content, 'mimetype': mimetype or None,
                'res_model': self._name, 'res_id': 0,
            })
        messages = self.sudo().create([{
            'user_id': user.id,
            'kind_id': kind.id or False,
            'title': title[:200],
            'body': body or False,
            'attachment_id': attachment.id if attachment else False,
            'url': url or False,
            'company_id': company.id if company else False,
            'data': data or False,
            'sender': sender or False,
            'origin': origin or False,
        } for user in users])
        if attachment and not attachment.res_id:
            attachment.sudo().write({'res_id': messages[0].id})
        if push if push is not None else (not kind or kind.push):
            messages._push()
        return messages

    def _push_url(self):
        self.ensure_one()
        return '%s#msg-%s' % (APP_PATH, self.id)

    def _push(self):
        """Queue a Web Push to each phone of each recipient (Odoo's mail.push queue and VAPID keys)."""
        Device = self.env['mail.push.device'].sudo()
        rows = []
        for message in self:
            devices = Device.search([('partner_id', '=', message.user_id.partner_id.id)])
            if not devices:
                continue
            payload = json.dumps({
                'title': message.title[:120],
                'options': {
                    'body': (message.preview or (message.attachment_id.name or ''))[:300],
                    'icon': ICON,
                    'badge': BADGE,
                    'tag': 'dl-%s' % message.id,
                    'data': {'url': message._push_url(), 'dl_message_id': message.id},
                },
            }, ensure_ascii=False)
            rows += [{'mail_push_device_id': d.id, 'payload': payload} for d in devices]
            message.pushed = len(devices)
        if not rows:
            return 0
        self.env['mail.push'].sudo().create(rows)
        cron = self.env.ref('mail.ir_cron_web_push_notification', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()
        return len(rows)

    # ------------------------------------------------------------------
    # The app
    # ------------------------------------------------------------------

    def _to_app(self, full=False):
        values = []
        for m in self:
            value = {
                'id': m.id, 'title': m.title, 'preview': m.preview or '', 'kind': m.kind_code or '',
                'icon': m.kind_id.icon or 'bell', 'kind_name': m.kind_id.name or '',
                'read': m.is_read, 'date': fields.Datetime.to_string(m.create_date),
                'sender': m.sender or '', 'url': m.url or '', 'company': m.company_id.name or '',
                'file': {'name': m.attachment_id.name, 'mimetype': m.attachment_id.mimetype or '',
                         'url': '%s/file/%s' % (APP_PATH, m.id)} if m.attachment_id else None,
            }
            if full:
                value['body'] = '' if is_html_empty(m.body) else str(m.body)
                value['data'] = m.data or {}
            values.append(value)
        return values

    def action_mark_read(self):
        self.filtered(lambda m: not m.is_read).write({'is_read': True, 'read_date': fields.Datetime.now()})

    def action_mark_unread(self):
        self.write({'is_read': False, 'read_date': False})

    def action_push_again(self):
        self._push()

    @api.model
    def _cron_cleanup(self):
        """Forget read messages after donialink_app.keep_days (default 180) days."""
        days = int(self.env['ir.config_parameter'].sudo().get_param('donialink_app.keep_days', 180) or 0)
        if days <= 0:
            return
        old = self.sudo().search([('is_read', '=', True),
                                  ('create_date', '<', fields.Datetime.now() - timedelta(days=days))])
        old.attachment_id.filtered(lambda a: a.res_model == self._name).unlink()
        old.unlink()

    @api.model
    def _file_content(self, attachment):
        return base64.b64decode(attachment.datas or b'')
