// TokoBiru - Kerangka halaman, navigasi utama, indikator tab, & menu profil
import { NAV, ROLE_LABEL } from '../core/constants.js';
import { isCustomer, state } from '../core/state.js';
import { $, $$, avatarTone, brandHtml, escapeHtml, getInitials, icon } from '../core/format.js';
import { bellHtml, renderBell } from './notify.js';
import { drawCart } from './cart.js';

// Diisi app.js: syncInstall ada di pages/profile.js, yang mengimpor shell.js (hindari impor melingkar)
export const shellHooks = { syncInstall: () => {} };

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

export const firstName = name => String(name).trim().split(/\s+/)[0] || String(name);

const AVATAR_URL = /^\/api\/(?:auth\/avatar|users\/[0-9a-fA-F]{24}\/avatar)\?v=\d+$/;
export const avatarPhoto = user => (typeof user?.photo === 'string' && AVATAR_URL.test(user.photo) ? user.photo : '');

export const avatarHtml = (user, size = '') => {
  const photo = avatarPhoto(user);
  return `<span class="av tone${avatarTone(user)}${size ? ' ' + size : ''}${photo ? ' has-photo' : ''}" aria-hidden="true">${photo ? `<img src="${photo}" alt="" decoding="async">` : escapeHtml(getInitials(user.name))}</span>`;
};

export const roleTag = user => `<span class="tag ${escapeHtml(user.role)}">${escapeHtml(ROLE_LABEL[user.role] || user.role)}</span>`;

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
      ${bellHtml()}
      ${customer ? `<button class="btn cart-btn" data-act="open-cart">${icon('cart')}<span class="hide-m">Keranjang</span><span class="cart-sum num" id="cart-sum" hidden></span><span class="count num" id="cart-count">0</span></button>` : ''}
      ${profileMenuHtml()}
    </div>
  </div></header>
  <main class="wrap"><div id="content">${skeletonHtml()}</div></main>
  ${customer ? cartDrawerHtml() : ''}`;

  moveNavIndicator();
  renderBell();
  if (customer) drawCart();
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
  if (open) { shellHooks.syncInstall(); $('[role=menuitem]:not([hidden])', root)?.focus(); }
  else if (focus) button.focus();
}

export {
  profileMenuOpen,
  setProfileMenu
};