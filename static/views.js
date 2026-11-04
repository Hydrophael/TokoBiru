// TokoBiru - tampilan: fungsi yang menghasilkan HTML tiap halaman

import {
  $,
  $$,
  MAX_CART_QTY,
  NAV,
  ORDER_FLOW,
  ROLE_LABEL,
  STATUS,
  STORAGE_KEYS,
  brandHtml,
  cartQty,
  emptyState,
  escapeHtml,
  formatDate,
  formatRupiah,
  getInitials,
  hashString,
  icon,
  isCustomer,
  isStaff,
  payRow,
  priceHtml,
  productEmoji,
  state,
  statusTag,
  stockInfo,
  storage
} from './core.js';
import { linkLabels, openModal, reducedMotion, toast } from './ui.js';

// === Modal pesanan berhasil ===

export function showOrderSuccess(order) {
  if (!order) return;
  openModal(`<div class="done"><svg class="done-ic" viewBox="0 0 52 52" aria-hidden="true"><circle cx="26" cy="26" r="24"/><path d="M15 27l8 8 14-19"/></svg>
    <h3>Pesanan berhasil dibuat</h3><p class="sub">Satu langkah lagi: bayar agar pesanan segera diproses.</p></div>
    <div class="r-pay">${payRow('Nominal', formatRupiah(order.total), order.total)}${payRow('Kode pesanan', order.code, order.code)}${state.payInfo ? payRow('Tujuan', state.payInfo, state.payInfo) : ''}
    <p class="muted small">Cantumkan kode pesanan saat membayar.</p></div>
    <div class="foot"><button class="btn primary" data-act="close-modal">Mengerti</button></div>`);
}

// === Halaman masuk / daftar ===

const TICKER_WORDS = ['Beras', 'Minyak goreng', 'Telur', 'Kopi', 'Sabun', 'Susu', 'Teh', 'Roti', 'Madu', 'Tisu'];

// [nama, harga, harga satuan]
const PRICE_TAGS = [
  ['Beras premium 5 kg', '72.000', 'Rp14.400 / kg'],
  ['Minyak goreng 2 L', '38.500', 'Rp19.250 / L'],
  ['Telur ayam 1 kg', '29.000', 'Rp29.000 / kg'],
  ['Kopi bubuk 200 g', '21.500', 'Rp10.750 / 100 g']
];

const loginFormHtml = () => `
    <h2>Selamat datang</h2><p class="muted">Masuk untuk belanja atau kelola toko.</p>
    <form data-form="login" novalidate>
      <div class="form-alert" role="alert"></div>
      <div class="field"><label for="f-id">Username atau email</label><input class="input" id="f-id" name="identifier"
        autocapitalize="none" spellcheck="false" placeholder="Contoh: budi atau budi@email.com"
        autocomplete="username" required maxlength="120"></div>
      <div class="field" style="margin-bottom:10px"><label for="f-pw">Password</label><input class="input" id="f-pw" name="password"
        type="password" placeholder="Password Anda" autocomplete="current-password" required maxlength="128"></div>
      <label class="showpw"><input type="checkbox" data-act="toggle-pw"> Tampilkan password</label>
      <button class="btn primary block" type="submit">Masuk</button>
    </form>`;

const registerFormHtml = () => `
    <h2>Buat akun</h2><p class="muted">Daftar sebagai pelanggan, gratis.</p>
    <form data-form="register" novalidate>
      <div class="form-alert" role="alert"></div>
      <div class="pair">
      <div class="field"><label for="r-name">Nama lengkap</label><input class="input" id="r-name" name="name"
        placeholder="Budi Santoso" required maxlength="50" autocomplete="name"></div>
      <div class="field"><label for="r-user">Username</label><input class="input" id="r-user" name="username"
        autocapitalize="none" spellcheck="false" placeholder="budisantoso" required maxlength="20" autocomplete="username"></div>
      </div>
      <div class="field"><label for="r-email">Email</label><input class="input" id="r-email" name="email"
        type="email" placeholder="nama@email.com" required maxlength="120" autocomplete="email"></div>
      <div class="pair">
      <div class="field"><label for="r-pw">Password</label><input class="input" id="r-pw" name="password"
        type="password" required minlength="8" maxlength="128" autocomplete="new-password" aria-describedby="r-pw-hint"></div>
      <div class="field"><label for="r-pw2">Ulangi password</label><input class="input" id="r-pw2" name="confirm"
        type="password" required autocomplete="new-password"></div>
      </div>
      <p class="muted small" id="r-pw-hint" style="margin:-2px 0 10px">Minimal 8 karakter, berisi huruf dan angka.</p>
      <label class="showpw"><input type="checkbox" data-act="toggle-pw"> Tampilkan password</label>
      <button class="btn primary block" type="submit">Daftar</button>
    </form>`;

