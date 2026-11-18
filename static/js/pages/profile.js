// TokoBiru - Profil akun, ganti password, buku alamat, tentang, & pengaturan PWA
import {
  ADDRESS_LABELS,
  ADDRESS_LIMIT,
  APP_INFO,
  PHONE_ERROR,
  PHONE_RE,
  RECIPIENT_ERROR,
  ROLE_LABEL,
  STORAGE_KEYS
} from '../core/constants.js';
import { isCustomer, state, storage } from '../core/state.js';
import {
  $$,
  cleanText,
  escapeHtml,
  icon,
  normalizePhone,
  validationError
} from '../core/format.js';
import { api } from '../api/client.js';
import { closeModal, confirmDialog, openModal, toast } from '../components/ui.js';
import { avatarHtml, avatarPhoto, refreshProfileMenu, roleTag, setProfileMenu } from '../components/shell.js';
import { AVATAR_HINT, avatarPreviewHtml } from '../components/photo.js';
import { pushRowHtml, renderPushRow, togglePush } from '../components/push.js';
import { reload } from '../core/router.js';
import { checkNewPassword } from './auth.js';

const myAddresses = () => state.user.addresses || [];
const findAddress = id => myAddresses().find(item => item.id === id);

export function profileModal() {
  const user = state.user;
  const customer = isCustomer();
  const photo = avatarPhoto(user);
  const addresses = user.addresses || [];
  const main = addresses.find(item => item.main) || addresses[0];

  const shipping = customer ? `
      <div class="pf-addr"><div class="set-t"><b>Alamat pengiriman</b>
        <small>${main ? escapeHtml(`${main.label}: ${main.address.replace(/\s+/g, ' ')}`) : 'Belum ada alamat tersimpan.'}</small></div>
        <button type="button" class="btn sm" data-act="address-open">${addresses.length ? 'Kelola' : 'Tambah'}</button></div>` : '';

  openModal(`<h3>Profil saya</h3>
    <div class="pf-head">${avatarHtml(user, 'xl')}<div class="pf-id"><b>${escapeHtml(user.name)}</b><span class="muted">@${escapeHtml(user.username)}</span>${roleTag(user)}</div></div>
    <form data-form="profile" novalidate><div class="form-alert" role="alert"></div>
      <div class="field photo-field pf-photo"><label>Foto profil (opsional)</label>
        <div class="photo-row">
          <div class="photo-preview round" data-photo-preview>${avatarPreviewHtml(photo)}</div>
          <div class="photo-side">
            <input type="file" class="sr-only" accept="image/*" data-photo-input data-photo-kind="avatar">
            <input type="hidden" name="image" value="" disabled>
            <div class="acts"><button type="button" class="btn sm" data-act="photo-pick">${icon('plus', 14)} Pilih foto</button>
              <button type="button" class="btn sm danger" data-act="photo-clear"${photo ? '' : ' hidden'}>${icon('trash', 13)} Hapus foto</button></div>
            <p class="muted small" data-photo-note>${AVATAR_HINT}</p>
          </div>
        </div></div>
      <div class="field"><label>Nama lengkap</label><input class="input" name="name" required maxlength="50" autocomplete="name" value="${escapeHtml(user.name)}"></div>
      <div class="field"><label>Email</label><input class="input" value="${escapeHtml(user.email)}" disabled></div>
      <p class="muted small" style="margin:-6px 0 14px">Username dan email tidak bisa diubah di sini.</p>${shipping}
      <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Simpan</button></div></form>`);
}

const addressCardHtml = item => {
  const id = escapeHtml(item.id);
  const label = escapeHtml(item.label);
  return `<li class="addr-card${item.main ? ' main' : ''}">
    <div class="addr-top"><span class="tag">${label}</span>${item.main ? '<span class="tag blue">Utama</span>' : ''}<span class="addr-who">${escapeHtml(item.recipient)}</span></div>
    <div class="addr-text">${escapeHtml(item.address)}</div>
    <div class="addr-phone num">${escapeHtml(item.phone)}</div>
    <div class="addr-acts">
      <button type="button" class="btn sm" data-act="address-edit" data-id="${id}">${icon('edit', 14)} Ubah</button>
      ${item.main ? '' : `<button type="button" class="btn sm" data-act="address-main" data-id="${id}">Jadikan utama</button>`}
      <button type="button" class="btn sm flat danger" data-act="address-del" data-id="${id}" aria-label="Hapus alamat ${label}">${icon('trash', 14)} Hapus</button>
    </div></li>`;
};

