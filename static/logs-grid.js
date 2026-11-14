// TokoBiru - tabel Log dengan Webix (datatable): urut kolom, pilih banyak, dan filter dari toolbar di atas tabel.
// Filter (kata kunci, kelompok, aksi) hidup di state.logFilter dan dihitung oleh filteredLogs() di core.js, jadi tabel
// Webix dan tabel HTML (layar sempit) memakai aturan yang sama.
//
// Aturan yang sengaja dipilih:
// - Webix hanya dimuat untuk master yang membuka halaman Log di layar lebar. Pelanggan dan HP tidak mengunduhnya.
// - Bila Webix gagal dimuat atau gagal dipasang, tabel HTML lama (dari views.js) tetap dipakai. Tidak ada fungsi yang hilang.
// - Tombol dan kotak centang memakai data-act yang sama seperti sebelumnya, jadi handler di app.js tidak berubah.
//   Klik di dalam sel Webix tetap sampai ke listener `document`.
// - Template sel berupa fungsi (bukan string "#kolom#"), jadi tidak memakai `new Function` dan data pengguna di-escape.

import { $, $$, ROLE_LABEL, actionLabel, detailLabel, escapeHtml, filteredLogs, formatDate, icon, logTone, state } from './core.js';

const VENDOR = '/static/';   // webix.min.js, webix.min.css, dan folder fonts/ diletakkan langsung di static/
const STYLES = [VENDOR + 'webix.min.css', VENDOR + 'webix-theme.css'];   // urutan penting: tema kita menimpa tema Webix
const SCRIPT = VENDOR + 'webix.min.js';
// Lebar minimum agar semua kolom muat tanpa terpotong (jumlah lebar kolom tetap + Detail minimum + padding halaman).
// Di bawah ini tabel HTML lama dipakai (di bawah 700px berubah jadi kartu), jadi Webix tidak dipakai.
const WIDE = matchMedia('(min-width: 1200px)');
const GRID_MIN_HEIGHT = 420;
const ROW_HEIGHT = 56;
const GRID_BOTTOM = 24;   // jarak tabel ke tepi bawah layar
// Tabel mengisi sisa layar di bawah toolbar, jadi halaman tidak punya dua area gulir yang bertumpuk
const gridHeight = host => Math.max(GRID_MIN_HEIGHT, Math.round(innerHeight - (host.getBoundingClientRect().top + scrollY) - GRID_BOTTOM));

let loading = null;   // satu percobaan muat per sesi: bila gagal, tidak diulang
let grid = null;
let applied = new Set();   // id baris yang sudah diberi gaya "picked"
let fallback = null;       // { host, html }: tabel HTML lama, disimpan supaya bisa dipulihkan
let stopFit = null;        // melepas pengamat ukuran milik grid yang sedang aktif
let onSelectionRef = null; // callback terakhir dari views.js, dipakai saat layar berganti lebar
let mountId = 0;           // penanda pemasangan terbaru (pemasangan lama yang telat dibatalkan)

const loadStyle = href => new Promise((resolve, reject) => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = href;
  link.onload = () => resolve();
  link.onerror = () => reject(new Error('CSS gagal dimuat: ' + href));
  document.head.appendChild(link);
});

