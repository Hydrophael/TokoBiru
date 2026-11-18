// TokoBiru - pusat notifikasi di dalam aplikasi: lonceng di header, daftar kabar, dan pembaruan otomatis.
// Kabar disimpan di server (koleksi notifications), jadi tetap ada walau notifikasi perangkat dimatikan.
// "Realtime" dibuat dengan cek berkala saat aplikasi terlihat, plus cek seketika saat push masuk atau
// saat pengguna kembali ke aplikasi. (Server berjalan di Vercel, jadi tidak memakai koneksi yang terus terbuka.)

import { $, api, escapeHtml, formatDate, icon, state } from './core.js';
import { pushActive } from './push.js';
import { toast } from './ui.js';

const POLL_MS = 20000;

const store = { items: [], unread: 0, loaded: false, timer: null, busy: false, seen: new Set() };

// Kabar dengan tag yang sama diperbarui di server (id tetap, created_at baru), jadi "sudah dilihat" dikenali dari id + waktunya
const seenKey = item => item.id + '|' + item.created_at;

// app.js mengisi `go` supaya modul ini tidak perlu mengenal navigasi aplikasi
export const notifyHooks = { go: () => { } };

function ago(iso) {
  const seconds = Math.max(0, Math.round((Date.now() + state.clockSkew - Date.parse(iso)) / 1000));
  if (Number.isNaN(seconds)) return '';
  if (seconds < 45) return 'Baru saja';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} menit lalu`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} jam lalu`;
  const days = Math.round(hours / 24);
  return days < 7 ? `${days} hari lalu` : formatDate(iso);
}

export const bellHtml = () => `<div class="np">
    <button type="button" class="btn bell" data-act="notif-toggle" aria-haspopup="dialog" aria-expanded="false" aria-controls="np-pop" aria-label="Notifikasi">
      ${icon('bell', 20)}<span class="bell-count num" id="bell-count" hidden></span>
    </button>
    <div class="np-scrim" data-act="notif-close" aria-hidden="true"></div>
    <div class="np-pop" id="np-pop" role="dialog" aria-label="Notifikasi" hidden>
      <div class="np-head"><b>Notifikasi</b><button type="button" class="linkbtn" id="np-readall" data-act="notif-read-all" hidden>Tandai semua dibaca</button></div>
      <div class="np-list" id="np-list" aria-live="polite"></div>
    </div>
  </div>`;

function listHtml() {
  if (!store.loaded) return '<div class="np-empty"><small>Memuat…</small></div>';
  if (!store.items.length) {
    return `<div class="np-empty">${icon('bell', 28)}<b>Belum ada notifikasi</b><small>Kabar pesanan akan muncul di sini.</small></div>`;
  }
  return store.items.map(item => `<button type="button" class="np-item${item.read ? '' : ' unread'}" data-act="notif-go" data-id="${escapeHtml(item.id)}" data-view="${escapeHtml(item.view)}">
      <span class="np-dot" aria-hidden="true"></span>
      <span class="np-t"><b>${escapeHtml(item.title)}</b><span>${escapeHtml(item.body)}</span><small>${escapeHtml(ago(item.created_at))}${item.read ? '' : ' · belum dibaca'}</small></span>
    </button>`).join('');
}

export function renderBell(bump = false) {
  const count = $('#bell-count');
  if (!count) return;
  const unread = store.unread;
  count.hidden = unread === 0;
  count.textContent = unread > 99 ? '99+' : String(unread);
  const bell = $('#app .bell');
  bell?.setAttribute('aria-label', unread ? `Notifikasi, ${unread} belum dibaca` : 'Notifikasi');
  if (bump && bell) {
    bell.classList.remove('bump');
    void bell.offsetWidth;   // mulai ulang animasi
    bell.classList.add('bump');
  }
  const list = $('#np-list');
  if (list) list.innerHTML = listHtml();
  const readAll = $('#np-readall');
  if (readAll) readAll.hidden = unread === 0;
}

export const panelOpen = () => Boolean($('#np-pop:not([hidden])'));

export function setPanel(open, { focus = false } = {}) {
  const root = $('#app .np');
  if (!root) return;
  const button = $('.bell', root);
  $('#np-pop').hidden = !open;
  root.classList.toggle('open', open);
  $('#app .top')?.classList.toggle('menu-open', open);
  button.setAttribute('aria-expanded', String(open));
  if (open) {
    renderBell();
    refreshNotifications();
    $('#np-pop .np-item, #np-pop .linkbtn:not([hidden])')?.focus();
  } else if (focus) button.focus();
}

// Toast hanya bila kabar tiba saat aplikasi terlihat dan perangkat tidak akan menampilkan banner sendiri
function announce(fresh) {
  if (document.hidden || pushActive()) return;
  if (fresh.length === 1) {
    toast(`${fresh[0].title} · ${fresh[0].body}`, '', { label: 'Lihat', fn: () => openById(fresh[0].id, fresh[0].view) });
  } else {
    toast(`${fresh.length} notifikasi baru`, '', { label: 'Buka', fn: () => setPanel(true) });
  }
}

export async function refreshNotifications() {
  if (!state.user || store.busy) return;
  const owner = state.user.id;
  store.busy = true;
  try {
    const data = await api('/notifications');
    if (!state.user || state.user.id !== owner) return;
    const first = !store.loaded;
    const fresh = data.items.filter(item => !item.read && !store.seen.has(seenKey(item)));
    data.items.forEach(item => store.seen.add(seenKey(item)));
    const grew = data.unread > store.unread;
    store.items = data.items;
    store.unread = data.unread;
    store.loaded = true;
    renderBell(grew && !first);
    if (!first && fresh.length) announce(fresh);
  } catch { /* gagal diam-diam: dicoba lagi pada giliran berikutnya */ } finally {
    store.busy = false;
  }
}

export function startNotifications() {
  stopNotifications();
  store.timer = setInterval(() => { if (!document.hidden) refreshNotifications(); }, POLL_MS);
  refreshNotifications();
}

export function stopNotifications() {
  clearInterval(store.timer);
  Object.assign(store, { items: [], unread: 0, loaded: false, timer: null, busy: false });
  store.seen.clear();
}

async function markRead(id) {
  const item = store.items.find(entry => entry.id === id);
  if (!item || item.read) return;
  item.read = true;
  store.unread = Math.max(0, store.unread - 1);
  renderBell();
  await api('/notifications/read', { method: 'POST', body: { ids: [id] } }).catch(() => { });
}

export async function markAllRead() {
  if (!store.unread) return;
  store.items.forEach(item => { item.read = true; });
  store.unread = 0;
  renderBell();
  await api('/notifications/read', { method: 'POST', body: { all: true } }).catch(() => { });
}

function openById(id, view) {
  markRead(id);
  setPanel(false);
  notifyHooks.go(view);
}

export const openNotification = el => openById(el.dataset.id, el.dataset.view);