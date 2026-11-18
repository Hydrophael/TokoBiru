// TokoBiru - Entry point aplikasi: merakit halaman, aksi, & menjalankan boot()
import { QRIS_POLL_MS, STORAGE_KEYS } from './constants.js';
import { isCustomer, state, storage } from './state.js';
import { $, escapeHtml } from './format.js';
import { api } from '../api/client.js';
import {
  animateDashboard,
  closeModal,
  confirmAccepted,
  toast
} from '../components/ui.js';
import '../components/layout.js';
import {
  markAllRead,
  notifyHooks,
  openNotification,
  panelOpen,
  refreshNotifications,
  setPanel
} from '../components/notify.js';
import {
  profileMenuOpen,
  setProfileMenu
} from '../components/shell.js';
import {
  addOneToCart,
  closeCart,
  openCart,
  removeFromCart,
  setCartQty
} from '../components/cart.js';
import {
  handlePayReturn,
  pageHooks,
  reload,
  setPendingOpenView,
  setPendingPayReturn,
  show,
  startSession,
  takeOpenView,
  takePayReturn
} from './router.js';
import {
  actions,
  bindEvents,
  eventHooks,
  formHandlers
} from './events.js';
import {
  authActions,
  authFormHandlers,
  onOtpFocus,
  onOtpInput,
  onOtpPointer,
  renderAuth,
  updatePasswordChecks
} from '../pages/auth.js';
import {
  afterShopRender,
  applyFilters,
  clearSearch,
  keepResultsInView,
  renderList,
  runShopSearch,
  shopActions,
  shopView,
  updateRailEdges
} from '../pages/shop.js';
import {
  checkoutActions,
  checkoutFormHandlers,
  pickCheckoutAddress,
  updateCheckout
} from '../pages/checkout.js';
import {
  orderActions,
  ordersView,
  pollQris,
  showOrderSuccess,
  tickTimers,
  uploadProof
} from '../pages/orders.js';
import {
  dashboardActions,
  dashboardView
} from '../pages/dashboard.js';
import {
  adminActions,
  adminFormHandlers,
  afterLogsRender,
  afterProductsRender,
  changeUserSetting,
  logsView,
  productsView,
  setLogAction,
  setProductCategory,
  typeLogSearch,
  usersView
} from '../pages/admin.js';
import {
  applySettings,
  loadSettings,
  profileActions,
  profileFormHandlers,
  syncInstall
} from '../pages/profile.js';
import { cartQty } from './state.js';

// Daftarkan view per halaman
Object.assign(pageHooks.views, {
  shop: shopView,
  dashboard: dashboardView,
  orders: ordersView,
  products: productsView,
  users: usersView,
  logs: logsView
});
Object.assign(pageHooks, {
  renderAuth,
  applySettings,
  animateDashboard,
  afterShopRender,
  afterLogsRender,
  afterProductsRender,
  showOrderSuccess
});

// Daftarkan event hooks lintas modul
Object.assign(eventHooks, {
  onOtpInput,
  onOtpFocus,
  onOtpPointer,
  updatePasswordChecks,
  typeLogSearch,
  setLogAction,
  setProductCategory,
  uploadProof,
  pickCheckoutAddress,
  updateCheckout,
  renderList,
  keepResultsInView,
  changeUserSetting,
  clearSearch,
  applyFilters,
  updateRailEdges,
  runShopSearch
});

// Gabungkan seluruh action handler (data-act)
Object.assign(
  actions,
  {
    nav: el => show(el.dataset.view),
    reload,
    'refresh-page': () => location.reload(),
    'close-modal': closeModal,
    overlay: (el, e) => { if (e.target === el && !el.querySelector('[data-keep]')) closeModal(); },
    'ask-ok': confirmAccepted,
    'add-cart': addOneToCart,
    'cart-inc': addOneToCart,
    'cart-dec': el => setCartQty(el.dataset.id, cartQty(el.dataset.id) - 1),
    'cart-del': removeFromCart,
    'open-cart': openCart,
    'close-cart': closeCart,
    'profile-menu': () => setProfileMenu(!profileMenuOpen()),
    'profile-close': () => setProfileMenu(false, { focus: true }),
    'notif-toggle': () => { setProfileMenu(false); setPanel(!panelOpen()); },
    'notif-close': () => setPanel(false, { focus: true }),
    'notif-go': openNotification,
    'notif-read-all': markAllRead
  },
  authActions,
  shopActions,
  checkoutActions,
  orderActions,
  dashboardActions,
  adminActions,
  profileActions
);

// Tambahkan aksi logout setelah router diimpor
import { logout } from './router.js';
actions.logout = logout;

// Gabungkan seluruh form handler (data-form)
Object.assign(
  formHandlers,
  authFormHandlers,
  checkoutFormHandlers,
  adminFormHandlers,
  profileFormHandlers
);

async function boot() {
  storage.remove(STORAGE_KEYS.legacyProfile);
  state.layout = storage.get(STORAGE_KEYS.layout) === 'rows' ? 'rows' : 'grid';
  loadSettings();
  applySettings();
  bindEvents();
  setInterval(pollQris, QRIS_POLL_MS);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { pollQris(); refreshNotifications(); } });
  addEventListener('pageshow', () => { pollQris(); refreshNotifications(); });
  addEventListener('online', () => refreshNotifications());
  notifyHooks.go = view => { if (state.user) show(view === 'dashboard' && !isCustomer() ? 'dashboard' : 'orders'); };
  setInterval(tickTimers, 1000);
  // Notifikasi diketuk saat aplikasi sudah terbuka: pindah ke layar yang diminta
  navigator.serviceWorker?.addEventListener('message', event => {
    if (event.data?.type === 'open-view' && state.user && ['orders', 'dashboard'].includes(event.data.view)) notifyHooks.go(event.data.view);
    if (event.data?.type === 'push-received') refreshNotifications();   // kabar baru tiba: lonceng ikut diperbarui
  });

  try {
    const me = await api('/auth/me');
    state.csrf = me.csrf;
    state.payInfo = me.pay_info || '';
    state.dummyQris = Boolean(me.qris_enabled ?? me.dummy_qris);   // nama lama; artinya "QRIS tersedia" (Xendit atau simulasi)
    state.qrisMinutes = Number(me.qris_minutes) || 60;
    state.ewalletMinutes = me.ewallet_minutes || {};
    state.ewalletOn = Boolean(me.ewallet_enabled);
    state.proofReader = Boolean(me.proof_reader);
    state.proofRetentionDays = Number(me.proof_retention_days) || 0;
    if (me.server_time) state.clockSkew = Date.parse(me.server_time) - Date.now();
    state.shipping = { fee: Number(me.shipping?.fee) || 0, freeMin: Number(me.shipping?.free_min) || 0 };
    state.resetEnabled = Boolean(me.reset_enabled);

    const payReturn = takePayReturn();
    const openView = takeOpenView();
    if (me.user) { await startSession(me.user, openView); await handlePayReturn(payReturn); }
    else {
      setPendingOpenView(openView);
      renderAuth('login');
      if (payReturn) {
        setPendingPayReturn(payReturn);
        toast('Masuk untuk melihat status pembayaran Anda.', 'ok');
      }
    }
  } catch (err) {
    $('#app').innerHTML = `<div class="empty" style="margin:15vh auto;max-width:460px"><b>Aplikasi belum bisa dimuat</b><p>${escapeHtml(err.message)}</p><button class="btn primary" data-act="refresh-page">Muat ulang</button></div>`;
  }
}

boot();
