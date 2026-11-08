// TokoBiru - pintu masuk frontend: alur aplikasi, aksi, form, dan event

import {
  $,
  $$,
  MAX_CART_QTY,
  NAV,
  STORAGE_KEYS,
  api,
  cartQty,
  createError,
  defaultView,
  escapeHtml,
  formatRupiah,
  hashString,
  hooks,
  icon,
  isCustomer,
  newRequestKey,
  priceHtml,
  productEmoji,
  state,
  stockInfo,
  storage
} from './core.js';
import {
  animateDashboard,
  closeModal,
  confirmAccepted,
  confirmDialog,
  EASE,
  flyToCart,
  openModal,
  reducedMotion,
  toast,
  withTransition
} from './ui.js';
import {
  aisleHtml,
  cartLines,
  cartTotal,
  categoryRailHtml,
  drawCart,
  forgotModal,
  orderCards,
  orderRailHtml,
  passwordModal,
  productModal,
  productRows,
  renderAuth,
  renderList,
  renderShell,
  resetModal,
  setCartQty,
  showOrderSuccess,
  userModal,
  views
} from './views.js';


// Sesi habis (401): kembali ke halaman masuk
hooks.onSessionExpired = () => {
  state.user = null;
  renderAuth();
  toast('Sesi berakhir. Masuk lagi untuk melanjutkan.', 'err');
  // sesi di server sudah dibersihkan, jadi token CSRF lama tidak berlaku lagi untuk login berikutnya
  api('/auth/me').then(me => { state.csrf = me.csrf; }).catch(() => {});
};

// === Alur aplikasi: sesi, navigasi, pemuatan data ===

async function onAuthed(result) {
  state.csrf = result.csrf;
  state.user = result.user;
  state.cart = storage.get(STORAGE_KEYS.cart(result.user.id)) || {};
  await show(defaultView());
}

async function loadProducts() {
  const result = await api('/products');
  state.products = result.products;
  state.categories = result.categories;
  state.productsTotal = result.total ?? result.products.length;
  state.productMap = Object.fromEntries(result.products.map(p => [p.id, p]));

  // Sesuaikan keranjang dengan katalog terbaru: buang produk yang hilang atau habis, batasi jumlah ke stok
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
  async logs() { state.logs = (await api('/logs')).logs; }
};

async function show(view) {
  const allowed = NAV.some(item => item.id === view && item.roles.includes(state.user.role));
  if (!allowed) view = defaultView();

  state.view = view;
  state.query = '';
  state.fresh = true;
  renderShell();
  window.scrollTo(0, 0);
  await reload();
}

