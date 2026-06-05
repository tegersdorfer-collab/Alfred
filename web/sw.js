// Jarvis Service Worker – network-first, kein Caching.
// Sorgt dafür, dass die installierte Homescreen-App immer die neueste Version lädt.
self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (e) => {
  e.respondWith(fetch(e.request).catch(() => new Response('', {status: 504})));
});
