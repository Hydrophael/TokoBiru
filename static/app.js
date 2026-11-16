import {
  $,
  $$,
  ADDRESS_LIMIT,
  MAX_CART_QTY,
  NAV,
  PAYMENT_LABEL,
  isEwallet,
  ewalletBadgeHtml,
  EWALLET_GROUP,
  ewalletChoices,
  chosenPayment,
  SHIPPING_LABEL,
  STORAGE_KEYS,
  api,
  cartQty,
  createError,
  defaultView,
  descriptionHtml,
  escapeHtml,
  formatRupiah,
  hashString,
  hooks,
  icon,
  isCustomer,
  isStaff,
  newRequestKey,
  paymentChoices,
  priceHtml,
  productEmoji,
  productImage,
  shippingFeeFor,
  state,
  stockInfo,
  storage,
  tileVisualHtml,
  countdownText,
  msLeft
} from './core.js';
import {
  animateDashboard,
  closeModal,
  confirmAccepted,
  confirmDialog,
  burst,
  EASE,
  flyToCart,
  openModal,
  reducedMotion,
  toast,
  withTransition
} from './ui.js';
import { choosePhoto, clearPhoto, compressImage, handlePhotoInput } from './photo.js';
import './layout.js';
import { detachPush, resumePush, testPush, togglePush } from './push.js';
import { applySettings, installApp, loadSettings, setTextSize, setTheme, settingsModal, syncInstall, toggleSetting } from './settings.js';
import { applyLogFilter, visibleLogIds } from './logs-grid.js';
import { applyProductFilter } from './products-grid.js';
import {
  aboutModal,
  addressFormModal,
  addressesModal,
  afterLogsRender,
  afterProductsRender,
  afterShopRender,
  appendCards,
  cartLines,
  cartTotal,
  drawCart,
  filterModal,
  forgotModal,
  orderCards,
  orderDetailModal,
  orderRailHtml,
  passwordModal,
  productModal,
  profileModal,
  qrisPaidHtml,
  refreshProfileMenu,
  renderAuth,
  renderList,
  renderOtp,
  renderShell,
  scrollRail,
  setCartQty,
  setResetInfo,
  showOrderSuccess,
  showResetStep,
  syncLogSelection,
  updateRailEdges,
  userModal,
  views
} from './views.js';

const MOBILE = matchMedia('(max-width:780px)');

const MIN_SERVER_SEARCH = 2;
const SEARCH_DEBOUNCE_MS = 200;
const LOG_SEARCH_DEBOUNCE_MS = 150;

const CHECKOUT_KEY_TTL_MS = 10 * 60 * 1000;

const PHONE_RE = /^\+?\d{8,15}$/;
const PHONE_ERROR = 'Isi nomor HP yang benar, contoh 081234567890';
const RECIPIENT_ERROR = 'Nama penerima minimal 2 karakter';
const CODE_REJECTED = 'Kode salah atau sudah kedaluwarsa. Periksa lagi, atau kirim ulang kode.';

let cartReturnFocus = null;
let searchDebounce = 0;
let searchSeq = 0;
let logSearchTimer = 0;
let resendTimer = null;
let otpTimer = null;
let pendingOpenView = '';   // layar yang diminta notifikasi, menunggu admin masuk
let pendingPayReturn = null;   // hasil bayar e-wallet yang menunggu pelanggan masuk


const emptyFilters = () => ({ inStock: false, min: null, max: null });
const emptyLogFilter = () => ({ q: '', group: '', action: '' });
const emptyProductFilter = () => ({ group: '', category: '' });

const cleanText = value => String(value || '').trim();
const normalizePhone = value => String(value || '').replace(/[\s.-]/g, '');

const myAddresses = () => state.user.addresses || [];
const findAddress = id => myAddresses().find(item => item.id === id);

const validationError = fields => createError('Periksa kembali isian Anda', { fields });


hooks.onSessionExpired = () => {
  state.user = null;
  renderAuth();
  toast('Sesi berakhir. Masuk lagi untuk melanjutkan.', 'err');
  api('/auth/me').then(me => { state.csrf = me.csrf; }).catch(() => { });
};

