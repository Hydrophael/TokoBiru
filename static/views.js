// TokoBiru - tampilan: fungsi yang menghasilkan HTML tiap halaman

import {
  $,
  $$,
  MAX_CART_QTY,
  NAV,
  ORDER_FLOW,
  ROLE_LABEL,
  SHOP_PAGE_SIZE,
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
  miniHtml,
  productImage,
  tileVisualHtml,
  state,
  statusTag,
  stockInfo,
  stockNote,
  storage
} from './core.js';
import { EASE, burst, linkLabels, openModal, reducedMotion, toast, tweenNumber } from './ui.js';
import { PHOTO_HINT, photoPreviewHtml } from './photo.js';

// === Modal pesanan berhasil ===

// Kotak "Cara bayar": dipakai di dialog sukses checkout dan di kartu pesanan yang masih menunggu bayar.
// Tiap baris: label kecil di atas, nilai di bawahnya, tombol Salin di kanan, jadi nilai panjang tidak berantakan.
function paymentBoxHtml(order, title = '') {
  const deadline = order.expires_at ? `Bayar sebelum <b>${formatDate(order.expires_at)}</b>` : '';
  const head = title || deadline
    ? `<div class="r-pay-head">${title ? `<b>${title}</b>` : ''}${deadline ? `<span>${deadline}</span>` : ''}</div>` : '';
  return `<section class="r-pay"${title ? ` aria-label="${title}"` : ''}>
    ${head}
    ${payRow('Nominal', formatRupiah(order.total), order.total)}
    ${payRow('Kode pesanan', order.code, order.code)}
    ${state.payInfo ? payRow('Tujuan', state.payInfo, state.payInfo, 'Tujuan bayar') : ''}
    <p class="r-pay-hint">Cantumkan kode pesanan saat transfer.</p>
  </section>`;
}