function authArtHtml() {
  const ticker = TICKER_WORDS.map(word => `<span>${word}</span><i></i>`).join('');
  const dots = PRICE_TAGS.map((_, index) => `<i${index ? '' : ' class="on"'}></i>`).join('');
  const slides = PRICE_TAGS.map(([name, price, unit], index) =>
    `<div class="pt-slide${index ? '' : ' on'}"><p class="pt-name">${name}</p><strong class="pt-price num"><sup>Rp</sup>${price}</strong><p class="pt-unit num">${unit}</p></div>`
  ).join('');

  return `<section class="auth-art">
      ${brandHtml('color:var(--hero-ink)')}
      <div class="art-body">
        <h1>Rak penuh,<br>stok jujur.</h1>
        <p>Pilih barang, isi keranjang, dan pantau pesanan sampai tiba. Pemilik toko melihat stok dan penjualan di tempat yang sama.</p>
        <div class="pricetag" aria-hidden="true">
          <div class="pt-head"><small>Harga rak</small><div class="pt-dots">${dots}</div></div>
          <div class="pt-slides">${slides}</div>
          <div class="pt-bars"></div>
        </div>
      </div>
      <div class="ticker" aria-hidden="true"><div>${ticker}${ticker}</div></div>
    </section>`;
}

function authPanelHtml(tab) {
  const isLogin = tab === 'login';
  return `<section class="auth-panel"><div class="auth-card">
      <div class="switch-tabs" role="tablist">
        <button role="tab" class="${isLogin ? 'active' : ''}" data-act="auth-tab" data-tab="login">Masuk</button>
        <button role="tab" class="${!isLogin ? 'active' : ''}" data-act="auth-tab" data-tab="register">Daftar</button>
      </div>
      ${isLogin ? loginFormHtml() : registerFormHtml()}
      <p class="alt muted">${isLogin ? 'Belum punya akun?' : 'Sudah punya akun?'} <button type="button" class="linkbtn" data-act="auth-tab" data-tab="${isLogin ? 'register' : 'login'}">${isLogin ? 'Daftar gratis' : 'Masuk'}</button></p>
    </div>
    </section>`;
}

export function renderAuth(tab = state.authTab) {
  state.authTab = tab;
  $('#app').innerHTML = `
  <div class="auth">
    ${authArtHtml()}
    ${authPanelHtml(tab)}
  </div>`;

  linkLabels($('#app'));
  startPriceTagRotation();

  // Fokus otomatis hanya di perangkat dengan mouse (hindari keyboard muncul di HP)
  if (matchMedia('(hover:hover) and (pointer:fine)').matches) {
    const firstInput = $('.auth-card form input:not([type=checkbox])');
    if (firstInput) firstInput.focus();
  }
}

let priceTagTimer;
function startPriceTagRotation() {
  clearInterval(priceTagTimer);
  const tag = $('.pricetag');
  if (!tag || reducedMotion.matches) return;

  const slides = $$('.pt-slide', tag);
  const dots = $$('.pt-dots i', tag);
  let current = 0;

  priceTagTimer = setInterval(() => {
    if (!tag.isConnected) return clearInterval(priceTagTimer);
    current = (current + 1) % slides.length;
    slides.forEach((slide, index) => slide.classList.toggle('on', index === current));
    dots.forEach((dot, index) => dot.classList.toggle('on', index === current));
  }, 4000);
}

// === Kerangka dan navigasi ===

function navHtml(items) {
  return items.map(item => {
    const active = state.view === item.id;
    return `<button class="${active ? 'active' : ''}" data-act="nav" data-view="${item.id}" aria-current="${active ? 'page' : 'false'}">${icon(item.icon, 20)}<span>${item.label}</span></button>`;
  }).join('');
}

const cartDrawerHtml = () => `<div class="scrim" id="scrim" data-act="close-cart"></div>
  <aside class="drawer" id="drawer" aria-label="Keranjang">
    <div class="drawer-head"><h3>Keranjang</h3><button class="btn sm flat" data-act="close-cart" aria-label="Tutup keranjang">${icon('x', 18)}</button></div>
    <div id="cart-items"></div>
    <div class="drawer-foot"><div class="line" style="border:0;padding:0 0 12px"><span>Total</span><span id="cart-total" class="price num">Rp 0</span></div>
      <button class="btn primary block" data-act="checkout" id="checkout-btn">Lanjut ke pemesanan</button></div>
  </aside>
  <button class="cartbar" id="cartbar" data-act="open-cart" aria-label="Buka keranjang" hidden></button>`;