export function addressesModal() {
  const addresses = state.user.addresses || [];
  const full = addresses.length >= ADDRESS_LIMIT;
  const list = addresses.length
    ? `<ul class="addr-list">${addresses.map(addressCardHtml).join('')}</ul>`
    : '<div class="addr-empty"><b>Belum ada alamat</b>Simpan sekali, dipakai terus saat memesan.</div>';

  openModal(`<h3>Alamat saya</h3><p class="sub">Tersimpan di akun Anda, jadi tetap ada di perangkat mana pun.</p>
    ${list}
    ${full ? `<p class="addr-limit">Maksimal ${ADDRESS_LIMIT} alamat. Hapus salah satu untuk menambah.</p>` : ''}
    <div class="foot"><button type="button" class="btn" data-act="close-modal">Tutup</button>
      <button type="button" class="btn primary" data-act="address-new"${full ? ' disabled' : ''}>${icon('plus', 15)} Tambah alamat</button></div>`);
}

export function addressFormModal(item = null) {
  const addresses = state.user.addresses || [];
  const values = item || { label: 'Rumah', recipient: state.user.name, phone: '', address: '', main: false };
  const canPickMain = addresses.length > 0 && !values.main;
  const options = ADDRESS_LABELS.map(label => `<option value="${label}"${label === values.label ? ' selected' : ''}>${label}</option>`).join('');

  openModal(`<h3>${item ? 'Ubah alamat' : 'Tambah alamat'}</h3>
    <form data-form="address" data-id="${item ? escapeHtml(item.id) : ''}" novalidate><div class="form-alert" role="alert"></div>
      <div class="field"><label>Label</label><select class="select" name="label">${options}</select></div>
      <div class="field"><label>Nama penerima</label><input class="input" name="recipient" required maxlength="50" autocomplete="name" value="${escapeHtml(values.recipient)}"></div>
      <div class="field"><label>Nomor HP / WhatsApp</label><input class="input" name="phone" type="tel" inputmode="tel" required maxlength="20" placeholder="Contoh: 081234567890" autocomplete="tel" value="${escapeHtml(values.phone)}"></div>
      <div class="field"><label>Alamat pengiriman</label><textarea class="input" name="address" required minlength="5" maxlength="160" placeholder="Nama jalan, nomor, kota" autocomplete="street-address">${escapeHtml(values.address)}</textarea></div>
      ${canPickMain ? '<label class="save-addr"><input type="checkbox" class="tick" name="main" value="1"> Jadikan alamat utama</label>' : ''}
      <div class="foot"><button type="button" class="btn" data-act="address-open">Batal</button><button type="submit" class="btn primary">Simpan</button></div></form>`);
}

export function aboutModal() {
  const standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const user = state.user;
  openModal(`<h3>Tentang aplikasi</h3>
    <div class="about-head"><span class="mark" aria-hidden="true"></span><div><b>${escapeHtml(APP_INFO.name)}</b><span>${escapeHtml(APP_INFO.tagline)}</span></div></div>
    <dl class="about-list">
      <div><dt>Versi</dt><dd class="num">${escapeHtml(APP_INFO.version)}</dd></div>
      <div><dt>Dibuka sebagai</dt><dd>${standalone ? 'Aplikasi terpasang' : 'Halaman web'}</dd></div>
      <div><dt>Masuk sebagai</dt><dd>@${escapeHtml(user.username)} (${escapeHtml(ROLE_LABEL[user.role] || user.role)})</dd></div>
      ${isCustomer() ? '' : `<div><dt>Dibangun dengan</dt><dd>${escapeHtml(APP_INFO.stack)}</dd></div>`}
    </dl>
    <p class="about-note">Data akun, alamat, dan pesanan disimpan di server toko. Keranjang dan pengaturan tampilan hanya tersimpan di perangkat ini.</p>
    <div class="foot"><button type="button" class="btn primary" data-act="close-modal">Tutup</button></div>`);
}


