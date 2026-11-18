// TokoBiru - daftarkan service worker supaya aplikasi bisa dipasang di layar utama
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => { /* tidak didukung atau diblokir: aplikasi tetap jalan biasa */ });
  });
}