export function renderShell() {
  const user = state.user;
  const navItems = NAV.filter(item => item.roles.includes(user.role));
  const customer = isCustomer();

  $('#app').innerHTML = `
  <header class="top"><div class="top-in">
    ${brandHtml()}
    <nav class="nav" aria-label="Menu utama">${navHtml(navItems)}</nav>
    <div class="top-r">
      ${customer ? `<button class="btn cart-btn" data-act="open-cart">${icon('cart')}<span class="hide-m">Keranjang</span><span class="count num" id="cart-count">0</span></button>` : ''}
      <div class="who"><b>${escapeHtml(user.name)}</b><span class="tag ${user.role}">${ROLE_LABEL[user.role]}</span></div>
      <button class="btn sm" data-act="logout" aria-label="Keluar">${icon('out', 15)}<span>Keluar</span></button>
    </div>
  </div></header>
  <main class="wrap"><div id="content"><div class="shelf">${'<div class="skeleton"></div>'.repeat(6)}</div></div></main>
  ${customer ? cartDrawerHtml() : ''}`;

  if (customer) drawCart();
}

// === Tampilan ===

// --- Belanja ---

function filteredProducts() {
  const query = state.query.trim().toLowerCase();
  const sort = state.sort;

  const compare = (a, b) => {
    if (sort === 'low') return a.price - b.price;
    if (sort === 'high') return b.price - a.price;
    return a.name.localeCompare(b.name, 'id');
  };

  return state.products
    .filter(p => (!state.category || p.category === state.category) && (!query || p.name.toLowerCase().includes(query)))
    .sort((a, b) => (a.stock === 0) - (b.stock === 0) || compare(a, b)); // stok habis selalu di bawah
}

export function aisleHtml() {
  const aisleNumber = state.categories.indexOf(state.category) + 1;
  return `<div class="aisle-sign"><span class="a-no">${aisleNumber ? 'Lorong ' + aisleNumber : 'Seluruh toko'}</span><b>${state.category ? escapeHtml(state.category) : 'Semua kategori'}</b></div>`;
}

export const categoryRailHtml = () =>
  `<button class="${!state.category ? 'active' : ''}" data-act="cat" data-cat="">Semua</button>` +
  state.categories.map(category =>
    `<button class="${state.category === category ? 'active' : ''}" data-act="cat" data-cat="${escapeHtml(category)}">${escapeHtml(category)}</button>`
  ).join('');

function cardFoot(product) {
  const qty = cartQty(product.id);
  const name = escapeHtml(product.name);

  let control;
  if (product.stock === 0) {
    control = '<button class="btn sm" disabled>Habis</button>';
  } else if (qty) {
    control = `<div class="qty sm"><button data-act="cart-dec" data-id="${product.id}" aria-label="Kurangi ${name}">−</button><span class="num" aria-live="polite">${qty}</span><button data-act="cart-inc" data-id="${product.id}" aria-label="Tambah ${name}">+</button></div>`;
  } else {
    control = `<button class="btn sm primary" data-act="add-cart" data-id="${product.id}" aria-label="Tambah ${name} ke keranjang">${icon('plus', 14)} Tambah</button>`;
  }
  return `<div class="lfoot" data-q="${qty}">${priceHtml(product.price)}${control}</div>`;
}

function productCardHtml(product, index) {
  return `
    <article class="label${product.stock === 0 ? ' soldout' : ''}" data-card="${product.id}" style="--i:${Math.min(index, 8)}">
      <div class="tile p${hashString(product.id) % 4}" data-act="detail" data-id="${product.id}"><span class="cat tag">${escapeHtml(product.category)}</span><span class="ini" aria-hidden="true">${productEmoji(product)}</span></div>
      <div class="lbody"><h3><button type="button" class="plink" data-act="detail" data-id="${product.id}">${escapeHtml(product.name)}</button></h3><p>${escapeHtml(product.description)}</p>${stockInfo(product)}</div>
      ${cardFoot(product)}
    </article>`;
}

function productCards(firstRender = false) {
  const list = filteredProducts();
  if (!state.products.length) return emptyState('Katalog masih kosong', 'Toko belum menambahkan produk. Silakan cek lagi nanti.');
  if (!list.length) return emptyState('Tidak ada yang cocok', 'Coba kata kunci lain atau pilih kategori Semua.');
  return `<div class="shelf${firstRender ? ' stagger' : ''}">${list.map(productCardHtml).join('')}</div>`;
}

