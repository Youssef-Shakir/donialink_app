/* DoniaLink App service worker: notifications, and the app opening without internet.
   Served at {{APP}}/sw.js (scope {{APP}}/). The API and files always go to the server. */
const VERSION = 'dl-app-{{VERSION}}';
const SHELL = ['{{APP}}', '{{IMG}}/icon-192.png', '{{IMG}}/favicon-32.png'];

self.addEventListener('install', (event) => {
    event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(SHELL)).catch(() => {}).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
    event.waitUntil(caches.keys()
        .then((keys) => Promise.all(keys.filter((k) => k.startsWith('dl-app-') && k !== VERSION).map((k) => caches.delete(k))))
        .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET') {
        return;
    }
    const url = new URL(request.url);
    if (url.origin !== self.location.origin) {
        return;
    }
    if (request.mode === 'navigate' && (url.pathname === '{{APP}}' || url.pathname === '{{APP}}/')) {
        // network first, so a new version shows at once; the saved page when there is no internet
        event.respondWith(fetch(request).then((response) => {
            if (response.ok && !response.redirected) {
                const copy = response.clone();
                caches.open(VERSION).then((cache) => cache.put('{{APP}}', copy));
            }
            return response;
        }).catch(() => caches.match('{{APP}}')));
        return;
    }
    if (url.pathname.startsWith('/web/assets/') || url.pathname.startsWith('/donialink_app/static/')) {
        // the app's styles and scripts (their address changes with each version): saved after the first use
        event.respondWith(caches.match(request).then((hit) => hit || fetch(request).then((response) => {
            if (response.ok) {
                const copy = response.clone();
                caches.open(VERSION).then((cache) => cache.put(request, copy));
            }
            return response;
        })));
    }
});

// Web Push sent by Odoo's mail.push queue: {title, options: {body, icon, tag, data: {url}}}
self.addEventListener('push', (event) => {
    let data = {};
    try {
        data = event.data ? event.data.json() : {};
    } catch (e) {
        data = { title: event.data ? event.data.text() : '' };
    }
    const options = Object.assign({ icon: '{{IMG}}/icon-192.png', badge: '{{IMG}}/favicon-32.png', dir: 'auto' },
        data.options || {});
    if (!options.tag) {
        delete options.tag;
    }
    options.data = Object.assign({}, options.data || {});
    event.waitUntil(self.registration.showNotification(data.title || 'DoniaLink', options).then(() => {
        if (self.navigator && self.navigator.setAppBadge) {
            return self.registration.getNotifications().then((list) => self.navigator.setAppBadge(list.length)).catch(() => {});
        }
    }));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const data = event.notification.data || {};
    let url = data.url;
    if (!url && data.model && data.res_id) {
        url = '/odoo/' + data.model + '/' + data.res_id;  // a Discuss message pushed by Odoo itself
    }
    const target = new URL(url || '{{APP}}', self.location.origin);
    if (target.origin !== self.location.origin) {
        return;
    }
    const inApp = target.pathname === '{{APP}}' || target.pathname.startsWith('{{APP}}/');
    event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
        const open = windows.find((w) => new URL(w.url).pathname.startsWith('{{APP}}'));
        if (open && inApp) {
            open.postMessage({ type: 'open', url: target.href });
            return open.focus();
        }
        return self.clients.openWindow(target.href);
    }));
});
