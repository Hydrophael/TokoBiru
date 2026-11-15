import {
  $,
  $$,
  MAX_CART_QTY,
  NAV,
  ORDER_FLOW,
  ADDRESS_LABELS,
  ADDRESS_LIMIT,
  APP_INFO,
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
  orderStatusText,
  stockInfo,
  stockNote,
  storage,
  actionLabel,
  detailLabel,
  LOG_GROUPS,
  logTone,
  PRODUCT_GROUPS,
  avatarTone,
  stockFlag,
  managedProducts,
  productGroupCount,
  PAYMENT_LABEL,
  isEwallet,
  SHIPPING_LABEL,
  countdownText,
  msLeft,
} from './core.js';
import { qrSvg } from './qr.js';
import { EASE, burst, linkLabels, openModal, reducedMotion, toast, tweenNumber } from './ui.js';
import { AVATAR_HINT, PHOTO_HINT, avatarPreviewHtml, photoPreviewHtml } from './photo.js';
import { actionTagHtml, actorHtml, logEmptyHtml, mountLogGrid, refreshLogGrid, visibleLogIds } from './logs-grid.js';
import { mountProductGrid, productActionsHtml, productCountHtml, productNameHtml, productResetHtml } from './products-grid.js';

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

export const qrisPaidHtml = () =>
  `<div class="qris-ok"><svg class="done-ic" viewBox="0 0 52 52" aria-hidden="true"><circle cx="26" cy="26" r="24"/><path d="M15 27l8 8 14-19"/></svg><b>Pembayaran diterima</b><span>Pesanan Anda segera diproses.</span></div>`;

// QR berisi tautan bayar; setelah discan, app.js mengganti kotak ini menjadi centang
export function qrisBoxHtml(order) {
  const payload = order.qr_string || (order.pay_path ? location.origin + order.pay_path : '');
  if (!payload) return '';
  const deadline = order.expires_at
    ? `<span class="qris-limit">Bayar dalam <b class="qris-timer" data-expires="${escapeHtml(order.expires_at)}">${countdownText(msLeft(order.expires_at))}</b></span>` : '';
  return `<section class="qris" data-qris="${escapeHtml(order.id)}" aria-label="Bayar dengan QRIS">
    <div class="qris-head"><b class="qris-logo">QRIS</b><span>TokoBiru</span></div>
    <div class="qris-qr">${qrSvg(payload)}</div>
    <div class="qris-total num">${formatRupiah(order.total)}</div>
    <p class="qris-hint">${order.qr_string ? 'Scan dengan GoPay, OVO, DANA, ShopeePay, atau m-banking yang mendukung QRIS. Status berubah otomatis setelah dibayar.' : 'Scan kode ini dengan kamera HP. Pesanan langsung berstatus dibayar.'}</p>
    ${deadline}
  </section>`;
}

// Tombol menuju e-wallet; kotak ini ikut dipantau polling (data-qris) sehingga berubah sendiri saat lunas
export function ewalletBoxHtml(order) {
  const name = escapeHtml(PAYMENT_LABEL[order.payment_method] || 'E-wallet');
  const deadline = order.expires_at
    ? `<span class="qris-limit">Bayar dalam <b class="qris-timer" data-expires="${escapeHtml(order.expires_at)}">${countdownText(msLeft(order.expires_at))}</b></span>` : '';
  const action = order.ewallet_url
    ? `<a class="btn primary" href="${escapeHtml(order.ewallet_url)}" target="_blank" rel="noopener">Bayar dengan ${name}</a>`
    : `<p class="qris-hint">Buka aplikasi ${name} lalu setujui pembayaran yang masuk.</p>`;
  return `<section class="qris" data-qris="${escapeHtml(order.id)}" aria-label="Bayar dengan ${name}">
    <div class="qris-head"><b class="qris-logo">${name}</b><span>TokoBiru</span></div>
    <div class="qris-total num">${formatRupiah(order.total)}</div>
    ${action}
    <p class="qris-hint">Status berubah otomatis setelah dibayar.</p>
    ${deadline}
  </section>`;
}

const cashNoteHtml = order =>
  `<div class="r-note">Siapkan uang tunai <b>${formatRupiah(order.total)}</b> ${order.shipping_method === 'pickup' ? 'saat mengambil pesanan di toko' : 'saat pesanan diterima'}. Kode pesanan: <b>${escapeHtml(order.code)}</b>.</div>`;

export function showOrderSuccess(order) {
  if (!order) return;
  openModal(`<div class="done"><svg class="done-ic" viewBox="0 0 52 52" aria-hidden="true"><circle cx="26" cy="26" r="24"/><path d="M15 27l8 8 14-19"/></svg>
    <h3>Pesanan berhasil dibuat</h3><p class="sub">${order.payment_method === 'cash' ? 'Pesanan Anda segera diproses.' : 'Satu langkah lagi: bayar agar pesanan segera diproses.'}</p></div>
    ${order.payment_method === 'cash' ? cashNoteHtml(order) : order.payment_method === 'qris' ? qrisBoxHtml(order) : isEwallet(order.payment_method) ? ewalletBoxHtml(order) : paymentBoxHtml(order)}
    <div class="foot"><button class="btn primary" data-act="close-modal">Mengerti</button></div>`);
}