async function startSession(user, view) {
  state.user = user;
  state.cart = storage.get(STORAGE_KEYS.cart(user.id)) || {};
  await migrateLocalAddress();
  if (isStaff()) resumePush();
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
  if (myAddresses().length) { storage.remove(key); return; }

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

async function logout() {
  setProfileMenu(false);
  await detachPush();
  try {
    const result = await api('/auth/logout', { method: 'POST', body: {} });
    state.csrf = result.csrf;
  } catch { }

  state.user = null;
  state.cart = {};
  state.checkout = null;
  state.query = '';
  state.searchIds = null;
  state.category = '';
  state.filters = emptyFilters();
  renderAuth('login');
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
  async orders() { state.orders = (await api('/orders')).orders; },
  async dashboard() { state.stats = await api('/stats'); },
  async users() { state.users = (await api('/users')).users; },
  async logs() {
    state.logs = (await api('/logs')).logs.filter(log => log.action !== 'log_hapus');
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
  state.logFilter = emptyLogFilter();
  state.productFilter = emptyProductFilter();
  state.fresh = true;
  applySettings();
  renderShell();
  window.scrollTo(0, 0);
  await reload();
}

async function reload() {
  try {
    await loaders[state.view]();
    const content = $('#content');
    content.classList.toggle('fresh', state.fresh);
    content.innerHTML = views[state.view]();
    if (state.view === 'dashboard') animateDashboard(content);
    if (state.view === 'shop') afterShopRender();
    if (state.view === 'logs') afterLogsRender();
    if (state.view === 'products') afterProductsRender();
    if (isCustomer()) drawCart();
    if (state.fresh) setTimeout(() => $$('#content .stagger').forEach(el => el.classList.remove('stagger')), 1200);
  } catch (err) {
    if (err.status === 401) return;
    $('#content').innerHTML = `<div class="empty"><b>Data belum bisa dimuat</b><p>${escapeHtml(err.message)}</p><button class="btn" data-act="reload">Coba lagi</button></div>`;
  } finally {
    state.fresh = false;
  }
}


function addOneToCart(el) {
  const id = el.dataset.id;
  const product = state.productMap[id];
  const card = el.closest('[data-card]');
  const current = cartQty(id);

  if (product && card && current < product.stock) flyToCart($('.ini, .photo', card));
  setCartQty(id, current + 1);
}

function removeFromCart(el) {
  const id = el.dataset.id;
  const qty = state.cart[id];
  const name = state.productMap[id].name;

  setCartQty(id, 0);
  toast(`${name} dihapus dari keranjang`, '', { label: 'Urungkan', fn: () => setCartQty(id, qty) });
}

function openCart() {
  cartReturnFocus = document.activeElement;
  $('#drawer').classList.add('open');
  $('#scrim').classList.add('open');
  document.documentElement.classList.add('lock');

  if (!reducedMotion.matches) {
    $$('#cart-items .citem').slice(0, 8).forEach((el, index) => el.animate(
      [{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }],
      { duration: 380, delay: 140 + index * 45, easing: EASE, fill: 'backwards' }
    ));
  }

  $('#drawer .drawer-head button')?.focus();
}

function closeCart() {
  const drawer = $('#drawer');
  if (!drawer || !drawer.classList.contains('open')) return;

  drawer.classList.remove('open');
  $('#scrim').classList.remove('open');
  document.documentElement.classList.remove('lock');
  if (cartReturnFocus && cartReturnFocus.isConnected) cartReturnFocus.focus();
  cartReturnFocus = null;
}

function reorder(el) {
  const order = state.orders.find(o => o.id === el.dataset.id);
  if (!order) return;
  if ($('#modal-root').firstChild) closeModal();

  let added = 0;
  let skipped = 0;
  order.items.forEach(item => {
    const product = state.productMap[item.product_id];
    if (!product || product.stock === 0) { skipped++; return; }
    state.cart[product.id] = Math.min(cartQty(product.id) + item.qty, product.stock, MAX_CART_QTY);
    added++;
  });

  drawCart();
  if (!added) return toast('Barang pada pesanan ini sedang tidak tersedia', 'err');
  toast(added + ' barang masuk keranjang' + (skipped ? ', ' + skipped + ' tidak tersedia' : ''));
  openCart();
}

function openProductDetail(el) {
  const product = state.productMap[el.dataset.id];
  if (!product) return;
  const inCart = cartQty(product.id);

  openModal(`<div class="dtile p${hashString(product.id) % 4}${productImage(product) ? ' has-photo' : ''}"><span class="tag">${escapeHtml(product.category)}</span>${tileVisualHtml(product)}</div>
      <h3>${escapeHtml(product.name)}</h3>
      <div class="ddesc">${descriptionHtml(product.description)}</div>
      <div class="dmeta">${priceHtml(product.price)}${stockInfo(product)}</div>
      ${inCart ? `<p class="muted small" style="margin-bottom:10px">Sudah ${inCart} di keranjang Anda.</p>` : ''}
      <div class="foot"><button class="btn" data-act="close-modal">Tutup</button>
      ${product.stock === 0 ? '' : `<button class="btn primary" data-act="detail-add" data-id="${product.id}">${icon('plus', 15)} Tambah ke keranjang</button>`}</div>`);
}

function addFromProductDetail(el) {
  const id = el.dataset.id;
  const product = state.productMap[id];
  const current = cartQty(id);

  if (product && current < product.stock) flyToCart($('.dtile .ini, .dtile .photo'));
  closeModal();
  setCartQty(id, current + 1);
}

function keepResultsInView() {
  const head = $('.results-head');
  if (!head) return;
  const top = head.getBoundingClientRect().top + scrollY - ($('#tools')?.offsetHeight || 0) - 80;
  if (scrollY > top) window.scrollTo({ top: Math.max(0, top), behavior: 'auto' });
}

const rerenderShop = () => withTransition(() => { renderList(); keepResultsInView(); });

function filterByCategory(el) {
  state.category = el.dataset.cat;
  withTransition(() => {
    renderList();
    keepResultsInView();

    const active = $('#rail .active');
    if (active) {
      active.focus({ preventScroll: true });
      active.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
    }
  });
}

function resetShopQuery() {
  clearTimeout(searchDebounce);
  searchSeq++;
  state.query = '';
  state.searchIds = null;
  const input = $('[data-input=shop-search]');
  if (input) input.value = '';
}

function clearSearch() {
  resetShopQuery();
  $('[data-input=shop-search]')?.focus();
  rerenderShop();
}

function clearAllFilters() {
  resetShopQuery();
  state.category = '';
  state.filters = emptyFilters();
  rerenderShop();
}

function removeFilter(el) {
  const kind = el.dataset.f;
  if (kind === 'q') return clearSearch();
  if (kind === 'price') { state.filters.min = null; state.filters.max = null; }
  if (kind === 'stock') state.filters.inStock = false;
  rerenderShop();
}

function applyFilters() {
  const readPrice = selector => {
    const digits = ($(selector).value || '').replace(/\D/g, '').slice(0, 12);
    return digits ? Number(digits) : null;
  };
  let min = readPrice('#f-min');
  let max = readPrice('#f-max');
  if (min !== null && max !== null && min > max) [min, max] = [max, min];

  state.filters = { inStock: $('#f-stock').checked, min, max };
  closeModal();
  rerenderShop();
}

function resetFilters() {
  state.filters = emptyFilters();
  closeModal();
  rerenderShop();
}

function setLayout(el) {
  state.layout = el.dataset.layout === 'rows' ? 'rows' : 'grid';
  storage.set(STORAGE_KEYS.layout, state.layout);
  $$('[data-act=layout]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.layout === state.layout)));
  $('#plist .shelf')?.classList.toggle('rows', state.layout === 'rows');
}

function loadMoreProducts() {
  const hadFocus = document.activeElement?.matches?.('[data-act=more]');
  const before = $$('#plist [data-card]').length;
  appendCards();

  const firstNew = $$('#plist [data-card]')[before];
  if (hadFocus && firstNew) $('.plink', firstNew).focus({ preventScroll: true });
}

async function searchOnServer(raw) {
  const query = raw.trim();
  const seq = ++searchSeq;
  if (query.length < MIN_SERVER_SEARCH) return;

  try {
    const result = await api('/products?q=' + encodeURIComponent(query));
    if (seq !== searchSeq || state.view !== 'shop' || state.query.trim() !== query) return;
    state.searchIds = result.products.map(product => product.id);
    renderList();
  } catch {
    if (seq === searchSeq) state.searchIds = null;
  }
}

function runShopSearch() {
  state.searchIds = null;
  renderList();
  keepResultsInView();
  searchOnServer(state.query);
}

const shortText = (text, max = 42) => {
  const flat = String(text).replace(/\s+/g, ' ').trim();
  return flat.length > max ? flat.slice(0, max - 1) + '…' : flat;
};

function addressPickerHtml(addresses, picked) {
  if (!addresses.length) return '';
  const options = addresses.map(item =>
    `<option value="${escapeHtml(item.id)}"${item === picked ? ' selected' : ''}>${escapeHtml(item.label)}${item.main ? ' (utama)' : ''}: ${escapeHtml(shortText(item.address))}</option>`).join('');
  return `<div class="field"><label>Kirim ke</label><select class="select" data-addr-pick>${options}<option value="">Alamat lain…</option></select></div>`;
}

function saveAddressHtml(addresses) {
  const first = addresses.length === 0;
  return `<label class="save-addr" data-save-addr${first ? '' : ' hidden'}><input type="checkbox" class="tick" name="save_address" value="1"${first ? ' checked' : ''}> Simpan alamat ini di akun saya</label>`;
}

function openCheckout() {
  const lines = cartLines();
  if (!lines.length) return;

  closeCart();
  const subtotal = cartTotal(lines);
  const fee = shippingFeeFor(subtotal, 'delivery');
  const addresses = myAddresses();
  const picked = addresses.find(item => item.main) || addresses[0] || null;
  const start = picked || { recipient: state.user.name, phone: '', address: '' };
  const summary = lines.map(({ product, qty }) =>
    `<li><span>${productEmoji(product)} ${escapeHtml(product.name)} <em>× ${qty}</em></span><b class="num">${formatRupiah(product.price * qty)}</b></li>`
  ).join('');
  const options = labels => Object.entries(labels).map(([value, text]) => `<option value="${value}">${text}</option>`).join('');
  const freeHint = state.shipping.fee && state.shipping.freeMin
    ? `<p class="muted small" style="margin:-6px 0 12px">Gratis ongkir untuk belanja mulai ${formatRupiah(state.shipping.freeMin)}.</p>` : '';
  const transferNote = state.payInfo
    ? `<div class="r-note" data-co-note="transfer">Bayar ke: <b>${escapeHtml(state.payInfo)}</b>. Pesanan diproses setelah admin mengonfirmasi pembayaran.</div>`
    : '';
  const cashNote = '<div class="r-note" data-co-note="cash" hidden>Bayar tunai saat pesanan diterima atau diambil. Siapkan uang pas bila bisa.</div>';
  const qrisNote = `<div class="r-note" data-co-note="qris" hidden>Kode QRIS tampil setelah pesanan dibuat. Bayar dalam ${state.qrisMinutes} menit; begitu pembayaran diterima, status pesanan otomatis menjadi dibayar.</div>`;

  const ewalletNote = Object.keys(PAYMENT_LABEL).filter(isEwallet).map(code =>
    `<div class="r-note" data-co-note="${code}" hidden>${code === 'ewallet_ovo' ? 'Setelah pesanan dibuat, segera buka aplikasi OVO (nomor HP di atas harus nomor OVO Anda) lalu setujui pembayaran. Permintaan OVO cepat kedaluwarsa.' : `Setelah pesanan dibuat, Anda diarahkan ke ${PAYMENT_LABEL[code]} untuk membayar.`} Bayar dalam ${state.ewalletMinutes[code] || 15} menit; status pesanan otomatis menjadi dibayar.</div>`).join('');

  openModal(`<h3>Buat pesanan</h3><p class="sub">${lines.length} produk, total <b class="num" data-co-total>${formatRupiah(subtotal + fee)}</b></p>
      <ul class="sum">${summary}<li><span data-co-ship-label>Ongkos kirim</span><b class="num" data-co-ship>${fee ? formatRupiah(fee) : 'Gratis'}</b></li></ul>
      <form data-form="checkout" novalidate><div class="form-alert" role="alert"></div>
        <div class="field"><label>Pengiriman</label><select class="select" name="shipping_method" data-co-pick>${options(SHIPPING_LABEL)}</select></div>
        ${freeHint}
        <div data-co-addr>${addressPickerHtml(addresses, picked)}</div>
        <div class="field"><label>Nama penerima</label><input class="input" name="recipient" required maxlength="50" autocomplete="name" value="${escapeHtml(start.recipient)}"></div>
        <div class="field"><label>Nomor HP / WhatsApp</label><input class="input" name="phone" type="tel" inputmode="tel" required maxlength="20" placeholder="Contoh: 081234567890" autocomplete="tel" value="${escapeHtml(start.phone)}"><div class="muted small" data-co-phone-hint hidden style="margin-top:6px">Untuk OVO, isi dengan nomor HP yang terdaftar di aplikasi OVO.</div></div>
        <div data-co-addr>
          <div class="field"><label>Alamat pengiriman</label><textarea class="input" name="address" required minlength="5" maxlength="160" placeholder="Nama jalan, nomor, kota" autocomplete="street-address">${escapeHtml(start.address)}</textarea></div>
          ${saveAddressHtml(addresses)}
        </div>
        <div class="field"><label>Catatan untuk penjual (opsional)</label><input class="input" name="note" maxlength="200"></div>
        <div class="field"><label>Pembayaran</label><select class="select" name="payment_method" data-co-pick>${options(paymentChoices())}</select></div>
        <div data-co-ewallet hidden><fieldset class="ew-pick"><legend>Pilih e-wallet</legend><div class="ew-grid">${Object.keys(ewalletChoices()).map((code, n) => `<label class="ew-opt"><input type="radio" name="ewallet_channel" value="${code}" data-co-pick${n ? '' : ' checked'} disabled>${ewalletBadgeHtml(code)}</label>`).join('')}</div></fieldset></div>
        ${transferNote}${cashNote}${qrisNote}${ewalletNote}
        <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Buat pesanan (${formatRupiah(subtotal + fee)})</button></div></form>`);
}

function updateCheckout(form) {
  const subtotal = cartTotal(cartLines());
  const shipping = form.elements.shipping_method.value;
  const group = form.elements.payment_method.value;
  const isWallet = group === EWALLET_GROUP;
  const picked = $('input[name=ewallet_channel]:checked', form);
  const payment = isWallet ? (picked ? picked.value : '') : group;
  const fee = shippingFeeFor(subtotal, shipping);
  const total = formatRupiah(subtotal + fee);
  const modal = form.closest('.modal');

  $('[data-co-total]', modal).textContent = total;
  $('[data-co-ship-label]', modal).textContent = shipping === 'pickup' ? 'Ambil di toko' : 'Ongkos kirim';
  $('[data-co-ship]', modal).textContent = fee ? formatRupiah(fee) : 'Gratis';
  $$('[data-co-addr]', form).forEach(el => { el.hidden = shipping === 'pickup'; });
  $('[data-co-ewallet]', form).hidden = !isWallet;
  $$('input[name=ewallet_channel]', form).forEach(radio => { radio.disabled = !isWallet; });
  $$('[data-co-note]', form).forEach(el => { el.hidden = el.dataset.coNote !== payment; });
  const phoneHint = $('[data-co-phone-hint]', form);
  if (phoneHint) phoneHint.hidden = payment !== 'ewallet_ovo';
  $('button[type=submit]', form).textContent = `Buat pesanan (${total})`;
}

function pickCheckoutAddress(select) {
  const form = select.closest('form');
  const item = findAddress(select.value);
  const set = (name, value) => { const input = form.elements[name]; if (input) input.value = value; };
  set('recipient', item ? item.recipient : state.user.name);
  set('phone', item ? item.phone : '');
  set('address', item ? item.address : '');

  const save = $('[data-save-addr]', form);
  if (save) {
    const offer = !item && myAddresses().length < ADDRESS_LIMIT;
    save.hidden = !offer;
    const box = $('input', save);
    if (box && !offer) box.checked = false;
  }
}

// Satu percobaan checkout memakai kunci yang sama, supaya klik ganda tidak membuat pesanan ganda
function checkoutKey(items, ...options) {
  const signature = JSON.stringify([items, ...options]);
  const current = state.checkout;
  const fresh = current && current.signature === signature && Date.now() - current.at < CHECKOUT_KEY_TTL_MS;
  if (!fresh) state.checkout = { signature, key: newRequestKey(), at: Date.now() };
  return state.checkout.key;
}

async function refreshAfterStockConflict(err) {
  closeModal();
  toast(err.message, 'err');
  if (state.view === 'shop') await reload();
  else await loadProducts();
  drawCart();
  openCart();
}


function filterOrders(el) {
  state.orderFilter = el.dataset.s;
  withTransition(() => {
    $('#orail').innerHTML = orderRailHtml();
    $('#olist').innerHTML = orderCards();
    $('#orail .active')?.focus({ preventScroll: true });
  });
}

// Bukti transfer: foto dikecilkan di browser (sisi terpanjang 1000 px, sekitar 120 KB) lalu dikirim sebagai data URL
async function uploadProof(input) {
  const file = input.files?.[0];
  const id = input.dataset.id;
  input.value = '';
  if (!file || !id) return;

  const button = input.closest('.r-proof')?.querySelector('[data-act="proof-pick"]');
  const label = button?.textContent;
  if (button) { button.disabled = true; button.textContent = 'Mengunggah…'; }
  try {
    const image = await compressImage(file, { side: 1000, target: 120 * 1024, limit: 200 * 1024 });
    const { order } = await api(`/orders/${id}/proof`, { method: 'POST', body: { image } });
    const index = state.orders.findIndex(item => item.id === id);
    if (index >= 0) state.orders[index] = order;
    toast('Bukti transfer terkirim. Admin akan mengecek pembayaran Anda.', 'ok');
    if ($(`#modal-root [data-order="${id}"]`)) orderDetailModal(order);
    if (state.view === 'orders' && $('#olist')) $('#olist').innerHTML = orderCards();
  } catch (err) {
    toast(err.fields?.image || err.message, 'err');
    if (button && button.isConnected) { button.disabled = false; button.textContent = label; }
  }
}

function openOrder(el) {
  const order = state.orders.find(item => item.id === el.dataset.id);
  if (order) orderDetailModal(order);
}

async function deleteOrder(el) {
  const order = state.orders.find(item => item.id === el.dataset.id);
  if (!order) return;
  const ok = await confirmDialog(`Hapus pesanan ${order.code}?`, 'Pesanan hilang dari daftar Anda. Toko tetap menyimpan catatannya untuk laporan.', 'Hapus', true);
  if (!ok) { orderDetailModal(order); return; }
  try {
    await api('/orders/' + order.id, { method: 'DELETE', body: {} });
    toast('Pesanan dihapus', 'ok');
  } catch (err) {
    toast(err.message, 'err');
  }
  await reload();
}

async function clearOrderHistory() {
  const ok = await confirmDialog('Bersihkan riwayat?', 'Semua pesanan selesai atau dibatalkan dihapus dari daftar Anda. Pesanan yang masih berjalan tidak ikut terhapus.', 'Bersihkan', true);
  if (!ok) return;
  try {
    const { removed } = await api('/orders/clear-history', { method: 'POST', body: {} });
    toast(removed ? `${removed} pesanan dihapus` : 'Tidak ada riwayat untuk dibersihkan', 'ok');
  } catch (err) {
    toast(err.message, 'err');
  }
  await reload();
}

async function resolvePaymentIssue(el) {
  const confirmed = await confirmDialog('Sudah ditangani?', 'Pastikan dana sudah dikembalikan atau selisihnya sudah dibereskan di Dashboard Xendit. Penanda akan dihapus dari pesanan ini.', 'Ya, sudah');
  if (!confirmed) return;
  try {
    await api(`/orders/${el.dataset.id}/issue-resolved`, { method: 'POST', body: {} });
    if ($('#modal-root').firstChild) closeModal();
    toast('Penanda dihapus', 'ok');
    await reload();
  } catch (err) {
    toast(err.message, 'err');
  }
}

async function changeOrderStatus(el) {
  const { id, status } = el.dataset;

  if (status === 'cancelled') {
    const confirmed = await confirmDialog('Batalkan pesanan?', 'Stok produk dikembalikan dan pesanan tidak bisa dibuka lagi.', 'Batalkan pesanan', true);
    if (!confirmed) return;
  }

  el.classList.add('loading');
  el.disabled = true;
  try {
    await api(`/orders/${id}/status`, { method: 'PATCH', body: { status } });
    if ($('#modal-root').firstChild) closeModal();
    toast('Status pesanan diperbarui', 'ok');
    state.justUpdatedOrderId = id;
    await reload();
    state.justUpdatedOrderId = null;
  } catch (err) {
    toast(err.message, 'err');
    await reload();
  }
}

const QRIS_POLL_MS = 1500;
let qrisBusy = false;

function showQrisResult(id, status) {
  const boxes = $$('[data-qris]').filter(box => box.dataset.qris === id);
  if (!boxes.length) return;

  for (const box of boxes) {
    if (status === 'cancelled') {
      box.innerHTML = '<div class="qris-ok bad"><b>Pesanan dibatalkan</b><span>Waktu bayar habis atau pesanan dibatalkan.</span></div>';
    } else {
      box.innerHTML = qrisPaidHtml();
      box.classList.add('paid');
      burst($('.done-ic', box));
    }
    // Setelah pembayaran selesai atau dibatalkan, ajakan "bayar" di modal sukses tidak relevan lagi
    box.closest('.modal')?.querySelector('.done .sub')?.remove();
    box.removeAttribute('data-qris');
  }
  const order = state.orders.find(item => item.id === id);
  if (order) order.status = status;
  if (state.view === 'orders') {
    setTimeout(async () => {
      if (state.view !== 'orders') return;
      await reload();
      const fresh = $(`#modal-root [data-order="${id}"]`) && state.orders.find(item => item.id === id);
      if (fresh) orderDetailModal(fresh);
    }, 1600);
  }
}

// Hitung mundur batas bayar: semua elemen [data-expires] diperbarui tiap detik
let lastExpiredReload = 0;
function tickTimers() {
  for (const el of $$('[data-expires]')) {
    const left = msLeft(el.dataset.expires);
    el.textContent = countdownText(left);
    el.classList.toggle('late', left < 5 * 60 * 1000);
    if (left > 0 || el.dataset.done) continue;
    el.dataset.done = '1';
    // Waktu habis: server memastikan statusnya, lalu tampilan ikut berubah
    if (el.closest('[data-qris]')) pollQris();
    else if (state.view === 'orders' && Date.now() - lastExpiredReload > 5000) { lastExpiredReload = Date.now(); reload(); }
  }
}

// Layar QR memantau status pesanan sampai dibayar atau dibatalkan
async function pollQris() {
  if (qrisBusy || document.hidden) return;
  const ids = [...new Set($$('[data-qris]').map(box => box.dataset.qris))];
  if (!ids.length) return;

  qrisBusy = true;
  try {
    for (const id of ids) {
      try {
        const { status } = await api(`/orders/${id}/status`);
        if (status !== 'pending') showQrisResult(id, status);
      } catch (err) {
        if (err.status === 401) return;
      }
    }
  } finally {
    qrisBusy = false;
  }
}

async function copyToClipboard(el) {
  try {
    await navigator.clipboard.writeText(el.dataset.text);
    toast(el.dataset.label + ' disalin');
  } catch {
    toast('Tidak bisa menyalin, salin manual', 'err');
  }
}

async function confirmAndDelete({ title, message, okLabel, path, successMessage }) {
  const confirmed = await confirmDialog(title, message, okLabel, true);
  if (!confirmed) return;

  try {
    await api(path, { method: 'DELETE' });
    toast(successMessage, 'ok');
    await reload();
  } catch (err) {
    toast(err.message, 'err');
  }
}

function deleteProduct(el) {
  const product = state.productMap[el.dataset.id];
  return confirmAndDelete({
    title: 'Hapus produk?',
    message: `"${product.name}" dihapus dari katalog. Pesanan lama tetap menyimpan datanya.`,
    okLabel: 'Hapus produk',
    path: '/products/' + product.id,
    successMessage: 'Produk dihapus'
  });
}

function resetProductQuery() {
  clearTimeout(searchDebounce);
  state.query = '';
}

function clearProductSearch() {
  resetProductQuery();
  applyProductFilter();
  $('[data-input="prod-search"]')?.focus();
}

function resetProductFilter() {
  resetProductQuery();
  state.productFilter = emptyProductFilter();
  applyProductFilter();
}

function setProductGroup(el) {
  state.productFilter.group = el.dataset.group;
  applyProductFilter();
}

function setProductCategory(select) {
  state.productFilter.category = select.value;
  applyProductFilter();
}

async function dashboardGo(el) {
  const { view, status, group } = el.dataset;
  if (status !== undefined) state.orderFilter = status;
  await show(view);
  if (group) { state.productFilter.group = group; applyProductFilter(); }
}

function deleteUser(el) {
  const user = state.users.find(u => u.id === el.dataset.id);
  return confirmAndDelete({
    title: 'Hapus pengguna?',
    message: `Akun @${user.username} dihapus permanen.`,
    okLabel: 'Hapus akun',
    path: '/users/' + user.id,
    successMessage: 'Akun dihapus'
  });
}

function confirmMakeAdmin(id) {
  const target = state.users.find(user => user.id === id);
  const who = target ? '@' + target.username : 'Pengguna ini';
  return confirmDialog('Jadikan Admin?', `${who} akan bisa mengelola produk, pesanan, dan melihat pendapatan toko.`, 'Jadikan Admin');
}

async function changeUserSetting(el) {
  const { id, change } = el.dataset;
  try {
    if (change === 'user-role') {
      if (el.value === 'admin' && !(await confirmMakeAdmin(id))) { await reload(); return; }
      await api('/users/' + id, { method: 'PATCH', body: { role: el.value } });
    } else if (change === 'user-active') {
      await api('/users/' + id, { method: 'PATCH', body: { active: el.checked } });
    }
    toast('Perubahan disimpan', 'ok');
    await reload();
  } catch (err) {
    toast(err.message, 'err');
    await reload();
  }
}

function pickLog(el) {
  if (el.checked) state.selectedLogs.add(el.dataset.id);
  else state.selectedLogs.delete(el.dataset.id);
  syncLogSelection();
}

function pickAllLogs(el) {
  state.selectedLogs.clear();
  if (el.checked) visibleLogIds().forEach(id => state.selectedLogs.add(id));
  syncLogSelection();
}

function clearLogSelection() {
  state.selectedLogs.clear();
  syncLogSelection();
}

async function deleteLogs(ids) {
  if (!ids.length) return;
  const many = ids.length > 1;
  const confirmed = await confirmDialog(
    many ? `Hapus ${ids.length} log?` : 'Hapus log ini?',
    'Log yang dihapus tidak bisa dikembalikan.',
    many ? `Hapus ${ids.length} log` : 'Hapus log',
    true
  );
  if (!confirmed) return;

  try {
    const { deleted } = await api('/logs/delete', { method: 'POST', body: { ids } });
    ids.forEach(id => state.selectedLogs.delete(id));
    toast(`${deleted} log dihapus`, 'ok');
    await reload();
  } catch (err) {
    toast(err.message, 'err');
  }
}

function typeLogSearch(input) {
  state.logFilter.q = input.value;
  const clear = $('.log-q-clear');
  if (clear) clear.hidden = !input.value;
  clearTimeout(logSearchTimer);
  logSearchTimer = setTimeout(applyLogFilter, LOG_SEARCH_DEBOUNCE_MS);
}

function setLogGroup(el) {
  state.logFilter.group = el.dataset.group;
  applyLogFilter();
}

function setLogAction(el) {
  state.logFilter.action = el.value;
  applyLogFilter();
}

function clearLogSearch() {
  state.logFilter.q = '';
  applyLogFilter();
  $('[data-log-q]')?.focus();
}

function resetLogFilter() {
  state.logFilter = emptyLogFilter();
  applyLogFilter();
}


const profileMenuOpen = () => Boolean($('#app .pm-pop:not([hidden])'));

function setProfileMenu(open, { focus = false } = {}) {
  const root = $('#app .pm');
  if (!root) return;
  const button = $('.pm-btn', root);
  $('.pm-pop', root).hidden = !open;
  root.classList.toggle('open', open);
  $('#app .top')?.classList.toggle('menu-open', open);
  button.setAttribute('aria-expanded', String(open));
  if (open) { syncInstall(); $('[role=menuitem]:not([hidden])', root)?.focus(); }
  else if (focus) button.focus();
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

function togglePasswordVisibility(checkbox) {
  $$('input[name=password],input[name=confirm],input[data-pw]', checkbox.closest('form')).forEach(input => {
    input.type = checkbox.checked ? 'text' : 'password';
  });
}

function updatePasswordChecks(form) {
  const password = form.elements.new_password.value;
  const rules = {
    len: password.length >= 8,
    letter: /[A-Za-z]/.test(password),
    digit: /\d/.test(password),
    match: password !== '' && password === form.elements.confirm.value
  };
  $$('[data-check]', form).forEach(item => item.toggleAttribute('data-ok', rules[item.dataset.check]));
}

function loginEmailHint() {
  const typed = ($('#f-id')?.value || '').trim();
  return typed.includes('@') ? typed : '';
}

function startResendCountdown(button, seconds) {
  clearInterval(resendTimer);
  if (!button) return;
  const box = button.closest('.resend');
  const endAt = Date.now() + seconds * 1000;
  const paint = () => {
    if (!button.isConnected) { clearInterval(resendTimer); return; }
    const left = Math.ceil((endAt - Date.now()) / 1000);
    if (left <= 0) {
      clearInterval(resendTimer);
      button.disabled = false;
      button.textContent = 'Kirim ulang kode';
      if (box) { box.classList.add('ready'); box.style.setProperty('--left', '0%'); }
      return;
    }
    button.disabled = true;
    button.textContent = `Kirim ulang dalam ${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;
    if (box) { box.classList.remove('ready'); box.style.setProperty('--left', Math.min(100, left / seconds * 100) + '%'); }
  };
  paint();
  resendTimer = setInterval(paint, 1000);
}

async function resendResetCode(button) {
  const flow = state.reset;
  const form = button.closest('form');
  if (!flow || !form) return;

  button.disabled = true;
  button.textContent = 'Mengirim…';
  try {
    const result = await api('/auth/forgot', { method: 'POST', body: { email: flow.sentTo || flow.email } });
    const retryAfter = Number(result.retry_after) || 60;
    flow.endAt = Date.now() + retryAfter * 1000;
    flow.code = '';
    toast('Jika email terdaftar, kode baru sudah dikirim. Kode lama tidak berlaku lagi.', 'ok');
    clearErrors(form);
    const input = form.elements.code;
    input.value = '';
    renderOtp(input.closest('[data-otp]'));
    input.focus();
    startResendCountdown(button, retryAfter);
  } catch (err) {
    toast(err.message, 'err');
    button.disabled = false;
    button.textContent = 'Kirim ulang kode';
  }
}

function onOtpInput(wrap) {
  renderOtp(wrap);
  const input = $('.otp-input', wrap);
  if (input.value.length !== 6) return;

  wrap.classList.add('wave');
  setTimeout(() => wrap.classList.remove('wave'), 900);

  const form = wrap.closest('form');
  clearTimeout(otpTimer);
  otpTimer = setTimeout(() => {
    const panel = form.closest('.wz-panel');
    if (!form.isConnected || (panel && panel.hidden) || input.value.length !== 6) return;
    if (form.requestSubmit) form.requestSubmit();
    else $('button[type=submit]', form)?.click();
  }, reducedMotion.matches ? 120 : 480);
}

function onOtpFocus(e) {
  const wrap = e.target.closest?.('[data-otp]');
  if (wrap) renderOtp(wrap);
}

function onOtpPointer(e) {
  const wrap = e.target.closest?.('[data-otp]');
  const input = wrap && $('.otp-input', wrap);
  if (!input) return;
  requestAnimationFrame(() => {
    try { input.setSelectionRange(input.value.length, input.value.length); } catch { }
  });
}

function wizardBack() {
  const panel = $('#modal-root .wz-panel:not([hidden])');
  const step = panel ? Number(panel.dataset.panel) : 1;
  if (step > 1 && step < 4) showResetStep(step - 1);
}

function finishReset() {
  closeModal();
  const field = $('#f-pw') || $('#f-id');
  if (field) field.focus();
}

async function backToCodeStep(err) {
  const form = $('#modal-root form[data-form="code"]');
  if (!form) return;
  state.reset.code = '';
  const input = form.elements.code;
  input.value = '';
  renderOtp(input.closest('[data-otp]'));
  clearErrors(form);
  await showResetStep(2);
  if (form.isConnected) showErrors(form, createError(err.message, { fields: { code: CODE_REJECTED } }));
}


const actions = {
  'auth-tab': el => renderAuth(el.dataset.tab),
  nav: el => show(el.dataset.view),
  'dash-go': dashboardGo,
  reload,
  logout,
  'refresh-page': () => location.reload(),

  'close-modal': closeModal,
  overlay: (el, e) => { if (e.target === el && !el.querySelector('[data-keep]')) closeModal(); },
  'ask-ok': confirmAccepted,

  cat: filterByCategory,
  'open-filter': filterModal,
  'apply-filter': applyFilters,
  'reset-filters': resetFilters,
  'rm-filter': removeFilter,
  'clear-all': clearAllFilters,
  'clear-search': clearSearch,
  layout: setLayout,
  more: loadMoreProducts,
  'to-top': () => window.scrollTo({ top: 0, behavior: 'smooth' }),
  'rail-prev': () => scrollRail(-1),
  'rail-next': () => scrollRail(1),
  detail: openProductDetail,
  'detail-add': addFromProductDetail,

  'add-cart': addOneToCart,
  'cart-inc': addOneToCart,
  'cart-dec': el => setCartQty(el.dataset.id, cartQty(el.dataset.id) - 1),
  'cart-del': removeFromCart,
  'open-cart': openCart,
  'close-cart': closeCart,
  checkout: openCheckout,
  ofilter: filterOrders,
  copy: copyToClipboard,
  'order-open': openOrder,
  'order-del': deleteOrder,
  'orders-clear': clearOrderHistory,
  reorder,
  'order-status': changeOrderStatus,
  'issue-done': resolvePaymentIssue,

  'product-new': () => productModal(null),
  'product-edit': el => productModal(state.productMap[el.dataset.id]),
  'product-del': deleteProduct,
  'prod-group': setProductGroup,
  'prod-q-clear': clearProductSearch,
  'prod-reset': resetProductFilter,
  'photo-pick': el => choosePhoto(el.closest('form')),
  'proof-pick': el => el.closest('.r-proof')?.querySelector('[data-proof-input]')?.click(),
  'photo-clear': el => clearPhoto(el.closest('form')),

  'user-new': userModal,
  'user-del': deleteUser,

  'profile-menu': () => setProfileMenu(!profileMenuOpen()),
  'profile-open': openProfile,
  'profile-close': () => setProfileMenu(false, { focus: true }),
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
  'push-toggle': togglePush,
  'push-test': testPush,

  'toggle-pw': togglePasswordVisibility,
  'forgot-open': () => forgotModal(loginEmailHint()),
  'forgot-resend': resendResetCode,
  'wiz-back': wizardBack,
  'wiz-finish': finishReset,

  'log-pick': pickLog,
  'log-pick-all': pickAllLogs,
  'log-clear': clearLogSelection,
  'log-group': setLogGroup,
  'log-q-clear': clearLogSearch,
  'log-reset': resetLogFilter,
  'log-del': el => deleteLogs([el.dataset.id]),
  'log-del-selected': () => deleteLogs([...state.selectedLogs])
};


function clearErrors(form) {
  $$('.invalid', form).forEach(input => { input.classList.remove('invalid'); input.removeAttribute('aria-invalid'); });
  $$('.field-err', form).forEach(msg => msg.remove());
  $('.form-alert', form)?.classList.remove('show');
}

function showErrors(form, err) {
  const invalid = [];
  Object.entries(err.fields || {}).forEach(([name, message]) => {
    const input = form.querySelector(`[name="${CSS.escape(name)}"]`);
    if (!input) return;
    input.classList.remove('invalid');
    void input.offsetWidth;
    input.classList.add('invalid');
    input.setAttribute('aria-invalid', 'true');

    const hint = document.createElement('small');
    hint.className = 'field-err';
    hint.setAttribute('role', 'alert');
    hint.textContent = message;
    (input.closest('.field') || input.parentNode).appendChild(hint);
    invalid.push(input);
  });

  const alert = $('.form-alert', form);
  if (alert) {
    alert.textContent = invalid.length ? '' : err.message;
    alert.classList.toggle('show', !invalid.length);
    if (!invalid.length) alert.scrollIntoView({ block: 'nearest' });
  }

  invalid.find(input => input.type !== 'hidden')?.focus();
}

function clearFieldError(input) {
  input.classList.remove('invalid');
  input.removeAttribute('aria-invalid');
  $('.field-err', input.closest('.field') || input.parentNode)?.remove();
  const form = input.closest('form');
  if (form && !$('.invalid', form)) $('.form-alert', form)?.classList.remove('show');
}

const passwordProblem = password =>
  password.length >= 8 && /[A-Za-z]/.test(password) && /\d/.test(password)
    ? ''
    : 'Password minimal 8 karakter dan mengandung huruf serta angka';

const mismatchError = () => validationError({ confirm: 'Konfirmasi password tidak sama' });

function checkNewPassword(data) {
  const weak = passwordProblem(data.new_password || '');
  if (weak) throw validationError({ new_password: weak });
  if (data.new_password !== data.confirm) throw mismatchError();
}

const formHandlers = {
  async login(form, data) {
    const result = await api('/auth/login', { method: 'POST', body: { identifier: data.identifier, password: data.password } });
    await onAuthed(result);
  },

  async register(form, data) {
    if (data.password !== data.confirm) throw mismatchError();
    const result = await api('/auth/register', {
      method: 'POST',
      body: { name: data.name, username: data.username, email: data.email, password: data.password }
    });
    await onAuthed(result);
  },

  async product(form, data) {
    const id = form.dataset.id;
    await api(id ? '/products/' + id : '/products', { method: id ? 'PUT' : 'POST', body: data });
    closeModal();
    toast(id ? 'Produk diperbarui' : 'Produk ditambahkan', 'ok');
    await reload();
  },

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

  async forgot(form, data) {
    const email = cleanText(data.email).toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(email)) throw validationError({ email: 'Format email tidak valid' });

    const flow = state.reset;
    const alreadySent = flow.sentTo === email && Date.now() < flow.endAt;
    if (!alreadySent) {
      const result = await api('/auth/forgot', { method: 'POST', body: { email } });
      const retryAfter = Number(result.retry_after) || 60;
      flow.sentTo = email;
      flow.endAt = Date.now() + retryAfter * 1000;
      flow.code = '';
      const input = $('#modal-root input[name=code]');
      if (input) { input.value = ''; renderOtp(input.closest('[data-otp]')); }
      setResetInfo({ expires: Number(result.expires_minutes) || 15 });
      startResendCountdown($('#modal-root [data-act="forgot-resend"]'), retryAfter);
    }
    flow.email = email;
    setResetInfo({ email });
    showResetStep(2);
  },

  async code(form, data) {
    const code = String(data.code || '').replace(/\D/g, '');
    if (!/^\d{6}$/.test(code)) throw validationError({ code: 'Kode terdiri dari 6 angka' });

    const flow = state.reset;
    try {
      await api('/auth/reset/check', { method: 'POST', body: { email: flow.sentTo || flow.email, code } });
    } catch (err) {
      if (err.fields && err.fields.code) {
        const input = form.elements.code;
        input.value = '';
        renderOtp(input.closest('[data-otp]'));
        throw createError(err.message, { fields: { code: CODE_REJECTED } });
      }
      throw err;
    }
    flow.code = code;
    showResetStep(3);
  },

  async reset(form, data) {
    checkNewPassword(data);
    const flow = state.reset;
    const email = flow.sentTo || flow.email;
    try {
      await api('/auth/reset', { method: 'POST', body: { email, code: flow.code, new_password: data.new_password } });
    } catch (err) {
      if (err.fields && err.fields.code) {
        await backToCodeStep(err);
        return;
      }
      throw err;
    }

    flow.code = '';
    form.elements.new_password.value = '';
    form.elements.confirm.value = '';
    updatePasswordChecks(form);

    const identifier = $('#f-id');
    if (identifier) identifier.value = email;
    showResetStep(4);
  },

  async 'user-create'(form, data) {
    await api('/users', { method: 'POST', body: data });
    closeModal();
    toast('Akun dibuat', 'ok');
    await reload();
  },

  async checkout(form, data) {
    const phone = normalizePhone(data.phone);
    if (!PHONE_RE.test(phone)) throw validationError({ phone: PHONE_ERROR });

    const recipient = cleanText(data.recipient);
    if (recipient.length < 2) throw validationError({ recipient: RECIPIENT_ERROR });
    const pickup = data.shipping_method === 'pickup';
    const address = pickup ? '' : cleanText(data.address);
    if (!pickup && address.length < 5) throw validationError({ address: 'Alamat minimal 5 karakter' });

    // Harga ikut dikirim: server menolak (409) bila harga katalog sudah berubah
    const items = cartLines().map(line => ({ product_id: line.product.id, qty: line.qty, price: line.product.price }));
    const payment = chosenPayment(data);
    let result;
    try {
      result = await api('/orders', {
        method: 'POST',
        body: { items, phone, address, recipient, note: data.note, shipping_method: data.shipping_method, payment_method: payment },
        headers: { 'Idempotency-Key': checkoutKey(items, data.shipping_method, payment) }
      });
    } catch (err) {
      if (err.status === 409 || err.status === 404) return refreshAfterStockConflict(err);
      throw err;
    }

    state.checkout = null;
    state.cart = {};
    if (!pickup && data.save_address === '1' && myAddresses().length < ADDRESS_LIMIT) {
      try {
        const saved = await api('/auth/addresses', {
          method: 'POST',
          body: { label: 'Rumah', recipient, phone, address, main: !myAddresses().length }
        });
        state.user.addresses = saved.addresses;
      } catch { }
    }
    closeModal();
    await show('orders');
    showOrderSuccess(result.order);
  }
};

async function onSubmit(e) {
  const form = e.target.closest('form[data-form]');
  if (!form) return;
  e.preventDefault();

  const handler = formHandlers[form.dataset.form];
  if (!handler) return;

  const submitButton = $('button[type=submit]', form);
  clearErrors(form);
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.classList.add('loading');
  }

  try {
    await handler(form, Object.fromEntries(new FormData(form)));
  } catch (err) {
    if (form.isConnected) showErrors(form, err);
    else toast(err.message, 'err');
  } finally {
    if (submitButton && submitButton.isConnected) {
      submitButton.disabled = false;
      submitButton.classList.remove('loading');
    }
  }
}


function onClick(e) {
  if (profileMenuOpen() && !e.target.closest('.pm')) setProfileMenu(false);
  const el = e.target.closest('[data-act]');
  if (!el) return;
  if (el.closest('.pm-pop') && profileMenuOpen()) setProfileMenu(false, { focus: true });
  actions[el.dataset.act]?.(el, e);
}

async function onChange(e) {
  const target = e.target;
  if (target.matches('[data-log-action]')) { setLogAction(target); return; }
  if (target.matches('[data-prod-category]')) { setProductCategory(target); return; }
  if (target.matches('[data-photo-input]')) { await handlePhotoInput(target); return; }
  if (target.matches('[data-proof-input]')) { await uploadProof(target); return; }
  if (target.matches('[data-addr-pick]')) { pickCheckoutAddress(target); return; }
  if (target.matches('[data-co-pick]')) { updateCheckout(target.closest('form')); return; }

  if (target.matches('[data-sort]')) {
    state.sort = target.value;
    renderList();
    keepResultsInView();
    return;
  }

  const el = target.closest('[data-change]');
  if (el) await changeUserSetting(el);
}

function syncDigitsInput(target) {
  const digits = target.closest('[data-digits]');
  if (!digits) return;
  const clean = digits.value.replace(/\D/g, '').slice(0, 6);
  if (clean !== digits.value) digits.value = clean;
  const otp = digits.closest('[data-otp]');
  if (otp) onOtpInput(otp);
}

function syncPasswordChecks(target) {
  const form = target.closest('form[data-pwcheck]');
  if (!form) return;
  updatePasswordChecks(form);
  const { new_password, confirm } = form.elements;
  if (confirm.classList.contains('invalid') && confirm.value === new_password.value) clearFieldError(confirm);
}

function syncSearchInput(target) {
  const el = target.closest('[data-input]');
  if (!el) return;

  const isShop = el.dataset.input === 'shop-search';
  state.query = el.value;
  if (isShop) {
    const clearButton = $('.search .clear');
    if (clearButton) clearButton.hidden = !el.value;
  }
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(isShop ? runShopSearch : applyProductFilter, SEARCH_DEBOUNCE_MS);
}

function onInput(e) {
  const target = e.target;
  if (target.matches('[data-log-q]')) { typeLogSearch(target); return; }
  if (target.classList?.contains('invalid')) clearFieldError(target);
  syncDigitsInput(target);
  syncPasswordChecks(target);
  syncSearchInput(target);
}

function handleEscape(modalOpen) {
  if (profileMenuOpen()) { setProfileMenu(false, { focus: true }); return; }
  const active = document.activeElement;
  if (modalOpen) closeModal();
  else if (active?.matches?.('[data-input=shop-search]') && active.value) clearSearch();
  else closeCart();
}

function moveMenuFocus(e) {
  const items = $$('#app .pm-pop [role=menuitem]').filter(item => !item.hidden);
  const at = items.indexOf(document.activeElement);
  const next = e.key === 'ArrowDown' ? (at + 1) % items.length : (at <= 0 ? items.length - 1 : at - 1);
  e.preventDefault();
  items[next].focus();
}

function trapFocus(e) {
  const focusable = $$('#modal-root button:not([disabled]), #modal-root input:not([disabled]), #modal-root select, #modal-root textarea')
    .filter(el => el.offsetParent !== null);
  if (!focusable.length) return;

  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const active = document.activeElement;

  if (!focusable.includes(active)) {
    e.preventDefault();
    first.focus();
  } else if (e.shiftKey && active === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && active === last) {
    e.preventDefault();
    first.focus();
  }
}

function onModalKeydown(e) {
  const modalOpen = Boolean($('#modal-root').firstChild);

  if (e.key === 'Escape') { handleEscape(modalOpen); return; }
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches?.('.receipt[data-act]')) { e.preventDefault(); e.target.click(); return; }
  if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && profileMenuOpen()) { moveMenuFocus(e); return; }
  if (e.key === 'Enter' && e.target.matches?.('#f-min, #f-max')) { e.preventDefault(); applyFilters(); return; }
  if (e.key === 'Tab' && modalOpen) trapFocus(e);
}

function onSearchShortcut(e) {
  if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
  if ($('#modal-root').firstChild) return;
  if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;

  const searchInput = $('.search input');
  if (searchInput) {
    e.preventDefault();
    searchInput.focus();
  }
}

function initDrawerSwipe() {
  const CLOSE_DISTANCE = 90;
  let startY = null;
  let drawer = null;

  document.addEventListener('pointerdown', e => {
    const head = e.target.closest('.drawer-head');
    if (!head || e.target.closest('button') || !MOBILE.matches) return;
    drawer = head.parentNode;
    startY = e.clientY;
    drawer.style.transition = 'none';
  });

  document.addEventListener('pointermove', e => {
    if (startY !== null) drawer.style.transform = `translateY(${Math.max(0, e.clientY - startY)}px)`;
  });

  const endSwipe = e => {
    if (startY === null) return;
    const distance = e.clientY - startY;
    drawer.style.transition = '';
    drawer.style.transform = '';
    startY = null;
    if (distance > CLOSE_DISTANCE) closeCart();
  };
  document.addEventListener('pointerup', endSwipe);
  document.addEventListener('pointercancel', endSwipe);
}

function initShopScroll() {
  let lastY = scrollY;
  let frame = 0;

  const update = () => {
    frame = 0;
    const y = scrollY;
    const toTop = $('.to-top');
    if (toTop) toTop.hidden = y < 900;

    const tools = $('#tools');
    if (!tools) return;
    if (!MOBILE.matches || y < 160 || tools.contains(document.activeElement)) {
      tools.classList.remove('away');
      lastY = y;
    } else if (y - lastY > 8) {
      tools.classList.add('away');
      lastY = y;
    } else if (lastY - y > 8) {
      tools.classList.remove('away');
      lastY = y;
    }
  };

  addEventListener('scroll', () => { if (!frame) frame = requestAnimationFrame(update); }, { passive: true });
  document.addEventListener('scroll', e => { if (e.target.id === 'rail') updateRailEdges(); }, true);
}

function bindEvents() {
  document.addEventListener('click', onClick);
  document.addEventListener('change', onChange);
  document.addEventListener('input', onInput);
  document.addEventListener('focusin', onOtpFocus);
  document.addEventListener('focusin', e => { if (profileMenuOpen() && !e.target.closest('.pm')) setProfileMenu(false); });
  document.addEventListener('focusout', onOtpFocus);
  document.addEventListener('pointerup', onOtpPointer);
  document.addEventListener('keydown', onModalKeydown);
  document.addEventListener('keydown', onSearchShortcut);
  document.addEventListener('submit', onSubmit);
  initDrawerSwipe();
  initShopScroll();

  addEventListener('offline', () => toast('Koneksi terputus. Pesanan baru bisa dibuat setelah tersambung.', 'err'));
  addEventListener('online', () => toast('Tersambung kembali', 'ok'));
}

// Pelanggan kembali dari e-wallet lewat /?bayar=ok atau /?bayar=gagal: buka daftar pesanan dan beri kabar
// Notifikasi pesanan membuka aplikasi lewat /?buka=orders (atau dashboard)
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

async function boot() {
  storage.remove(STORAGE_KEYS.legacyProfile);
  state.layout = storage.get(STORAGE_KEYS.layout) === 'rows' ? 'rows' : 'grid';
  loadSettings();
  applySettings();
  bindEvents();
  setInterval(pollQris, QRIS_POLL_MS);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) pollQris(); });
  addEventListener('pageshow', () => pollQris());
  setInterval(tickTimers, 1000);
  // Notifikasi diketuk saat aplikasi sudah terbuka: pindah ke layar yang diminta
  navigator.serviceWorker?.addEventListener('message', event => {
    if (event.data?.type === 'open-view' && state.user && isStaff()) show(event.data.view);
  });

  try {
    const me = await api('/auth/me');
    state.csrf = me.csrf;
    state.payInfo = me.pay_info || '';
    state.dummyQris = Boolean(me.qris_enabled ?? me.dummy_qris);   // nama lama; artinya "QRIS tersedia" (Xendit atau simulasi)
    state.qrisMinutes = Number(me.qris_minutes) || 60;
    state.ewalletMinutes = me.ewallet_minutes || {};
    state.ewalletOn = Boolean(me.ewallet_enabled);
    if (me.server_time) state.clockSkew = Date.parse(me.server_time) - Date.now();
    state.shipping = { fee: Number(me.shipping?.fee) || 0, freeMin: Number(me.shipping?.free_min) || 0 };
    state.resetEnabled = Boolean(me.reset_enabled);

    const payReturn = takePayReturn();
    const openView = takeOpenView();
    if (me.user) { await startSession(me.user, openView); await handlePayReturn(payReturn); }
    else {
      pendingOpenView = openView;
      renderAuth('login');
      if (payReturn) {
        pendingPayReturn = payReturn;
        toast('Masuk untuk melihat status pembayaran Anda.', 'ok');
      }
    }
  } catch (err) {
    $('#app').innerHTML = `<div class="empty" style="margin:15vh auto;max-width:460px"><b>Aplikasi belum bisa dimuat</b><p>${escapeHtml(err.message)}</p><button class="btn primary" data-act="refresh-page">Muat ulang</button></div>`;
  }
}

boot();