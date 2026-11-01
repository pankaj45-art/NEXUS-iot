/* NEXUS IoT Service Worker — PWA & Offline Support */
const CACHE_NAME = 'nexus-iot-shell-v5';
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/app.css?v=13',
  '/app.js?v=13',
  '/workstation.js?v=15',
  '/studio.js?v=14',
  '/digital-twin-3d.js?v=14',
  '/ai-connection.js?v=10',
  '/api-response.js?v=15',
  '/neural-wallpaper.js?v=15',
  '/favicon.svg',
  '/icon-192.png',
  '/icon-512.png',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // API calls: Network first, never cache POST/PUT/DELETE
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(req).catch(() => {
        return new Response(
          JSON.stringify({
            error: {
              code: 'offline',
              message: 'You are currently offline. Local cache is active.'
            }
          }),
          { status: 503, headers: { 'Content-Type': 'application/json' } }
        );
      })
    );
    return;
  }

  // HTML / Navigation requests: Network first, fall back to cache
  if (req.mode === 'navigate' || req.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(req).then((networkRes) => {
        if (networkRes && networkRes.status === 200) {
          const resClone = networkRes.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, resClone));
        }
        return networkRes;
      }).catch(() => caches.match('/index.html'))
    );
    return;
  }

  // Static assets: Network first, fall back to cache
  event.respondWith(
    fetch(req).then((networkRes) => {
      if (networkRes && networkRes.status === 200) {
        const resClone = networkRes.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, resClone));
      }
      return networkRes;
    }).catch(() => caches.match(req))
  );
});