export function passwordModal() {
  openModal(`<h3>Ganti password</h3><p class="sub">Setelah diganti, perangkat lain yang sedang masuk akan keluar otomatis.</p>
    <form data-form="password" novalidate><div class="form-alert" role="alert"></div>
      <div class="field"><label>Password lama</label><input class="input" name="current_password" data-pw type="password" required maxlength="128" autocomplete="current-password"></div>
      <div class="field"><label>Password baru</label><input class="input" name="new_password" data-pw type="password" required minlength="8" maxlength="128" autocomplete="new-password" placeholder="Minimal 8 karakter"></div>
      <div class="field"><label>Ulangi password baru</label><input class="input" name="confirm" data-pw type="password" required autocomplete="new-password"></div>
      <p class="muted small" style="margin:-2px 0 10px">Minimal 8 karakter, berisi huruf dan angka.</p>
      <label class="showpw"><input type="checkbox" data-act="toggle-pw"> Tampilkan password</label>
      <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Ganti password</button></div></form>`);
}


const openFromMenu = openFn => { setProfileMenu(false, { focus: true }); openFn(); };
const openProfile = () => openFromMenu(profileModal);
const openPassword = () => openFromMenu(passwordModal);

async function setMainAddress(el) {
  const item = findAddress(el.dataset.id);
  if (!item) return;
  try {
    const result = await api('/auth/addresses/' + item.id, {
      method: 'PUT',
      body: { label: item.label, recipient: item.recipient, phone: item.phone, address: item.address, main: true }
    });
    state.user.addresses = result.addresses;
    addressesModal();
    toast('Alamat utama diganti', 'ok');
  } catch (err) {
    toast(err.message, 'err');
  }
}

async function deleteAddress(el) {
  const item = findAddress(el.dataset.id);
  if (!item) return;
  const ok = await confirmDialog(`Hapus alamat ${item.label}?`, 'Alamat ini dihapus dari akun Anda. Pesanan yang sudah dibuat tidak berubah.', 'Hapus', true);
  if (!ok) { addressesModal(); return; }
  try {
    const result = await api('/auth/addresses/' + item.id, { method: 'DELETE', body: {} });
    state.user.addresses = result.addresses;
    toast('Alamat dihapus', 'ok');
  } catch (err) {
    toast(err.message, 'err');
  }
  addressesModal();
}

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
      ${pushRowHtml()}
    </div>
    <div class="foot"><button type="button" class="btn primary" data-act="close-modal">Selesai</button></div>`);
  renderPushRow();
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

export const profileActions = {
  'profile-open': openProfile,
  'change-password': openPassword,
  'address-open': () => addressesModal(),
  'address-new': () => addressFormModal(),
  'address-edit': el => addressFormModal(findAddress(el.dataset.id) || null),
  'address-main': setMainAddress,
  'address-del': deleteAddress,
  'about-open': () => aboutModal(),
  'settings-open': settingsModal,
  'set-text': setTextSize,
  'set-theme': setTheme,
  'set-toggle': toggleSetting,
  'install-app': installApp,
  'push-toggle': togglePush
};

export const profileFormHandlers = {
  async password(form, data) {
    checkNewPassword(data);
    await api('/auth/password', {
      method: 'PATCH',
      body: { current_password: data.current_password, new_password: data.new_password }
    });
    closeModal();
    toast('Password diganti. Perangkat lain perlu masuk lagi.', 'ok');
    if (state.view === 'logs') await reload();
  },

  async profile(form, data) {
    const name = cleanText(data.name);
    if (name.length < 2) throw validationError({ name: 'Nama lengkap minimal 2 karakter' });

    const body = { name };
    if ('image' in data) body.image = data.image;

    const result = await api('/auth/profile', { method: 'PATCH', body });
    state.user = result.user;
    refreshProfileMenu();
    closeModal();
    toast('Profil disimpan', 'ok');
    if (state.view === 'users' || state.view === 'logs') await reload();
  },

  async address(form, data) {
    const id = form.dataset.id;
    const recipient = cleanText(data.recipient);
    const phone = normalizePhone(data.phone);
    const address = cleanText(data.address);
    const errors = {};
    if (recipient.length < 2) errors.recipient = RECIPIENT_ERROR;
    if (!PHONE_RE.test(phone)) errors.phone = PHONE_ERROR;
    if (address.length < 5) errors.address = 'Alamat minimal 5 karakter';
    if (Object.keys(errors).length) throw validationError(errors);

    const result = await api(id ? '/auth/addresses/' + id : '/auth/addresses', {
      method: id ? 'PUT' : 'POST',
      body: { label: data.label, recipient, phone, address, main: data.main === '1' }
    });
    state.user.addresses = result.addresses;
    toast(id ? 'Alamat diperbarui' : 'Alamat ditambahkan', 'ok');
    addressesModal();
  },
};