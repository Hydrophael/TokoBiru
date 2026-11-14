// TokoBiru - service worker: membuat aplikasi bisa dipasang dan membuka kerangka halaman saat sinyal buruk.
// Disajikan dari /sw.js (bukan /static/) supaya cakupannya seluruh situs.
//
// Aturan yang sengaja dipilih:
// - /api/ TIDAK PERNAH disimpan: pesanan, stok, dan data login selalu diambil langsung dari server.
// - File lain (halaman, JS, CSS) memakai "jaringan dulu": bila ada sinyal, versi terbaru yang dipakai,
//   jadi setelah deploy tidak ada campuran file lama dan baru. Salinan tersimpan hanya dipakai saat offline.

const CACHE = 'tokobiru-shell-v2';
const SHELL = ['/', '/static/style.css', '/static/app.js', '/static/core.js', '/static/views.js',
  '/static/ui.js', '/static/photo.js', '/static/layout.js', '/static/webix-core.js', '/static/logs-grid.js', '/static/products-grid.js'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => Promise.all(SHELL.map(url => cache.add(url).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;       // font Google dan lainnya diurus browser
  if (url.pathname.startsWith('/api/')) return;           // data hidup: tidak disimpan
  if (url.pathname === '/sw.js') return;

  event.respondWith(
    fetch(request)
      .then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request).then(hit => hit || (request.mode === 'navigate' ? caches.match('/') : undefined)))
  );
});