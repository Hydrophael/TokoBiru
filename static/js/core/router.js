// TokoBiru - Router tampilan, manajemen sesi, & sinkronisasi URL parameter
import { NAV, PHONE_RE, STORAGE_KEYS } from './constants.js';
import { defaultView, isCustomer, isEwallet, state, storage } from './state.js';
import { $, $$, cleanText, escapeHtml, normalizePhone } from './format.js';
import { api, hooks } from '../api/client.js';
import { toast } from '../components/ui.js';
import { renderShell, setProfileMenu } from '../components/shell.js';
import { drawCart } from '../components/cart.js';
import { setPanel, startNotifications, stopNotifications } from '../components/notify.js';
import { offerPush, pushEndpoint, resumePush } from '../components/push.js';

let pendingOpenView = '';
let pendingPayReturn = null;

export const pageHooks = {
  views: {},
  renderAuth: () => {},
  applySettings: () => {},
  animateDashboard: () => {},
  afterShopRender: () => {},
  afterLogsRender: () => {},
  afterProductsRender: () => {},
  showOrderSuccess: () => {}
};

export const getPendingOpenView = () => pendingOpenView;
export const setPendingOpenView = v => { pendingOpenView = v; };
export const getPendingPayReturn = () => pendingPayReturn;
export const setPendingPayReturn = v => { pendingPayReturn = v; };

hooks.onSessionExpired = () => {
  stopNotifications();
  state.user = null;
  pageHooks.renderAuth();
  toast('Sesi berakhir. Masuk lagi untuk melanjutkan.', 'err');
  api('/auth/me').then(me => { state.csrf = me.csrf; }).catch(() => { });
};

async function startSession(user, view) {
  state.user = user;
  state.cart = storage.get(STORAGE_KEYS.cart(user.id)) || {};
  await migrateLocalAddress();
  startNotifications();
  resumePush();
  offerPush(isStaff());   // staf ditawari saat masuk; pelanggan ditawari setelah pesanan pertama
  await show(view || defaultView());
}

async function onAuthed(result) {
  state.csrf = result.csrf;
  const openView = pendingOpenView;
  pendingOpenView = '';
  await startSession(result.user, openView);
  if (pendingPayReturn) {
    const payResult = pendingPayReturn;
    pendingPayReturn = null;
    await handlePayReturn(payResult);
  }
}

async function migrateLocalAddress() {
  if (!isCustomer()) return;
  const key = STORAGE_KEYS.profile(state.user.id);
  const old = storage.get(key);
  if (!old) return;
  if ((state.user.addresses || []).length) { storage.remove(key); return; }

  const phone = normalizePhone(old.phone);
  const address = cleanText(old.address);
  if (!PHONE_RE.test(phone) || address.length < 5) { storage.remove(key); return; }
  try {
    const result = await api('/auth/addresses', {
      method: 'POST',
      body: { label: 'Rumah', recipient: state.user.name, phone, address, main: true }
    });
    state.user.addresses = result.addresses;
    storage.remove(key);
  } catch { }
}

// Token CSRF bisa usang (mis. masuk lagi di tab lain): ambil yang baru lalu coba sekali lagi
async function requestLogout(body) {
  try {
    return await api('/auth/logout', { method: 'POST', body });
  } catch (err) {
    if (err.status !== 403) throw err;
    const me = await api('/auth/me');
    state.csrf = me.csrf;
    return api('/auth/logout', { method: 'POST', body });
  }
}

async function logout() {
  setProfileMenu(false);
  setPanel(false);
  const endpoint = await pushEndpoint();   // perangkat ini dilepas dari akun lewat permintaan keluar yang sama
  try {
    const result = await requestLogout(endpoint ? { endpoint } : {});
    state.csrf = result.csrf;
  } catch (err) {
    // Keluar yang gagal (offline, server sibuk) tidak boleh tampak berhasil: sesi di server masih hidup.
    // 401 berarti sesi memang sudah berakhir, jadi lanjut keluar.
    if (err.status !== 401) {
      toast(err.status === 0 ? 'Tidak ada sambungan, belum bisa keluar. Coba lagi saat tersambung.' : err.message, 'err');
      return;
    }
  }

  stopNotifications();
  state.user = null;
  state.cart = {};
  state.checkout = null;
  state.query = '';
  state.searchIds = null;
  state.category = '';
  state.filters = ({ inStock: false, min: null, max: null });
  pageHooks.renderAuth('login');
  toast('Anda sudah keluar');
}