const TICKER_WORDS = ['Beras', 'Minyak goreng', 'Telur', 'Kopi', 'Sabun', 'Susu', 'Teh', 'Roti', 'Madu', 'Tisu'];

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
      <div class="field"><label for="r-email">Email</label><input class="input" id="r-email" name="email"
        type="email" placeholder="nama@gmail.com" required maxlength="120" autocomplete="email" autocapitalize="none" spellcheck="false"></div>
      <div class="pair">
      <div class="field"><label for="r-pw">Password</label><input class="input" id="r-pw" name="password"
        type="password" placeholder="Minimal 8 karakter" required minlength="8" maxlength="128" autocomplete="new-password" aria-describedby="r-pw-hint"></div>
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
        <h1><span class="ln"><span>Belanja mudah</span></span><span class="ln"><span>dari rumah.</span></span></h1>
        <p>Beragam kebutuhan dalam satu tempat. Pilih barang, pesan dengan mudah, dan pantau pesananmu sampai tiba!</p>
        <div class="pricetag" aria-hidden="true">
          <div class="pt-head"><small>Harga rak</small><div class="pt-dots">${dots}</div></div>
          <div class="pt-slides">${slides}</div>
          <div class="pt-bars"></div>
        </div>
      </div>
      <div class="ticker" aria-hidden="true"><div>${ticker}${ticker}</div></div>
    </section>`;
}

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

function focusFirstField() {
  if (!matchMedia('(hover:hover) and (pointer:fine)').matches) return;
  const firstInput = $('.auth-card form input:not([type=checkbox])');
  if (firstInput) firstInput.focus();
}

let swapToken = 0;

async function swapAuthTab(card, tab) {
  const tabs = $('.switch-tabs', card);
  if (tabs.dataset.tab === tab) return;

  const swap = $('.auth-swap', card);
  const token = ++swapToken;
  swap.getAnimations().forEach(animation => animation.cancel());
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

  swap.style.pointerEvents = 'none';
  try {
    await swap.animate(
      [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: `translateX(${-direction * 14}px)` }],
      { duration: 90, easing: 'ease-in', fill: 'forwards' }
    ).finished;
  } catch { return; }
  if (token !== swapToken) return;

  replaceContent();
  const toHeight = swap.offsetHeight;
  if (fromHeight !== toHeight) {
    swap.style.overflow = 'hidden';
    swap.animate([{ height: fromHeight + 'px' }, { height: toHeight + 'px' }], { duration: 260, easing: EASE })
      .onfinish = () => { swap.style.overflow = ''; };
  }

  staggerIn(swap, direction, 0, { duration: 260, step: 18 });
}

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
  staggerIn($('.auth-swap'), 0, 460);
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

function navHtml(items) {
  return items.map(item => {
    const active = state.view === item.id;
    return `<button class="${active ? 'active' : ''}" data-act="nav" data-view="${item.id}" aria-current="${active ? 'page' : 'false'}">${icon(item.icon, 20)}<span>${item.label}</span></button>`;
  }).join('');
}

const cartDrawerHtml = () => `<div class="scrim" id="scrim" data-act="close-cart"></div>
  <aside class="drawer" id="drawer" aria-label="Keranjang">
    <div class="drawer-head"><h3>Keranjang <small class="muted num" id="cart-n"></small></h3><button class="btn sm flat" data-act="close-cart" aria-label="Tutup keranjang">${icon('x', 18)}</button></div>
    <div id="cart-items"></div>
    <div class="drawer-foot"><div class="line" style="border:0;padding:0 0 12px"><span>Total</span><span id="cart-total" class="price num">Rp 0</span></div>
      <button class="btn primary block" data-act="checkout" id="checkout-btn">Lanjut ke pemesanan</button></div>
  </aside>
  <button class="cartbar" id="cartbar" data-act="open-cart" aria-label="Buka keranjang" hidden></button>`;

const skeletonHtml = () => `<div class="shelf">${'<div class="skeleton"></div>'.repeat(8)}</div>`;

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

const firstName = name => String(name).trim().split(/\s+/)[0] || String(name);

const AVATAR_URL = /^\/api\/(?:auth\/avatar|users\/[0-9a-fA-F]{24}\/avatar)\?v=\d+$/;
export const avatarPhoto = user => (typeof user?.photo === 'string' && AVATAR_URL.test(user.photo) ? user.photo : '');

export const avatarHtml = (user, size = '') => {
  const photo = avatarPhoto(user);
  return `<span class="av tone${avatarTone(user)}${size ? ' ' + size : ''}${photo ? ' has-photo' : ''}" aria-hidden="true">${photo ? `<img src="${photo}" alt="" decoding="async">` : escapeHtml(getInitials(user.name))}</span>`;
};

const roleTag = user => `<span class="tag ${escapeHtml(user.role)}">${escapeHtml(ROLE_LABEL[user.role] || user.role)}</span>`;

const menuItem = (act, iconName, title, hint = '', attrs = '') =>
  `<button type="button" class="pm-item" role="menuitem" data-act="${act}"${attrs}>${icon(iconName, 20)}<span class="pm-t"><b>${title}</b>${hint ? `<small>${hint}</small>` : ''}</span></button>`;

const quickTile = (act, iconName, label, attrs = '') =>
  `<button type="button" class="pm-q" role="menuitem" data-act="${act}"${attrs}><span class="pm-qi">${icon(iconName, 20)}</span><span>${label}</span></button>`;

function profileMenuHtml() {
  const user = state.user;
  const customer = isCustomer();
  const name = escapeHtml(user.name);

  const quick = customer ? `<div class="pm-quick" role="none">
      ${quickTile('nav', 'receipt', 'Pesanan', ' data-view="orders"')}
      ${quickTile('address-open', 'pin', 'Alamat')}
      ${quickTile('open-cart', 'cart', 'Keranjang')}
    </div>` : '';

  return `<div class="pm">
      <button type="button" class="pm-btn" data-act="profile-menu" aria-haspopup="menu" aria-expanded="false" aria-controls="pm-pop" aria-label="Menu akun ${name}">
        ${avatarHtml(user)}
        <span class="pm-who"><small>${customer ? 'Halo,' : escapeHtml(ROLE_LABEL[user.role] || user.role)}</small><b>${escapeHtml(firstName(user.name))}</b></span>
        ${icon('chevron', 16)}
      </button>
      <div class="pm-scrim" data-act="profile-close" aria-hidden="true"></div>
      <div class="pm-pop" id="pm-pop" role="menu" aria-label="Akun" hidden>
        <div class="pm-head" role="none">
          ${avatarHtml(user, 'lg')}
          <div class="pm-id"><b>${name}</b><span class="pm-mail">${escapeHtml(user.email)}</span>${customer ? '' : roleTag(user)}</div>
        </div>
        ${quick}
        <div class="pm-list" role="none">
          ${menuItem('profile-open', 'user', 'Profil saya', 'Nama dan data akun')}
          ${menuItem('change-password', 'key', 'Ganti password', 'Jaga akun tetap aman')}
          <div class="pm-sep" role="separator"></div>
          ${menuItem('settings-open', 'gear', 'Pengaturan', 'Tema, ukuran teks, animasi')}
          ${menuItem('about-open', 'info', 'Tentang aplikasi', 'Versi dan penyimpanan data')}
          ${menuItem('install-app', 'download', 'Pasang aplikasi', 'Buka lebih cepat dari layar utama', ' hidden')}
          <div class="pm-sep" role="separator"></div>
          ${menuItem('logout', 'out', 'Keluar', '').replace('class="pm-item"', 'class="pm-item danger"')}
        </div>
      </div>
    </div>`;
}

export function refreshProfileMenu() {
  const current = $('#app .pm');
  if (current) current.outerHTML = profileMenuHtml();
}

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
      <div><dt>Dibangun dengan</dt><dd>${escapeHtml(APP_INFO.stack)}</dd></div>
    </dl>
    <p class="about-note">Data akun, alamat, dan pesanan disimpan di server toko. Keranjang dan pengaturan tampilan hanya tersimpan di perangkat ini.</p>
    <div class="foot"><button type="button" class="btn primary" data-act="close-modal">Tutup</button></div>`);
}

