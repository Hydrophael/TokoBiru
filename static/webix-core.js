// TokoBiru - dasar bersama tabel Webix: pemuat, pemasangan, ukuran, dan cadangan tabel HTML

import { $, state } from './core.js';

const VENDOR = '/static/';
const STYLES = [VENDOR + 'webix.min.css', VENDOR + 'webix-theme.css'];   // tema kita harus setelah tema Webix
const SCRIPT = VENDOR + 'webix.min.js';

// Di bawah lebar ini tabel HTML lama dipakai
export const WIDE = matchMedia('(min-width: 1200px)');

const GRID_MIN_HEIGHT = 420;
const GRID_BOTTOM = 24;

// Tabel mengisi sisa layar di bawah toolbar, supaya tidak ada dua area gulir bertumpuk
export const gridHeight = host =>
  Math.max(GRID_MIN_HEIGHT, Math.round(innerHeight - (host.getBoundingClientRect().top + scrollY) - GRID_BOTTOM));

export const sortHead = (text, extra = '') => ({ text, css: ('tb-sortable ' + extra).trim() });

let loading = null;   // satu percobaan muat per sesi

const loadStyle = href => new Promise((resolve, reject) => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = href;
  link.onload = () => resolve();
  link.onerror = () => reject(new Error('CSS gagal dimuat: ' + href));
  document.head.appendChild(link);
});

const loadScript = src => new Promise((resolve, reject) => {
  // Mode strict (tanpa eval) harus diset sebelum webix.min.js dimuat, jadi CSP tidak perlu dilonggarkan
  window.webix_strict = true;
  // Webix 11.4.0 memakai event "unload" yang dilarang Chrome: dialihkan ke "pagehide" selama skrip dimuat
  window.addEventListener = function (type, ...rest) {
    return EventTarget.prototype.addEventListener.call(this, type === 'unload' ? 'pagehide' : type, ...rest);
  };
  const restoreListener = () => { delete window.addEventListener; };
  const script = document.createElement('script');
  script.src = src;
  script.onload = () => {
    restoreListener();
    if (typeof window.webix?.ui === 'function') resolve(); else reject(new Error('Webix termuat tapi tidak siap'));
  };
  script.onerror = () => { restoreListener(); reject(new Error('Webix gagal dimuat')); };
  document.head.appendChild(script);
});

export function loadWebix() {
  if (typeof window.webix?.ui === 'function') return Promise.resolve();
  if (!loading) loading = Promise.all([...STYLES.map(loadStyle), loadScript(SCRIPT)]);
  return loading;
}

const controllers = new Set();

// Satu pengendali per halaman bertabel. settle() dipanggil baik saat Webix aktif maupun saat tabel HTML dipakai.
// maxHeight (opsional): tinggi isi tabel. Bila isinya lebih pendek dari sisa layar, tabel tidak dipaksa setinggi layar
// (tidak ada ruang kosong dan tidak ada jalur gulir yang tidak perlu). refit() dipanggil setelah jumlah baris berubah.
export function createGridController({ name, view, hostSelector, toolsSelector, hasData, create, settle, onFit, onDestroy, maxHeight }) {
  let grid = null;
  let fallback = null;   // { host, html }: tabel HTML lama
  let stopFit = null;
  let mountId = 0;       // pemasangan lama yang telat dibatalkan
  let refit = () => {};

  const targetHeight = host => {
    const room = gridHeight(host);
    return maxHeight ? Math.min(room, Math.max(0, maxHeight())) : room;
  };

  const live = () => Boolean(grid && grid.$view && grid.$view.isConnected);
  const tag = `[${name}/Webix]`;

  function destroy() {
    if (stopFit) { stopFit(); stopFit = null; }
    refit = () => {};
    if (grid) { try { grid.destructor(); } catch { /* sudah terlepas */ } }
    grid = null;
    if (onDestroy) onDestroy();
  }

  function restore() {
    const saved = fallback;
    fallback = null;
    destroy();
    if (saved && saved.host.isConnected) {
      saved.host.classList.remove('grid-host');
      saved.host.style.height = '';
      saved.host.innerHTML = saved.html;
    }
  }

  // Webix mengukur wadah sebelum tata letak selesai, jadi ukuran disesuaikan ulang saat font dan wadah berubah
  function startFit(host) {
    let lastWidth = 0;
    let lastHeight = 0;
    let timer = 0;
    const fit = () => {
      if (!live()) { destroy(); return; }
      const width = host.clientWidth;
      const height = targetHeight(host);
      if (width === lastWidth && height === lastHeight) return;
      lastWidth = width;
      lastHeight = height;
      host.style.height = height + 'px';
      grid.adjust();
      if (onFit) onFit(grid);
    };
    const schedule = () => { clearTimeout(timer); timer = setTimeout(fit, 60); };
    refit = () => { lastWidth = 0; lastHeight = 0; fit(); };

    requestAnimationFrame(fit);
    if (document.fonts?.ready) document.fonts.ready.then(schedule);
    addEventListener('resize', schedule);
    const observer = 'ResizeObserver' in window ? new ResizeObserver(schedule) : null;
    observer?.observe(host);
    const tools = toolsSelector ? $(toolsSelector) : null;
    if (tools) observer?.observe(tools);
    stopFit = () => {
      clearTimeout(timer);
      removeEventListener('resize', schedule);
      observer?.disconnect();
    };
  }

  async function mount() {
    const id = ++mountId;
    for (const other of controllers) if (other !== controller) other.restore();
    restore();

    const host = $(hostSelector);
    if (!host) return console.info(`${tag} dilewati: elemen ${hostSelector} tidak ada (views.js belum versi baru?)`);
    if (!hasData()) return console.info(`${tag} dilewati: belum ada data`);
    if (!WIDE.matches) { settle(); return console.info(`${tag} dilewati: layar sempit, memakai tabel kartu`); }

    try { await loadWebix(); } catch (err) { console.warn(`${tag} gagal dimuat, memakai tabel lama:`, err); settle(); return; }
    if (id !== mountId || !host.isConnected || !WIDE.matches) return;

    const html = host.innerHTML;
    try {
      host.innerHTML = '';
      host.classList.add('grid-host');
      fallback = { host, html };
      host.style.height = targetHeight(host) + 'px';
      grid = create(host);
      startFit(host);
      settle();
      console.info(`${tag} tabel Webix aktif`);
    } catch (err) {
      console.error(`Tabel ${name} (Webix) gagal dipasang, memakai tabel biasa:`, err);
      restore();
      settle();
    }
  }

  const controller = { mount, restore, destroy, live, refit: () => refit(), get grid() { return grid; } };
  controllers.add(controller);

  const onWidthChange = () => { if (state.view === view) mount(); };
  if (WIDE.addEventListener) WIDE.addEventListener('change', onWidthChange);
  else if (WIDE.addListener) WIDE.addListener(onWidthChange);   // Safari lama

  return controller;
}