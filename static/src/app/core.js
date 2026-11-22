/** @odoo-module ignore **/
/* DoniaLink App core: the app shell other modules build on.
 *
 * A module adds a screen in the bundle donialink_app.assets_app:
 *
 *     DLApp.screen('cash', {
 *         title: (t) => t('Cash box'),          // optional, the top bar title
 *         async render(el, params, app) { ... }  // draws into el; params from the address (#cash/12 -> ['12'])
 *     });
 *     DLApp.text({ar: {'Cash box': 'الصندوق'}}); // its words in Arabic
 *
 * and a donialink.app.screen record with the same key, which puts its tile on the home page.
 * Helpers: app.rpc(action, params) for /dl/app/api, app.call(route, params) for its own JSON routes,
 * app.go('#key'), app.toast(text), app.t(text), app.h(tag, attrs, children), app.icon(name).
 */
(function () {
    'use strict';

    const WORDS = { ar: {}, en: {} };
    const screens = {};
    const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent)
        || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;

    const ICONS = {
        bell: 'M12 3a6 6 0 0 0-6 6v3.6L4.3 15.4A1 1 0 0 0 5.2 17h13.6a1 1 0 0 0 .9-1.6L18 12.6V9a6 6 0 0 0-6-6Zm-2.5 15a2.5 2.5 0 0 0 5 0',
        report: 'M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm7 0v5h5M9 13h6M9 17h6M9 9h2',
        cash: 'M3 7h18v10H3zM12 12m-2.5 0a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0M6 10v4M18 10v4',
        receipt: 'M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3',
        chart: 'M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6',
        alert: 'M12 3 2 20h20L12 3Zm0 7v4m0 3v.5',
        box: 'M3 8l9-5 9 5v8l-9 5-9-5V8Zm0 0 9 5 9-5M12 13v8',
        card: 'M3 6h18v12H3zM3 10h18M7 15h4',
        info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 8v5m0-8.5V8',
        odoo: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
        settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.3 7.3 0 0 0-2-1.2L14.5 3h-5l-.4 2.6a7.3 7.3 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7.3 7.3 0 0 0 2 1.2l.4 2.6h5l.4-2.6a7.3 7.3 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2Z',
        back: 'M15 5l-7 7 7 7',
        file: 'M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm7 0v5h5',
        clip: 'M16 7l-7.5 7.5a2.1 2.1 0 0 0 3 3L19 10a4 4 0 0 0-5.7-5.7L5.8 11.8a6 6 0 0 0 8.5 8.5L20 14.5',
        chat: 'M4 5h16v11H8l-4 4zM8 9h8M8 12h5',
        check: 'M5 12l5 5 9-10',
        home: 'M4 11l8-7 8 7v9h-5v-6H9v6H4z',
        camera: 'M4 7h3l2-3h6l2 3h3v12H4zM12 13m-3.5 0a3.5 3.5 0 1 0 7 0a3.5 3.5 0 1 0-7 0',
        install: 'M12 3v12m-5-5 5 5 5-5M5 21h14',
    };

    const app = {
        session: null,
        lang: (document.documentElement.lang || 'en').slice(0, 2),
        isIOS, standalone,
        el: null,
        screens,

        // -------------------------------------------------- words
        t(text, ...args) {
            const table = WORDS[app.lang] || {};
            let out = Object.prototype.hasOwnProperty.call(table, text) ? table[text] : text;
            if (typeof out === 'function') {
                return out(...args);
            }
            args.forEach((a, i) => { out = out.replace('{' + i + '}', a); });
            return out;
        },

        // -------------------------------------------------- server
        async call(route, params) {
            if (!navigator.onLine) {
                throw new Error(app.t('No internet connection.'));
            }
            const response = await fetch(route, {
                method: 'POST', credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: params || {} }),
            });
            if (response.status === 401 || response.status === 403 || response.redirected) {
                app.login();
                throw new Error(app.t('Please log in again.'));
            }
            const data = await response.json();
            if (data.error) {
                const name = (data.error.data && data.error.data.name) || '';
                if (data.error.code === 100 || name.includes('SessionExpired')) {
                    app.login();
                    throw new Error(app.t('Please log in again.'));
                }
                throw new Error((data.error.data && data.error.data.message) || app.t('Server error. Try again.'));
            }
            const result = data.result;
            if (result && result.error) {
                const err = new Error(result.message || app.t('Server error. Try again.'));
                err.code = result.error;
                throw err;
            }
            return result;
        },
        rpc(action, params) {
            return app.call('/dl/app/api/' + action, params);
        },
        login() {
            window.location.href = '/web/login?redirect=' + encodeURIComponent('/dl/app' + window.location.hash);
        },

        // -------------------------------------------------- drawing
        h(tag, attrs, children) {
            const node = document.createElement(tag);
            for (const [key, value] of Object.entries(attrs || {})) {
                if (value === null || value === undefined || value === false) {
                    continue;
                }
                if (key === 'class') {
                    node.className = value;
                } else if (key === 'html') {
                    node.innerHTML = value;
                } else if (key === 'text') {
                    node.textContent = value;
                } else if (key.startsWith('on') && typeof value === 'function') {
                    node.addEventListener(key.slice(2), value);
                } else {
                    node.setAttribute(key, value === true ? '' : value);
                }
            }
            for (const child of [].concat(children === undefined ? [] : children)) {
                if (child === null || child === undefined || child === false) {
                    continue;
                }
                node.append(child instanceof Node ? child : document.createTextNode(String(child)));
            }
            return node;
        },
        icon(name, cls) {
            const ns = 'http://www.w3.org/2000/svg';
            const svg = document.createElementNS(ns, 'svg');
            svg.setAttribute('viewBox', '0 0 24 24');
            svg.setAttribute('aria-hidden', 'true');
            svg.setAttribute('class', 'dl-icon ' + (cls || ''));
            const path = document.createElementNS(ns, 'path');
            path.setAttribute('d', ICONS[name] || ICONS.box);
            svg.append(path);
            return svg;
        },
        toast(text, kind) {
            const node = document.getElementById('dl-toast');
            node.textContent = text;
            node.className = 'dl-toast ' + (kind || '');
            node.hidden = false;
            clearTimeout(app._toastTimer);
            app._toastTimer = setTimeout(() => { node.hidden = true; }, 3500);
        },
        date(value) {
            if (!value) {
                return '';
            }
            const d = new Date(value.replace(' ', 'T') + 'Z');
            const today = new Date();
            const sameDay = d.toDateString() === today.toDateString();
            const locale = app.lang === 'ar' ? 'ar-IQ' : 'en-GB';
            return sameDay
                ? d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })
                : d.toLocaleDateString(locale, { day: 'numeric', month: 'short' });
        },
        topbar(title, back) {
            const bar = app.h('header', { class: 'dl-topbar' }, [
                back ? app.h('button', { class: 'dl-icon-btn', 'aria-label': app.t('Back'),
                    onclick: () => (history.length > 1 ? history.back() : app.go('')) }, app.icon('back', 'dl-flip')) : null,
                app.h('h1', {}, title),
            ]);
            return bar;
        },

        // -------------------------------------------------- screens and navigation
        screen(key, definition) {
            screens[key] = definition;
        },
        text(tables) {
            for (const [lang, words] of Object.entries(tables || {})) {
                WORDS[lang] = Object.assign(WORDS[lang] || {}, words);
            }
        },
        go(hash) {
            const target = hash && !hash.startsWith('#') ? '#' + hash : (hash || '');
            if (window.location.hash === target || (!target && !window.location.hash)) {
                app.route();
            } else if (!target) {
                history.pushState(null, '', window.location.pathname);
                app.route();
            } else {
                window.location.hash = target;
            }
        },
        open(url) {
            // a message's or a tile's link: an app screen (#key), this Odoo (/odoo…) or another site
            if (!url) {
                return;
            }
            if (url.startsWith('#')) {
                app.go(url);
            } else if (/^https?:\/\//.test(url) && !url.startsWith(window.location.origin)) {
                window.open(url, '_blank', 'noopener');
            } else {
                window.location.href = url;
            }
        },
        async route() {
            const hash = decodeURIComponent(window.location.hash.slice(1));
            let key = hash.split('/')[0] || 'home';
            let params = hash.split('/').slice(1);
            const msg = /^msg-(\d+)$/.exec(key);
            if (msg) {
                key = 'message';
                params = [msg[1]];
            }
            const record = /^([a-z_]+)-(\d+)$/.exec(key);   // #task-12: screen "task" with the id
            if (!msg && record && screens[record[1]]) {
                key = record[1];
                params = [record[2]].concat(params);
            }
            const definition = screens[key];
            const tile = (app.session.screens || []).find((s) => s.key === key);
            if (!definition) {
                if (tile && tile.url) {
                    app.open(tile.url);
                    return;
                }
                return app.go('');
            }
            if (key !== 'home' && key !== 'message' && !tile && !definition.always) {
                return app.go('');  // a screen this person may not open
            }
            app.current = key;
            const el = app.h('div', { class: 'dl-screen dl-screen-' + key });
            app.el.replaceChildren(el);
            window.scrollTo(0, 0);
            try {
                await definition.render(el, params, app);
            } catch (e) {
                el.append(app.h('div', { class: 'dl-error' }, e.message || String(e)));
            }
        },

        // -------------------------------------------------- badges
        setUnread(count) {
            app.session.unread = count;
            document.querySelectorAll('[data-unread]').forEach((node) => {
                node.textContent = count > 99 ? '99+' : String(count);
                node.hidden = !count;
            });
            if ('setAppBadge' in navigator) {
                (count ? navigator.setAppBadge(count) : navigator.clearAppBadge()).catch(() => {});
            }
        },
        async refreshBadges() {
            try {
                const data = await app.rpc('badges');
                app.setUnread(data.unread);
                for (const tile of app.session.screens) {
                    tile.badge = data.badges[tile.key] || 0;
                }
                document.querySelectorAll('[data-badge]').forEach((node) => {
                    const value = data.badges[node.dataset.badge] || 0;
                    node.textContent = value > 99 ? '99+' : String(value);
                    node.hidden = !value;
                });
            } catch (e) { /* offline: try again later */ }
        },

        // -------------------------------------------------- push notifications
        pushSupported() {
            return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
        },
        swReady(ms) {
            // the service worker of the app; never waits forever (no https, blocked, still installing)
            return Promise.race([navigator.serviceWorker.ready, new Promise((resolve, reject) => setTimeout(
                () => reject(new Error(app.t('Notifications are not ready: reload the app (it needs a secure https address).'))),
                ms || 6000))]);
        },
        async pushState() {
            // 'on' | 'off' | 'blocked' | 'install' (iPhone: install first) | 'unsupported'
            if (isIOS && !standalone) {
                return 'install';
            }
            if (!app.pushSupported()) {
                return 'unsupported';
            }
            if (Notification.permission === 'denied') {
                return 'blocked';
            }
            let reg;
            try {
                reg = await app.swReady(4000);
            } catch (e) {
                return 'notready';
            }
            const sub = await reg.pushManager.getSubscription();
            return sub && Notification.permission === 'granted' ? 'on' : 'off';
        },
        async pushOn() {
            if (await Notification.requestPermission() !== 'granted') {
                throw new Error(app.t('Notifications are blocked: allow them in the browser settings.'));
            }
            const reg = await app.swReady();
            const key = app.session.push_key;
            let sub = await reg.pushManager.getSubscription();
            if (sub && sub.options && sub.options.applicationServerKey) {
                const current = btoa(String.fromCharCode(...new Uint8Array(sub.options.applicationServerKey)))
                    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
                if (current !== key) {
                    await sub.unsubscribe();
                    sub = null;
                }
            }
            if (!sub) {
                const pad = '='.repeat((4 - key.length % 4) % 4);
                const raw = atob((key + pad).replace(/-/g, '+').replace(/_/g, '/'));
                sub = await reg.pushManager.subscribe({
                    userVisibleOnly: true, applicationServerKey: Uint8Array.from(raw, (c) => c.charCodeAt(0)),
                });
            }
            await app.rpc('push_subscribe', { subscription: sub.toJSON(), vapid_key: key });
            await app.rpc('push_test');
        },
        async pushOff() {
            const reg = await app.swReady();
            const sub = await reg.pushManager.getSubscription();
            if (sub) {
                await app.rpc('push_unsubscribe', { endpoint: sub.endpoint });
                await sub.unsubscribe();
            }
        },

        // -------------------------------------------------- install
        installPrompt: null,
        async install() {
            if (app.installPrompt) {
                app.installPrompt.prompt();
                await app.installPrompt.userChoice;
                app.installPrompt = null;
                return true;
            }
            return false;
        },

        // -------------------------------------------------- start
        async start() {
            app.el = document.getElementById('dl-app');
            if ('serviceWorker' in navigator) {
                navigator.serviceWorker.register('/dl/app/sw.js', { scope: '/dl/app' }).catch(() => {});
                navigator.serviceWorker.addEventListener('message', (event) => {
                    if (event.data && event.data.type === 'open' && event.data.url) {
                        const url = new URL(event.data.url, window.location.origin);
                        app.go(url.hash || '');
                        app.refreshBadges();
                    }
                });
            }
            window.addEventListener('beforeinstallprompt', (event) => {
                event.preventDefault();
                app.installPrompt = event;
                document.querySelectorAll('[data-install]').forEach((n) => { n.hidden = false; });
            });
            const offline = document.getElementById('dl-offline');
            const net = () => {
                offline.hidden = navigator.onLine;
                offline.textContent = app.t('No internet connection.');
            };
            window.addEventListener('online', () => { net(); app.refreshBadges(); });
            window.addEventListener('offline', net);
            net();
            try {
                app.session = await app.rpc('session');
            } catch (e) {
                app.el.replaceChildren(app.h('div', { class: 'dl-error' }, [e.message,
                    app.h('button', { class: 'dl-btn', onclick: () => window.location.reload() }, app.t('Try again'))]));
                return;
            }
            app.lang = (app.session.user.lang || app.lang).slice(0, 2);
            window.addEventListener('hashchange', () => app.route());
            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'visible') {
                    app.refreshBadges();
                }
            });
            setInterval(() => { if (document.visibilityState === 'visible') { app.refreshBadges(); } }, 60000);
            await app.route();
            app.setUnread(app.session.unread);
        },
    };

    window.DLApp = app;
    document.addEventListener('DOMContentLoaded', () => app.start());
})();