export function renderShell() {
  const user = state.user;
  const navItems = NAV.filter(item => item.roles.includes(user.role));
  const customer = isCustomer();

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
      ${customer ? `<button class="btn cart-btn" data-act="open-cart">${icon('cart')}<span class="hide-m">Keranjang</span><span class="cart-sum num" id="cart-sum" hidden></span><span class="count num" id="cart-count">0</span></button>` : ''}
      ${profileMenuHtml()}
    </div>
  </div></header>
  <main class="wrap"><div id="content">${skeletonHtml()}</div></main>
  ${customer ? cartDrawerHtml() : ''}`;

  moveNavIndicator();
  if (customer) drawCart();
}

const truncationNotice = () => state.productsTotal > state.products.length
  ? `<p class="muted small" role="status">Katalog sangat besar: hanya ${state.products.length} dari ${state.productsTotal} produk yang dimuat.</p>`
  : '';

const hasPriceFilter = () => state.filters.min !== null || state.filters.max !== null;
export const activeFilterCount = () => (hasPriceFilter() ? 1 : 0) + (state.filters.inStock ? 1 : 0);
export const hasAnyFilter = () => Boolean(state.category || state.query.trim() || activeFilterCount());

function matchingProducts(skipCategory = false) {
  const query = state.query.trim().toLowerCase();
  const { inStock, min, max } = state.filters;
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
    if (sort === 'auto' && rank) return rank.get(a.id) - rank.get(b.id);
    return a.name.localeCompare(b.name, 'id');
  };

  return list.sort((a, b) => (a.stock === 0) - (b.stock === 0) || compare(a, b));
}

const countLabel = total =>
  total > SHOP_PAGE_SIZE ? `${Math.min(state.shopLimit, total)} dari ${total} produk` : `${total} produk`;

export function aisleHtml() {
  const aisleNumber = state.categories.indexOf(state.category) + 1;
  return `<span class="aisle-sign"><span class="a-no">${aisleNumber ? 'Lorong ' + aisleNumber : 'Seluruh toko'}</span><b>${state.category ? escapeHtml(state.category) : 'Semua kategori'}</b></span>`;
}

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
  if (select.dataset.q === String(searching)) return;
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
      <div class="tile p${hashString(product.id) % 4}${productImage(product) ? ' has-photo' : ''}" data-act="detail" data-id="${product.id}"><span class="cat tag">${escapeHtml(product.category)}</span>${stockFlag(product)}${tileVisualHtml(product)}</div>
      <div class="lbody"><h3><button type="button" class="plink" data-act="detail" data-id="${product.id}" title="${escapeHtml(product.name)}">${escapeHtml(product.name)}</button></h3>${description ? `<p class="ldesc" data-act="detail" data-id="${product.id}">${escapeHtml(description)}</p>` : ''}${stockNote(product)}</div>
      ${cardFoot(product)}
    </article>`;
}

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
  const photos = list.some(product => productImage(product)) ? ' photos' : '';
  return `<div class="shelf${firstRender ? ' stagger' : ''}${layout}${photos}">${list.slice(0, state.shopLimit).map(productCardHtml).join('')}</div>
    <div class="more" id="more">${moreHtml(list.length)}</div>`;
}

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
  watchMore();
}

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
  <section class="welcome" aria-label="Selamat datang">
    <div class="w-text"><h2>Halo, ${escapeHtml(firstName(state.user.name))}!</h2><p>Mau belanja apa hari ini? Pilih barang, masukkan ke keranjang, lalu buat pesanan.</p></div>
    <div class="w-side">
      <div class="w-facts"><span class="w-fact"><b class="num">${state.products.length}</b>produk</span><span class="w-fact"><b class="num">${state.categories.length}</b>kategori</span></div>
      <button type="button" class="btn yellow" id="w-cart" data-act="open-cart" hidden></button>
    </div>
  </section>
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
  void el.offsetWidth;
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
  const welcomeCart = $('#w-cart');
  if (welcomeCart) {
    welcomeCart.hidden = !lines.length;
    welcomeCart.innerHTML = `${icon('cart', 17)} Lihat keranjang · ${formatRupiah(total)}`;
  }
  const drawerCount = $('#cart-n');
  if (drawerCount) drawerCount.textContent = lines.length ? `${count} barang` : '';
  const sumEl = $('#cart-sum');
  if (sumEl) { sumEl.hidden = !lines.length; sumEl.textContent = formatRupiah(total); }

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

function timelineHtml(status, order = {}) {
  if (status === 'cancelled') return '';
  const flow = order.cod ? ORDER_FLOW.filter(key => key !== 'paid') : ORDER_FLOW;
  const currentIndex = status === 'completed' ? flow.length : flow.indexOf(status);

  const steps = flow.map((key, n) => {
    const cls = n < currentIndex ? 'done' : n === currentIndex ? 'now' : '';
    const ariaCurrent = n === currentIndex ? ' aria-current="step"' : '';
    const marker = n < currentIndex ? icon('check', 12) : n + 1;
    return `<li class="${cls}"${ariaCurrent}><i>${marker}</i><span>${orderStatusText(key, order)}</span></li>`;
  }).join('');

  return `<ol class="steps" aria-label="Progres pesanan">${steps}</ol>`;
}

const statusButton = (order, status, label, cls = '') =>
  `<button class="btn sm ${cls}" data-act="order-status" data-id="${order.id}" data-status="${status}">${label}</button>`;

