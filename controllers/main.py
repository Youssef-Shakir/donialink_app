# -*- coding: utf-8 -*-
"""The DoniaLink App (PWA) at /dl/app: page, manifest, service worker, files and a small JSON API.

Login is Odoo's own (/web/login), so internal and portal users both work and the same session opens the full
Odoo. Every API call reads and writes only the logged-in person's own messages and settings."""
import base64
import binascii
import json
import logging
from pathlib import Path

from odoo import _, fields, http, tools
from odoo.exceptions import AccessDenied, AccessError, UserError
from odoo.http import request
from odoo.service import security

_logger = logging.getLogger(__name__)

APP = '/dl/app'
STATIC = Path(__file__).resolve().parent.parent / 'static'
IMG = '/donialink_app/static/img'
PAGE_SIZE = 30


def _version():
    module = request.env['ir.module.module'].sudo().search([('name', '=', 'donialink_app')], limit=1)
    return module.latest_version or '1'


def _brand_company():
    """The client the app is branded with: the person's company, else the main company."""
    user = request.env.user
    if user and not user._is_public():
        return user.company_id.sudo()
    return (request.env.ref('base.main_company', raise_if_not_found=False)
            or request.env['res.company'].sudo().search([], limit=1)).sudo()


def _app_name():
    """The client's name (or donialink_app.name when set), never ours."""
    return (request.env['ir.config_parameter'].sudo().get_param('donialink_app.name')
            or _brand_company().name or 'App')


ICON_SIZES = (32, 180, 192, 512)