async function reload() {
  try {
    await loaders[state.view]();
    const content = $('#content');
    content.classList.toggle('fresh', state.fresh);   // animasi masuk hanya saat halaman baru dibuka
    content.innerHTML = views[state.view]();
    if (state.view === 'dashboard') animateDashboard(content);
    if (isCustomer()) drawCart();
    if (state.fresh) setTimeout(() => $$('#content .stagger').forEach(el => el.classList.remove('stagger')), 1200);
  } catch (err) {
    if (err.status === 401) return; // sesi berakhir sudah ditangani di api()
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

  if (product && card && current < product.stock) flyToCart($('.ini', card));
  setCartQty(id, current + 1);
}

// === Aksi (handler data-act, dipanggil dari onClick) ===

let cartReturnFocus = null;  // fokus yang dikembalikan saat laci keranjang ditutup

function openCart() {
  cartReturnFocus = document.activeElement;
  $('#drawer').classList.add('open');
  $('#scrim').classList.add('open');
  document.documentElement.classList.add('lock');

  // isi keranjang masuk bergantian setelah laci terbuka
  if (!reducedMotion.matches) {
    $$('#cart-items .citem').slice(0, 8).forEach((el, index) => el.animate(
      [{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }],
      { duration: 380, delay: 140 + index * 45, easing: EASE, fill: 'backwards' }
    ));
  }

  const closeButton = $('#drawer .drawer-head button');
  if (closeButton) closeButton.focus();
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

async function logout() {
  try {
    const result = await api('/auth/logout', { method: 'POST', body: {} });
    state.csrf = result.csrf;
  } catch { /* tetap keluar di sisi klien */ }

  state.user = null;
  state.cart = {};
  state.checkout = null;
  state.query = '';
  state.category = '';
  renderAuth('login');
  toast('Anda sudah keluar');
}

function filterByCategory(el) {
  state.category = el.dataset.cat;
  withTransition(() => {
    $('#rail').innerHTML = categoryRailHtml();
    renderList();
    $('#aisle').innerHTML = aisleHtml();

    const active = $('#rail .active');
    if (active) {
      active.focus({ preventScroll: true });
      active.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
    }
  });
}

function filterOrders(el) {
  state.orderFilter = el.dataset.s;
  withTransition(() => {
    $('#orail').innerHTML = orderRailHtml();
    $('#olist').innerHTML = orderCards();
    const active = $('#orail .active');
    if (active) active.focus({ preventScroll: true });
  });
}

function openProductDetail(el) {
  const product = state.productMap[el.dataset.id];
  if (!product) return;
  const inCart = cartQty(product.id);

  openModal(`<div class="dtile p${hashString(product.id) % 4}"><span class="tag">${escapeHtml(product.category)}</span><span class="ini" aria-hidden="true">${productEmoji(product)}</span></div>
      <h3>${escapeHtml(product.name)}</h3><p class="sub">${escapeHtml(product.description) || 'Belum ada deskripsi untuk produk ini.'}</p>
      <div class="dmeta">${priceHtml(product.price)}${stockInfo(product)}</div>
      ${inCart ? `<p class="muted small" style="margin-bottom:10px">Sudah ${inCart} di keranjang Anda.</p>` : ''}
      <div class="foot"><button class="btn" data-act="close-modal">Tutup</button>
      ${product.stock === 0 ? '' : `<button class="btn primary" data-act="detail-add" data-id="${product.id}">${icon('plus', 15)} Tambah ke keranjang</button>`}</div>`);
}

function addFromProductDetail(el) {
  const id = el.dataset.id;
  const product = state.productMap[id];
  const current = cartQty(id);

  if (product && current < product.stock) flyToCart($('.dtile .ini'));
  closeModal();
  setCartQty(id, current + 1);
}

function removeFromCart(el) {
  const id = el.dataset.id;
  const qty = state.cart[id];
  const name = state.productMap[id].name;

  setCartQty(id, 0);
  toast(`${name} dihapus dari keranjang`, '', { label: 'Urungkan', fn: () => setCartQty(id, qty) });
}

function openCheckout() {
  const lines = cartLines();
  if (!lines.length) return;

  closeCart();
  const total = cartTotal(lines);
  const profile = storage.get(STORAGE_KEYS.profile(state.user.id)) || {};
  const summary = lines.map(({ product, qty }) =>
    `<li><span>${productEmoji(product)} ${escapeHtml(product.name)} <em>× ${qty}</em></span><b class="num">${formatRupiah(product.price * qty)}</b></li>`
  ).join('');
  const payNote = state.payInfo
    ? `<div class="r-note">Bayar ke: <b>${escapeHtml(state.payInfo)}</b>. Pesanan diproses setelah admin mengonfirmasi pembayaran.</div>`
    : '';

  openModal(`<h3>Buat pesanan</h3><p class="sub">${lines.length} produk, total <b class="num">${formatRupiah(total)}</b></p>
      <ul class="sum">${summary}</ul>
      <form data-form="checkout" novalidate><div class="form-alert" role="alert"></div>
        <div class="field"><label>Nomor HP / WhatsApp</label><input class="input" name="phone" type="tel" inputmode="tel" required maxlength="20" placeholder="Contoh: 081234567890" autocomplete="tel" value="${escapeHtml(profile.phone || '')}"></div>
        <div class="field"><label>Alamat pengiriman</label><textarea class="input" name="address" required minlength="5" maxlength="160" placeholder="Nama jalan, nomor, kota" autocomplete="street-address">${escapeHtml(profile.address || '')}</textarea></div>
        <div class="field"><label>Catatan untuk penjual (opsional)</label><input class="input" name="note" maxlength="200"></div>
        ${payNote}
        <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Buat pesanan (${formatRupiah(total)})</button></div></form>`);
}

async function copyToClipboard(el) {
  try {
    await navigator.clipboard.writeText(el.dataset.text);
    toast(el.dataset.label + ' disalin');
  } catch {
    toast('Tidak bisa menyalin, salin manual', 'err');
  }
}

function reorder(el) {
  const order = state.orders.find(o => o.id === el.dataset.id);
  if (!order) return;

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
    toast('Status pesanan diperbarui', 'ok');
    state.justUpdatedOrderId = id;
    await reload();
    state.justUpdatedOrderId = null;
  } catch (err) {
    toast(err.message, 'err');
    await reload();
  }
}

// konfirmasi dulu, lalu hapus lewat API dan muat ulang halaman
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

function togglePasswordVisibility(checkbox) {
  $$('input[name=password],input[name=confirm],input[data-pw]', checkbox.closest('form')).forEach(input => {
    input.type = checkbox.checked ? 'text' : 'password';
  });
}

// --- Lupa password ---

// Bila pengguna sudah mengetik email di form masuk, bawa ke form Lupa password
function loginEmailHint() {
  const typed = ($('#f-id')?.value || '').trim();
  return typed.includes('@') ? typed : '';
}

let resendTimer = null;

// Tombol kirim ulang aktif lagi setelah hitung mundur selesai (dihitung dari jam, bukan dari jumlah detak, agar tidak meleset di tab latar)
function startResendCountdown(button, seconds) {
  clearInterval(resendTimer);
  if (!button) return;
  const endAt = Date.now() + seconds * 1000;
  const paint = () => {
    if (!button.isConnected) { clearInterval(resendTimer); return; }
    const left = Math.ceil((endAt - Date.now()) / 1000);
    if (left <= 0) {
      clearInterval(resendTimer);
      button.disabled = false;
      button.textContent = 'Kirim ulang kode';
      return;
    }
    button.disabled = true;
    button.textContent = `Kirim ulang dalam ${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;
  };
  paint();
  resendTimer = setInterval(paint, 1000);
}

async function resendResetCode(button) {
  const form = button.closest('form');
  button.disabled = true;
  button.textContent = 'Mengirim…';
  try {
    const result = await api('/auth/forgot', { method: 'POST', body: { email: form.elements.email.value } });
    toast('Jika email terdaftar, kode baru sudah dikirim. Kode lama tidak berlaku lagi.', 'ok');
    clearErrors(form);
    form.elements.code.value = '';
    form.elements.code.focus();
    startResendCountdown(button, Number(result.retry_after) || 120);
  } catch (err) {
    toast(err.message, 'err');
    button.disabled = false;
    button.textContent = 'Kirim ulang kode';
  }
}

// Daftar syarat password ikut berubah saat mengetik (hanya petunjuk; server tetap yang memutuskan)
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

// data-act -> handler(elemen, event)
const actions = {
  'auth-tab':      el => renderAuth(el.dataset.tab),
  nav:             el => show(el.dataset.view),
  reload,
  logout,
  'close-modal':   closeModal,
  overlay:         (el, e) => { if (e.target === el) closeModal(); },
  'ask-ok':        confirmAccepted,
  cat:             filterByCategory,
  detail:          openProductDetail,
  'detail-add':    addFromProductDetail,
  'add-cart':      addOneToCart,
  'cart-inc':      addOneToCart,
  'cart-dec':      el => setCartQty(el.dataset.id, cartQty(el.dataset.id) - 1),
  'cart-del':      removeFromCart,
  'open-cart':     openCart,
  'close-cart':    closeCart,
  checkout:        openCheckout,
  ofilter:         filterOrders,
  copy:            copyToClipboard,
  reorder,
  'order-status':  changeOrderStatus,
  'product-new':   () => productModal(null),
  'product-edit':  el => productModal(state.productMap[el.dataset.id]),
  'product-del':   deleteProduct,
  'user-new':      userModal,
  'change-password': passwordModal,
  'forgot-open':   () => forgotModal(loginEmailHint()),
  'forgot-change': el => forgotModal(el.dataset.email),
  'forgot-resend': resendResetCode,
  'user-del':      deleteUser,
  'toggle-pw':     togglePasswordVisibility,
  'refresh-page':  () => location.reload()
};

// === Form ===

function clearErrors(form) {
  $$('.invalid', form).forEach(input => input.classList.remove('invalid'));
  $$('.field-err', form).forEach(msg => msg.remove());
  const alert = $('.form-alert', form);
  if (alert) alert.classList.remove('show');
}

function showErrors(form, err) {
  const alert = $('.form-alert', form);
  if (alert) {
    alert.textContent = err.message;
    alert.classList.add('show');
  }

  Object.entries(err.fields || {}).forEach(([name, message]) => {
    const input = form.querySelector(`[name="${CSS.escape(name)}"]`);
    if (!input) return;
    input.classList.add('invalid');

    const hint = document.createElement('small');
    hint.className = 'field-err';
    hint.textContent = message;
    (input.closest('.field') || input.parentNode).appendChild(hint);
  });
}

// bentuknya sama dengan error dari server
const validationError = fields => createError('Periksa kembali isian Anda', { fields });

// Satu kunci per isi keranjang. Bila respons hilang di jalan lalu pelanggan mengulang, server mengembalikan
// pesanan yang sudah dibuat, bukan membuat pesanan kedua. Kunci kedaluwarsa agar keranjang yang sama
// berjam-jam kemudian tidak "menghidupkan" pesanan lama.
const CHECKOUT_KEY_TTL_MS = 10 * 60 * 1000;

function checkoutKey(items) {
  const signature = JSON.stringify(items);
  const current = state.checkout;
  const fresh = current && current.signature === signature && Date.now() - current.at < CHECKOUT_KEY_TTL_MS;
  if (!fresh) state.checkout = { signature, key: newRequestKey(), at: Date.now() };
  return state.checkout.key;
}

// Stok atau harga berubah sejak katalog dimuat: tutup form, muat ulang katalog, dan tampilkan keranjang yang sudah disesuaikan
async function refreshAfterStockConflict(err) {
  closeModal();
  toast(err.message, 'err');
  if (state.view === 'shop') await reload();   // sekaligus menggambar ulang kartu produk
  else await loadProducts();
  drawCart();
  openCart();
}

// handler submit per data-form; lempar error untuk ditampilkan
const formHandlers = {
  async login(form, data) {
    const result = await api('/auth/login', { method: 'POST', body: { identifier: data.identifier, password: data.password } });
    await onAuthed(result);
  },

  async register(form, data) {
    if (data.password !== data.confirm) {
      throw validationError({ confirm: 'Konfirmasi password tidak sama' });
    }
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
    if (data.new_password !== data.confirm) {
      throw validationError({ confirm: 'Konfirmasi password tidak sama' });
    }
    await api('/auth/password', {
      method: 'PATCH',
      body: { current_password: data.current_password, new_password: data.new_password }
    });
    closeModal();
    toast('Password diganti. Perangkat lain perlu masuk lagi.', 'ok');
  },

  async forgot(form, data) {
    const email = String(data.email || '').trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(email)) throw validationError({ email: 'Format email tidak valid' });
    const result = await api('/auth/forgot', { method: 'POST', body: { email } });
    // ganti isi modal; jawaban server sama untuk email terdaftar maupun tidak
    const retryAfter = Number(result.retry_after) || 120;
    resetModal(email, { retryAfter, expiresMinutes: Number(result.expires_minutes) || 15 });
    startResendCountdown($('[data-act="forgot-resend"]'), retryAfter);
  },

  async reset(form, data) {
    const code = String(data.code || '').trim();
    if (!/^\d{6}$/.test(code)) throw validationError({ code: 'Kode terdiri dari 6 angka' });
    if (data.new_password !== data.confirm) {
      throw validationError({ confirm: 'Konfirmasi password tidak sama' });
    }
    await api('/auth/reset', { method: 'POST', body: { email: data.email, code, new_password: data.new_password } });
    closeModal();
    toast('Password diganti. Silakan masuk dengan password baru.', 'ok');
    // email sudah terisi di form masuk; tinggal ketik password baru
    const identifier = $('#f-id');
    if (identifier) {
      identifier.value = data.email;
      ($('#f-pw') || identifier).focus();
    }
  },

  async 'user-create'(form, data) {
    await api('/users', { method: 'POST', body: data });
    closeModal();
    toast('Akun dibuat', 'ok');
    await reload();
  },

  async checkout(form, data) {
    const phone = String(data.phone || '').replace(/[\s.\-]/g, '');
    if (!/^\+?\d{8,15}$/.test(phone)) {
      throw validationError({ phone: 'Isi nomor HP yang benar, contoh 081234567890' });
    }

    const address = data.address.trim();
    storage.set(STORAGE_KEYS.profile(state.user.id), { phone, address });

    // harga ikut dikirim: server menolak (409) bila harga di katalog sudah berubah dari yang dilihat pelanggan
    const items = cartLines().map(line => ({ product_id: line.product.id, qty: line.qty, price: line.product.price }));
    let result;
    try {
      result = await api('/orders', {
        method: 'POST',
        body: { items, phone, address, note: data.note },
        headers: { 'Idempotency-Key': checkoutKey(items) }
      });
    } catch (err) {
      // 409: stok tidak cukup atau harga berubah, 404: produk sudah dihapus. Katalog di layar sudah basi.
      if (err.status === 409 || err.status === 404) return refreshAfterStockConflict(err);
      throw err;
    }

    state.checkout = null;
    state.cart = {};
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
    // Form bisa sudah hilang dari DOM (mis. setelah sesi berakhir); pakai toast sebagai gantinya
    if (form.isConnected) showErrors(form, err);
    else toast(err.message, 'err');
  } finally {
    if (submitButton && submitButton.isConnected) {
      submitButton.disabled = false;
      submitButton.classList.remove('loading');
    }
  }
}

// === Event listener ===

function onClick(e) {
  const el = e.target.closest('[data-act]');
  if (!el) return;
  const handler = actions[el.dataset.act];
  if (handler) handler(el, e);
}

async function onChange(e) {
  if (e.target.matches('[data-sort]')) {
    state.sort = e.target.value;
    renderList();
    return;
  }

  const el = e.target.closest('[data-change]');
  if (!el) return;
  const id = el.dataset.id;

  try {
    if (el.dataset.change === 'user-role') await api('/users/' + id, { method: 'PATCH', body: { role: el.value } });
    if (el.dataset.change === 'user-active') await api('/users/' + id, { method: 'PATCH', body: { active: el.checked } });
    toast('Perubahan disimpan', 'ok');
    await reload();
  } catch (err) {
    toast(err.message, 'err');
    await reload();
  }
}

let searchDebounce;
function onInput(e) {
  // kode reset hanya angka (tempel "123 456" pun jadi 123456)
  const digits = e.target.closest('[data-digits]');
  if (digits) {
    const clean = digits.value.replace(/\D/g, '').slice(0, 6);
    if (clean !== digits.value) digits.value = clean;
  }

  const pwForm = e.target.closest('form[data-pwcheck]');
  if (pwForm) updatePasswordChecks(pwForm);

  const el = e.target.closest('[data-input]');
  if (!el) return;

  state.query = el.value;
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    if (el.dataset.input === 'shop-search') renderList();
    else $('#prows').innerHTML = productRows();
  }, 120);
}

// Escape menutup modal/laci; Tab dikurung di dalam modal
function onModalKeydown(e) {
  const modalOpen = $('#modal-root').firstChild;

  if (e.key === 'Escape') {
    if (modalOpen) closeModal();
    else closeCart();
    return;
  }

  if (e.key !== 'Tab' || !modalOpen) return;

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

// geser laci ke bawah untuk menutup (layar kecil)
function initDrawerSwipe() {
  const CLOSE_DISTANCE = 90;
  let startY = null;
  let drawer = null;
  const isMobile = () => matchMedia('(max-width:780px)').matches;

  document.addEventListener('pointerdown', e => {
    const head = e.target.closest('.drawer-head');
    if (!head || e.target.closest('button') || !isMobile()) return;
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

function bindEvents() {
  document.addEventListener('click', onClick);
  document.addEventListener('change', onChange);
  document.addEventListener('input', onInput);
  document.addEventListener('keydown', onModalKeydown);
  document.addEventListener('keydown', onSearchShortcut);
  document.addEventListener('submit', onSubmit);
  initDrawerSwipe();

  addEventListener('offline', () => toast('Koneksi terputus. Pesanan baru bisa dibuat setelah tersambung.', 'err'));
  addEventListener('online', () => toast('Tersambung kembali', 'ok'));
}

// === Mulai ===

async function boot() {
  storage.remove(STORAGE_KEYS.legacyProfile);   // buang profil lama yang bisa memuat data pengguna sebelumnya
  bindEvents();

  try {
    const me = await api('/auth/me');
    state.csrf = me.csrf;
    state.payInfo = me.pay_info || '';
    state.resetEnabled = Boolean(me.reset_enabled);

    if (me.user) {
      state.user = me.user;
      state.cart = storage.get(STORAGE_KEYS.cart(me.user.id)) || {};
      await show(defaultView());
    } else {
      renderAuth('login');
    }
  } catch (err) {
    $('#app').innerHTML = `<div class="empty" style="margin:15vh auto;max-width:460px"><b>Aplikasi belum bisa dimuat</b><p>${escapeHtml(err.message)}</p><button class="btn primary" data-act="refresh-page">Muat ulang</button></div>`;
  }
}

boot();