export function renderList() {
  $('#plist').innerHTML = productCards();
  const counter = $('#rcount');
  if (counter) counter.textContent = filteredProducts().length + ' produk';
}

const sortOptionHtml = (value, label) =>
  `<option value="${value}"${state.sort === value ? ' selected' : ''}>${label}</option>`;

const shopView = () => `
  <div class="page-head"><div><h2>Belanja</h2><p class="muted">Pilih barang, masukkan ke keranjang, lalu buat pesanan.</p></div></div>
  <div class="tools">
    <label class="search">${icon('search')}<input data-input="shop-search" placeholder="Cari nama produk" maxlength="50" aria-label="Cari produk"></label>
    <div class="rail" id="rail">${categoryRailHtml()}</div>
  </div>
  <div class="aisle" id="aisle" aria-hidden="true">${aisleHtml()}</div>
  <div class="toolbar"><span class="muted small" id="rcount" aria-live="polite">${filteredProducts().length} produk</span>
    <label class="sortsel">Urutkan <select class="select sm" data-sort aria-label="Urutkan produk">${sortOptionHtml('name', 'Nama A–Z')}${sortOptionHtml('low', 'Harga terendah')}${sortOptionHtml('high', 'Harga tertinggi')}</select></label></div>
  <div id="plist">${productCards(true)}</div>`;

// --- Keranjang ---

export const cartLines = () =>
  Object.entries(state.cart)
    .map(([id, qty]) => ({ product: state.productMap[id], qty }))
    .filter(line => line.product);

export const cartTotal = lines => lines.reduce((sum, line) => sum + line.product.price * line.qty, 0);

function cartItemHtml({ product, qty }) {
  return `
    <div class="citem"><span class="mini" aria-hidden="true">${productEmoji(product)}</span>
      <div class="meta"><b>${escapeHtml(product.name)}</b><span class="muted small num">${formatRupiah(product.price)}</span><br>
        <div class="qty"><button data-act="cart-dec" data-id="${product.id}" aria-label="Kurangi jumlah">−</button><span class="num">${qty}</span><button data-act="cart-inc" data-id="${product.id}" aria-label="Tambah jumlah">+</button></div></div>
      <div class="right"><b class="num">${formatRupiah(product.price * qty)}</b><br><button class="btn sm danger" style="margin-top:8px" data-act="cart-del" data-id="${product.id}" aria-label="Hapus ${escapeHtml(product.name)}">${icon('trash', 13)}</button></div>
    </div>`;
}

function bump(el) {
  el.classList.remove('bump');
  void el.offsetWidth; // paksa reflow agar animasi mulai ulang
  el.classList.add('bump');
}

function renderCartBar(lines, count, total) {
  const bar = $('#cartbar');
  if (!bar) return;

  bar.hidden = !lines.length || state.view !== 'shop';
  bar.innerHTML = `<span class="cb-l">${icon('cart', 20)}<b class="num">${count} barang</b></span><span class="cb-r num">${formatRupiah(total)} ›</span>`;

  if (!bar.hidden && bar.dataset.n !== count) {
    const isFirstRender = bar.dataset.n === undefined;
    bar.dataset.n = count;
    if (!isFirstRender) bump(bar);
  }
}

// jaga fokus keyboard saat footer kartu diganti
function syncCardFooters() {
  $$('[data-card]').forEach(card => {
    const product = state.productMap[card.dataset.card];
    const footer = $('.lfoot', card);
    const qty = product ? cartQty(product.id) : 0;
    if (!product || footer.dataset.q === String(qty)) return;

    const hadFocus = footer.contains(document.activeElement);
    const focusedAction = hadFocus ? document.activeElement.dataset.act : '';

    footer.outerHTML = cardFoot(product);

    if (hadFocus) {
      const newFooter = $('.lfoot', card);
      const toFocus =
        newFooter.querySelector(`[data-act="${focusedAction}"]`) ||
        newFooter.querySelector('[data-act=cart-inc],[data-act=add-cart]') ||
        newFooter.querySelector('button');
      toFocus.focus();
    }
  });
}

