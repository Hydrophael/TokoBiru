// TokoBiru - Halaman autentikasi (login & registrasi)
import { state } from '../core/state.js';
import { $, $$, brandHtml, cleanText, escapeHtml, icon, validationError } from '../core/format.js';
import { api } from '../api/client.js';
import { EASE, linkLabels, reducedMotion } from '../components/ui.js';
import {
  createResetFormHandlers,
  forgotModal,
  onOtpFocus,
  onOtpInput,
  onOtpPointer,
  resetActions
} from '../components/reset-wizard.js';
import { onAuthed } from '../core/router.js';

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


export const authActions = {
  'auth-tab': el => renderAuth(el.dataset.tab),
  'toggle-pw': togglePasswordVisibility,
  'forgot-open': () => forgotModal(loginEmailHint()),
  ...resetActions
};

export const authFormHandlers = {
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
    await onAuthed(result);,
  ...createResetFormHandlers(checkNewPassword, updatePasswordChecks)
};

export {
  renderAuth,
  updatePasswordChecks,
  onOtpInput,
  onOtpFocus,
  onOtpPointer,
  passwordProblem,
  mismatchError,
  checkNewPassword
};