async function loadProducts() {
  const result = await api('/products');
  state.products = result.products;
  state.categories = result.categories;
  state.productsTotal = result.total ?? result.products.length;
  state.productMap = Object.fromEntries(result.products.map(p => [p.id, p]));

  let adjusted = 0;
  Object.keys(state.cart).forEach(id => {
    const product = state.productMap[id];
    if (!product) { delete state.cart[id]; return; }
    if (product.stock === 0) { delete state.cart[id]; adjusted++; return; }
    if (state.cart[id] > product.stock) { state.cart[id] = product.stock; adjusted++; }
  });
  if (adjusted) toast(`${adjusted} barang di keranjang disesuaikan dengan stok terbaru`);
}

const loaders = {
  shop: loadProducts,
  products: loadProducts,
  async orders() {
    state.orders = (await api('/orders')).orders;
    // "Beli lagi" membaca katalog dari state.productMap. Bila aplikasi dibuka langsung ke Pesanan (mis. lewat notifikasi),
    // katalog belum pernah dimuat, jadi semua barang dianggap tidak tersedia. Gagal memuat tidak boleh merusak daftar pesanan.
    if (isCustomer() && !state.products.length) await loadProducts().catch(() => { });
  },
  async dashboard() { state.stats = await api('/stats'); },
  async users() { state.users = (await api('/users')).users; },
  async logs() {
    state.logs = (await api('/logs')).logs;
    const present = new Set(state.logs.map(log => log.id));
    state.selectedLogs.forEach(id => { if (!present.has(id)) state.selectedLogs.delete(id); });
  }
};

async function show(view) {
  const allowed = NAV.some(item => item.id === view && item.roles.includes(state.user.role));
  if (!allowed) view = defaultView();

  state.view = view;
  state.query = '';
  state.searchIds = null;
  state.logFilter = ({ q: '', group: '', action: '' });
  state.productFilter = ({ group: '', category: '' });
  state.fresh = true;
  pageHooks.applySettings();
  renderShell();
  window.scrollTo(0, 0);
  await reload();
}

async function reload() {
  try {
    await loaders[state.view]();
    const content = $('#content');
    content.classList.toggle('fresh', state.fresh);
    content.innerHTML = pageHooks.views[state.view]();
    if (state.view === 'dashboard') pageHooks.animateDashboard(content);
    if (state.view === 'shop') pageHooks.afterShopRender();
    if (state.view === 'logs') pageHooks.afterLogsRender();
    if (state.view === 'products') pageHooks.afterProductsRender();
    if (isCustomer()) drawCart();
    if (state.fresh) setTimeout(() => $$('#content .stagger').forEach(el => el.classList.remove('stagger')), 1200);
  } catch (err) {
    if (err.status === 401) return;
    $('#content').innerHTML = `<div class="empty"><b>Data belum bisa dimuat</b><p>${escapeHtml(err.message)}</p><button class="btn" data-act="reload">Coba lagi</button></div>`;
  } finally {
    state.fresh = false;
  }
}

function takeOpenView() {
  const view = new URLSearchParams(location.search).get('buka');
  if (!view) return '';
  history.replaceState(null, '', location.pathname);
  return view === 'orders' || view === 'dashboard' ? view : '';
}

function takePayReturn() {
  const result = new URLSearchParams(location.search).get('bayar');
  if (!result) return '';
  history.replaceState(null, '', location.pathname);
  return result === 'ok' || result === 'gagal' ? result : '';
}

async function handlePayReturn(result) {
  if (!result || !isCustomer()) return;
  await show('orders');
  if (result === 'ok') {
    toast('Terima kasih! Pembayaran sedang dicek, status pesanan berubah otomatis.', 'ok');
    watchPayReturn();
  } else toast('Pembayaran belum berhasil. Cek status pesanan Anda di bawah.', 'err');
}

// Kabar lunas dari e-wallet bisa tiba beberapa detik setelah pelanggan kembali: segarkan daftar sampai tidak ada yang menunggu
async function watchPayReturn() {
  const waiting = () => state.orders.some(order => order.status === 'pending' && isEwallet(order.payment_method));
  for (let attempt = 0; attempt < 20 && waiting(); attempt++) {
    if (state.view !== 'orders') return;
    if (!$('#modal-root').firstChild) await reload();
    if (!waiting()) return;
    await new Promise(resolve => setTimeout(resolve, 1500));
  }
}

export { startSession, onAuthed, logout, loadProducts, show, reload, takeOpenView, takePayReturn, handlePayReturn, watchPayReturn };
