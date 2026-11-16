// TokoBiru - notifikasi pesanan (Web Push) untuk admin dan master.
// Browser menyimpan "langganan" ke layanan push-nya, server menyimpan langganan itu, lalu mengirim kabar
// (pesanan baru, pembayaran masuk, masalah pembayaran) walau aplikasi sedang tertutup. Service worker (sw.js) yang menampilkannya.

import { $, api, createError, isStaff, state, storage } from './core.js';
import { toast } from './ui.js';

const flagKey = () => 'tb_push_' + state.user?.id;   // hanya akun yang mengaktifkannya yang didaftarkan ulang di perangkat ini

const supported = () => 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
const isIos = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const isInstalled = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;

export const pushAvailable = () => isStaff() && Boolean(state.user?.push_key);

function keyBytes(base64Url) {
  const padded = (base64Url + '='.repeat((4 - base64Url.length % 4) % 4)).replace(/-/g, '+').replace(/_/g, '/');
  return Uint8Array.from(atob(padded), ch => ch.charCodeAt(0));
}

// serviceWorker.ready tidak pernah selesai bila pendaftaran gagal, jadi dibatasi waktu
async function registration() {
  const timeout = new Promise((_, reject) => setTimeout(() => reject(createError('Layanan notifikasi belum siap. Muat ulang halaman lalu coba lagi.')), 5000));
  return Promise.race([navigator.serviceWorker.ready, timeout]);
}

async function currentSubscription() {
  try { return await (await registration()).pushManager.getSubscription(); } catch { return null; }
}

// unsupported | need-install (iPhone di Safari biasa) | denied | on | off
export async function pushStatus() {
  if (!supported()) return isIos() && !isInstalled() ? 'need-install' : 'unsupported';
  if (Notification.permission === 'denied') return 'denied';
  const subscription = await currentSubscription();
  return subscription && storage.get(flagKey()) ? 'on' : 'off';
}

// Langganan lama yang dibuat dengan kunci server berbeda tidak akan menerima kabar: buang lalu buat ulang
function sameServerKey(subscription, key) {
  const current = subscription.options?.applicationServerKey;
  if (!current) return true;
  const bytes = new Uint8Array(current);
  return bytes.length === key.length && bytes.every((value, i) => value === key[i]);
}

async function subscribe() {
  const reg = await registration();
  const key = keyBytes(state.user.push_key);
  const options = { userVisibleOnly: true, applicationServerKey: key };
  let subscription = await reg.pushManager.getSubscription();
  if (subscription && !sameServerKey(subscription, key)) {
    await subscription.unsubscribe().catch(() => { });
    subscription = null;
  }
  if (!subscription) subscription = await reg.pushManager.subscribe(options);

  const send = () => api('/push/subscribe', { method: 'POST', body: { subscription: subscription.toJSON() } });
  try {
    await send();
  } catch (err) {
    // Hanya langganan yang ditolak server (422) yang dibuat ulang; jaringan putus atau server sibuk cukup dilempar
    if (err.status !== 422) throw err;
    await subscription.unsubscribe().catch(() => { });
    subscription = await reg.pushManager.subscribe(options);
    await send();
  }
}

export async function enablePush() {
  if (!supported()) throw createError('Browser ini belum mendukung notifikasi.');
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw createError('Izin notifikasi tidak diberikan. Izinkan dulu di pengaturan browser.');
  await subscribe();
  storage.set(flagKey(), true);
}

export async function disablePush() {
  storage.remove(flagKey());
  const subscription = await currentSubscription();
  if (!subscription) return;
  await api('/push/unsubscribe', { method: 'POST', body: { endpoint: subscription.endpoint } }).catch(() => { });
  await subscription.unsubscribe().catch(() => { });
}

// Saat keluar: perangkat ini dilepas dari akun di server (agar akun lain di perangkat yang sama tidak menerima kabar toko),
// tapi izin dan langganan di browser dibiarkan supaya masuk lagi tidak perlu mengaktifkan ulang.
export async function detachPush() {
  if (!supported() || !state.user) return;
  const subscription = await currentSubscription();
  if (subscription) await api('/push/unsubscribe', { method: 'POST', body: { endpoint: subscription.endpoint } }).catch(() => { });
}

// Saat masuk: bila akun ini pernah mengaktifkannya di perangkat ini dan izinnya masih ada, daftarkan lagi tanpa bertanya
export async function resumePush() {
  if (!pushAvailable() || !supported() || !storage.get(flagKey())) return;
  if (Notification.permission !== 'granted') { storage.remove(flagKey()); return; }
  try { await subscribe(); } catch { /* gagal diam-diam: tombol di Pengaturan tetap bisa dipakai */ }
}

// --- Baris di modal Pengaturan ---

export const pushRowHtml = () => !pushAvailable() ? '' :
  `<div class="set-row"><div class="set-t"><b id="sw-push">Notifikasi pesanan</b><small id="push-hint">Memeriksa…</small>
    <button type="button" class="btn sm" data-act="push-test" hidden style="margin-top:8px">Kirim notifikasi uji</button></div>
    <button type="button" class="tgl" role="switch" data-act="push-toggle" aria-labelledby="sw-push" aria-checked="false" disabled><i></i></button></div>`;

const HINT = {
  unsupported: 'Browser ini belum mendukung notifikasi.',
  'need-install': 'Di iPhone, pasang dulu TokoBiru: ketuk Bagikan, lalu Tambah ke Layar Utama. Buka dari ikonnya.',
  denied: 'Notifikasi diblokir di pengaturan browser. Izinkan dulu di sana, lalu muat ulang.',
  off: 'Dapat kabar pesanan baru dan pembayaran masuk, walau aplikasi tertutup.',
  on: 'Aktif di perangkat ini.'
};

export async function renderPushRow() {
  const toggle = $('[data-act="push-toggle"]');
  if (!toggle) return;
  const status = await pushStatus();
  if (!toggle.isConnected) return;
  toggle.setAttribute('aria-checked', String(status === 'on'));
  toggle.disabled = !['on', 'off'].includes(status);
  $('#push-hint').textContent = HINT[status];
  $('[data-act="push-test"]').hidden = status !== 'on';
}

export async function togglePush(el) {
  if (el.dataset.busy) return;
  el.dataset.busy = '1';
  try {
    if (el.getAttribute('aria-checked') === 'true') {
      await disablePush();
      toast('Notifikasi dimatikan di perangkat ini');
    } else {
      await enablePush();
      toast('Notifikasi aktif di perangkat ini', 'ok');
    }
  } catch (err) {
    toast(err.message, 'err');
  } finally {
    delete el.dataset.busy;
    renderPushRow();
  }
}

export async function testPush(el) {
  if (el.disabled) return;
  el.disabled = true;
  try {
    const result = await api('/push/test', { method: 'POST', body: {} });
    toast(result.sent ? 'Notifikasi uji dikirim. Seharusnya muncul sebentar lagi.' : 'Terkirim ke layanan, tapi perangkat belum menerimanya. Coba aktifkan ulang.', result.sent ? 'ok' : 'err');
  } catch (err) {
    toast(err.message, 'err');
  } finally {
    el.disabled = false;
  }
}