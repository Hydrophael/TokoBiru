// TokoBiru - pengaturan di perangkat ini: tema, ukuran teks, animasi, getar, tampilan katalog, dan pasang aplikasi.
// Semua tersimpan di localStorage perangkat (bukan di akun), jadi tidak perlu endpoint server.

import { $, $$, STORAGE_KEYS, isCustomer, state, storage } from './core.js';
import { openModal, toast } from './ui.js';

const DEFAULTS = { text: 'md', calm: false, haptic: true, theme: 'light' };

// Tema: terang, gelap, atau mengikuti perangkat. theme.js (dimuat di <head>) yang memasangnya ke <html>
const THEMES = [['light', 'Terang'], ['dark', 'Gelap'], ['auto', 'Otomatis']];

// Admin memakai tabel dengan tinggi baris tetap, jadi pilihan terbesar hanya untuk pelanggan
const TEXT_SIZES = [['md', 'Normal'], ['lg', 'Besar'], ['xl', 'Terbesar']];
const sizesFor = () => (isCustomer() ? TEXT_SIZES : TEXT_SIZES.slice(0, 2));

export const settings = { ...DEFAULTS };

export function loadSettings() {
  const saved = storage.get(STORAGE_KEYS.settings) || {};
  settings.text = TEXT_SIZES.some(([id]) => id === saved.text) ? saved.text : DEFAULTS.text;
  settings.calm = saved.calm === true;
  settings.haptic = saved.haptic !== false;
  settings.theme = THEMES.some(([id]) => id === saved.theme) ? saved.theme : DEFAULTS.theme;
}

// Dipasang sebagai atribut/kelas di <html>; CSS dan ui.js membacanya dari sana
export function applySettings() {
  const root = document.documentElement;
  const allowed = state.user ? sizesFor().some(([id]) => id === settings.text) : true;
  root.dataset.text = allowed ? settings.text : 'lg';
  root.classList.toggle('calm', settings.calm);
  root.classList.toggle('no-haptic', !settings.haptic);
  if (window.tbTheme) window.tbTheme.apply(settings.theme);
}

const save = () => storage.set(STORAGE_KEYS.settings, settings);

// --- Pasang aplikasi (PWA) ---
let installEvent = null;

export function syncInstall() {
  $$('[data-act="install-app"]').forEach(button => { button.hidden = !installEvent; });
}

addEventListener('beforeinstallprompt', event => {
  // Tanpa preventDefault(): Chrome tidak mencatat peringatan "Banner not shown" di Console.
  // Event disimpan, dan tombol "Pasang aplikasi" di menu yang memunculkan dialognya lewat installApp().
  installEvent = event;
  syncInstall();
});
addEventListener('appinstalled', () => { installEvent = null; syncInstall(); toast('TokoBiru terpasang di layar utama', 'ok'); });

export async function installApp() {
  if (!installEvent) return;
  const prompt = installEvent;
  installEvent = null;
  syncInstall();
  try { await prompt.prompt(); } catch { /* dibatalkan */ }
}

// --- Modal pengaturan ---

const segment = (label, act, key, options, current) =>
  `<div class="choice" role="group" aria-label="${label}">${options.map(([id, text]) =>
    `<button type="button" data-act="${act}" ${key}="${id}" aria-pressed="${id === current}">${text}</button>`).join('')}</div>`;

const switchRow = (key, title, hint) =>
  `<div class="set-row"><div class="set-t"><b id="sw-${key}">${title}</b><small>${hint}</small></div>
    <button type="button" class="tgl" role="switch" data-act="set-toggle" data-key="${key}" aria-labelledby="sw-${key}" aria-checked="${Boolean(settings[key])}"><i></i></button></div>`;

export function settingsModal() {
  const customer = isCustomer();

  const catalog = customer
    ? `<div class="set-row stack"><div class="set-t"><b>Tampilan katalog</b><small>Cara produk ditampilkan di halaman Belanja.</small></div>
        ${segment('Tampilan katalog', 'layout', 'data-layout', [['grid', 'Kartu'], ['rows', 'Daftar']], state.layout)}</div>`
    : '';

  const haptic = customer && 'vibrate' in navigator
    ? switchRow('haptic', 'Getar saat menambah barang', 'Getaran singkat di HP saat barang masuk keranjang.')
    : '';

  openModal(`<h3>Pengaturan</h3><p class="sub">Berlaku di perangkat ini saja.</p>
    <div class="set-group">
      ${catalog}
      <div class="set-row wide"><div class="set-t"><b>Tema</b><small>Gelap lebih nyaman di ruangan redup. Otomatis mengikuti perangkat.</small></div>
        ${segment('Tema', 'set-theme', 'data-v', THEMES, settings.theme)}</div>
      <div class="set-row wide"><div class="set-t"><b>Ukuran teks</b><small>Perbesar bila tulisan terasa kecil.</small></div>
        ${segment('Ukuran teks', 'set-text', 'data-v', sizesFor(), settings.text)}</div>
      ${switchRow('calm', 'Kurangi animasi', 'Matikan gerakan dan efek terbang ke keranjang.')}
      ${haptic}
    </div>
    <div class="foot"><button type="button" class="btn primary" data-act="close-modal">Selesai</button></div>`);
}

export function setTextSize(el) {
  settings.text = el.dataset.v;
  save();
  applySettings();
  $$('[data-act="set-text"]').forEach(button => button.setAttribute('aria-pressed', String(button === el)));
}

export function setTheme(el) {
  if (!THEMES.some(([id]) => id === el.dataset.v)) return;
  settings.theme = el.dataset.v;
  save();
  applySettings();
  $$('[data-act="set-theme"]').forEach(button => button.setAttribute('aria-pressed', String(button === el)));
}

export function toggleSetting(el) {
  const key = el.dataset.key;
  if (!(key in DEFAULTS) || typeof DEFAULTS[key] !== 'boolean') return;
  settings[key] = !settings[key];
  save();
  applySettings();
  el.setAttribute('aria-checked', String(settings[key]));
}