function staffOrderActions(order) {
  switch (order.status) {
    case 'pending': if (order.cod) return statusButton(order, 'shipped', 'Tandai dikirim', 'primary') + statusButton(order, 'cancelled', 'Batalkan', 'danger');
      return statusButton(order, 'paid', order.payment_method === 'cash' ? 'Terima pembayaran tunai' : 'Konfirmasi pembayaran', 'primary') + statusButton(order, 'cancelled', 'Batalkan', 'danger');
    case 'paid':    return statusButton(order, 'shipped', 'Tandai dikirim', 'primary') + statusButton(order, 'cancelled', 'Batalkan', 'danger');
    case 'shipped': return order.cod
      ? statusButton(order, 'completed', 'Selesai, uang diterima', 'primary') + statusButton(order, 'cancelled', 'Batalkan', 'danger')
      : statusButton(order, 'completed', 'Tandai selesai', 'primary');
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

const shippingLineHtml = order => order.shipping_method
  ? `<li><span>${order.shipping_method === 'pickup' ? 'Ambil di toko' : 'Ongkos kirim'}</span><span class="num">${order.shipping_fee ? formatRupiah(order.shipping_fee) : 'Gratis'}</span></li>`
  : '';

const infoRow = (label, value) => (value ? `<div><dt>${label}</dt><dd>${value}</dd></div>` : '');

const CLOSED_ORDER = ['completed', 'cancelled'];

function orderInfoHtml(order) {
  return `<dl class="r-info">${infoRow('Penerima', escapeHtml(order.recipient))}${infoRow('Pengiriman', escapeHtml(SHIPPING_LABEL[order.shipping_method] || ''))}${infoRow('Pembayaran', escapeHtml(PAYMENT_LABEL[order.payment_method] || ''))}${infoRow('Kirim ke', escapeHtml(order.address))}${
    infoRow('HP/WA', order.phone ? `<span class="num">${escapeHtml(order.phone)}</span>` : '')}${
    infoRow('Catatan', escapeHtml(order.note))}</dl>`;
}

const AUTO_CANCEL_TEXT = {
  expired: 'Dibatalkan otomatis karena melewati batas waktu bayar.',
  payment_failed: 'Dibatalkan otomatis karena pembayaran e-wallet gagal atau ditolak. Silakan buat pesanan baru.'
};
// Masalah uang yang harus ditangani admin: pembayaran masuk setelah pesanan batal, atau nominal tidak cocok
const paymentFlagText = order => order.needs_refund
  ? 'Uang pelanggan sudah masuk tetapi pesanan dibatalkan. Kembalikan dana: lewat Dashboard Xendit untuk QRIS/e-wallet, atau transfer balik untuk transfer bank.'
  : order.payment_issue ? 'Nominal pembayaran tidak sama dengan total pesanan. Periksa di Dashboard Xendit.' : '';
const paymentFlagBrief = order => paymentFlagText(order)
  ? `<p class="r-hint"><b>⚠ ${order.needs_refund ? 'Perlu refund' : 'Nominal tidak cocok'}</b></p>` : '';
const paymentFlagBox = order => paymentFlagText(order)
  ? `<div class="r-note"><b>⚠ ${order.needs_refund ? 'Perlu refund' : 'Nominal tidak cocok'}</b><br>${paymentFlagText(order)}<br>
      <button type="button" class="btn sm" data-act="issue-done" data-id="${order.id}">Sudah ditangani</button></div>` : '';
const orderAutoCancelHtml = order => AUTO_CANCEL_TEXT[order.cancel_reason]
  ? `<p class="r-auto">${AUTO_CANCEL_TEXT[order.cancel_reason]}</p>` : '';

function orderPayBoxHtml(order) {
  if (order.payment_method === 'cash') return cashNoteHtml(order);
  if (isEwallet(order.payment_method)) return ewalletBoxHtml(order);
  return order.payment_method === 'qris' ? qrisBoxHtml(order) : orderPaymentHtml(order);
}

function orderSummaryHtml(order) {
  const [first, ...rest] = order.items;
  return `${first ? escapeHtml(first.name) : 'Pesanan'}${rest.length ? ` <em>+${rest.length} lainnya</em>` : ''}`;
}

// Kartu ringkas: rincian lengkap dibuka lewat orderDetailModal supaya daftar tidak memanjang
function orderCardHtml(order, staff, index = 0) {
  const statusColor = STATUS[order.status][1];
  const statusLabel = orderStatusText(order.status, order);
  const justUpdated = order.id === state.justUpdatedOrderId ? ' just' : '';
  const owner = staff ? ', atas nama <b>' + escapeHtml(order.username) + '</b>' : '';
  const hint = !staff && order.status === 'pending' && order.payment_method !== 'cash'
    ? ((order.payment_method === 'qris' || isEwallet(order.payment_method)) && order.expires_at
      ? `<p class="r-hint">Bayar dalam <b class="qris-timer" data-expires="${escapeHtml(order.expires_at)}">${countdownText(msLeft(order.expires_at))}</b></p>`
      : '<p class="r-hint">Belum dibayar. Buka untuk bayar.</p>') : '';
  const acts = staff ? orderActions(order) : '';

  return `
    <article class="receipt st-${order.status}" style="--i:${Math.min(index, 8)}" data-act="order-open" data-id="${order.id}" role="button" tabindex="0" aria-label="Buka pesanan ${escapeHtml(order.code)}">
      <div class="r-top"><span class="r-code num">${escapeHtml(order.code)}</span>
        <span class="muted small r-date">${formatDate(order.created_at)}${owner}</span>
        <span class="stamp ${statusColor}${justUpdated}">${statusLabel}</span></div>
      <p class="r-sum">${orderSummaryHtml(order)}</p>
      ${hint}${staff ? paymentFlagBrief(order) : ''}
      <div class="r-foot"><strong class="num">${formatRupiah(order.total)}</strong><span class="r-more">Lihat detail</span></div>
      ${acts ? `<div class="acts">${acts}</div>` : ''}
    </article>`;
}

export function orderDetailModal(order) {
  const staff = isStaff();
  const statusColor = STATUS[order.status][1];
  const statusLabel = orderStatusText(order.status, order);
  const owner = staff ? ' · atas nama <b>' + escapeHtml(order.username) + '</b>' : '';
  const payment = !staff && order.status === 'pending' ? orderPayBoxHtml(order) : '';
  const remove = !staff && CLOSED_ORDER.includes(order.status)
    ? `<button type="button" class="btn sm danger push" data-act="order-del" data-id="${order.id}">Hapus pesanan</button>` : '';

  openModal(`<div data-order="${order.id}">
    <h3>${escapeHtml(order.code)}</h3>
    <div class="od-head"><span class="muted small">${formatDate(order.created_at)}${owner}</span><span class="stamp ${statusColor}">${statusLabel}</span></div>
    ${timelineHtml(order.status, order)}
    <ul class="r-lines">${order.items.map(orderLineHtml).join('')}${shippingLineHtml(order)}</ul>
    <div class="r-total"><span>Total</span><strong class="num">${formatRupiah(order.total)}</strong></div>
    ${orderInfoHtml(order)}${orderAutoCancelHtml(order)}${staff ? paymentFlagBox(order) : ''}${payment}
    <div class="foot wrap"><button type="button" class="btn sm" data-act="close-modal">Tutup</button>${orderActions(order)}${remove}</div>
  </div>`);
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
  <div class="page-head"><div><h2>${customer ? 'Pesanan saya' : 'Semua pesanan'}</h2><p class="muted">${customer ? 'Lihat status dan riwayat pesanan Anda.' : 'Konfirmasi pembayaran, kirim, dan selesaikan pesanan pelanggan.'}</p></div>${customer && state.orders.some(o => CLOSED_ORDER.includes(o.status)) ? '<button type="button" class="btn sm" data-act="orders-clear">Bersihkan riwayat</button>' : ''}</div>
  <div class="rail" id="orail">${orderRailHtml()}</div>
  <div id="olist">${orderCards(state.fresh)}</div>`;
}

function factHtml({ value, label, note = '', tone = '', wide = false, go = null }) {
  const cls = `fact${tone ? ' ' + tone : ''}${wide ? ' wide' : ''}`;
  const inner = `<b class="num">${value}</b><span>${label}${note ? `<small>${note}</small>` : ''}</span>`;
  if (!go) return `<div class="${cls}">${inner}</div>`;
  const attrs = Object.entries(go).map(([key, val]) => ` data-${key}="${escapeHtml(val)}"`).join('');
  return `<button type="button" class="${cls}" data-act="dash-go"${attrs}>${inner}<i class="go-arrow" aria-hidden="true">${icon('right', 16)}</i></button>`;
}

function dashboardFactsHtml(stats) {
  const today = stats.today || { orders: 0, revenue: 0 };
  const pending = stats.orders.pending;
  const stockTotal = stats.low_stock_total ?? stats.low_stock.length;
  const outCount = stats.out_of_stock_total ?? stats.low_stock.filter(product => product.stock === 0).length;
  const lowCount = stockTotal - outCount;
  const totals = state.user.role === 'master' ? stats.users : null;
  const userTotal = totals ? totals.user + totals.admin + totals.master : 0;

  return `<div class="facts">
      ${factHtml({ value: today.orders, label: 'Pesanan hari ini', tone: today.orders ? '' : 'zero' })}
      ${factHtml({ value: formatRupiah(today.revenue), label: 'Pendapatan hari ini', tone: today.revenue ? '' : 'zero' })}
      ${factHtml({ value: pending, label: 'Menunggu pembayaran', tone: pending ? 'attn' : 'zero',
        go: pending ? { view: 'orders', status: 'pending' } : null })}
      ${factHtml({ value: stockTotal, label: 'Stok menipis', note: outCount ? `${outCount} sudah habis` : '', tone: stockTotal ? 'attn' : 'zero',
        go: stockTotal ? { view: 'products', group: lowCount ? 'low' : 'out' } : null })}
      ${factHtml({ value: stats.products, label: 'Produk di katalog', wide: !totals, go: { view: 'products' } })}
      ${totals ? factHtml({ value: userTotal, label: 'Pengguna', note: `${totals.user} pelanggan, ${totals.admin} admin, ${totals.master} master`, go: { view: 'users' } }) : ''}
    </div>`;
}

function revenueHeroHtml(stats) {
  const paidOrders = stats.paid_orders ?? (stats.orders.paid + stats.orders.shipped + stats.orders.completed);
  const average = paidOrders ? Math.round(stats.revenue / paidOrders) : 0;
  return `<div class="revenue">
      <div><span>Total pendapatan dari pesanan yang sudah dibayar</span><strong class="num">${formatRupiah(stats.revenue)}</strong></div>
      <div class="hstats">
        <div class="hstat"><b class="num">${paidOrders}</b><span>Pesanan dibayar</span></div>
        <div class="hstat"><b class="num">${formatRupiah(average)}</b><span>Rata-rata per pesanan</span></div>
        <div class="hstat"><b class="num">${stats.orders.total}</b><span>Semua pesanan</span></div>
      </div>
    </div>`;
}

function orderStatusBarsHtml(stats) {
  const keys = Object.keys(STATUS);
  const max = Math.max(1, ...keys.map(key => stats.orders[key]));
  return keys.map(key => {
    const count = stats.orders[key];
    const width = Math.round(count / max * 100);
    const inner = `<span>${STATUS[key][0]}</span><span class="track"><span class="fill" style="width:${width}%"></span></span><span class="right num">${count}</span>`;
    return count
      ? `<button type="button" class="bar s-${key}" data-act="dash-go" data-view="orders" data-status="${key}" aria-label="${STATUS[key][0]}: ${count} pesanan, buka daftar">${inner}</button>`
      : `<div class="bar s-${key} zero">${inner}</div>`;
  }).join('');
}

const recentOrdersHtml = stats => stats.recent.length
  ? stats.recent.map(order => `<div class="line"><span class="l-main"><b class="num">${escapeHtml(order.code)}</b><span class="muted small">${escapeHtml(order.username)}${order.created_at ? ', ' + escapeHtml(formatDate(order.created_at)) : ''}</span></span><span class="l-end">${statusTag(order.status, order)} <b class="num">${formatRupiah(order.total)}</b></span></div>`).join('')
  : '<p class="muted">Belum ada pesanan masuk.</p>';

const lowStockHtml = stats => stats.low_stock.length
  ? `<div class="restock">${stats.low_stock.map(product => `<div class="line"><span class="cell">${miniHtml(product)}<span><b>${escapeHtml(product.name)}</b><br><span class="muted small">${escapeHtml(product.category)}</span></span></span>${stockInfo(product)}</div>`).join('')}</div>`
  : `<p class="all-good">${icon('check', 20)} Semua stok masih aman.</p>`;

function dashboardView() {
  const stats = state.stats;
  const restockTotal = stats.low_stock_total ?? stats.low_stock.length;
  const restockBadge = restockTotal ? `<span class="tag warn">${restockTotal} produk</span>` : '';
  const updated = new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
  return `
  <div class="page-head"><div><h2>Ringkasan</h2><p class="muted">Penjualan, pesanan, dan stok. Angka &ldquo;hari ini&rdquo; dihitung sejak pukul 00.00 WIB.</p></div>
    <div class="head-act"><span class="updated">Diperbarui ${updated}</span><button class="btn" data-act="reload">Perbarui data</button></div></div>
  <div class="lead">
    ${revenueHeroHtml(stats)}
    ${dashboardFactsHtml(stats)}
  </div>
  <div class="two">
    <div class="panel"><div class="panel-head"><h3>Pesanan terbaru</h3>
        <button type="button" class="btn sm flat" data-act="nav" data-view="orders">Lihat semua ${icon('right', 14)}</button></div>
      ${recentOrdersHtml(stats)}
    </div>
    <div class="panel col"><div class="panel-head"><h3>Pesanan per status</h3></div>
      <div class="bars">${orderStatusBarsHtml(stats)}</div>
    </div>
  </div>
  <div class="panel"><div class="panel-head"><h3>Perlu restok</h3>${restockBadge}
      <button type="button" class="btn sm" data-act="nav" data-view="products">Atur stok produk</button></div>
    ${lowStockHtml(stats)}
    ${restockTotal > stats.low_stock.length ? `<p class="muted small" style="margin-top:12px">Menampilkan ${stats.low_stock.length} produk dengan stok paling sedikit dari ${restockTotal}.</p>` : ''}
  </div>`;
}

function productRowHtml(product, index = 0) {
  return `<tr style="--i:${Math.min(index, 10)}"${product.stock === 0 ? ' class="prod-out"' : ''}>
    <td data-label="Produk">${productNameHtml(product)}</td>
    <td data-label="Kategori"><span class="tag">${escapeHtml(product.category)}</span></td>
    <td data-label="Harga" class="num-cell"><b class="num">${formatRupiah(product.price)}</b></td>
    <td data-label="Stok">${stockInfo(product)}</td>
    <td data-label="Aksi">${productActionsHtml(product)}</td></tr>`;
}

const productAddButton = () => `<button type="button" class="btn primary" data-act="product-new">${icon('plus', 15)} Tambah produk</button>`;

export function productRows() {
  const list = managedProducts();

  if (!list.length) {
    const hasProducts = state.products.length > 0;
    return `<tr><td colspan="5">${hasProducts
      ? emptyState('Tidak ada produk yang cocok', 'Ubah kata kunci atau lepas filter yang aktif.', productResetHtml())
      : emptyState('Belum ada produk', 'Tambahkan produk pertama agar pelanggan bisa mulai belanja.', productAddButton())}</td></tr>`;
  }
  return list.map(productRowHtml).join('');
}

function productToolsHtml() {
  const { group, category } = state.productFilter;
  const categories = [...new Set(state.products.map(product => product.category))].sort((a, b) => a.localeCompare(b, 'id'));
  const chips = PRODUCT_GROUPS.map(item =>
    `<button type="button" class="log-chip${item.id === 'out' ? ' is-alert' : ''}" data-act="prod-group" data-group="${item.id}" aria-pressed="${item.id === group}">${item.label}${item.id ? `<span class="log-chip-n">${productGroupCount(item.id)}</span>` : ''}</button>`
  ).join('');
  return `
  <div class="log-tools prod-tools">
    <div class="log-find">
      <div class="log-search">
        ${icon('search', 18)}
        <input type="search" data-input="prod-search" value="${escapeHtml(state.query)}" placeholder="Cari nama produk atau kategori" aria-label="Cari produk" maxlength="50" autocomplete="off" spellcheck="false">
        <button type="button" class="log-q-clear" data-act="prod-q-clear" aria-label="Hapus kata kunci"${state.query ? '' : ' hidden'}>${icon('x', 16)}</button>
      </div>
      <select class="select log-action" data-prod-category aria-label="Saring menurut kategori">
        <option value="">Semua kategori</option>
        ${categories.map(name => `<option value="${escapeHtml(name)}"${name === category ? ' selected' : ''}>${escapeHtml(name)}</option>`).join('')}
      </select>
    </div>
    <div class="log-groups" role="group" aria-label="Status stok">${chips}</div>
    <div class="log-status" id="prod-status" role="status" aria-live="polite">${productCountHtml(managedProducts().length)}</div>
  </div>`;
}

const productsView = () => {
  const { category } = state.productFilter;
  if (category && !state.products.some(product => product.category === category)) state.productFilter.category = '';
  const hasProducts = state.products.length > 0;
  return `
  <div class="page-head"><div><h2>Produk</h2><p class="muted">Tambah produk, ubah harga dan stok, atau hapus dari katalog.</p></div>
    ${productAddButton()}</div>
  ${truncationNotice()}
  ${hasProducts ? productToolsHtml() : ''}
  <div class="tbl-wrap prod-table${state.fresh ? ' stagger' : ''}" id="product-host">${hasProducts
    ? `<table><thead><tr><th>Produk</th><th>Kategori</th><th class="right">Harga</th><th>Stok</th><th class="right">Aksi</th></tr></thead><tbody id="prows">${productRows()}</tbody></table>`
    : emptyState('Belum ada produk', 'Tambahkan produk pertama agar pelanggan bisa mulai belanja.', productAddButton())}</div>`;
};

export const afterProductsRender = () => mountProductGrid(productRows);

export function productModal(product) {
  const isEdit = Boolean(product);
  const values = product || { name: '', category: '', price: '', stock: '', description: '' };
  const image = productImage(product);
  const categoryOptions = state.categories.map(c => `<option value="${escapeHtml(c)}">`).join('');

  openModal(`
    <h3>${isEdit ? 'Ubah produk' : 'Tambah produk'}</h3>${isEdit ? '<p class="sub">Perubahan langsung tampil di katalog pelanggan.</p>' : ''}
    <form data-form="product" data-id="${isEdit ? product.id : ''}" autocomplete="off" novalidate>
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
      <div class="field"><label>Nama produk</label><input class="input" name="name" required maxlength="80" autocomplete="off" value="${escapeHtml(values.name)}"></div>
      <div class="row2">
        <div class="field"><label>Kategori</label><input class="input" name="category" list="cats" required maxlength="30" placeholder="Contoh: Sembako" value="${escapeHtml(values.category)}"><datalist id="cats">${categoryOptions}</datalist></div>
        <div class="field"><label>Harga (Rp)</label><input class="input" name="price" type="number" placeholder="Contoh: 38000" min="100" max="100000000" step="1" required value="${escapeHtml(values.price)}"></div>
      </div>
      <div class="field"><label>Stok</label><input class="input" name="stock" type="number" placeholder="Contoh: 20" min="0" max="100000" step="1" required value="${escapeHtml(values.stock)}"></div>
      <div class="field"><label>Deskripsi (opsional)</label><textarea class="input" name="description" maxlength="300" placeholder="Keterangan singkat produk">${escapeHtml(values.description)}</textarea></div>
      <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Simpan produk</button></div>
    </form>`);
}

const roleSelectHtml = user =>
  `<select class="select sm" data-change="user-role" data-id="${user.id}" aria-label="Role ${escapeHtml(user.username)}"><option value="user" ${user.role === 'user' ? 'selected' : ''}>Pelanggan</option><option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Admin</option></select>`;

const activeSwitchHtml = user =>
  `<label class="sw"><input type="checkbox" data-change="user-active" data-id="${user.id}" ${user.active ? 'checked' : ''} aria-label="Aktif ${escapeHtml(user.username)}"><span></span></label>`;

const userMiniHtml = user => {
  const photo = avatarPhoto(user);
  return `<span class="mini${photo ? ' has-photo' : ''}">${photo ? `<img src="${photo}" alt="" decoding="async">` : escapeHtml(getInitials(user.name))}</span>`;
};

function userRowHtml(user, index = 0) {
  const locked = user.role === 'master' || user.id === state.user.id;
  return `<tr style="--i:${Math.min(index, 10)}"><td data-label="Pengguna"><div class="cell">${userMiniHtml(user)}<div><b>${escapeHtml(user.name)}</b><div class="muted small">@${escapeHtml(user.username)}</div></div></div></td>
    <td data-label="Email">${escapeHtml(user.email)}</td>
    <td data-label="Role">${locked ? `<span class="tag ${user.role}">${ROLE_LABEL[user.role]}</span>` : roleSelectHtml(user)}</td>
    <td data-label="Aktif">${locked ? '<span class="tag ok">Aktif</span>' : activeSwitchHtml(user)}</td>
    <td data-label="Terdaftar" class="muted small">${formatDate(user.created_at)}</td>
    <td data-label="Aksi"><div class="acts end">${locked ? '<span class="muted small">Dilindungi</span>' : `<button class="btn sm danger" data-act="user-del" data-id="${user.id}" aria-label="Hapus ${escapeHtml(user.username)}">${icon('trash', 13)}</button>`}</div></td></tr>`;
}

const usersView = () => `
  <div class="page-head"><div><h2>Pengguna</h2></div>
    <button class="btn primary" data-act="user-new">${icon('plus', 15)} Tambah pengguna</button></div>
  <div class="tbl-wrap${state.fresh ? ' stagger' : ''}"><table><thead><tr><th>Pengguna</th><th>Email</th><th>Role</th><th>Aktif</th><th>Terdaftar</th><th class="right">Aksi</th></tr></thead><tbody>
  ${state.users.map(userRowHtml).join('')}</tbody></table></div>`;

export function userModal() {
  openModal(`<h3>Tambah pengguna</h3><p class="sub">Buat akun admin untuk staf, atau akun pelanggan.</p>
    <form data-form="user-create" novalidate><div class="form-alert" role="alert"></div>
      <div class="field"><label>Nama lengkap</label><input class="input" name="name" required maxlength="50" placeholder="Nama lengkap"></div>
      <div class="row2"><div class="field"><label>Username</label><input class="input" name="username" required maxlength="20" placeholder="Username unik"></div>
      <div class="field"><label>Role</label><select class="select" name="role"><option value="admin">Admin</option><option value="user">Pelanggan</option></select></div></div>
      <div class="field"><label>Email</label><input class="input" name="email" type="email" required maxlength="120" placeholder="nama@gmail.com"></div>
      <div class="field"><label>Password</label><input class="input" name="password" type="password" required minlength="8" maxlength="128" autocomplete="new-password" placeholder="Minimal 8 karakter"></div>
      <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Buat akun</button></div></form>`);
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

const RESET_STEP_NAMES = ['Email', 'Kode', 'Password'];
const RESET_ANNOUNCE = {
  1: 'Langkah 1 dari 3: isi email',
  2: 'Langkah 2 dari 3: masukkan kode',
  3: 'Langkah 3 dari 3: buat password baru',
  4: 'Password berhasil diganti'
};
const OTP_LENGTH = 6;

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
          <div class="field"><label>Email</label><input class="input" name="email" type="email" required maxlength="120" autocomplete="email" autocapitalize="none" spellcheck="false" placeholder="nama@gmail.com" value="${escapeHtml(email)}"></div>
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

export function setResetInfo({ email, expires } = {}) {
  if (email !== undefined) $$('#modal-root [data-email]').forEach(el => { el.textContent = email; });
  if (expires !== undefined) $$('#modal-root [data-expires]').forEach(el => { el.textContent = expires; });
}

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
      void cell.offsetWidth;
      cell.classList.add('pop');
    }
  });

  wrap.dataset.len = value.length;
  if (value.length < cells.length) wrap.classList.remove('wave');
}

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

function staggerPanel(panel, direction) {
  if (reducedMotion.matches) return;
  const parts = $$(':scope > h3, :scope > p, :scope > form > *, :scope > .done > *', panel)
    .filter(el => el.getClientRects().length);
  parts.forEach((el, index) => el.animate(
    [{ opacity: 0, transform: `translate(${direction * 14}px, 8px)` }, { opacity: 1, transform: 'none' }],
    { duration: 300, delay: index * 28, easing: EASE, fill: 'backwards' }
  ));
}

function celebrate(panel) {
  setTimeout(() => {
    const mark = $('.done-ic', panel);
    if (mark && mark.isConnected) burst(mark);
  }, 420);
}

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

  if (current === next) {
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
  body.style.overflow = 'clip';
  current.style.pointerEvents = 'none';
  try {
    await current.animate(
      [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: `translateX(${-direction * 18}px)` }],
      { duration: 110, easing: 'ease-in', fill: 'forwards' }
    ).finished;
  } catch { return; }
  if (token !== wizardToken || !wz.isConnected) return;

  reveal();
  const toHeight = body.offsetHeight;
  if (fromHeight !== toHeight) {
    body.animate([{ height: fromHeight + 'px' }, { height: toHeight + 'px' }], { duration: 280, easing: EASE });
  }
  staggerPanel(next, direction);
  setTimeout(() => { if (token === wizardToken) body.style.overflow = ''; }, 320);
}

function logRowHtml(log, index = 0) {
  const picked = state.selectedLogs.has(log.id);
  const alert = logTone(log.action) === 'err';
  return `<tr data-log="${log.id}" class="${picked ? 'picked' : ''}${alert ? ' log-alert' : ''}" style="--i:${Math.min(index, 10)}">
    <td data-label="Pilih" class="pick"><input type="checkbox" class="tick" data-act="log-pick" data-id="${log.id}"${picked ? ' checked' : ''} aria-label="Pilih log ${escapeHtml(actionLabel(log.action))}"></td>
    <td data-label="Waktu" class="muted small log-time">${formatDate(log.ts)}</td><td data-label="Pengguna">${actorHtml(log)}</td>
    <td data-label="Aksi">${actionTagHtml(log)}</td><td data-label="Detail">${escapeHtml(detailLabel(log))}</td><td data-label="IP" class="muted small log-ip">${escapeHtml(log.ip)}</td>
    <td data-label="Hapus" class="row-del"><button type="button" class="btn sm flat log-del" data-act="log-del" data-id="${log.id}" aria-label="Hapus log ${escapeHtml(actionLabel(log.action))}" title="Hapus log ini">${icon('trash', 16)}</button></td></tr>`;
}

function logActionsHtml() {
  const count = state.selectedLogs.size;
  if (!count) {
    const shown = visibleLogIds().length;
    const total = state.logs.length;
    return `<span class="log-count">${shown === total ? `${total} log` : `Menampilkan <b>${shown}</b> dari ${total} log`}</span>`;
  }
  return `<span class="log-count"><b>${count}</b> dipilih</span>
    <button type="button" class="btn sm" data-act="log-clear">Batal pilih</button>
    <button type="button" class="btn sm solid-danger" data-act="log-del-selected">${icon('trash', 15)} Hapus ${count} log</button>`;
}

export function syncLogSelection() {
  const boxes = $$('[data-act="log-pick-all"]');
  const actions = $('#log-actions');
  if (!boxes.length || !actions) return;

  const visible = visibleLogIds();
  const pickedVisible = visible.filter(id => state.selectedLogs.has(id)).length;
  for (const box of boxes) {
    box.checked = pickedVisible > 0 && pickedVisible === visible.length;
    box.indeterminate = pickedVisible > 0 && pickedVisible < visible.length;
    box.disabled = !visible.length;
  }
  actions.innerHTML = logActionsHtml();
  actions.classList.toggle('is-bulk', state.selectedLogs.size > 0);
  $$('#content tr[data-log]').forEach(row => {
    const picked = state.selectedLogs.has(row.dataset.log);
    row.classList.toggle('picked', picked);
    $('.tick', row).checked = picked;
  });
  refreshLogGrid();
}

export const afterLogsRender = () => mountLogGrid(syncLogSelection);

function logToolsHtml() {
  const { q, group, action } = state.logFilter;
  const actions = [...new Set(state.logs.map(log => log.action))]
    .sort((a, b) => actionLabel(a).localeCompare(actionLabel(b), 'id'));
  const countIn = test => state.logs.filter(log => test(log.action)).length;
  return `
  <div class="log-tools">
    <div class="log-find">
      <div class="log-search">
        ${icon('search', 18)}
        <input type="search" data-log-q value="${escapeHtml(q)}" placeholder="Cari pengguna, aksi, detail, atau IP" aria-label="Cari log" autocomplete="off" spellcheck="false">
        <button type="button" class="log-q-clear" data-act="log-q-clear" aria-label="Hapus kata kunci"${q ? '' : ' hidden'}>${icon('x', 16)}</button>
      </div>
      <select class="select log-action" data-log-action aria-label="Saring menurut aksi">
        <option value="">Semua aksi</option>
        ${actions.map(code => `<option value="${escapeHtml(code)}"${code === action ? ' selected' : ''}>${escapeHtml(actionLabel(code))}</option>`).join('')}
      </select>
    </div>
    <div class="log-groups" role="group" aria-label="Kelompok log">
      ${LOG_GROUPS.map(item => `<button type="button" class="log-chip${item.id === 'alert' ? ' is-alert' : ''}" data-act="log-group" data-group="${item.id}" aria-pressed="${item.id === group}">${item.label}${item.id === 'alert' ? `<span class="log-chip-n">${countIn(item.test)}</span>` : ''}</button>`).join('')}
    </div>
    <label class="pickall log-all-m"><input type="checkbox" class="tick" data-act="log-pick-all" aria-label="Pilih semua log yang tampil"> Pilih semua yang tampil</label>
    <div class="log-status" id="log-actions" role="status" aria-live="polite">${logActionsHtml()}</div>
  </div>`;
}

const logsView = () => {
  if (state.logFilter.action && !state.logs.some(log => log.action === state.logFilter.action)) state.logFilter.action = '';
  return `
  <div class="page-head"><div><h2>Log aktivitas</h2><p class="muted">${state.logs.length} aktivitas terakhir di toko.</p></div><button class="btn" data-act="reload">Perbarui data</button></div>
  ${state.logs.length ? logToolsHtml() : ''}
  <div class="tbl-wrap log-table${state.fresh ? ' stagger' : ''}" id="log-host"><table><thead><tr><th class="pick"><input type="checkbox" class="tick" data-act="log-pick-all" aria-label="Pilih semua log yang tampil"></th><th>Waktu</th><th>Pengguna</th><th>Aksi</th><th>Detail</th><th>IP</th><th><span class="sr-only">Hapus</span></th></tr></thead><tbody>
  ${state.logs.map(logRowHtml).join('') || `<tr><td colspan="7">${emptyState('Belum ada aktivitas')}</td></tr>`}
  </tbody></table><div class="log-empty" id="log-none" hidden>${logEmptyHtml()}</div></div>`;
};

export const views = {
  shop: shopView,
  dashboard: dashboardView,
  orders: ordersView,
  products: productsView,
  users: usersView,
  logs: logsView
};