// TokoBiru - tema terang / gelap / otomatis (mengikuti perangkat).
// Skrip biasa (bukan module) yang dimuat di <head> sebelum CSS, supaya halaman langsung tampil dalam tema pilihan
// dan tidak berkedip terang dulu. Pilihan disimpan oleh settings.js di localStorage ("tb_settings"), kunci "theme".
// CSS hanya perlu membaca html[data-theme="dark"]; nilai "auto" sudah diterjemahkan di sini menjadi terang atau gelap.
(function () {
  var SETTINGS_KEY = 'tb_settings';
  var BAR = { light: '#0b5fc4', dark: '#0f1d31' };   // warna bilah status browser HP
  var query = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  var pref = 'light';

  function resolve(value) {
    return value === 'dark' || (value === 'auto' && query && query.matches) ? 'dark' : 'light';
  }

  function apply(value) {
    pref = value === 'dark' || value === 'auto' ? value : 'light';
    var theme = resolve(pref);
    document.documentElement.setAttribute('data-theme', theme);
    var scheme = document.querySelector('meta[name="color-scheme"]');
    if (scheme) scheme.setAttribute('content', theme);
    var bar = document.querySelector('meta[name="theme-color"]');
    if (bar) bar.setAttribute('content', BAR[theme]);
  }

  var saved = null;
  try { saved = JSON.parse(localStorage.getItem(SETTINGS_KEY)); } catch (e) { /* mode privat atau data rusak: pakai terang */ }
  apply(saved && saved.theme);

  // Pilihan "Otomatis": ikuti perangkat saat ia berganti terang/gelap
  function onSystemChange() { if (pref === 'auto') apply(pref); }
  if (query) {
    if (query.addEventListener) query.addEventListener('change', onSystemChange);
    else if (query.addListener) query.addListener(onSystemChange);   // Safari lama
  }

  window.tbTheme = { apply: apply };
})();