export function showOrderSuccess(order) {
  if (!order) return;
  openModal(`<div class="done"><svg class="done-ic" viewBox="0 0 52 52" aria-hidden="true"><circle cx="26" cy="26" r="24"/><path d="M15 27l8 8 14-19"/></svg>
    <h3>Pesanan berhasil dibuat</h3><p class="sub">Satu langkah lagi: bayar agar pesanan segera diproses.</p></div>
    ${paymentBoxHtml(order)}
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
        autocapitalize="none" spellcheck="false" placeholder="Username atau email Anda"
        autocomplete="username" required maxlength="120"></div>
      <div class="field" style="margin-bottom:10px"><label for="f-pw">Password</label><input class="input" id="f-pw" name="password"
        type="password" placeholder="Password Anda" autocomplete="current-password" required maxlength="128"></div>
      <label class="showpw"><input type="checkbox" data-act="toggle-pw"> Tampilkan password</label>
      <button class="btn primary block" type="submit">Masuk</button>
    </form>`;

// Tautan hanya muncul bila server sudah dikonfigurasi untuk mengirim email
const forgotLinkHtml = () => state.resetEnabled
  ? '<p class="alt"><button type="button" class="linkbtn" data-act="forgot-open">Lupa password?</button></p>'
  : '';

const registerFormHtml = () => `
    <h2>Buat akun</h2><p class="muted">Daftar sebagai pelanggan, gratis.</p>
    <form data-form="register" novalidate>
      <div class="form-alert" role="alert"></div>
      <div class="pair">
      <div class="field"><label for="r-name">Nama lengkap</label><input class="input" id="r-name" name="name"
        placeholder="Nama lengkap Anda" required maxlength="50" autocomplete="name"></div>
      <div class="field"><label for="r-user">Username</label><input class="input" id="r-user" name="username"
        autocapitalize="none" spellcheck="false" placeholder="Pilih username unik" required maxlength="20" autocomplete="username"></div>
      </div>
      <div class="pair">
      <div class="field"><label for="r-email">Email</label><input class="input" id="r-email" name="email"
        type="email" placeholder="nama@email.com" required maxlength="120" autocomplete="email" autocapitalize="none" spellcheck="false"></div>
      <div class="field"><label for="r-email2">Ulangi email</label><input class="input" id="r-email2" name="email_confirm"
        type="email" placeholder="Ketik ulang email" required maxlength="120" autocomplete="off" autocapitalize="none" spellcheck="false"></div>
      </div>
      <div class="pair">
      <div class="field"><label for="r-pw">Password</label><input class="input" id="r-pw" name="password"
        type="password" placeholder="Minimal 8 karakter" required minlength="8" maxlength="128" autocomplete="new-password" aria-describedby="r-pw-hint"></div>
      <div class="field"><label for="r-pw2">Ulangi password</label><input class="input" id="r-pw2" name="confirm"
        type="password" placeholder="Ulangi password" required autocomplete="new-password"></div>
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
        <h1><span class="ln"><span>Rak penuh,</span></span><span class="ln"><span>stok jujur.</span></span></h1>
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

// Kartu terdiri dari tab (tetap) dan area formulir (diganti saat pindah tab)
function authTabsHtml(tab) {
  const isLogin = tab === 'login';
  return `<div class="switch-tabs" role="tablist" data-tab="${tab}">
        <button role="tab" aria-selected="${isLogin}" class="${isLogin ? 'active' : ''}" data-act="auth-tab" data-tab="login">Masuk</button>
        <button role="tab" aria-selected="${!isLogin}" class="${!isLogin ? 'active' : ''}" data-act="auth-tab" data-tab="register">Daftar</button>
      </div>`;
}

function authFormAreaHtml(tab) {
  const isLogin = tab === 'login';
  return `${isLogin ? loginFormHtml() + forgotLinkHtml() : registerFormHtml()}
      <p class="alt muted">${isLogin ? 'Belum punya akun?' : 'Sudah punya akun?'} <button type="button" class="linkbtn" data-act="auth-tab" data-tab="${isLogin ? 'register' : 'login'}">${isLogin ? 'Daftar gratis' : 'Masuk'}</button></p>`;
}

const authPanelHtml = tab =>
  `<section class="auth-panel"><div class="auth-card">${authTabsHtml(tab)}<div class="auth-swap">${authFormAreaHtml(tab)}</div></div></section>`;

// Fokus otomatis hanya di perangkat dengan mouse (hindari keyboard muncul di HP)
function focusFirstField() {
  if (!matchMedia('(hover:hover) and (pointer:fine)').matches) return;
  const firstInput = $('.auth-card form input:not([type=checkbox])');
  if (firstInput) firstInput.focus();
}

// Pindah Masuk/Daftar: bagian kiri tidak disentuh. Formulir lama keluar, kartu menyesuaikan tinggi,
// lalu isi baru masuk satu per satu dari arah tab yang dipilih.
let swapToken = 0;

async function swapAuthTab(card, tab) {
  const tabs = $('.switch-tabs', card);
  if (tabs.dataset.tab === tab) return;

  const swap = $('.auth-swap', card);
  const token = ++swapToken;
  swap.getAnimations().forEach(animation => animation.cancel());  // klik tab lagi di tengah animasi
  swap.style.overflow = '';
  swap.style.pointerEvents = '';
  const fromHeight = swap.offsetHeight;
  const direction = tab === 'register' ? 1 : -1;

  tabs.dataset.tab = tab;
  $$('button', tabs).forEach(button => {
    const active = button.dataset.tab === tab;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', active);
  });

  const replaceContent = () => {
    swap.getAnimations().forEach(animation => animation.cancel());
    swap.innerHTML = authFormAreaHtml(tab);
    swap.style.pointerEvents = '';
    linkLabels(swap);
    focusFirstField();
  };

  if (reducedMotion.matches) return replaceContent();

  // 1. isi lama keluar ke arah berlawanan
  swap.style.pointerEvents = 'none';
  try {
    await swap.animate(
      [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: `translateX(${-direction * 14}px)` }],
      { duration: 90, easing: 'ease-in', fill: 'forwards' }
    ).finished;
  } catch { return; }              // dibatalkan oleh pemanggilan berikutnya
  if (token !== swapToken) return;

  // 2. ganti isi, lalu tinggi kartu menyesuaikan
  replaceContent();
  const toHeight = swap.offsetHeight;
  if (fromHeight !== toHeight) {
    swap.style.overflow = 'hidden';
    swap.animate([{ height: fromHeight + 'px' }, { height: toHeight + 'px' }], { duration: 260, easing: EASE })
      .onfinish = () => { swap.style.overflow = ''; };
  }

  // 3. bagian-bagian formulir masuk bergantian
  staggerIn(swap, direction, 0, { duration: 260, step: 18 });
}

// Judul, kolom isian, dan tombol muncul satu per satu (direction 0 = naik dari bawah saja)
function staggerIn(swap, direction, startDelay, { duration = 420, step = 36 } = {}) {
  if (reducedMotion.matches) return;
  const parts = $$(':scope > h2, :scope > p, :scope > form > *', swap).filter(el => el.getClientRects().length);
  parts.forEach((el, index) => el.animate(
    [{ opacity: 0, transform: `translate(${direction * 12}px, 10px)` }, { opacity: 1, transform: 'none' }],
    { duration, delay: startDelay + index * step, easing: EASE, fill: 'backwards' }
  ));
}

export function renderAuth(tab = state.authTab) {
  state.authTab = tab;

  const card = $('#app .auth .auth-card');
  if (card) {
    // Halaman masuk sudah tampil: ganti formulirnya saja, bagian kiri tetap utuh
    swapAuthTab(card, tab);
    return;
  }

  $('#app').innerHTML = `
  <div class="auth">
    ${authArtHtml()}
    ${authPanelHtml(tab)}
  </div>`;
  startPriceTagRotation();
  linkLabels($('#app'));
  focusFirstField();
  staggerIn($('.auth-swap'), 0, 460);   // setelah kartu muncul
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

const skeletonHtml = () => `<div class="shelf">${'<div class="skeleton"></div>'.repeat(8)}</div>`;

// Penanda menu aktif meluncur ke tombol yang dipilih (posisi dibaca dari tombolnya)
function moveNavIndicator() {
  const nav = $('.nav');
  const active = nav && $('button.active', nav);
  if (!active) return;

  const first = !nav.classList.contains('ready');
  nav.style.setProperty('--x', active.offsetLeft + 'px');
  nav.style.setProperty('--y', active.offsetTop + 'px');
  nav.style.setProperty('--w', active.offsetWidth + 'px');
  nav.style.setProperty('--h', active.offsetHeight + 'px');
  if (first) requestAnimationFrame(() => requestAnimationFrame(() => nav.classList.add('ready')));
}

function updateNav() {
  $$('.nav button').forEach(button => {
    const active = button.dataset.view === state.view;
    button.classList.toggle('active', active);
    button.setAttribute('aria-current', active ? 'page' : 'false');
  });
  moveNavIndicator();
}

let navFrame;
addEventListener('resize', () => { cancelAnimationFrame(navFrame); navFrame = requestAnimationFrame(moveNavIndicator); });
if (document.fonts && document.fonts.ready) document.fonts.ready.then(moveNavIndicator);

export function renderShell() {
  const user = state.user;
  const navItems = NAV.filter(item => item.roles.includes(user.role));
  const customer = isCustomer();

  // Kerangka sudah tampil (pindah menu): header tidak digambar ulang, hanya penanda menu yang bergeser
  const header = $('#app .top');
  if (header && header.dataset.user === String(user.id)) {
    updateNav();
    const content = $('#content');
    content.classList.remove('fresh');
    content.innerHTML = skeletonHtml();
    return;
  }

  $('#app').innerHTML = `
  <header class="top" data-user="${escapeHtml(user.id)}"><div class="top-in">
    ${brandHtml()}
    <nav class="nav" aria-label="Menu utama"><span class="nav-ind" aria-hidden="true"></span>${navHtml(navItems)}</nav>
    <div class="top-r">
      ${customer ? `<button class="btn cart-btn" data-act="open-cart">${icon('cart')}<span class="hide-m">Keranjang</span><span class="count num" id="cart-count">0</span></button>` : ''}
      <div class="who"><b>${escapeHtml(user.name)}</b><span class="tag ${user.role}">${ROLE_LABEL[user.role]}</span></div>
      <button class="btn sm" data-act="change-password" aria-label="Ganti password" title="Ganti password">${icon('key', 15)}</button>
      <button class="btn sm" data-act="logout" aria-label="Keluar">${icon('out', 15)}<span>Keluar</span></button>
    </div>
  </div></header>
  <main class="wrap"><div id="content">${skeletonHtml()}</div></main>
  ${customer ? cartDrawerHtml() : ''}`;

  moveNavIndicator();
  if (customer) drawCart();
}

// === Tampilan ===

// --- Belanja ---

const truncationNotice = () => state.productsTotal > state.products.length
  ? `<p class="muted small" role="status">Katalog sangat besar: hanya ${state.products.length} dari ${state.productsTotal} produk yang dimuat.</p>`
  : '';

// Filter tambahan (harga dan stok). Kategori dan kata pencarian punya kontrolnya sendiri.
const hasPriceFilter = () => state.filters.min !== null || state.filters.max !== null;
export const activeFilterCount = () => (hasPriceFilter() ? 1 : 0) + (state.filters.inStock ? 1 : 0);
export const hasAnyFilter = () => Boolean(state.category || state.query.trim() || activeFilterCount());

// Produk yang lolos semua filter, belum diurutkan.
// skipCategory = true dipakai untuk menghitung jumlah produk per kategori pada rel kategori.
function matchingProducts(skipCategory = false) {
  const query = state.query.trim().toLowerCase();
  const { inStock, min, max } = state.filters;
  // Hasil pencarian server (indeks teks) dipakai bila sudah tiba; sebelum itu, filter nama di sisi klien
  const rank = query && state.searchIds ? new Map(state.searchIds.map((id, index) => [id, index])) : null;
  const matchesQuery = p => rank ? rank.has(p.id) : (!query || p.name.toLowerCase().includes(query));

  const list = state.products.filter(p =>
    (skipCategory || !state.category || p.category === state.category) &&
    matchesQuery(p) &&
    (!inStock || p.stock > 0) &&
    (min === null || p.price >= min) &&
    (max === null || p.price <= max));
  return { list, rank };
}

function filteredProducts() {
  const { list, rank } = matchingProducts();
  const sort = state.sort;

  const compare = (a, b) => {
    if (sort === 'low') return a.price - b.price;
    if (sort === 'high') return b.price - a.price;
    if (sort === 'auto' && rank) return rank.get(a.id) - rank.get(b.id);   // sedang mencari: paling relevan dulu
    return a.name.localeCompare(b.name, 'id');
  };

  return list.sort((a, b) => (a.stock === 0) - (b.stock === 0) || compare(a, b)); // stok habis selalu di bawah
}

const countLabel = total =>
  total > SHOP_PAGE_SIZE ? `${Math.min(state.shopLimit, total)} dari ${total} produk` : `${total} produk`;

// Papan lorong: kategori terpilih, kini berupa papan kecil di kepala daftar (bukan spanduk besar)
export function aisleHtml() {
  const aisleNumber = state.categories.indexOf(state.category) + 1;
  return `<span class="aisle-sign"><span class="a-no">${aisleNumber ? 'Lorong ' + aisleNumber : 'Seluruh toko'}</span><b>${state.category ? escapeHtml(state.category) : 'Semua kategori'}</b></span>`;
}

// Rel kategori: tiap kategori memperlihatkan jumlah produk yang cocok dengan pencarian/filter saat ini
function categoryCounts() {
  const counts = {};
  matchingProducts(true).list.forEach(p => { counts[p.category] = (counts[p.category] || 0) + 1; });
  return counts;
}

export function categoryRailHtml() {
  const counts = categoryCounts();
  const total = Object.values(counts).reduce((sum, n) => sum + n, 0);
  const chip = (value, label, count) =>
    `<button type="button" class="${state.category === value ? 'active' : ''}${count ? '' : ' zero'}" data-act="cat" data-cat="${escapeHtml(value)}" aria-pressed="${state.category === value}">${escapeHtml(label)}<span class="n num">${count}</span></button>`;
  return chip('', 'Semua', total) + state.categories.map(category => chip(category, category, counts[category] || 0)).join('');
}

// Penanda ada kategori yang tersembunyi di kiri/kanan rel (pudar di tepi + panah di desktop)
export function updateRailEdges() {
  const rail = $('#rail');
  const wrap = $('#rail-wrap');
  if (!rail || !wrap) return;
  const maxScroll = rail.scrollWidth - rail.clientWidth;
  wrap.classList.toggle('can-prev', rail.scrollLeft > 4);
  wrap.classList.toggle('can-next', rail.scrollLeft < maxScroll - 4);
}

export function scrollRail(direction) {
  const rail = $('#rail');
  if (rail) rail.scrollBy({ left: direction * rail.clientWidth * 0.7, behavior: 'smooth' });
}

addEventListener('resize', updateRailEdges);
if (document.fonts && document.fonts.ready) document.fonts.ready.then(updateRailEdges);

// Chip filter aktif: kata pencarian, harga, dan stok. Setiap chip bisa dilepas satu per satu.
function chipsHtml() {
  const chips = [];
  const query = state.query.trim();
  const { min, max, inStock } = state.filters;

  if (query) chips.push(['q', `Cari “${query}”`]);
  if (hasPriceFilter()) {
    const label = min !== null && max !== null ? `${formatRupiah(min)} – ${formatRupiah(max)}`
      : min !== null ? `Mulai ${formatRupiah(min)}` : `Sampai ${formatRupiah(max)}`;
    chips.push(['price', label]);
  }
  if (inStock) chips.push(['stock', 'Stok tersedia']);
  if (!chips.length) return '';

  const items = chips.map(([key, label]) =>
    `<button type="button" class="chip" data-act="rm-filter" data-f="${key}" aria-label="Hapus filter ${escapeHtml(label)}"><span>${escapeHtml(label)}</span>${icon('x', 14)}</button>`
  ).join('');
  const clearAll = chips.length + (state.category ? 1 : 0) > 1
    ? '<button type="button" class="chip clear-all" data-act="clear-all">Hapus semua</button>' : '';
  return items + clearAll;
}

// Urutan: tanpa pencarian "Nama A–Z" (auto); saat mencari "Paling relevan" jadi pilihan awal
const sortOptionHtml = (value, label) =>
  `<option value="${value}"${state.sort === value ? ' selected' : ''}>${label}</option>`;

function sortOptionsHtml() {
  const searching = Boolean(state.query.trim());
  return sortOptionHtml('auto', searching ? 'Paling relevan' : 'Nama A–Z') +
    (searching ? sortOptionHtml('name', 'Nama A–Z') : '') +
    sortOptionHtml('low', 'Harga terendah') + sortOptionHtml('high', 'Harga tertinggi');
}

function syncSortOptions() {
  const select = $('[data-sort]');
  if (!select) return;
  const searching = Boolean(state.query.trim());
  if (select.dataset.q === String(searching)) return;   // pilihan tidak berubah: jangan ganggu dropdown yang sedang dipakai
  if (!searching && state.sort === 'name') state.sort = 'auto';
  select.dataset.q = String(searching);
  select.innerHTML = sortOptionsHtml();
}

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
  const description = String(product.description ?? '').trim();
  return `
    <article class="label${product.stock === 0 ? ' soldout' : ''}" data-card="${product.id}" style="--i:${Math.min(index, 8)}">
      <div class="tile p${hashString(product.id) % 4}${productImage(product) ? ' has-photo' : ''}" data-act="detail" data-id="${product.id}"><span class="cat tag">${escapeHtml(product.category)}</span>${tileVisualHtml(product)}</div>
      <div class="lbody"><h3><button type="button" class="plink" data-act="detail" data-id="${product.id}" title="${escapeHtml(product.name)}">${escapeHtml(product.name)}</button></h3>${description ? `<p class="ldesc" data-act="detail" data-id="${product.id}">${escapeHtml(description)}</p>` : ''}${stockNote(product)}</div>
      ${cardFoot(product)}
    </article>`;
}

// Bagian bawah daftar: kemajuan dan tombol "Tampilkan lagi". Kartu berikutnya juga dimuat otomatis saat daftar hampir habis.
function moreHtml(total) {
  if (total <= SHOP_PAGE_SIZE) return '';
  const shown = Math.min(state.shopLimit, total);
  if (shown >= total) return `<p class="muted small num">Semua ${total} produk sudah tampil</p>`;

  const next = Math.min(SHOP_PAGE_SIZE, total - shown);
  return `<p class="muted small num">Menampilkan ${shown} dari ${total} produk</p>
    <div class="more-bar" aria-hidden="true"><i style="width:${Math.round(shown / total * 100)}%"></i></div>
    <button type="button" class="btn" data-act="more">Tampilkan ${next} lagi</button>`;
}

function productCards(firstRender = false, list = filteredProducts()) {
  if (!state.products.length) return emptyState('Katalog masih kosong', 'Toko belum menambahkan produk. Silakan cek lagi nanti.');
  if (!list.length) {
    return emptyState('Tidak ada produk yang cocok', 'Coba kata kunci lain, ubah rentang harga, atau pilih kategori Semua.',
      hasAnyFilter() ? '<button class="btn primary" data-act="clear-all">Hapus semua filter</button>' : '');
  }
  const layout = state.layout === 'rows' ? ' rows' : '';
  const photos = list.some(product => productImage(product)) ? ' photos' : '';   // ada foto: semua kartu berukuran sama supaya baris rata
  return `<div class="shelf${firstRender ? ' stagger' : ''}${layout}${photos}">${list.slice(0, state.shopLimit).map(productCardHtml).join('')}</div>
    <div class="more" id="more">${moreHtml(list.length)}</div>`;
}

// Memuat kartu secara bertahap: katalog ratusan produk tidak digambar sekaligus
let moreObserver = null;

export function watchMore() {
  if (moreObserver) moreObserver.disconnect();
  const sentinel = $('#more');
  if (!sentinel || typeof IntersectionObserver === 'undefined') return;

  moreObserver = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) appendCards();
  }, { rootMargin: '0px 0px 480px 0px' });
  moreObserver.observe(sentinel);
}

export function appendCards() {
  const shelf = $('#plist .shelf');
  if (!shelf) return;

  const list = filteredProducts();
  const from = shelf.children.length;
  if (from >= list.length) return;

  state.shopLimit = from + SHOP_PAGE_SIZE;
  shelf.insertAdjacentHTML('beforeend', list.slice(from, state.shopLimit).map(productCardHtml).join(''));
  $('#more').innerHTML = moreHtml(list.length);
  const counter = $('#rcount');
  if (counter) counter.textContent = countLabel(list.length);
  watchMore();   // dipasang ulang: bila ujung daftar masih dekat layar, tahap berikutnya langsung dimuat
}

// Sinkronkan bagian di sekitar daftar (jumlah, rel kategori, papan lorong, chip, tombol filter, urutan)
function syncShopControls(total) {
  const setHtml = (selector, html) => { const el = $(selector); if (el) el.innerHTML = html; };

  const counter = $('#rcount');
  if (counter) counter.textContent = countLabel(total);
  setHtml('#rail', categoryRailHtml());
  setHtml('#aisle', aisleHtml());
  setHtml('#chips', chipsHtml());

  const clearButton = $('.search .clear');
  if (clearButton) clearButton.hidden = !state.query;

  const filterButton = $('.filter-btn');
  if (filterButton) {
    const count = activeFilterCount();
    const badge = $('.fcount', filterButton);
    filterButton.classList.toggle('on', count > 0);
    badge.hidden = !count;
    badge.textContent = count;
  }
  syncSortOptions();
  updateRailEdges();
}

// Gambar ulang daftar dari awal (kata cari, kategori, urutan, atau filter berubah)
export function renderList() {
  state.shopLimit = SHOP_PAGE_SIZE;
  const list = filteredProducts();
  $('#plist').innerHTML = productCards(false, list);
  syncShopControls(list.length);
  watchMore();
}

export function afterShopRender() {
  watchMore();
  updateRailEdges();
}

// Jendela filter: rentang harga dan sembunyikan stok habis (jadi lembar bawah di HP)
export function filterModal() {
  const { inStock, min, max } = state.filters;
  const prices = state.products.map(p => p.price);
  const range = prices.length
    ? `Harga produk saat ini berkisar ${formatRupiah(Math.min(...prices))} sampai ${formatRupiah(Math.max(...prices))}.`
    : '';

  openModal(`<h3>Filter produk</h3>
    <p class="sub">${range}</p>
    <div class="row2">
      <div class="field"><label>Harga terendah (Rp)</label><input class="input num" id="f-min" inputmode="numeric" autocomplete="off" placeholder="0" value="${min ?? ''}"></div>
      <div class="field"><label>Harga tertinggi (Rp)</label><input class="input num" id="f-max" inputmode="numeric" autocomplete="off" placeholder="Tanpa batas" value="${max ?? ''}"></div>
    </div>
    <label class="showpw"><input type="checkbox" id="f-stock"${inStock ? ' checked' : ''}> Sembunyikan produk yang habis</label>
    <div class="foot"><button class="btn" data-act="reset-filters">Atur ulang</button><button class="btn primary" data-act="apply-filter">Tampilkan hasil</button></div>`);
}

const layoutButton = (layout, label, iconName) =>
  `<button type="button" data-act="layout" data-layout="${layout}" aria-pressed="${state.layout === layout}" aria-label="${label}" title="${label}">${icon(iconName, 18)}</button>`;

const railArrow = (side, label) =>
  `<button type="button" class="rail-arrow ${side}" data-act="rail-${side === 'prev' ? 'prev' : 'next'}" aria-label="${label}" tabindex="-1">${icon(side === 'prev' ? 'left' : 'right', 18)}</button>`;

function shopView() {
  const list = filteredProducts();
  const filterCount = activeFilterCount();
  const searching = Boolean(state.query.trim());

  return `
  <div class="page-head"><div><h2>Belanja</h2><p class="muted">Pilih barang, masukkan ke keranjang, lalu buat pesanan.</p></div></div>
  <div class="tools" id="tools">
    <div class="tools-row">
      <label class="search">${icon('search')}<input data-input="shop-search" placeholder="Cari nama produk" maxlength="50" aria-label="Cari produk" autocomplete="off" value="${escapeHtml(state.query)}"><button type="button" class="clear" data-act="clear-search" aria-label="Hapus pencarian"${searching ? '' : ' hidden'}>${icon('x', 16)}</button></label>
      <button type="button" class="btn filter-btn${filterCount ? ' on' : ''}" data-act="open-filter" aria-label="Filter harga dan stok">${icon('sliders')}<span class="hide-m">Filter</span><b class="fcount num"${filterCount ? '' : ' hidden'}>${filterCount}</b></button>
    </div>
    <div class="rail-wrap" id="rail-wrap">
      ${railArrow('prev', 'Geser kategori ke kiri')}
      <div class="rail" id="rail">${categoryRailHtml()}</div>
      ${railArrow('next', 'Geser kategori ke kanan')}
    </div>
  </div>
  <div class="results-head">
    <div class="aisle" id="aisle" aria-hidden="true">${aisleHtml()}</div>
    <span class="muted small rcount" id="rcount" aria-live="polite">${countLabel(list.length)}</span>
    <div class="rh-tools">
      <label class="sortsel"><span class="hide-m">Urutkan</span><select class="select sm" data-sort data-q="${searching}" aria-label="Urutkan produk">${sortOptionsHtml()}</select></label>
      <div class="seg" role="group" aria-label="Tampilan daftar">${layoutButton('grid', 'Tampilan kartu', 'grid')}${layoutButton('rows', 'Tampilan daftar', 'list')}</div>
    </div>
  </div>
  <div class="chips" id="chips">${chipsHtml()}</div>
  ${truncationNotice()}
  <div id="plist">${productCards(state.fresh, list)}</div>
  <button type="button" class="to-top" data-act="to-top" aria-label="Kembali ke atas" hidden>${icon('up', 20)}</button>`;
}

// --- Keranjang ---

export const cartLines = () =>
  Object.entries(state.cart)
    .map(([id, qty]) => ({ product: state.productMap[id], qty }))
    .filter(line => line.product);

export const cartTotal = lines => lines.reduce((sum, line) => sum + line.product.price * line.qty, 0);

function cartItemHtml({ product, qty }) {
  return `
    <div class="citem">${miniHtml(product)}
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
  tweenNumber($('#cart-total'), total, formatRupiah);

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

const orderPaymentHtml = order => paymentBoxHtml(order, 'Cara bayar');

const orderLineHtml = item =>
  `<li><span>${escapeHtml(item.name)}</span><span class="num">${formatRupiah(item.subtotal)}</span><em class="num">${item.qty} × ${formatRupiah(item.price)}</em></li>`;

const infoRow = (label, value) => (value ? `<div><dt>${label}</dt><dd>${value}</dd></div>` : '');

function orderCardHtml(order, staff, index = 0) {
  const [statusLabel, statusColor] = STATUS[order.status];
  const justUpdated = order.id === state.justUpdatedOrderId ? ' just' : '';
  const owner = staff ? ', atas nama <b>' + escapeHtml(order.username) + '</b>' : '';
  const info = `<dl class="r-info">${infoRow('Kirim ke', escapeHtml(order.address))}${
    infoRow('HP/WA', order.phone ? `<span class="num">${escapeHtml(order.phone)}</span>` : '')}${
    infoRow('Catatan', escapeHtml(order.note))}</dl>`;
  const autoCancel = order.cancel_reason === 'expired'
    ? '<p class="r-auto">Dibatalkan otomatis karena melewati batas waktu bayar.</p>' : '';
  const payment = !staff && order.status === 'pending' ? orderPaymentHtml(order) : '';

  return `
    <article class="receipt st-${order.status}" style="--i:${Math.min(index, 8)}">
      <div class="r-top"><span class="r-code num">${escapeHtml(order.code)}</span>
        <span class="muted small r-date">${formatDate(order.created_at)}${owner}</span>
        <span class="stamp ${statusColor}${justUpdated}">${statusLabel}</span></div>
      ${timelineHtml(order.status)}
      <ul class="r-lines">${order.items.map(orderLineHtml).join('')}</ul>
      <div class="r-total"><span>Total</span><strong class="num">${formatRupiah(order.total)}</strong></div>
      ${info}${autoCancel}
      ${payment}
      <div class="acts">${orderActions(order)}</div>
    </article>`;
}

export function orderCards(animate = false) {
  const staff = isStaff();
  const list = state.orders.filter(o => !state.orderFilter || o.status === state.orderFilter);

  if (!list.length) {
    return emptyState(
      state.orderFilter ? 'Tidak ada pesanan dengan status ini' : 'Belum ada pesanan',
      staff ? 'Pesanan pelanggan akan muncul di sini.' : 'Pesanan Anda akan muncul di sini setelah checkout.'
    );
  }
  return `<div class="receipts${animate ? ' stagger' : ''}">${list.map((order, index) => orderCardHtml(order, staff, index)).join('')}</div>`;
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
  <div id="olist">${orderCards(state.fresh)}</div>`;
}

// --- Ringkasan ---

function dashboardFactsHtml(stats) {
  const showUserTotals = state.user.role === 'master' && stats.users;
  const userTotals = showUserTotals
    ? `<div class="fact" style="grid-column:1/-1"><b class="num">${stats.users.user + stats.users.admin + stats.users.master}</b><span>Pengguna: ${stats.users.user} pelanggan, ${stats.users.admin} admin, ${stats.users.master} master</span></div>`
    : '';

  const today = stats.today || { orders: 0, revenue: 0 };
  return `<div class="facts">
      <div class="fact"><b class="num">${today.orders}</b><span>Pesanan hari ini</span></div>
      <div class="fact"><b class="num">${formatRupiah(today.revenue)}</b><span>Pendapatan hari ini (sudah dibayar)</span></div>
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
  ? stats.low_stock.map(product => `<div class="line"><span class="cell">${miniHtml(product)}<span><b>${escapeHtml(product.name)}</b><br><span class="muted small">${escapeHtml(product.category)}</span></span></span>${stockInfo(product)}</div>`).join('')
  : '<p class="muted">Semua stok masih aman.</p>';

function dashboardView() {
  const stats = state.stats;
  return `
  <div class="page-head"><div><h2>Ringkasan</h2><p class="muted">Penjualan, pesanan, dan stok. Angka &ldquo;hari ini&rdquo; dihitung sejak pukul 00.00 WIB.</p></div>
    <button class="btn" data-act="reload">Perbarui data</button></div>
  <div class="lead">
    <div class="revenue"><span>Total pendapatan dari pesanan yang sudah dibayar</span><strong class="num">${formatRupiah(stats.revenue)}</strong></div>
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

function productRowHtml(product, index = 0) {
  return `<tr style="--i:${Math.min(index, 10)}">
    <td data-label="Produk"><div class="cell">${miniHtml(product)}<div><b>${escapeHtml(product.name)}</b><div class="muted small">${escapeHtml(String(product.description ?? '').slice(0, 60))}</div></div></div></td>
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
  ${truncationNotice()}
  <div class="tbl-wrap${state.fresh ? ' stagger' : ''}"><table><thead><tr><th>Produk</th><th>Kategori</th><th>Harga</th><th>Stok</th><th class="right">Aksi</th></tr></thead><tbody id="prows">${productRows()}</tbody></table></div>`;

export function productModal(product) {
  const isEdit = Boolean(product);
  const values = product || { name: '', category: '', price: '', stock: '', description: '' };
  const image = productImage(product);
  const categoryOptions = state.categories.map(c => `<option value="${escapeHtml(c)}">`).join('');

  openModal(`
    <h3>${isEdit ? 'Ubah produk' : 'Tambah produk'}</h3><p class="sub">${isEdit ? 'Perubahan langsung tampil di katalog pelanggan.' : 'Produk baru langsung muncul di katalog.'}</p>
    <form data-form="product" data-id="${isEdit ? product.id : ''}" novalidate>
      <div class="form-alert" role="alert"></div>
      ${isEdit ? `<input type="hidden" name="base_stock" value="${escapeHtml(product.stock)}">` : ''}
      <div class="field photo-field"><label>Foto produk (opsional)</label>
        <div class="photo-row">
          <div class="photo-preview" data-photo-preview>${photoPreviewHtml(image)}</div>
          <div class="photo-side">
            <input type="file" class="sr-only" accept="image/*" data-photo-input>
            <input type="hidden" name="image" value="" disabled>
            <div class="acts"><button type="button" class="btn sm" data-act="photo-pick">${icon('plus', 14)} Pilih foto</button>
              <button type="button" class="btn sm danger" data-act="photo-clear"${image ? '' : ' hidden'}>${icon('trash', 13)} Hapus foto</button></div>
            <p class="muted small" data-photo-note>${PHOTO_HINT}</p>
          </div>
        </div></div>
      <div class="field"><label>Nama produk</label><input class="input" name="name" required maxlength="80" placeholder="Contoh: Beras Premium 5 kg" value="${escapeHtml(values.name)}"></div>
      <div class="row2">
        <div class="field"><label>Kategori</label><input class="input" name="category" list="cats" required maxlength="30" placeholder="Contoh: Sembako" value="${escapeHtml(values.category)}"><datalist id="cats">${categoryOptions}</datalist></div>
        <div class="field"><label>Harga (Rp)</label><input class="input" name="price" type="number" placeholder="Contoh: 38000" min="100" max="100000000" step="1" required value="${escapeHtml(values.price)}"></div>
      </div>
      <div class="field"><label>Stok</label><input class="input" name="stock" type="number" placeholder="Contoh: 20" min="0" max="100000" step="1" required value="${escapeHtml(values.stock)}"></div>
      <div class="field"><label>Deskripsi (opsional)</label><textarea class="input" name="description" maxlength="300" placeholder="Keterangan singkat produk">${escapeHtml(values.description)}</textarea></div>
      <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Simpan produk</button></div>
    </form>`);
}

// --- Pengguna ---

const roleSelectHtml = user =>
  `<select class="select sm" data-change="user-role" data-id="${user.id}" aria-label="Role ${escapeHtml(user.username)}"><option value="user" ${user.role === 'user' ? 'selected' : ''}>Pelanggan</option><option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Admin</option></select>`;

const activeSwitchHtml = user =>
  `<label class="sw"><input type="checkbox" data-change="user-active" data-id="${user.id}" ${user.active ? 'checked' : ''} aria-label="Aktif ${escapeHtml(user.username)}"><span></span></label>`;

function userRowHtml(user, index = 0) {
  // Akun master dan akun sendiri tidak bisa diubah dari sini
  const locked = user.role === 'master' || user.id === state.user.id;
  return `<tr style="--i:${Math.min(index, 10)}"><td data-label="Pengguna"><div class="cell"><span class="mini">${escapeHtml(getInitials(user.name))}</span><div><b>${escapeHtml(user.name)}</b><div class="muted small">@${escapeHtml(user.username)}</div></div></div></td>
    <td data-label="Email">${escapeHtml(user.email)}</td>
    <td data-label="Role">${locked ? `<span class="tag ${user.role}">${ROLE_LABEL[user.role]}</span>` : roleSelectHtml(user)}</td>
    <td data-label="Aktif">${locked ? '<span class="tag ok">Aktif</span>' : activeSwitchHtml(user)}</td>
    <td data-label="Terdaftar" class="muted small">${formatDate(user.created_at)}</td>
    <td data-label="Aksi"><div class="acts end">${locked ? '<span class="muted small">Dilindungi</span>' : `<button class="btn sm danger" data-act="user-del" data-id="${user.id}" aria-label="Hapus ${escapeHtml(user.username)}">${icon('trash', 13)}</button>`}</div></td></tr>`;
}

const usersView = () => `
  <div class="page-head"><div><h2>Pengguna</h2><p class="muted">Atur role, nonaktifkan, atau hapus akun. Akun master tidak bisa diubah dari sini.</p></div>
    <button class="btn primary" data-act="user-new">${icon('plus', 15)} Tambah pengguna</button></div>
  <div class="tbl-wrap${state.fresh ? ' stagger' : ''}"><table><thead><tr><th>Pengguna</th><th>Email</th><th>Role</th><th>Aktif</th><th>Terdaftar</th><th class="right">Aksi</th></tr></thead><tbody>
  ${state.users.map(userRowHtml).join('')}</tbody></table></div>`;

export function userModal() {
  openModal(`<h3>Tambah pengguna</h3><p class="sub">Buat akun admin untuk staf, atau akun pelanggan.</p>
    <form data-form="user-create" novalidate><div class="form-alert" role="alert"></div>
      <div class="field"><label>Nama lengkap</label><input class="input" name="name" required maxlength="50" placeholder="Nama lengkap"></div>
      <div class="row2"><div class="field"><label>Username</label><input class="input" name="username" required maxlength="20" placeholder="Username unik"></div>
      <div class="field"><label>Role</label><select class="select" name="role"><option value="admin">Admin</option><option value="user">Pelanggan</option></select></div></div>
      <div class="field"><label>Email</label><input class="input" name="email" type="email" required maxlength="120" placeholder="nama@email.com"></div>
      <div class="field"><label>Password</label><input class="input" name="password" type="password" required minlength="8" maxlength="128" autocomplete="new-password" placeholder="Minimal 8 karakter"></div>
      <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Buat akun</button></div></form>`);
}

// --- Akun ---

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

// --- Pemulihan password: satu modal bertahap (email -> kode -> password baru -> selesai) ---
// Semua langkah dirender sekali lalu ditampilkan bergantian, jadi isian (mis. password) tidak hilang saat pengguna kembali.

const RESET_STEP_NAMES = ['Email', 'Kode', 'Password'];
const RESET_ANNOUNCE = {
  1: 'Langkah 1 dari 3: isi email',
  2: 'Langkah 2 dari 3: masukkan kode',
  3: 'Langkah 3 dari 3: buat password baru',
  4: 'Password berhasil diganti'
};
const OTP_LENGTH = 6;

// Satu <input> asli (isi otomatis dari SMS/email dan tempel tetap berfungsi) dengan enam kotak hanya sebagai tampilan
const otpHtml = () => `<div class="otp" data-otp>
        <input class="otp-input" name="code" data-digits inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" aria-describedby="otp-hint">
        <div class="otp-cells" aria-hidden="true">${Array.from({ length: OTP_LENGTH }, (_, k) => `<span class="otp-cell" style="--k:${k}"></span>`).join('')}</div>
      </div>`;

function resetWizardHtml(email) {
  const steps = RESET_STEP_NAMES.map((name, index) =>
    `<li data-s="${index + 1}"${index ? '' : ' class="now" aria-current="step"'}><i>${index + 1}</i><span>${name}</span></li>`
  ).join('');

  return `<div class="wz" data-keep data-step="1">
    <div class="wz-top">
      <ol class="wz-steps" aria-label="Langkah pemulihan password">${steps}</ol>
      <button type="button" class="btn sm flat wz-close" data-act="close-modal" aria-label="Tutup">${icon('x', 18)}</button>
    </div>
    <div class="wz-body">
      <section class="wz-panel" data-panel="1">
        <h3>Lupa password</h3><p class="sub">Masukkan email akun Anda. Kami kirim kode 6 angka untuk membuat password baru.</p>
        <form data-form="forgot" novalidate><div class="form-alert" role="alert"></div>
          <div class="field"><label>Email</label><input class="input" name="email" type="email" required maxlength="120" autocomplete="email" autocapitalize="none" spellcheck="false" placeholder="nama@email.com" value="${escapeHtml(email)}"></div>
          <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Kirim kode</button></div></form>
      </section>
      <section class="wz-panel" data-panel="2" hidden>
        <h3>Masukkan kode</h3><p class="sub">Jika akun dengan email <b class="email-chip" data-email></b> terdaftar, kode 6 angka sudah dikirim dan berlaku <span data-expires>15</span> menit. Cek juga folder spam.</p>
        <form data-form="code" novalidate><div class="form-alert" role="alert"></div>
          <div class="field"><label>Kode 6 angka</label>${otpHtml()}</div>
          <p class="otp-hint muted small" id="otp-hint">Ketik atau tempel 6 angka yang sudah dikirim.</p>
          <div class="resend"><span>Belum menerima kode?</span><button type="button" class="linkbtn" data-act="forgot-resend" disabled>Kirim ulang kode</button><i class="resend-bar" aria-hidden="true"></i></div>
          <div class="foot"><button type="button" class="btn" data-act="wiz-back">Ubah email</button><button type="submit" class="btn primary">Lanjut</button></div></form>
      </section>
      <section class="wz-panel" data-panel="3" hidden>
        <h3>Buat password baru</h3><p class="sub">Pilih password yang belum pernah Anda pakai. Perangkat lain yang sedang masuk akan keluar otomatis.</p>
        <form data-form="reset" data-pwcheck novalidate><div class="form-alert" role="alert"></div>
          <div class="field"><label>Password baru</label><input class="input" name="new_password" data-pw type="password" required minlength="8" maxlength="128" autocomplete="new-password" placeholder="Minimal 8 karakter"></div>
          <div class="field"><label>Ulangi password baru</label><input class="input" name="confirm" data-pw type="password" required autocomplete="new-password"></div>
          <ul class="pw-checks" aria-label="Syarat password">
            <li data-check="len">Minimal 8 karakter</li><li data-check="letter">Ada huruf</li>
            <li data-check="digit">Ada angka</li><li data-check="match">Kedua password sama</li>
          </ul>
          <label class="showpw"><input type="checkbox" data-act="toggle-pw"> Tampilkan password</label>
          <div class="foot"><button type="button" class="btn" data-act="wiz-back">Kembali</button><button type="submit" class="btn primary">Ganti password</button></div></form>
      </section>
      <section class="wz-panel" data-panel="4" hidden>
        <div class="done"><svg class="done-ic" viewBox="0 0 52 52" aria-hidden="true"><circle cx="26" cy="26" r="24"/><path d="M15 27l8 8 14-19"/></svg>
          <h3>Password berhasil diganti</h3><p class="sub">Silakan masuk dengan password baru Anda.</p></div>
        <div class="foot"><button type="button" class="btn primary block" data-act="wiz-finish">Masuk sekarang</button></div>
      </section>
    </div>
    <p class="sr-only" id="wz-live" role="status" aria-live="polite"></p>
  </div>`;
}

export function forgotModal(email = '') {
  state.reset = { email: '', sentTo: '', endAt: 0, code: '' };
  openModal(resetWizardHtml(email));
}

// Isi teks bantu (email tujuan, masa berlaku kode) lewat textContent supaya aman dari injeksi HTML
export function setResetInfo({ email, expires } = {}) {
  if (email !== undefined) $$('#modal-root [data-email]').forEach(el => { el.textContent = email; });
  if (expires !== undefined) $$('#modal-root [data-expires]').forEach(el => { el.textContent = expires; });
}

// Enam kotak mengikuti isi <input>: digit muncul membal, kotak aktif punya kursor
export function renderOtp(wrap) {
  const input = $('.otp-input', wrap);
  if (!input) return;
  const cells = $$('.otp-cell', wrap);
  const value = input.value;
  const previous = Number(wrap.dataset.len || 0);
  const focused = document.activeElement === input;
  const activeIndex = Math.min(value.length, cells.length - 1);

  cells.forEach((cell, index) => {
    const digit = value[index] || '';
    if (cell.textContent !== digit) cell.textContent = digit;
    cell.classList.toggle('filled', index < value.length);
    cell.classList.toggle('active', focused && index === activeIndex);
    if (index >= previous && index < value.length) {
      cell.classList.remove('pop');
      void cell.offsetWidth;   // paksa reflow agar animasi mulai ulang
      cell.classList.add('pop');
    }
  });

  wrap.dataset.len = value.length;
  if (value.length < cells.length) wrap.classList.remove('wave');
}

// Penanda langkah: garis penghubung terisi, langkah selesai berubah jadi centang
function setStepper(wz, step) {
  $$('.wz-steps li', wz).forEach(li => {
    const n = Number(li.dataset.s);
    const done = n < step;
    li.classList.toggle('done', done);
    li.classList.toggle('now', n === step);
    if (n === step) li.setAttribute('aria-current', 'step');
    else li.removeAttribute('aria-current');

    const mark = $('i', li);
    const kind = done ? 'check' : 'num';
    if (mark.dataset.kind !== kind) {
      mark.dataset.kind = kind;
      mark.innerHTML = done ? icon('check', 14) : String(n);
    }
  });
}

// Judul langkah yang sedang tampil menjadi nama dialog (dibaca pembaca layar)
function markTitle(wz, panel) {
  $$('h3', wz).forEach(heading => heading.removeAttribute('id'));
  const heading = $('h3', panel);
  if (heading) {
    heading.id = 'modal-title';
    heading.tabIndex = -1;
  }
  const modal = $('#modal-root .modal');
  if (modal) modal.setAttribute('aria-labelledby', 'modal-title');
}

function focusPanel(panel) {
  const target = $('input:not([type=checkbox]):not([type=hidden])', panel) || $('.btn.primary', panel);
  if (target) target.focus();
}

// Judul, teks, kolom isian, dan tombol muncul satu per satu dari arah perpindahan
function staggerPanel(panel, direction) {
  if (reducedMotion.matches) return;
  const parts = $$(':scope > h3, :scope > p, :scope > form > *, :scope > .done > *', panel)
    .filter(el => el.getClientRects().length);
  parts.forEach((el, index) => el.animate(
    [{ opacity: 0, transform: `translate(${direction * 14}px, 8px)` }, { opacity: 1, transform: 'none' }],
    { duration: 300, delay: index * 28, easing: EASE, fill: 'backwards' }
  ));
}

// Konfeti kecil setelah centang selesai tergambar
function celebrate(panel) {
  setTimeout(() => {
    const mark = $('.done-ic', panel);
    if (mark && mark.isConnected) burst(mark);
  }, 420);
}

// Pindah langkah: isi lama keluar, tinggi modal menyesuaikan dengan mulus, isi baru masuk berurutan.
// Panggilan beruntun aman: yang terakhir menang dan panel yang sedang tampil selalu dibaca dari DOM.
let wizardToken = 0;

export async function showResetStep(step) {
  const wz = $('#modal-root .wz');
  if (!wz) return;
  const next = $(`.wz-panel[data-panel="${step}"]`, wz);
  const current = $('.wz-panel:not([hidden])', wz);
  const body = $('.wz-body', wz);
  if (!next || !current || !body) return;

  const token = ++wizardToken;
  wz.dataset.step = step;
  setStepper(wz, step);
  const live = $('#wz-live', wz);
  if (live) live.textContent = RESET_ANNOUNCE[step] || '';

  if (current === next) {   // sudah di langkah ini (mis. tekan dua kali): batalkan animasi keluar yang tertunda
    next.getAnimations().forEach(animation => animation.cancel());
    next.style.pointerEvents = '';
    body.style.overflow = '';
    focusPanel(next);
    return;
  }

  const direction = step > Number(current.dataset.panel) ? 1 : -1;
  const reveal = () => {
    current.getAnimations().forEach(animation => animation.cancel());
    current.hidden = true;
    current.style.pointerEvents = '';
    next.hidden = false;
    markTitle(wz, next);
    focusPanel(next);
    if (step === 4) celebrate(next);
  };

  if (reducedMotion.matches) {
    reveal();
    return;
  }

  const fromHeight = body.offsetHeight;
  body.getAnimations().forEach(animation => animation.cancel());
  body.style.overflow = 'clip';        // geseran samping tidak boleh memunculkan scrollbar
  current.style.pointerEvents = 'none';
  try {
    await current.animate(
      [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: `translateX(${-direction * 18}px)` }],
      { duration: 110, easing: 'ease-in', fill: 'forwards' }
    ).finished;
  } catch { return; }                  // dibatalkan oleh panggilan berikutnya
  if (token !== wizardToken || !wz.isConnected) return;

  reveal();
  const toHeight = body.offsetHeight;
  if (fromHeight !== toHeight) {
    body.animate([{ height: fromHeight + 'px' }, { height: toHeight + 'px' }], { duration: 280, easing: EASE });
  }
  staggerPanel(next, direction);
  setTimeout(() => { if (token === wizardToken) body.style.overflow = ''; }, 320);
}

// --- Log ---

function logRowHtml(log, index = 0) {
  const isFailure = /gagal|ditolak/.test(log.action);
  const roleTag = log.role !== '-'
    ? `<span class="tag ${escapeHtml(log.role)}">${escapeHtml(ROLE_LABEL[log.role] || log.role)}</span>`
    : '';
  return `<tr style="--i:${Math.min(index, 10)}"><td data-label="Waktu" class="muted small">${formatDate(log.ts)}</td><td data-label="Pengguna"><b>${escapeHtml(log.actor)}</b> ${roleTag}</td>
    <td data-label="Aksi"><span class="tag ${isFailure ? 'err' : ''}">${escapeHtml(log.action)}</span></td><td data-label="Detail">${escapeHtml(log.detail)}</td><td data-label="IP" class="muted small">${escapeHtml(log.ip)}</td></tr>`;
}

const logsView = () => `
  <div class="page-head"><div><h2>Log aktivitas</h2><p class="muted">150 aktivitas terakhir di toko, termasuk login gagal dan akses yang ditolak.</p></div><button class="btn" data-act="reload">Perbarui data</button></div>
  <div class="tbl-wrap${state.fresh ? ' stagger' : ''}"><table><thead><tr><th>Waktu</th><th>Pengguna</th><th>Aksi</th><th>Detail</th><th>IP</th></tr></thead><tbody>
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