// sekaligus menyimpan keranjang ke localStorage
export function drawCart() {
  const itemsEl = $('#cart-items');
  if (!itemsEl) return;

  const lines = cartLines();
  const total = cartTotal(lines);
  const count = String(lines.reduce((sum, line) => sum + line.qty, 0));

  itemsEl.innerHTML = lines.length
    ? lines.map(cartItemHtml).join('')
    : emptyState('Keranjang masih kosong', 'Pilih barang di halaman Belanja, lalu tekan Keranjang.', '<button class="btn primary" data-act="close-cart">Mulai belanja</button>');
  $('#cart-total').textContent = formatRupiah(total);

  const countEl = $('#cart-count');
  if (countEl.textContent !== count) {
    countEl.textContent = count;
    bump(countEl);
  }

  $('#checkout-btn').disabled = !lines.length;
  renderCartBar(lines, count, total);
  syncCardFooters();
  storage.set(STORAGE_KEYS.cart(state.user.id), state.cart);
}

export function setCartQty(id, qty) {
  const product = state.productMap[id];
  if (!product) return;

  if (qty <= 0) {
    delete state.cart[id];
  } else if (qty > product.stock) {
    toast(`Stok ${product.name} tinggal ${product.stock}`, 'err');
    state.cart[id] = product.stock;
  } else {
    state.cart[id] = Math.min(qty, MAX_CART_QTY);
  }
  drawCart();
}

// --- Pesanan ---

function timelineHtml(status) {
  if (status === 'cancelled') return '';
  const currentIndex = status === 'completed' ? ORDER_FLOW.length : ORDER_FLOW.indexOf(status);

  const steps = ORDER_FLOW.map((key, n) => {
    const cls = n < currentIndex ? 'done' : n === currentIndex ? 'now' : '';
    const ariaCurrent = n === currentIndex ? ' aria-current="step"' : '';
    const marker = n < currentIndex ? icon('check', 12) : n + 1;
    return `<li class="${cls}"${ariaCurrent}><i>${marker}</i><span>${STATUS[key][0]}</span></li>`;
  }).join('');

  return `<ol class="steps" aria-label="Progres pesanan">${steps}</ol>`;
}

const statusButton = (order, status, label, cls = '') =>
  `<button class="btn sm ${cls}" data-act="order-status" data-id="${order.id}" data-status="${status}">${label}</button>`;

function staffOrderActions(order) {
  switch (order.status) {
    case 'pending': return statusButton(order, 'paid', 'Konfirmasi pembayaran', 'primary') + statusButton(order, 'cancelled', 'Batalkan', 'danger');
    case 'paid':    return statusButton(order, 'shipped', 'Tandai dikirim', 'primary') + statusButton(order, 'cancelled', 'Batalkan', 'danger');
    case 'shipped': return statusButton(order, 'completed', 'Tandai selesai', 'primary');
    default:        return '';
  }
}

function customerOrderActions(order) {
  switch (order.status) {
    case 'pending':   return statusButton(order, 'cancelled', 'Batalkan pesanan', 'danger');
    case 'shipped':   return statusButton(order, 'completed', 'Pesanan sudah diterima', 'primary');
    case 'completed':
    case 'cancelled': return `<button class="btn sm primary" data-act="reorder" data-id="${order.id}">Beli lagi</button>`;
    default:          return '';
  }
}

const orderActions = order => (isStaff() ? staffOrderActions(order) : customerOrderActions(order));

const orderPaymentHtml = order =>
  `<div class="r-pay"><b>Cara bayar</b>${payRow('Nominal', formatRupiah(order.total), order.total)}${payRow('Kode pesanan', order.code, order.code)}${state.payInfo ? payRow('Tujuan', state.payInfo, state.payInfo, 'Tujuan bayar') : ''}<p class="muted small">Cantumkan kode pesanan saat membayar. Pesanan diproses setelah admin mengonfirmasi pembayaran.</p></div>`;

const orderLineHtml = item =>
  `<li><span>${escapeHtml(item.name)}</span><span class="num">${formatRupiah(item.subtotal)}</span><em class="num">${item.qty} × ${formatRupiah(item.price)}</em></li>`;

function orderCardHtml(order, staff) {
  const [statusLabel, statusColor] = STATUS[order.status];
  const justUpdated = order.id === state.justUpdatedOrderId ? ' just' : '';
  const owner = staff ? ', atas nama <b>' + escapeHtml(order.username) + '</b>' : '';
  const note = order.note ? '<br>Catatan: ' + escapeHtml(order.note) : '';
  const payment = !staff && order.status === 'pending' ? orderPaymentHtml(order) : '';

  return `
    <article class="receipt">
      <div class="r-top"><div><span class="r-code num">${escapeHtml(order.code)}</span><span class="muted small">${formatDate(order.created_at)}${owner}</span></div>
        <span class="stamp ${statusColor}${justUpdated}">${statusLabel}</span></div>
      ${timelineHtml(order.status)}
      <ul class="r-lines">${order.items.map(orderLineHtml).join('')}</ul>
      <div class="r-total"><span>Total</span><strong class="num">${formatRupiah(order.total)}</strong></div>
      <div class="r-addr">Kirim ke: ${escapeHtml(order.address)}${note}</div>
      ${payment}
      <div class="acts">${orderActions(order)}</div>
    </article>`;
}

