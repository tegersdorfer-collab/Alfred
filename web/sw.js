// Alfred Service Worker – network-first, kein Caching.
// Sorgt dafür, dass die installierte Homescreen-App immer die neueste Version lädt.
self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (e) => {
  e.respondWith(fetch(e.request).catch(() => new Response('', {status: 504})));
});

// Push-Benachrichtigungen (PWA-Alternative zu Telegram)
self.addEventListener('push', (e) => {
  let data = {title: 'Alfred', body: '', url: '/'};
  try { data = Object.assign(data, e.data.json()); } catch (err) {}
  const ICON = 'https://em-content.zobj.net/source/apple/391/robot_1f916.png';
  e.waitUntil(self.registration.showNotification(data.title, {
    body: data.body,
    icon: ICON,
    badge: ICON,
    data: {url: data.url || '/'},
  }));
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(
    self.clients.matchAll({type: 'window'}).then((clients) => {
      for (const c of clients) { if (c.url.includes(self.location.origin)) return c.focus(); }
      return self.clients.openWindow(url);
    })
  );
});
