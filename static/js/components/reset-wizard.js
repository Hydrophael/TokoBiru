// TokoBiru - Komponen modal wizard OTP reset password (4 langkah)
import { CODE_REJECTED } from '../core/constants.js';
import { state } from '../core/state.js';
import { $, $$, createError, escapeHtml, icon } from '../core/format.js';
import { api } from '../api/client.js';
import { EASE, burst, closeModal, openModal, reducedMotion, toast } from './ui.js';
import { clearErrors, showErrors } from '../core/events.js';

let resendTimer = null;
let otpTimer = null;

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

export function createResetFormHandlers(checkNewPassword, updatePasswordChecks) {
  return {

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
  };
}

export const resetActions = {
  'forgot-resend': resendResetCode,
  'wiz-back': wizardBack,
  'wiz-finish': finishReset
};

export {
  forgotModal,
  setResetInfo,
  renderOtp,
  showResetStep,
  onOtpInput,
  onOtpFocus,
  onOtpPointer
};
