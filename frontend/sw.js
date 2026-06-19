// Service Worker — Aguacol PWA
// Versión mínima: cache de assets estáticos para instalabilidad.
// No intercepta API calls para evitar datos obsoletos.

const CACHE_NAME = 'aguacol-v14';
const STATIC_ASSETS = [
  '/',
  '/static/css/bootstrap.min.css',
  '/static/css/bootstrap-icons.css',
  '/static/css/styles.css',
  '/static/css/responsive.css',
  '/static/assets/img/logo_v5.png',
  '/static/assets/img/icons/icon-192.png',
  '/static/assets/img/icons/icon-512.png'
];

// Install: pre-cache shell assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Pre-caching shell assets');
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Fetch: network-first for API, cache-first for static assets
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Never cache API calls or auth endpoints
  if (url.pathname.startsWith('/api/') || url.pathname.includes('login')) {
    return; // Let browser handle normally
  }

  // For static assets: try cache first, fall back to network
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        // Cache successful GET requests for static resources
        if (response.ok && event.request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, clone);
          });
        }
        return response;
      });
    })
  );
});