export function orderCards() {
  const staff = isStaff();
  const list = state.orders.filter(o => !state.orderFilter || o.status === state.orderFilter);

  if (!list.length) {
    return emptyState(
      state.orderFilter ? 'Tidak ada pesanan dengan status ini' : 'Belum ada pesanan',
      staff ? 'Pesanan pelanggan akan muncul di sini.' : 'Pesanan Anda akan muncul di sini setelah checkout.'
    );
  }
  return `<div class="receipts">${list.map(order => orderCardHtml(order, staff)).join('')}</div>`;
}

export const orderRailHtml = () =>
  ['', ...Object.keys(STATUS)].map(status =>
    `<button class="${state.orderFilter === status ? 'active' : ''}" data-act="ofilter" data-s="${status}">${status ? STATUS[status][0] : 'Semua'}</button>`
  ).join('');

function ordersView() {
  const customer = isCustomer();
  return `
  <div class="page-head"><div><h2>${customer ? 'Pesanan saya' : 'Semua pesanan'}</h2><p class="muted">${customer ? 'Lihat status dan riwayat pesanan Anda.' : 'Konfirmasi pembayaran, kirim, dan selesaikan pesanan pelanggan.'}</p></div></div>
  <div class="rail" id="orail">${orderRailHtml()}</div>
  <div id="olist">${orderCards()}</div>`;
}

// --- Ringkasan ---

function dashboardFactsHtml(stats) {
  const showUserTotals = state.user.role === 'master' && stats.users;
  const userTotals = showUserTotals
    ? `<div class="fact" style="grid-column:1/-1"><b class="num">${stats.users.user + stats.users.admin + stats.users.master}</b><span>Pengguna: ${stats.users.user} pelanggan, ${stats.users.admin} admin, ${stats.users.master} master</span></div>`
    : '';

  return `<div class="facts">
      <div class="fact"><b class="num">${stats.orders.total}</b><span>Total pesanan</span></div>
      <div class="fact"><b class="num">${stats.orders.pending}</b><span>Menunggu pembayaran</span></div>
      <div class="fact"><b class="num">${stats.products}</b><span>Produk di katalog</span></div>
      <div class="fact"><b class="num">${stats.low_stock.length}</b><span>Stok menipis</span></div>
      ${userTotals}
    </div>`;
}

function orderStatusBarsHtml(stats) {
  const keys = Object.keys(STATUS);
  const max = Math.max(1, ...keys.map(key => stats.orders[key]));
  return keys.map(key => {
    const width = Math.round(stats.orders[key] / max * 100);
    return `<div class="bar"><span>${STATUS[key][0]}</span><div class="track"><div class="fill" style="width:${width}%"></div></div><span class="right num">${stats.orders[key]}</span></div>`;
  }).join('');
}

const recentOrdersHtml = stats => stats.recent.length
  ? stats.recent.map(order => `<div class="line"><span><b class="num">${escapeHtml(order.code)}</b> <span class="muted small">${escapeHtml(order.username)}</span></span><span>${statusTag(order.status)} <b class="num">${formatRupiah(order.total)}</b></span></div>`).join('')
  : '<p class="muted">Belum ada pesanan masuk.</p>';

const lowStockHtml = stats => stats.low_stock.length
  ? stats.low_stock.map(product => `<div class="line"><span class="cell"><span class="mini" aria-hidden="true">${productEmoji(product)}</span><span><b>${escapeHtml(product.name)}</b><br><span class="muted small">${escapeHtml(product.category)}</span></span></span>${stockInfo(product)}</div>`).join('')
  : '<p class="muted">Semua stok masih aman.</p>';

function dashboardView() {
  const stats = state.stats;
  return `
  <div class="page-head"><div><h2>Ringkasan</h2><p class="muted">Penjualan, pesanan, dan stok hari ini.</p></div>
    <button class="btn" data-act="reload">Perbarui data</button></div>
  <div class="lead">
    <div class="revenue"><span>Pendapatan dari pesanan yang sudah dibayar</span><strong class="num">${formatRupiah(stats.revenue)}</strong></div>
    ${dashboardFactsHtml(stats)}
  </div>
  <div class="two">
    <div class="panel"><h3>Pesanan per status</h3>
      ${orderStatusBarsHtml(stats)}
      <h3 style="margin-top:26px">Pesanan terbaru</h3>
      ${recentOrdersHtml(stats)}
    </div>
    <div class="panel"><h3>Perlu restok</h3>
      ${lowStockHtml(stats)}
      <div style="margin-top:16px"><button class="btn block" data-act="nav" data-view="products">Atur stok produk</button></div>
    </div>
  </div>`;
}

