// Service Worker — Aguacol PWA
// Versión mínima: cache de assets estáticos para instalabilidad.
// No intercepta API calls para evitar datos obsoletos.

const CACHE_NAME = 'aguacol-v17-flush';
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
  self.skipWaiting();
});

// Activate: purge all old caches immediately
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Fetch: Network-first for ALL requests to ensure fresh JS/CSS/API updates
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Never cache API calls or auth endpoints
  if (url.pathname.startsWith('/api/') || url.pathname.includes('login')) {
    return;
  }

  // Network-First for JS and CSS files to guarantee fresh code
  if (url.pathname.endsWith('.js') || url.pathname.endsWith('.css') || event.request.mode === 'navigate' || url.pathname === '/' || url.pathname === '/index.html') {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.ok && event.request.method === 'GET') {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, clone);
            });
          }
          return response;
        })
        .catch(() => {
          return caches.match(event.request);
        })
    );
    return;
  }

  // Cache-first fallback only for static images/fonts
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request);
    })
  );
});