const loadScript = src => new Promise((resolve, reject) => {
  // Mode strict Webix: tanpa eval / new Function, jadi CSP (script-src 'self') tidak perlu dilonggarkan.
  // Harus diset SEBELUM webix.min.js dimuat. Konsekuensinya, template sel harus berupa fungsi (sudah begitu).
  window.webix_strict = true;
  // Webix (v11.4.0) mendaftarkan event "unload" yang kini dilarang Chrome (muncul sebagai pelanggaran di konsol).
  // Selama skrip dimuat, pendaftaran itu dialihkan ke "pagehide", pengganti resminya. Setelah itu dikembalikan.
  // Hapus peretasan ini bila Webix versi baru sudah tidak memakai "unload".
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

function loadWebix() {
  if (typeof window.webix?.ui === 'function') return Promise.resolve();
  // CSS dan JS diunduh bersamaan; tabel baru dibuat setelah keduanya siap, jadi Webix tidak mengukur sebelum gaya terpasang.
  if (!loading) loading = Promise.all([...STYLES.map(loadStyle), loadScript(SCRIPT)]);
  return loading;
}

const live = () => Boolean(grid && grid.$view && grid.$view.isConnected);

function destroyGrid() {
  if (stopFit) { stopFit(); stopFit = null; }
  if (grid) { try { grid.destructor(); } catch { /* sudah terlepas */ } }
  grid = null;
  applied = new Set();
}

// Bongkar tabel Webix dan kembalikan tabel HTML lama (dipakai saat layar menyempit atau pemasangan gagal)
function restoreTable() {
  const saved = fallback;
  fallback = null;
  destroyGrid();
  if (saved && saved.host.isConnected) {
    saved.host.classList.remove('grid-host');
    saved.host.style.height = '';
    saved.host.innerHTML = saved.html;
  }
}

// id log yang sedang tampil (setelah filter). Sama untuk tabel Webix maupun tabel HTML.
export const visibleLogIds = () => filteredLogs().map(log => log.id);

// Sinkronkan gaya baris terpilih dan kotak centang dengan state.selectedLogs
export function refreshLogGrid() {
  if (!live()) return;

  let dirty = false;
  grid.eachRow(id => {
    const picked = state.selectedLogs.has(id);
    if (picked === applied.has(id)) return;
    if (picked) { grid.addRowCss(id, 'picked', true); applied.add(id); }
    else { grid.removeRowCss(id, 'picked', true); applied.delete(id); }
    dirty = true;
  }, true);
  if (!dirty) return;

  // menggambar ulang sel mengganti elemen, jadi fokus keyboard dikembalikan ke kotak yang sama
  const active = document.activeElement;
  const keep = active && grid.$view.contains(active) ? active.dataset.id : '';
  grid.refresh();
  if (keep) grid.$view.querySelector(`input.tick[data-id="${CSS.escape(keep)}"]`)?.focus();
}

// --- Isi sel (juga dipakai tabel HTML di views.js) ---

export const actorHtml = log => {
  if (log.actor === 'anonim' && log.role === '-') return '<span class="log-anon">Belum login</span>';
  const role = log.role !== '-'
    ? `<span class="tag ${escapeHtml(log.role)}">${escapeHtml(ROLE_LABEL[log.role] || log.role)}</span>`
    : '';
  return `<span class="log-who"><b>${escapeHtml(log.actor)}</b>${role}</span>`;
};

// Warna tag mengikuti jenis aksi (lihat logTone); teksnya tetap menjelaskan, jadi arti tidak bergantung pada warna saja
export const actionTagHtml = log => `<span class="tag ${logTone(log.action)}">${escapeHtml(actionLabel(log.action))}</span>`;

export const logEmptyHtml = () =>
  `<div class="log-empty-box"><b>Tidak ada log yang cocok</b><span>Ubah kata kunci atau lepas filter yang aktif.</span>` +
  `<button type="button" class="btn sm" data-act="log-reset">Hapus semua filter</button></div>`;

const pickCell = log =>
  `<input type="checkbox" class="tick" data-act="log-pick" data-id="${escapeHtml(log.id)}"${state.selectedLogs.has(log.id) ? ' checked' : ''} aria-label="Pilih log ${escapeHtml(actionLabel(log.action))}">`;

const deleteCell = log =>
  `<button type="button" class="btn sm flat log-del" data-act="log-del" data-id="${escapeHtml(log.id)}" aria-label="Hapus log ${escapeHtml(actionLabel(log.action))}" title="Hapus log ini">${icon('trash', 16)}</button>`;

const SELECT_ALL = '<input type="checkbox" class="tick" data-act="log-pick-all" aria-label="Pilih semua log yang tampil">';

const sortHead = text => ({ text, css: 'tb-sortable' });   // kursor tangan di kepala kolom yang bisa diurutkan

// Terapkan state.logFilter ke tabel yang sedang tampil (Webix atau HTML), lalu segarkan toolbar dan hitungan.
// Dipanggil dari app.js setiap kata kunci, kelompok, atau aksi berubah, dan setelah halaman Log digambar.
export function applyLogFilter() {
  const filter = state.logFilter;
  const shown = filteredLogs();
  const ids = new Set(shown.map(log => log.id));

  // centang pada baris yang tersembunyi dilepas supaya "Hapus N log" tidak menghapus yang tidak terlihat
  state.selectedLogs.forEach(id => { if (!ids.has(id)) state.selectedLogs.delete(id); });

  $$('.log-chip').forEach(chip => chip.setAttribute('aria-pressed', String(chip.dataset.group === filter.group)));
  const clear = $('.log-q-clear');
  if (clear) clear.hidden = !filter.q;
  const search = $('[data-log-q]');
  if (search && search.value !== filter.q) search.value = filter.q;
  const select = $('[data-log-action]');
  if (select && select.value !== filter.action) select.value = filter.action;

  if (live()) {
    grid.filter(row => ids.has(row.id));
    fitRows();
    grid.refresh();
    if (shown.length) grid.hideOverlay(); else grid.showOverlay(logEmptyHtml());
  } else {
    $$('#content tr[data-log]').forEach(row => row.classList.toggle('is-hidden', !ids.has(row.dataset.log)));
    const none = $('#log-none');
    if (none) none.hidden = shown.length > 0;
  }
  if (onSelectionRef) onSelectionRef();
}

// Tinggi baris mengikuti Detail yang membungkus; Webix mengukur teksnya saja, jadi ditambah ruang napas atas-bawah
function fitRows() {
  grid.adjustRowHeight('detail', true);
  grid.eachRow(id => {
    const item = grid.getItem(id);
    if (item.$height > ROW_HEIGHT) item.$height += 14;
  }, true);
}

function buildGrid(host, onSelection) {
  // Tinggi tetap pada wadah: tabel menggulir sendiri, kepala tabel tetap terlihat, dan hanya baris yang tampil yang
  // digambar. Webix mengikuti ukuran wadahnya karena tidak diberi height sendiri.
  host.style.height = gridHeight(host) + 'px';

  // Salinan (Webix menambah field internal pada objeknya). Aksi dan detail disimpan sudah dalam bentuk ramah baca,
  // jadi urutan kolom bekerja pada teks yang sama dengan yang dilihat pengguna. Baris gagal/ditolak diberi penanda.
  const rows = state.logs.map(log => ({
    ...log,
    label: actionLabel(log.action),
    detail: detailLabel(log),
    $css: logTone(log.action) === 'err' ? 'log-alert' : ''
  }));

  grid = window.webix.ui({
    container: host,
    view: 'datatable',
    css: 'tb-grid',
    hover: 'tb-hover',
    fixedRowHeight: false,
    rowHeight: ROW_HEIGHT,
    minRowHeight: ROW_HEIGHT,
    headerRowHeight: 46,
    scrollX: false,     // lebar kolom sudah pas di layar lebar; tanpa bilah gulir horizontal yang kosong
    select: false,
    columns: [
      { id: 'pick', header: [{ text: SELECT_ALL, css: 'tb-pickhead' }], width: 56, css: 'tb-edge', template: pickCell },
      { id: 'ts', header: [sortHead('Waktu')], width: 178, sort: 'string', template: log => escapeHtml(formatDate(log.ts)), css: 'tb-muted tb-nowrap' },
      { id: 'actor', header: [sortHead('Pengguna')], width: 220, sort: 'string', template: actorHtml },
      { id: 'label', header: [sortHead('Aksi')], width: 236, sort: 'string', template: actionTagHtml },
      { id: 'detail', header: [sortHead('Detail')], fillspace: true, minWidth: 220, sort: 'string', css: 'tb-wrap', template: log => escapeHtml(log.detail) },
      { id: 'ip', header: [sortHead('IP')], width: 132, sort: 'string', css: 'tb-muted tb-num', template: log => escapeHtml(log.ip) },
      { id: 'del', header: [''], width: 68, css: 'tb-end', template: deleteCell }
    ],
    data: rows
  });

  grid.markSorting('ts', 'desc');   // urutan dari server: terbaru di atas
  fitRows();
  grid.refresh();

  // Webix mengukur wadahnya saat dibuat, padahal tata letak halaman belum selesai: lebar disesuaikan ulang
  // setelah digambar, setelah font selesai dimuat, dan setiap ukuran wadah atau toolbar berubah. Tinggi baris ikut dihitung ulang.
  let lastWidth = 0;
  let lastHeight = 0;
  let timer = 0;
  const fit = () => {
    if (!live()) return;
    const width = host.clientWidth;
    const height = gridHeight(host);
    if (width === lastWidth && height === lastHeight) return;
    lastWidth = width;
    lastHeight = height;
    host.style.height = height + 'px';
    grid.adjust();
    fitRows();
    grid.refresh();
    onSelection();   // kepala tabel digambar ulang: kotak "pilih semua" disegarkan
  };
  const schedule = () => { clearTimeout(timer); timer = setTimeout(fit, 60); };

  requestAnimationFrame(fit);
  if (document.fonts?.ready) document.fonts.ready.then(schedule);
  addEventListener('resize', schedule);
  const observer = 'ResizeObserver' in window ? new ResizeObserver(schedule) : null;
  observer?.observe(host);
  const tools = $('.log-tools');
  if (tools) observer?.observe(tools);
  stopFit = () => {
    clearTimeout(timer);
    removeEventListener('resize', schedule);
    observer?.disconnect();
  };
}

// Dipanggil setiap halaman Log selesai digambar. onSelection = syncLogSelection (views.js).
// Juga dipanggil ulang saat lebar layar melewati batas WIDE, supaya tabel berganti tanpa memuat ulang halaman.
export async function mountLogGrid(onSelection) {
  onSelectionRef = onSelection;
  const id = ++mountId;
  restoreTable();   // grid lama (bila ada) dibongkar; tabel HTML dikembalikan bila hostnya masih di halaman

  const host = $('#log-host');
  if (!host) return console.info('[Log/Webix] dilewati: elemen #log-host tidak ada (views.js belum versi baru?)');
  if (!state.logs.length) return console.info('[Log/Webix] dilewati: belum ada log');
  if (!WIDE.matches) { applyLogFilter(); return console.info('[Log/Webix] dilewati: layar sempit, memakai tabel kartu'); }

  try { await loadWebix(); } catch (err) { console.warn('[Log/Webix] gagal dimuat, memakai tabel lama:', err); applyLogFilter(); return; }   // tabel lama tetap tampil
  // pengguna pindah halaman, layar menyempit, atau ada pemasangan yang lebih baru selama menunggu
  if (id !== mountId || !host.isConnected || !WIDE.matches) return;

  const html = host.innerHTML;
  try {
    host.innerHTML = '';
    host.classList.add('grid-host');
    fallback = { host, html };
    buildGrid(host, onSelection);
    applyLogFilter();
    console.info('[Log/Webix] tabel Webix aktif');
  } catch (err) {
    console.error('Tabel Log (Webix) gagal dipasang, memakai tabel biasa:', err);
    restoreTable();
    applyLogFilter();
  }
}

// Layar diputar atau jendela diubah ukurannya melewati batas lebar: pasang atau bongkar Webix sesuai lebarnya
const onWidthChange = () => {
  if (state.view === 'logs' && onSelectionRef) mountLogGrid(onSelectionRef);
};
if (WIDE.addEventListener) WIDE.addEventListener('change', onWidthChange);
else if (WIDE.addListener) WIDE.addListener(onWidthChange);   // Safari lama