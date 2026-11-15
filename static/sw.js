// TokoBiru - service worker: membuat aplikasi bisa dipasang dan membuka kerangka halaman saat sinyal buruk.
// Disajikan dari /sw.js (bukan /static/) supaya cakupannya seluruh situs.
//
// Aturan yang sengaja dipilih:
// - /api/ TIDAK PERNAH disimpan: pesanan, stok, dan data login selalu diambil langsung dari server.
// - File lain (halaman, JS, CSS) memakai "jaringan dulu": bila ada sinyal, versi terbaru yang dipakai,
//   jadi setelah deploy tidak ada campuran file lama dan baru. Salinan tersimpan hanya dipakai saat offline.

const CACHE = 'tokobiru-shell-v7';
const NETWORK_TIMEOUT_MS = 4000;   // lewat batas ini dan ada salinan tersimpan, pakai salinan
const SHELL = ['/', '/static/style.css', '/static/app.js', '/static/core.js', '/static/views.js',
  '/static/ui.js', '/static/photo.js', '/static/settings.js', '/static/layout.js', '/static/webix-core.js', '/static/logs-grid.js', '/static/products-grid.js', '/static/theme.js', '/static/qr.js', '/static/pwa.js',
  '/static/icons/pay/dana.png', '/static/icons/pay/shopeepay.png', '/static/icons/pay/ovo.png'];

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
  if (url.pathname.startsWith('/pay/')) return;           // halaman bayar QRIS: jangan disimpan
  if (url.pathname === '/sw.js') return;

  event.respondWith((async () => {
    const network = fetch(request).then(response => {
      // Hanya respons utuh (200) yang disimpan; waitUntil menjaga penyimpanan tidak terputus
      if (response.status === 200) {
        const copy = response.clone();
        event.waitUntil(caches.open(CACHE).then(cache => cache.put(request, copy)).catch(() => {}));
      }
      return response;
    });
    network.catch(() => {});
    try {
      return await Promise.race([
        network,
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), NETWORK_TIMEOUT_MS))
      ]);
    } catch {
      const hit = await caches.match(request);
      if (hit) return hit;
      if (request.mode === 'navigate') {
        const shell = await caches.match('/');
        if (shell) return shell;
      }
      return network;   // tidak ada salinan: tetap tunggu jaringan
    }
  })());
});