// --- Produk ---

function productRowHtml(product) {
  return `<tr>
    <td data-label="Produk"><div class="cell"><span class="mini" aria-hidden="true">${productEmoji(product)}</span><div><b>${escapeHtml(product.name)}</b><div class="muted small">${escapeHtml(String(product.description ?? '').slice(0, 60))}</div></div></div></td>
    <td data-label="Kategori"><span class="tag">${escapeHtml(product.category)}</span></td><td data-label="Harga"><b class="num">${formatRupiah(product.price)}</b></td><td data-label="Stok">${stockInfo(product)}</td>
    <td data-label="Aksi"><div class="acts end"><button class="btn sm" data-act="product-edit" data-id="${product.id}">${icon('edit', 13)} Ubah</button>
      <button class="btn sm danger" data-act="product-del" data-id="${product.id}" aria-label="Hapus ${escapeHtml(product.name)}">${icon('trash', 13)}</button></div></td></tr>`;
}

export function productRows() {
  const query = state.query.trim().toLowerCase();
  const list = state.products.filter(p =>
    !query || p.name.toLowerCase().includes(query) || p.category.toLowerCase().includes(query)
  );

  if (!list.length) {
    const hasProducts = state.products.length > 0;
    return `<tr><td colspan="5">${emptyState(
      hasProducts ? 'Tidak ada yang cocok' : 'Belum ada produk',
      hasProducts ? 'Coba kata kunci lain.' : 'Tambahkan produk pertama agar pelanggan bisa mulai belanja.'
    )}</td></tr>`;
  }
  return list.map(productRowHtml).join('');
}

const productsView = () => `
  <div class="page-head"><div><h2>Produk</h2><p class="muted">Tambah, ubah harga dan stok, atau hapus produk.</p></div>
    <div class="acts"><label class="search">${icon('search')}<input data-input="prod-search" placeholder="Cari produk atau kategori" maxlength="50" aria-label="Cari"></label>
    <button class="btn primary" data-act="product-new">${icon('plus', 15)} Tambah produk</button></div></div>
  <div class="tbl-wrap"><table><thead><tr><th>Produk</th><th>Kategori</th><th>Harga</th><th>Stok</th><th class="right">Aksi</th></tr></thead><tbody id="prows">${productRows()}</tbody></table></div>`;

export function productModal(product) {
  const isEdit = Boolean(product);
  const values = product || { name: '', category: '', price: '', stock: '', description: '' };
  const categoryOptions = state.categories.map(c => `<option value="${escapeHtml(c)}">`).join('');

  openModal(`
    <h3>${isEdit ? 'Ubah produk' : 'Tambah produk'}</h3><p class="sub">${isEdit ? 'Perubahan langsung tampil di katalog pelanggan.' : 'Produk baru langsung muncul di katalog.'}</p>
    <form data-form="product" data-id="${isEdit ? product.id : ''}" novalidate>
      <div class="form-alert" role="alert"></div>
      <div class="field"><label>Nama produk</label><input class="input" name="name" required maxlength="80" value="${escapeHtml(values.name)}"></div>
      <div class="row2">
        <div class="field"><label>Kategori</label><input class="input" name="category" list="cats" required maxlength="30" value="${escapeHtml(values.category)}"><datalist id="cats">${categoryOptions}</datalist></div>
        <div class="field"><label>Harga (Rp)</label><input class="input" name="price" type="number" min="100" max="100000000" step="1" required value="${escapeHtml(values.price)}"></div>
      </div>
      <div class="field"><label>Stok</label><input class="input" name="stock" type="number" min="0" max="100000" step="1" required value="${escapeHtml(values.stock)}"></div>
      <div class="field"><label>Deskripsi (opsional)</label><textarea class="input" name="description" maxlength="300">${escapeHtml(values.description)}</textarea></div>
      <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Simpan produk</button></div>
    </form>`);
}

// --- Pengguna ---

const roleSelectHtml = user =>
  `<select class="select sm" data-change="user-role" data-id="${user.id}" aria-label="Role ${escapeHtml(user.username)}"><option value="user" ${user.role === 'user' ? 'selected' : ''}>Pelanggan</option><option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Admin</option></select>`;

