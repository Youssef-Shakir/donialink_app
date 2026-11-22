/** @odoo-module ignore **/
/* DoniaLink App: chat, on Odoo Discuss. Direct chats and groups with the people of your companies (portal staff
   too); photos and files; new messages are pushed by Odoo to your phone and show here while a chat is open. */
(function () {
    'use strict';
    const app = window.DLApp;
    const { h, t } = app;

    app.text({
        ar: {
            'Chat': 'المحادثات', 'Talk to your team': 'تحدّث مع فريقك', 'New chat': 'محادثة جديدة', 'New group': 'مجموعة جديدة',
            'No conversation yet.': 'لا توجد محادثات بعد.', 'Search a person': 'ابحث عن شخص', 'Group name': 'اسم المجموعة',
            'Create group': 'إنشاء المجموعة', 'Write a message': 'اكتب رسالة', 'Send': 'إرسال', 'You': 'أنت',
            'Older messages': 'رسائل أقدم', 'Choose who is in the group.': 'اختر أعضاء المجموعة.', '{0} people': '{0} أشخاص',
            'Photo or file': 'صورة أو ملف', 'Nobody to chat with yet.': 'لا يوجد أشخاص للمحادثة بعد.',
        },
    });

    function time(value) {
        if (!value) {
            return '';
        }
        const d = new Date(value.replace(' ', 'T') + 'Z');
        const today = new Date();
        const sameDay = d.toDateString() === today.toDateString();
        return d.toLocaleString(app.lang === 'ar' ? 'ar-IQ' : 'en-GB', sameDay ? { hour: '2-digit', minute: '2-digit' } : { day: 'numeric', month: 'short' });
    }

    const initials = (name) => (name || '?').split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase();

    // ------------------------------------------------------------------ list

    async function listScreen(el) {
        el.append(app.topbar(t('Chat'), true));
        const body = h('div', { class: 'dl-stack' });
        el.append(body);
        const actions = h('div', { class: 'dl-row' }, [
            h('button', { class: 'dl-btn small', onclick: () => pickPeople(false) }, '+ ' + t('New chat')),
            h('button', { class: 'dl-btn small ghost', onclick: () => pickPeople(true) }, '+ ' + t('New group')),
        ]);
        const picker = h('div', { class: 'dl-card', hidden: true });
        const list = h('div', { class: 'dl-card flush' });
        body.append(actions, picker, list);

        async function load() {
            const data = await app.rpc('chats');
            list.replaceChildren(data.chats.length ? h('div', { class: 'dl-list' }, data.chats.map((c) => h('a', {
                class: 'dl-chat-row' + (c.unread ? ' unread' : ''), href: '#chat-' + c.id,
            }, [
                h('span', { class: 'dl-chat-avatar' + (c.type === 'group' ? ' group' : '') }, c.type === 'group' ? app.icon('chat') : initials(c.name)),
                h('span', { class: 'dl-msg-main' }, [
                    h('span', { class: 'dl-msg-title' }, c.name),
                    h('span', { class: 'dl-msg-preview' }, (c.last_mine ? t('You') + ': ' : '') + (c.last || '')),
                ]),
                h('span', { class: 'dl-chat-side' }, [
                    h('small', { class: 'dl-muted' }, time(c.date)),
                    c.unread ? h('span', { class: 'dl-count' }, String(c.unread)) : null,
                ]),
            ]))) : h('p', { class: 'dl-empty' }, t('No conversation yet.')));
        }

        async function pickPeople(group) {
            const data = await app.rpc('chat_people');
            const chosen = new Set();
            const search = h('input', { class: 'dl-input', type: 'search', placeholder: t('Search a person') });
            const name = group ? h('input', { class: 'dl-input', placeholder: t('Group name') }) : null;
            const rows = h('div', { class: 'dl-list dl-people' });
            function draw() {
                const q = search.value.trim().toLowerCase();
                rows.replaceChildren(...data.people.filter((p) => !q || p.name.toLowerCase().includes(q)).map((p) => h(group ? 'label' : 'button', {
                    class: 'dl-person', type: group ? null : 'button',
                    onclick: group ? null : async () => app.go('chat-' + (await app.rpc('chat_open', { user_id: p.id })).chat_id),
                }, [
                    group ? h('input', { type: 'checkbox', checked: chosen.has(p.id), onchange: (ev) => {
                        if (ev.target.checked) { chosen.add(p.id); } else { chosen.delete(p.id); }
                    } }) : null,
                    h('span', { class: 'dl-chat-avatar small' }, initials(p.name)),
                    h('span', { class: 'dl-msg-main' }, [h('b', {}, p.name), h('small', { class: 'dl-muted' }, p.company)]),
                ])));
                if (!rows.children.length) {
                    rows.append(h('p', { class: 'dl-empty' }, t('Nobody to chat with yet.')));
                }
            }
            search.oninput = draw;
            picker.replaceChildren(...[name, search, rows, group ? h('button', { class: 'dl-btn', onclick: async () => {
                if (!chosen.size) {
                    return app.toast(t('Choose who is in the group.'), 'bad');
                }
                const r = await app.rpc('chat_group', { name: name.value, user_ids: [...chosen] });
                app.go('chat-' + r.chat_id);
            } }, t('Create group')) : null].filter(Boolean));
            picker.hidden = false;
            draw();
            search.focus();
        }
        load();
    }

    // ------------------------------------------------------------------ conversation

    function readFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve({ filename: file.name, mimetype: file.type || '', content_b64: String(reader.result).split(',')[1] });
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    function bubble(m) {
        return h('div', { class: 'dl-bubble' + (m.mine ? ' mine' : '') }, [
            m.mine ? null : h('b', { class: 'dl-bubble-author' }, m.author),
            m.body ? h('div', { class: 'dl-bubble-text', html: m.body }) : null,
            ...m.files.map((f) => (f.mimetype.startsWith('image/')
                ? h('a', { href: f.url, target: '_blank' }, h('img', { class: 'dl-bubble-img', src: f.url, alt: f.name, loading: 'lazy' }))
                : h('a', { class: 'dl-bubble-file', href: f.url + '?download=1' }, '📎 ' + f.name))),
            h('small', { class: 'dl-bubble-time' }, time(m.date)),
        ]);
    }

    async function chatScreen(el, id) {
        const chatId = parseInt(id, 10);
        const data = await app.rpc('chat_messages', { chat_id: chatId });
        el.append(app.topbar(data.chat.name, true));
        if (data.chat.type === 'group') {
            el.append(h('p', { class: 'dl-muted dl-chat-members' }, data.chat.members.join('، ')));
        }
        const thread = h('div', { class: 'dl-thread' });
        let first = data.messages.length ? data.messages[0].id : null;
        let last = data.messages.length ? data.messages[data.messages.length - 1].id : null;
        const older = h('button', { class: 'dl-link', hidden: !data.more, onclick: async () => {
            const more = await app.rpc('chat_messages', { chat_id: chatId, before: first });
            thread.prepend(...more.messages.map(bubble));
            first = more.messages.length ? more.messages[0].id : first;
            older.hidden = !more.more;
        } }, t('Older messages'));
        thread.append(...data.messages.map(bubble));
        const input = h('textarea', { class: 'dl-input dl-chat-input', rows: 1, placeholder: t('Write a message') });
        const files = h('input', { type: 'file', multiple: true, hidden: true, accept: 'image/*,application/pdf,*/*' });
        const sendBtn = h('button', { class: 'dl-btn small', type: 'submit' }, t('Send'));
        const form = h('form', { class: 'dl-chat-bar', onsubmit: async (ev) => {
            ev.preventDefault();
            const text = input.value.trim();
            const attached = [];
            for (const f of files.files) { attached.push(await readFile(f)); }
            if (!text && !attached.length) {
                return;
            }
            sendBtn.disabled = true;
            try {
                const r = await app.rpc('chat_send', { chat_id: chatId, body: text, files: attached });
                input.value = '';
                files.value = '';
                if (r.message && (!last || r.message.id > last)) {
                    thread.append(bubble(r.message));
                    last = r.message.id;
                    scroll();
                }
            } catch (e) { app.toast(e.message, 'bad'); }
            sendBtn.disabled = false;
        } }, [
            h('button', { class: 'dl-icon-btn', type: 'button', 'aria-label': t('Photo or file'), onclick: () => files.click() }, app.icon('clip')),
            files, input, sendBtn,
        ]);
        input.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter' && !ev.shiftKey && !app.isIOS) {
                ev.preventDefault();
                form.requestSubmit();
            }
        });
        el.append(h('div', { class: 'dl-chat' }, [older, thread]), form);
        const scroll = () => window.scrollTo(0, document.body.scrollHeight);
        scroll();
        // new messages while the chat is open
        const timer = setInterval(async () => {
            if (app.current !== 'chat' || !document.body.contains(thread)) {
                return clearInterval(timer);
            }
            try {
                const fresh = await app.rpc('chat_messages', { chat_id: chatId, after: last });
                const added = fresh.messages.filter((m) => !last || m.id > last);
                if (added.length) {
                    thread.append(...added.map(bubble));
                    last = added[added.length - 1].id;
                    scroll();
                }
            } catch (e) { /* offline: try again */ }
        }, 4000);
    }

    app.screen('chat', {
        async render(el, params) {
            return params[0] ? chatScreen(el, params[0]) : listScreen(el);
        },
    });
}());
