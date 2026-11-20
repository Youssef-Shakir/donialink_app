/** @odoo-module ignore **/
/* DoniaLink App: the core screens (home, notifications, reports, a message, settings). */
(function () {
    'use strict';
    const app = window.DLApp;
    const { h, t } = app;

    app.text({
        ar: {
            'Notifications': 'الإشعارات', 'Reports': 'التقارير', 'Settings': 'الإعدادات', 'Back': 'رجوع',
            'Open Odoo': 'فتح أودو', 'Home': 'الرئيسية', 'Hello, {0}': 'مرحباً، {0}',
            'Latest': 'آخر الإشعارات', 'See all': 'عرض الكل', 'Nothing new.': 'لا جديد.',
            'No notifications yet.': 'لا توجد إشعارات بعد.', 'No reports yet.': 'لا توجد تقارير بعد.',
            'Unread': 'غير المقروءة', 'All': 'الكل', 'Mark all read': 'تعليم الكل كمقروء',
            'Load more': 'عرض المزيد', 'Open file': 'فتح الملف', 'Download': 'تنزيل', 'Open': 'فتح',
            'This message is no longer here.': 'هذه الرسالة لم تعد موجودة.',
            'No internet connection.': 'لا يوجد اتصال بالإنترنت.', 'Please log in again.': 'سجّل الدخول مرة أخرى.',
            'Server error. Try again.': 'حدث خطأ في الخادم. حاول مرة أخرى.', 'Try again': 'حاول مرة أخرى',
            'This phone': 'هذا الهاتف', 'What you receive': 'ما يصلك',
            'Turn on notifications': 'تشغيل الإشعارات', 'Turn off notifications': 'إيقاف الإشعارات',
            'Notifications are on for this phone.': 'الإشعارات مفعّلة على هذا الهاتف.',
            'Notifications are off for this phone.': 'الإشعارات متوقفة على هذا الهاتف.',
            'Notifications are blocked: allow them in the browser settings.': 'الإشعارات محظورة: اسمح بها من إعدادات المتصفح.',
            'Add the app to your Home Screen first to get notifications.': 'أضف التطبيق إلى الشاشة الرئيسية أولاً لتصلك الإشعارات.',
            'This browser does not support notifications.': 'هذا المتصفح لا يدعم الإشعارات.',
            'Notifications turned on. A test is on its way.': 'تم تشغيل الإشعارات. سيصلك إشعار تجريبي.',
            'Notifications turned off.': 'تم إيقاف الإشعارات.',
            'Get notified on this phone': 'فعّل الإشعارات على هذا الهاتف',
            'Reports and alerts reach you at once.': 'تصلك التقارير والتنبيهات فوراً.',
            'Install the app': 'ثبّت التطبيق', 'Install': 'تثبيت', 'Later': 'لاحقاً',
            'Install the app on your phone': 'ثبّت التطبيق على هاتفك',
            'Tap Share ⬆︎ (on iOS 26 it is inside the ⋯ button at the bottom)': 'اضغط زر المشاركة ⬆︎ (في iOS 26 تجده داخل زر ⋯ أسفل الشاشة)',
            'Scroll down or tap "View More"': 'مرّر القائمة للأسفل أو اضغط «عرض المزيد»',
            'Choose "Add to Home Screen", then "Add"': 'اختر «إضافة إلى الشاشة الرئيسية» ثم «إضافة»',
            'Opened from WhatsApp or Telegram? Open it in Safari first.': 'فتحته من واتساب أو تيليجرام؟ افتحه أولاً في سفاري.',
            'Always on': 'مفعّل دائماً', 'Saved': 'تم الحفظ', 'Log out': 'تسجيل الخروج',
            'Account': 'الحساب', 'App version {0}': 'إصدار التطبيق {0}',
            'Nothing to receive yet.': 'لا يوجد ما يصلك بعد.',
            'Powered by DoniaLink': 'بواسطة دنيا لينك',
        },
    });

    // ------------------------------------------------------------------ pieces

    function messageRow(m) {
        return h('a', { class: 'dl-msg' + (m.read ? '' : ' unread'), href: '#msg-' + m.id }, [
            h('span', { class: 'dl-msg-icon' }, app.icon(m.file ? 'report' : m.icon)),
            h('span', { class: 'dl-msg-main' }, [
                h('span', { class: 'dl-msg-title' }, m.title),
                m.preview ? h('span', { class: 'dl-msg-preview' }, m.preview) : null,
                h('span', { class: 'dl-msg-meta' }, [m.kind_name || m.sender, m.company].filter(Boolean).join(' · ')),
            ]),
            h('span', { class: 'dl-msg-date' }, app.date(m.date)),
        ]);
    }

    async function pushBanner(container) {
        const state = await app.pushState().catch(() => 'unsupported');
        let dismissed = false;
        try { dismissed = localStorage.getItem('dl-push-later') === '1'; } catch (e) { /* private mode */ }
        if (dismissed || !['off', 'install'].includes(state)) {
            return;
        }
        const banner = h('div', { class: 'dl-banner' }, [
            app.icon(state === 'install' ? 'install' : 'bell'),
            h('div', { class: 'dl-banner-text' }, [
                h('b', {}, state === 'install' ? t('Install the app') : t('Get notified on this phone')),
                h('span', {}, state === 'install' ? t('Add the app to your Home Screen first to get notifications.')
                    : t('Reports and alerts reach you at once.')),
            ]),
            h('div', { class: 'dl-banner-actions' }, [
                h('button', { class: 'dl-btn small', onclick: async () => {
                    if (state === 'install') {
                        return app.go('settings');
                    }
                    try {
                        await app.pushOn();
                        app.toast(t('Notifications turned on. A test is on its way.'), 'ok');
                        banner.remove();
                    } catch (e) { app.toast(e.message, 'bad'); }
                } }, state === 'install' ? t('Install') : t('Turn on notifications')),
                h('button', { class: 'dl-link', onclick: () => {
                    try { localStorage.setItem('dl-push-later', '1'); } catch (e) { /* ignore */ }
                    banner.remove();
                } }, t('Later')),
            ]),
        ]);
        container.prepend(banner);
    }

    function installSteps() {
        if (app.standalone) {
            return null;
        }
        if (app.isIOS) {
            return h('div', { class: 'dl-card' }, [
                h('h2', {}, t('Install the app on your phone')),
                h('ol', { class: 'dl-steps' }, [
                    h('li', {}, t('Tap Share ⬆︎ (on iOS 26 it is inside the ⋯ button at the bottom)')),
                    h('li', {}, t('Scroll down or tap "View More"')),
                    h('li', {}, t('Choose "Add to Home Screen", then "Add"')),
                ]),
                h('p', { class: 'dl-muted' }, t('Opened from WhatsApp or Telegram? Open it in Safari first.')),
            ]);
        }
        const button = h('button', { class: 'dl-btn', 'data-install': '', hidden: !app.installPrompt, onclick: async () => {
            if (await app.install()) {
                button.hidden = true;
            }
        } }, [app.icon('install'), t('Install the app')]);
        return h('div', { class: 'dl-card', 'data-install': '', hidden: !app.installPrompt }, [button]);
    }

    // ------------------------------------------------------------------ home

    app.screen('home', {
        async render(el) {
            const s = app.session;
            const tiles = s.screens.filter((x) => x.home);
            el.append(h('header', { class: 'dl-hero' }, [
                s.logo ? h('img', { class: 'dl-hero-logo', src: s.logo, alt: s.user.company }) : null,
                h('div', { class: 'dl-hero-text' }, [
                    h('span', { class: 'dl-hero-company' }, s.user.company),
                    h('h1', {}, t('Hello, {0}', s.user.name.split(' ')[0])),
                ]),
                h('a', { class: 'dl-icon-btn dl-bell', href: '#inbox', 'aria-label': t('Notifications') }, [
                    app.icon('bell'), h('span', { class: 'dl-count', 'data-unread': '', hidden: !s.unread }, String(s.unread)),
                ]),
                h('a', { class: 'dl-icon-btn', href: '#settings', 'aria-label': t('Settings') }, app.icon('settings')),
            ]));
            const body = h('div', { class: 'dl-stack' });
            el.append(body);
            pushBanner(body);
            body.append(h('nav', { class: 'dl-tiles' }, tiles.map((tile) => h('a', {
                class: 'dl-tile', href: tile.url ? tile.url : '#' + tile.key,
                target: tile.url && /^https?:/.test(tile.url) ? '_blank' : null,
            }, [
                h('span', { class: 'dl-tile-icon' }, app.icon(tile.icon)),
                h('span', { class: 'dl-tile-name' }, t(tile.name)),
                tile.description ? h('span', { class: 'dl-tile-desc' }, t(tile.description)) : null,
                tile.key === 'inbox'
                    ? h('span', { class: 'dl-count', 'data-unread': '', hidden: !s.unread }, String(s.unread))
                    : h('span', { class: 'dl-count', 'data-badge': tile.key, hidden: !tile.badge }, String(tile.badge || '')),
            ]))));
            if (s.summary && app.summaryHome) {
                app.summaryHome(body);
            }
            const latest = h('section', { class: 'dl-card' }, [
                h('div', { class: 'dl-card-head' }, [h('h2', {}, t('Latest')), h('a', { href: '#inbox' }, t('See all'))]),
            ]);
            body.append(latest);
            const data = await app.rpc('inbox', { limit: 5 });
            latest.append(data.messages.length ? h('div', { class: 'dl-list' }, data.messages.map(messageRow))
                : h('p', { class: 'dl-empty' }, t('Nothing new.')));
        },
    });

    // ------------------------------------------------------------------ notifications

    function listScreen(options) {
        return {
            title: options.title,
            async render(el, params) {
                let filter = params[0] === 'unread' ? 'unread' : 'all';
                el.append(app.topbar(t(options.title), true));
                const tabs = options.tabs ? h('div', { class: 'dl-tabs', role: 'tablist' }) : null;
                const list = h('div', { class: 'dl-list' });
                const more = h('button', { class: 'dl-btn ghost', hidden: true }, t('Load more'));
                if (tabs) {
                    for (const [key, label] of [['all', 'All'], ['unread', 'Unread']]) {
                        const tab = h('button', { role: 'tab', 'aria-selected': String(filter === key), onclick: () => {
                            filter = key;
                            tabs.querySelectorAll('button').forEach((b) => b.setAttribute('aria-selected', String(b === tab)));
                            load(true);
                        } }, t(label));
                        tabs.append(tab);
                    }
                    el.append(h('div', { class: 'dl-row' }, [tabs, h('button', { class: 'dl-link', onclick: async () => {
                        const data = await app.rpc('read', { all: true });
                        app.setUnread(data.unread);
                        list.querySelectorAll('.unread').forEach((n) => n.classList.remove('unread'));
                    } }, t('Mark all read'))]));
                }
                el.append(h('div', { class: 'dl-card flush' }, list), more);
                let last = null;
                async function load(reset) {
                    if (reset) {
                        list.replaceChildren();
                        last = null;
                    }
                    const data = await app.rpc('inbox', Object.assign({ before: last, unread: filter === 'unread' }, options.params || {}));
                    let messages = data.messages;
                    if (options.only) {
                        messages = messages.filter(options.only);
                    }
                    list.append(...messages.map(messageRow));
                    if (!list.children.length && !data.more) {
                        list.append(h('p', { class: 'dl-empty' }, t(options.empty)));
                    }
                    last = data.messages.length ? data.messages[data.messages.length - 1].id : last;
                    more.hidden = !data.more;
                    app.setUnread(data.unread);
                }
                more.addEventListener('click', () => load(false));
                await load(true);
            },
        };
    }

    app.screen('inbox', listScreen({ title: 'Notifications', empty: 'No notifications yet.', tabs: true }));
    app.screen('reports', listScreen({ title: 'Reports', empty: 'No reports yet.', only: (m) => !!m.file }));

    app.screen('message', {
        always: true,
        async render(el, params) {
            el.append(app.topbar(t('Notifications'), true));
            let data;
            try {
                data = await app.rpc('message', { message_id: Number(params[0]) });
            } catch (e) {
                el.append(h('p', { class: 'dl-empty' }, e.code === 'not_found' ? t('This message is no longer here.') : e.message));
                return;
            }
            const m = data.message;
            app.setUnread(data.unread);
            const card = h('article', { class: 'dl-card dl-message' }, [
                h('div', { class: 'dl-msg-meta' }, [m.kind_name || m.sender, m.company, app.date(m.date)].filter(Boolean).join(' · ')),
                h('h1', {}, m.title),
                m.body ? h('div', { class: 'dl-body', html: m.body }) : null,
            ]);
            if (m.file) {
                card.append(h('div', { class: 'dl-file' }, [
                    app.icon('file'),
                    h('span', { class: 'dl-file-name' }, m.file.name),
                    h('a', { class: 'dl-btn small', href: m.file.url, target: '_blank', rel: 'noopener' }, t('Open file')),
                    h('a', { class: 'dl-link', href: m.file.url + '?download=1' }, t('Download')),
                ]));
                if ((m.file.mimetype || '').startsWith('image/')) {
                    card.append(h('img', { class: 'dl-image', src: m.file.url, alt: m.file.name }));
                }
            }
            if (m.url) {
                card.append(h('button', { class: 'dl-btn', onclick: () => app.open(m.url) }, t('Open')));
            }
            card.querySelectorAll('.dl-body a[href]').forEach((a) => { a.target = '_blank'; a.rel = 'noopener'; });
            el.append(card);
        },
    });

    // ------------------------------------------------------------------ settings

    app.screen('settings', {
        always: true,
        async render(el) {
            el.append(app.topbar(t('Settings'), true));
            const s = app.session;

            const phone = h('section', { class: 'dl-card' }, [h('h2', {}, t('This phone'))]);
            const status = h('p', { class: 'dl-muted' });
            const toggle = h('button', { class: 'dl-btn' });
            phone.append(status, toggle);
            async function showPush() {
                const state = await app.pushState().catch(() => 'unsupported');
                const words = {
                    on: 'Notifications are on for this phone.', off: 'Notifications are off for this phone.',
                    blocked: 'Notifications are blocked: allow them in the browser settings.',
                    install: 'Add the app to your Home Screen first to get notifications.',
                    unsupported: 'This browser does not support notifications.',
                };
                status.textContent = t(words[state]);
                toggle.hidden = !['on', 'off'].includes(state);
                toggle.textContent = state === 'on' ? t('Turn off notifications') : t('Turn on notifications');
                toggle.className = state === 'on' ? 'dl-btn ghost' : 'dl-btn';
                toggle.onclick = async () => {
                    toggle.disabled = true;
                    try {
                        if (state === 'on') {
                            await app.pushOff();
                            app.toast(t('Notifications turned off.'));
                        } else {
                            await app.pushOn();
                            app.toast(t('Notifications turned on. A test is on its way.'), 'ok');
                        }
                    } catch (e) { app.toast(e.message, 'bad'); }
                    toggle.disabled = false;
                    showPush();
                };
            }
            el.append(phone);
            const steps = installSteps();
            if (steps) {
                el.append(steps);
            }
            showPush();

            const kinds = h('section', { class: 'dl-card' }, [h('h2', {}, t('What you receive'))]);
            const list = h('div', { class: 'dl-switches' });
            function drawKinds(rows) {
                list.replaceChildren(...rows.map((k) => {
                    const input = h('input', { type: 'checkbox', role: 'switch', id: 'kind-' + k.code,
                        checked: k.on, disabled: !k.can_mute });
                    input.addEventListener('change', async () => {
                        try {
                            const data = await app.rpc('kind_set', { code: k.code, on: input.checked });
                            app.session.kinds = data.kinds;
                            app.toast(t('Saved'), 'ok');
                        } catch (e) {
                            input.checked = !input.checked;
                            app.toast(e.message, 'bad');
                        }
                    });
                    return h('label', { class: 'dl-switch', for: 'kind-' + k.code }, [
                        h('span', { class: 'dl-switch-text' }, [h('b', {}, k.name),
                            h('span', {}, k.can_mute ? k.description : (k.description ? k.description + ' · ' : '') + t('Always on'))]),
                        input,
                    ]);
                }));
                if (!rows.length) {
                    list.append(h('p', { class: 'dl-empty' }, t('Nothing to receive yet.')));
                }
            }
            drawKinds(s.kinds);
            kinds.append(list);
            el.append(kinds);

            el.append(h('section', { class: 'dl-card' }, [
                h('h2', {}, t('Account')),
                h('div', { class: 'dl-account' }, [
                    h('img', { src: s.user.avatar, alt: '', class: 'dl-avatar' }),
                    h('div', {}, [h('b', {}, s.user.name), h('span', { class: 'dl-muted' }, s.user.company)]),
                ]),
                h('a', { class: 'dl-btn ghost', href: '/web/session/logout?redirect=/dl/app' }, t('Log out')),
                h('p', { class: 'dl-footer' }, t('App version {0}', s.version)),
            ]));
        },
    });
})();