const activeSwitchHtml = user =>
  `<label class="sw"><input type="checkbox" data-change="user-active" data-id="${user.id}" ${user.active ? 'checked' : ''} aria-label="Aktif ${escapeHtml(user.username)}"><span></span></label>`;

function userRowHtml(user) {
  // Akun master dan akun sendiri tidak bisa diubah dari sini
  const locked = user.role === 'master' || user.id === state.user.id;
  return `<tr><td data-label="Pengguna"><div class="cell"><span class="mini">${escapeHtml(getInitials(user.name))}</span><div><b>${escapeHtml(user.name)}</b><div class="muted small">@${escapeHtml(user.username)}</div></div></div></td>
    <td data-label="Email">${escapeHtml(user.email)}</td>
    <td data-label="Role">${locked ? `<span class="tag ${user.role}">${ROLE_LABEL[user.role]}</span>` : roleSelectHtml(user)}</td>
    <td data-label="Aktif">${locked ? '<span class="tag ok">Aktif</span>' : activeSwitchHtml(user)}</td>
    <td data-label="Terdaftar" class="muted small">${formatDate(user.created_at)}</td>
    <td data-label="Aksi"><div class="acts end">${locked ? '<span class="muted small">Dilindungi</span>' : `<button class="btn sm danger" data-act="user-del" data-id="${user.id}" aria-label="Hapus ${escapeHtml(user.username)}">${icon('trash', 13)}</button>`}</div></td></tr>`;
}

const usersView = () => `
  <div class="page-head"><div><h2>Pengguna</h2><p class="muted">Atur role, nonaktifkan, atau hapus akun. Akun master tidak bisa diubah dari sini.</p></div>
    <button class="btn primary" data-act="user-new">${icon('plus', 15)} Tambah pengguna</button></div>
  <div class="tbl-wrap"><table><thead><tr><th>Pengguna</th><th>Email</th><th>Role</th><th>Aktif</th><th>Terdaftar</th><th class="right">Aksi</th></tr></thead><tbody>
  ${state.users.map(userRowHtml).join('')}</tbody></table></div>`;

export function userModal() {
  openModal(`<h3>Tambah pengguna</h3><p class="sub">Buat akun admin untuk staf, atau akun pelanggan.</p>
    <form data-form="user-create" novalidate><div class="form-alert" role="alert"></div>
      <div class="field"><label>Nama lengkap</label><input class="input" name="name" required maxlength="50"></div>
      <div class="row2"><div class="field"><label>Username</label><input class="input" name="username" required maxlength="20"></div>
      <div class="field"><label>Role</label><select class="select" name="role"><option value="admin">Admin</option><option value="user">Pelanggan</option></select></div></div>
      <div class="field"><label>Email</label><input class="input" name="email" type="email" required maxlength="120"></div>
      <div class="field"><label>Password</label><input class="input" name="password" type="password" required minlength="8" maxlength="128" autocomplete="new-password"></div>
      <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Buat akun</button></div></form>`);
}

// --- Log ---

function logRowHtml(log) {
  const isFailure = /gagal|ditolak/.test(log.action);
  const roleTag = log.role !== '-'
    ? `<span class="tag ${escapeHtml(log.role)}">${escapeHtml(ROLE_LABEL[log.role] || log.role)}</span>`
    : '';
  return `<tr><td data-label="Waktu" class="muted small">${formatDate(log.ts)}</td><td data-label="Pengguna"><b>${escapeHtml(log.actor)}</b> ${roleTag}</td>
    <td data-label="Aksi"><span class="tag ${isFailure ? 'err' : ''}">${escapeHtml(log.action)}</span></td><td data-label="Detail">${escapeHtml(log.detail)}</td><td data-label="IP" class="muted small">${escapeHtml(log.ip)}</td></tr>`;
}

const logsView = () => `
  <div class="page-head"><div><h2>Log aktivitas</h2><p class="muted">150 aktivitas terakhir di toko, termasuk login gagal dan akses yang ditolak.</p></div><button class="btn" data-act="reload">Perbarui data</button></div>
  <div class="tbl-wrap"><table><thead><tr><th>Waktu</th><th>Pengguna</th><th>Aksi</th><th>Detail</th><th>IP</th></tr></thead><tbody>
  ${state.logs.map(logRowHtml).join('') || `<tr><td colspan="5">${emptyState('Belum ada aktivitas')}</td></tr>`}
  </tbody></table></div>`;

export const views = {
  shop: shopView,
  dashboard: dashboardView,
  orders: ordersView,
  products: productsView,
  users: usersView,
  logs: logsView
};