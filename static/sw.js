// TokoBiru - service worker: membuat aplikasi bisa dipasang dan membuka kerangka halaman saat sinyal buruk.
// Disajikan dari /sw.js (bukan /static/) supaya cakupannya seluruh situs.
//
// Aturan yang sengaja dipilih:
// - /api/ TIDAK PERNAH disimpan: pesanan, stok, dan data login selalu diambil langsung dari server.
// - File lain (halaman, JS, CSS) memakai "jaringan dulu": bila ada sinyal, versi terbaru yang dipakai,
//   jadi setelah deploy tidak ada campuran file lama dan baru. Salinan tersimpan hanya dipakai saat offline.

const CACHE = 'tokobiru-shell-v15';
const NETWORK_TIMEOUT_MS = 4000;   // lewat batas ini dan ada salinan tersimpan, pakai salinan
const SHELL = ['/', '/static/css/style.css', '/static/css/base/tokens.css', '/static/css/base/reset.css', '/static/css/base/animations.css', '/static/css/layout/header.css', '/static/css/layout/container.css', '/static/css/components/buttons.css', '/static/css/components/forms.css', '/static/css/components/badges.css', '/static/css/components/overlays.css', '/static/css/components/popovers.css', '/static/css/components/tables.css', '/static/css/pages/auth.css', '/static/css/pages/catalog.css', '/static/css/pages/orders.css', '/static/css/pages/admin.css', '/static/css/pages/profile.css', '/static/css/themes/dark.css', '/static/css/themes/webix.css',
  '/static/js/api/client.js', '/static/js/components/cart.js', '/static/js/components/layout.js', '/static/js/components/logs-grid.js', '/static/js/components/notify.js', '/static/js/components/order-payment.js', '/static/js/components/photo.js', '/static/js/components/products-grid.js', '/static/js/components/push.js', '/static/js/components/reset-wizard.js', '/static/js/components/shell.js', '/static/js/components/theme.js', '/static/js/components/ui.js', '/static/js/components/webix-core.js', '/static/js/core/app.js', '/static/js/core/constants.js', '/static/js/core/core.js', '/static/js/core/events.js', '/static/js/core/format.js', '/static/js/core/pwa.js', '/static/js/core/router.js', '/static/js/core/state.js', '/static/js/pages/admin.js', '/static/js/pages/auth.js', '/static/js/pages/checkout.js', '/static/js/pages/dashboard.js', '/static/js/pages/orders.js', '/static/js/pages/profile.js', '/static/js/pages/shop.js', '/static/vendor/qr.js',
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

// --- Notifikasi push: server mengirim kabar pesanan, di sini ditampilkan walau aplikasi tertutup ---
self.addEventListener('push', event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data ? event.data.text() : '' }; }
  const options = {
    body: data.body || '',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/badge-96.png',   // ikon kecil monokrom di bilah status Android
    data: { url: typeof data.url === 'string' && data.url.startsWith('/') && !data.url.startsWith('//') ? data.url : '/' }
  };
  // Tag sama = menggantikan notifikasi lama untuk pesanan yang sama, bukan menumpuk
  if (data.tag) { options.tag = data.tag; options.renotify = true; }
  event.waitUntil((async () => {
    // Aplikasi yang sedang terbuka diberi tahu supaya lonceng di dalamnya langsung diperbarui
    const windows = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    windows.forEach(client => client.postMessage({ type: 'push-received' }));
    await self.registration.showNotification(data.title || 'TokoBiru', options);
  })());
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || '/', self.location.origin);
  const view = target.searchParams.get('buka');
  event.waitUntil((async () => {
    const windows = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    const sameOrigin = windows.filter(client => new URL(client.url).origin === self.location.origin);
    const open = sameOrigin.find(client => client.visibilityState === 'visible') || sameOrigin[0];
    if (open) {
      try { await open.focus(); } catch { /* tidak bisa difokuskan: pesan tetap dikirim */ }
      if (view) open.postMessage({ type: 'open-view', view });
      return;
    }
    await clients.openWindow(target.href);
  })());
});