def _logo_png(company, size, maskable=False):
    """The company logo centred on a white square of ``size`` px (PNG), or None without a logo."""
    if not company.logo:
        return None
    try:
        from PIL import Image
        import io
        logo = Image.open(io.BytesIO(base64.b64decode(company.logo))).convert('RGBA')
        canvas = Image.new('RGBA', (size, size), (255, 255, 255, 255))
        inner = int(size * (0.62 if maskable else 0.82))
        logo.thumbnail((inner, inner), Image.LANCZOS)
        canvas.paste(logo, ((size - logo.width) // 2, (size - logo.height) // 2), logo)
        out = io.BytesIO()
        canvas.convert('RGB').save(out, format='PNG', optimize=True)
        return out.getvalue()
    except Exception as e:  # noqa: BLE001 - a broken logo falls back to the default icon
        _logger.info('DoniaLink App: company logo unusable as icon: %s', e)
        return None


class DonialinkApp(http.Controller):

    # ------------------------------------------------------------------
    # Files of the installable app
    # ------------------------------------------------------------------

    @http.route([APP, APP + '/'], type='http', auth='public', sitemap=False)
    def app_page(self, **kw):
        if request.env.user._is_public():
            return request.redirect('/web/login?redirect=%s' % APP, 303)
        user = request.env.user
        lang = user.lang or 'en_US'
        response = request.render('donialink_app.app_page', {
            'app_name': _app_name(),
            'app_lang': lang.split('_')[0],
            'direction': 'rtl' if lang.startswith(('ar', 'fa', 'he', 'ur')) else 'ltr',
            'version': _version(),
            'img': IMG,
            'icon': APP + '/icon',
        })
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @http.route(APP + '/manifest.webmanifest', type='http', auth='public', sitemap=False)
    def app_manifest(self, **kw):
        name = _app_name()
        manifest = {
            'name': name,
            'short_name': name[:12],
            'description': _('Notifications, reports and your business on your phone.'),
            'id': APP,
            'start_url': APP,
            'scope': APP,
            'display': 'standalone',
            'orientation': 'portrait',
            'background_color': '#0a1622',
            'theme_color': '#0e3f64',
            'dir': 'auto',
            'icons': [
                {'src': f'{APP}/icon/192.png', 'sizes': '192x192', 'type': 'image/png'},
                {'src': f'{APP}/icon/512.png', 'sizes': '512x512', 'type': 'image/png'},
                {'src': f'{APP}/icon/maskable-512.png', 'sizes': '512x512', 'type': 'image/png',
                 'purpose': 'maskable'},
            ],
        }
        return request.make_response(json.dumps(manifest, ensure_ascii=False), headers=[
            ('Content-Type', 'application/manifest+json; charset=utf-8'), ('Cache-Control', 'no-cache')])

    @http.route(APP + '/sw.js', type='http', auth='public', sitemap=False)
    def app_service_worker(self, **kw):
        js = (STATIC / 'src' / 'app' / 'sw.js').read_text(encoding='utf-8')
        js = (js.replace('{{VERSION}}', _version()).replace('{{IMG}}', IMG).replace('{{APP}}', APP)
              .replace('{{NAME}}', json.dumps(_app_name())[1:-1]))
        return request.make_response(js, headers=[
            ('Content-Type', 'application/javascript; charset=utf-8'),
            ('Cache-Control', 'no-cache'),
            ('Service-Worker-Allowed', APP),   # the app is /dl/app (no slash): the worker must cover it
        ])

    @http.route([APP + '/icon/<int:size>.png', APP + '/icon/maskable-<int:size>.png'], type='http', auth='public',
                sitemap=False)
    def app_icon(self, size, **kw):
        """The app icon from the client's logo (home screen, notifications, favicon)."""
        size = size if size in ICON_SIZES else 192
        maskable = 'maskable' in request.httprequest.path
        png = _logo_png(_brand_company(), size, maskable=maskable)
        if png is None:
            name = {32: 'favicon-32.png', 180: 'icon-180.png', 512: 'icon-maskable-512.png' if maskable else 'icon-512.png'}
            png = (STATIC / 'img' / name.get(size, 'icon-192.png')).read_bytes()
        return request.make_response(png, headers=[('Content-Type', 'image/png'), ('Cache-Control', 'public, max-age=3600')])

    @http.route(APP + '/chat/file/<int:attachment_id>', type='http', auth='user', sitemap=False)
    def app_chat_file(self, attachment_id, download=None, **kw):
        """A file of a chat message, for the members of that conversation only."""
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        if not attachment or attachment.res_model != 'discuss.channel' or not request.env['discuss.channel.member'].sudo(
        ).search_count([('channel_id', '=', attachment.res_id), ('partner_id', '=', request.env.user.partner_id.id)]):
            raise request.not_found()
        return request.env['ir.binary']._get_stream_from(attachment).get_response(as_attachment=bool(download))

    @http.route(APP + '/file/<int:message_id>', type='http', auth='user', sitemap=False)
    def app_file(self, message_id, download=None, **kw):
        message = request.env['donialink.app.message'].sudo().browse(message_id).exists()
        if not message or message.user_id != request.env.user or not message.attachment_id:
            raise request.not_found()
        attachment = message.attachment_id
        stream = request.env['ir.binary']._get_stream_from(attachment)
        return stream.get_response(as_attachment=bool(download))

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    @http.route(APP + '/api/<string:action>', type='json', auth='user', methods=['POST'], csrf=False)
    def app_api(self, action, **params):
        method = getattr(self, '_api_%s' % action, None)
        if not method:
            return {'error': 'unknown_action'}
        try:
            return method(**params)
        except (AccessError, UserError) as e:
            request.env.cr.rollback()
            return {'error': 'refused', 'message': str(e.args[0] if e.args else e)}
        except TypeError as e:
            _logger.info('DoniaLink App: bad call to %s: %s', action, e)
            return {'error': 'bad_request'}

    def _messages(self):
        return request.env['donialink.app.message'].sudo()

    def _mine(self, domain=None):
        return [('user_id', '=', request.env.user.id)] + (domain or [])

    def _unread(self):
        return self._messages().search_count(self._mine([('is_read', '=', False)]))

    def _kinds(self):
        """The kinds this person receives or received, with their switch."""
        user = request.env.user
        Kind = request.env['donialink.app.kind'].sudo()
        received = self._messages()._read_group(self._mine(), ['kind_id'])
        kinds = Kind.search(['|', '|', ('recipient_ids', 'in', user.id), ('muted_user_ids', 'in', user.id),
                             ('id', 'in', [k.id for (k,) in received if k])])
        return [{'code': k.code, 'name': k.name, 'description': k.description or '', 'icon': k.icon or 'bell',
                 'on': user not in k.muted_user_ids, 'can_mute': k.user_can_mute} for k in kinds]

    def _api_session(self):
        user = request.env.user
        user.sudo().dl_app_last_seen = fields.Datetime.now()
        screens = request.env['donialink.app.screen']._for_user(user)
        return {
            'app_name': _app_name(),
            'version': _version(),
            'logo': APP + '/icon/192.png',
            'user': {'id': user.id, 'name': user.name, 'lang': user.lang or 'en_US',
                     'internal': user._is_internal(), 'company': user.company_id.name,
                     'avatar': '/web/image/res.users/%s/avatar_128' % user.id},
            'screens': screens._to_app(user),
            'unread': self._unread(),
            'kinds': self._kinds(),
            'push_key': request.env['mail.push.device'].sudo().get_web_push_vapid_public_key(),
            'summary': request.env['donialink.app.summary']._info(user),
        }

    def _api_password(self, old, new):
        """The person changes their own password (internal or portal); the session stays open."""
        new = new or ''
        if len(new) < 8:
            raise UserError(_('The new password needs at least 8 characters.'))
        try:
            request.env['res.users'].change_password(old or '', new)
        except AccessDenied:
            raise UserError(_('The current password is wrong.')) from None
        request.session.session_token = security.compute_session_token(request.session, request.env)
        return {'ok': True}

    # business summary (donialink_agent's read tools; access checked in donialink.app.summary)

    def _api_summary_card(self, part, company_id, period='today'):
        return request.env['donialink.app.summary'].card(str(part), company_id, str(period or 'today'))

    def _api_summary_glance(self, company_id):
        return request.env['donialink.app.summary'].glance(company_id)

    # tasks (record rules apply: the person's own tasks, all of their companies for task managers)

    def _tasks(self):
        return request.env['donialink.app.task']

    def _task(self, task_id):
        task = self._tasks().browse(int(task_id)).exists()
        if not task:
            raise UserError(_('This task is no longer here.'))
        task.check_access('read')
        return task

    def _team_check(self):
        if not request.env.user.has_group('donialink_app.group_task_manager'):
            raise AccessError(_('Only task managers can do this.'))

    def _api_tasks_mine(self):
        user = request.env.user
        today = fields.Datetime.to_datetime(fields.Date.context_today(user))
        tasks = self._tasks().search(['&', ('user_ids', 'in', user.id), '|', ('state', 'in', ('todo', 'progress')),
                                      '&', ('state', '=', 'done'), ('done_date', '>=', today)], limit=200)
        # found with the person's rights (record rules); read with sudo: names of the company, creator, people
        return {'tasks': tasks.sudo()._to_app()}

    def _api_tasks_team(self, user_id=None, state=None):
        self._team_check()
        domain = [('company_id', 'in', request.env.user.company_ids.ids)]
        if user_id:
            domain.append(('user_ids', 'in', int(user_id)))
        domain.append(('state', '=', state) if state in ('todo', 'progress', 'done', 'cancelled')
                      else ('state', 'in', ('todo', 'progress')))
        people = request.env['donialink.app.admin'].sudo()._people().filtered(
            lambda u: u.active and u.company_ids & request.env.user.company_ids)
        return {'tasks': self._tasks().search(domain, limit=300).sudo()._to_app(),
                'people': [{'id': u.id, 'name': u.name} for u in people]}

    def _api_task(self, task_id):
        return {'task': self._task(task_id).sudo()._to_app(full=True)[0]}

    def _api_task_do(self, task_id, step, note=None, photos=None):
        task = self._task(task_id)
        if step == 'start':
            task.action_start()
        elif step == 'done':
            files = []
            for photo in (photos or [])[:5]:
                try:
                    content = base64.b64decode((photo or {}).get('content_b64') or '', validate=True)
                except (binascii.Error, ValueError):
                    raise UserError(_('This photo could not be read.')) from None
                if not content or len(content) > 8 * 1024 * 1024:
                    raise UserError(_('Each photo must be smaller than 8 MB.'))
                files.append(((photo.get('filename') or 'photo.jpg')[:200], content, photo.get('mimetype') or 'image/jpeg'))
            task.action_done(note=(note or '').strip()[:2000] or None, photos=files)
        elif step == 'cancel':
            task.action_cancel()
        elif step == 'reset':
            task.action_reset()
        else:
            return {'error': 'bad_request'}
        return {'task': task.sudo()._to_app(full=True)[0]}

    def _api_task_line(self, line_id, done):
        line = request.env['donialink.app.task.line'].browse(int(line_id)).exists()
        if not line:
            return {'error': 'not_found'}
        line.task_id._check_can_do()
        line.done = bool(done)
        return {'task': line.task_id.sudo()._to_app(full=True)[0]}

    def _api_task_comment(self, task_id, body):
        task = self._task(task_id)
        body = (body or '').strip()
        if body:
            task.sudo().message_post(body=body, author_id=request.env.user.partner_id.id,
                                     message_type='comment', subtype_xmlid='mail.mt_note')
        return {'task': task.sudo()._to_app(full=True)[0]}

    def _api_task_create(self, name, user_ids, deadline=None, description=None, priority='0', lines=None,
                         photo_required=False, repeat='none', repeat_weekdays=None):
        self._team_check()
        allowed = request.env['donialink.app.admin'].sudo()._people().filtered(
            lambda u: u.active and u.company_ids & request.env.user.company_ids)
        users = allowed.filtered(lambda u: u.id in [int(i) for i in user_ids or []])
        if not users or not (name or '').strip():
            raise UserError(_('Give the task a name and someone to do it.'))
        task = self._tasks().create({
            'name': name.strip()[:200], 'user_ids': [(6, 0, users.ids)], 'deadline': deadline or False,
            'description': (description or '').strip() or False, 'priority': str(priority or '0'),
            'line_ids': [(0, 0, {'name': str(n)[:200]}) for n in (lines or []) if str(n).strip()],
            'photo_required': bool(photo_required),
            'repeat': repeat if repeat in ('none', 'daily', 'weekly') else 'none',
            'repeat_weekdays': repeat_weekdays or False,
        })
        return {'task': task.sudo()._to_app(full=True)[0]}

    # chat (Odoo Discuss: direct chats and groups, portal users too; access = being a member) -----------

    def _chat_people(self):
        """The people one can chat with: app users of the person's companies (internal and portal)."""
        user = request.env.user
        people = request.env['donialink.app.admin'].sudo().with_context(
            allowed_company_ids=user.company_ids.ids)._people()
        return people.filtered(lambda u: u.active and u != user)

    def _chat_member(self, channel_id):
        member = request.env['discuss.channel.member'].sudo().search(
            [('channel_id', '=', int(channel_id or 0)), ('partner_id', '=', request.env.user.partner_id.id)], limit=1)
        if not member:
            raise AccessError(_('You are not in this conversation.'))
        return member

    def _chat_title(self, channel):
        me = request.env.user.partner_id
        if channel.channel_type == 'chat':
            other = channel.channel_member_ids.partner_id - me
            return other[:1].name or channel.name
        return channel.name or ', '.join((channel.channel_member_ids.partner_id - me).mapped('name'))

    def _chat_message(self, message):
        me = request.env.user.partner_id
        return {
            'id': message.id, 'mine': message.author_id == me, 'author': message.author_id.name or '',
            'body': str(message.body or ''), 'date': fields.Datetime.to_string(message.date),
            'files': [{'id': a.id, 'name': a.name, 'mimetype': a.mimetype or '',
                       'url': '%s/chat/file/%s' % (APP, a.id)} for a in message.attachment_ids],
        }

    def _api_chats(self):
        me = request.env.user.partner_id
        members = request.env['discuss.channel.member'].sudo().search([
            ('partner_id', '=', me.id), ('channel_id.channel_type', 'in', ('chat', 'group'))])
        Message = request.env['mail.message'].sudo()
        bot = request.env.ref('base.partner_root')
        rows = []
        for member in members:
            channel = member.channel_id
            if channel.channel_type == 'chat' and bot in channel.channel_member_ids.partner_id:
                continue   # Odoo's welcome chat with OdooBot
            last = Message.search([('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
                                   ('message_type', '=', 'comment')], order='id desc', limit=1)
            if channel.channel_type == 'chat' and not last:
                continue   # a direct chat nobody wrote in yet
            preview = ' '.join(tools.html2plaintext(last.body or '').split())[:120] if last else ''
            if last and not preview and last.attachment_ids:
                preview = '📎 ' + last.attachment_ids[0].name
            rows.append({
                'id': channel.id, 'type': channel.channel_type, 'name': self._chat_title(channel),
                'members': len(channel.channel_member_ids), 'unread': member.message_unread_counter,
                'last': preview, 'last_mine': bool(last and last.author_id == me),
                'date': fields.Datetime.to_string(last.date if last else channel.create_date),
            })
        rows.sort(key=lambda r: r['date'] or '', reverse=True)
        return {'chats': rows}

    def _api_chat_people(self):
        return {'people': [{'id': u.id, 'partner_id': u.partner_id.id, 'name': u.name,
                            'company': u.company_id.name} for u in self._chat_people()]}

    def _api_chat_open(self, user_id):
        other = self._chat_people().filtered(lambda u: u.id == int(user_id or 0))
        if not other:
            raise AccessError(_('You can not chat with this person.'))
        channel = request.env['discuss.channel'].sudo().channel_get([other.partner_id.id])
        return {'chat_id': channel.id}

    def _api_chat_group(self, name, user_ids):
        people = self._chat_people().filtered(lambda u: u.id in [int(i) for i in user_ids or []])
        if not people:
            raise UserError(_('Choose who is in the group.'))
        channel = request.env['discuss.channel'].sudo().create_group(
            partners_to=(people.partner_id | request.env.user.partner_id).ids, name=(name or '').strip()[:100])
        return {'chat_id': channel.id}

    def _api_chat_messages(self, chat_id, before=None, after=None, limit=40):
        member = self._chat_member(chat_id)
        channel = member.channel_id
        domain = [('model', '=', 'discuss.channel'), ('res_id', '=', channel.id), ('message_type', '=', 'comment')]
        if before:
            domain.append(('id', '<', int(before)))
        if after:
            domain.append(('id', '>', int(after)))
        limit = max(1, min(int(limit or 40), 100))
        messages = request.env['mail.message'].sudo().search(domain, order='id desc', limit=limit + 1)
        more = len(messages) > limit
        messages = messages[:limit]
        if messages and not before:
            member._mark_as_read(messages[0].id)
        return {
            'chat': {'id': channel.id, 'type': channel.channel_type, 'name': self._chat_title(channel),
                     'members': [p.name for p in channel.channel_member_ids.partner_id]},
            'messages': [self._chat_message(m) for m in reversed(messages)], 'more': more and not after,
        }

    def _api_chat_send(self, chat_id, body=None, files=None):
        member = self._chat_member(chat_id)
        channel = member.channel_id
        text = (body or '').strip()[:4000]
        attachments = request.env['ir.attachment'].sudo()
        for item in (files or [])[:5]:
            try:
                content = base64.b64decode((item or {}).get('content_b64') or '', validate=True)
            except (binascii.Error, ValueError):
                raise UserError(_('This file could not be read.')) from None
            if not content or len(content) > 15 * 1024 * 1024:
                raise UserError(_('Each file must be smaller than 15 MB.'))
            attachments |= attachments.create({
                'name': (item.get('filename') or 'file')[:200], 'raw': content,
                'mimetype': item.get('mimetype') or None, 'res_model': 'discuss.channel', 'res_id': channel.id})
        if not text and not attachments:
            return {'error': 'bad_request'}
        message = channel.sudo().with_context(mail_create_nosubscribe=True).message_post(
            body=tools.plaintext2html(text) if text else '', author_id=request.env.user.partner_id.id,
            message_type='comment', subtype_xmlid='mail.mt_comment', attachment_ids=attachments.ids)
        member._mark_as_read(message.id)
        return {'message': self._chat_message(message)}

    def _api_badges(self):
        user = request.env.user
        screens = request.env['donialink.app.screen']._for_user(user)
        return {'unread': self._unread(), 'badges': {s.key: s._badge(user) for s in screens}}

    def _api_inbox(self, kind=None, unread=False, before=None, limit=PAGE_SIZE):
        domain = self._mine()
        if kind:
            domain.append(('kind_code', '=', str(kind)))
        if unread:
            domain.append(('is_read', '=', False))
        if before:
            domain.append(('id', '<', int(before)))
        limit = max(1, min(int(limit or PAGE_SIZE), 100))
        messages = self._messages().search(domain, limit=limit + 1)
        return {'messages': messages[:limit]._to_app(), 'more': len(messages) > limit, 'unread': self._unread()}

    def _api_message(self, message_id):
        message = self._messages().search(self._mine([('id', '=', int(message_id))]), limit=1)
        if not message:
            return {'error': 'not_found'}
        message.action_mark_read()
        return {'message': message._to_app(full=True)[0], 'unread': self._unread()}

    def _api_read(self, ids=None, all=False):  # noqa: A002 - the app's word
        domain = self._mine([('is_read', '=', False)])
        if not all:
            domain.append(('id', 'in', [int(i) for i in (ids or [])]))
        self._messages().search(domain).action_mark_read()
        return {'unread': self._unread()}

    def _api_kind_set(self, code, on):
        user = request.env.user
        kind = request.env['donialink.app.kind']._get(code)
        if not kind:
            return {'error': 'not_found'}
        if not kind.user_can_mute and not on:
            return {'error': 'refused', 'message': _('This notification can not be switched off.')}
        kind.sudo().write({'muted_user_ids': [(3 if on else 4, user.id)]})
        return {'kinds': self._kinds()}

    def _api_push_subscribe(self, subscription, vapid_key):
        """This phone gets this person's notifications (Odoo's mail.push.device, so Discuss pushes come too)."""
        Device = request.env['mail.push.device'].sudo()
        if vapid_key != Device.get_web_push_vapid_public_key():
            return {'error': 'push_key', 'message': _('The server key changed. Turn notifications on again.')}
        endpoint = (subscription or {}).get('endpoint')
        keys = (subscription or {}).get('keys') or {}
        if not isinstance(endpoint, str) or not endpoint.startswith('https://') or len(endpoint) > 2048 \
                or not keys.get('p256dh') or not keys.get('auth'):
            return {'error': 'bad_request'}
        values = {'partner_id': request.env.user.partner_id.id,
                  'keys': json.dumps({'p256dh': str(keys['p256dh']), 'auth': str(keys['auth'])}),
                  'expiration_time': False}
        device = Device.search([('endpoint', '=', endpoint)], limit=1)
        if device:
            device.write(values)
        else:
            Device.create(dict(values, endpoint=endpoint))
        return {'push': True}

    def _api_push_unsubscribe(self, endpoint):
        request.env['mail.push.device'].sudo().search(
            [('endpoint', '=', endpoint), ('partner_id', '=', request.env.user.partner_id.id)]).unlink()
        return {'push': False}

    def _api_push_test(self):
        user = request.env.user
        self._messages().with_user(user).sudo().send(
            title=_('Notifications are on'), body=_('This phone will receive notifications from %s.', _app_name()),
            users=user, origin='test', push=True)
        return {'ok': True}
