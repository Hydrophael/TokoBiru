// TokoBiru - Delegasi event global, validasi form, keyboard, swipe, & scroll
import { SEARCH_DEBOUNCE_MS } from './constants.js';
import { state } from './state.js';
import { $, $$ } from './format.js';
import { closeModal, toast } from '../components/ui.js';
import { profileMenuOpen, setProfileMenu } from '../components/shell.js';
import { closeCart } from '../components/cart.js';
import { panelOpen, setPanel } from '../components/notify.js';
import { handlePhotoInput } from '../components/photo.js';
import { applyProductFilter } from '../components/products-grid.js';

export const MOBILE = matchMedia('(max-width:780px)');
let searchDebounce = 0;

export const actions = {};
export const formHandlers = {};
export const eventHooks = {
  onOtpInput: () => {},
  onOtpFocus: () => {},
  onOtpPointer: () => {},
  updatePasswordChecks: () => {},
  typeLogSearch: () => {},
  setLogAction: () => {},
  setProductCategory: () => {},
  uploadProof: async () => {},
  pickCheckoutAddress: () => {},
  updateCheckout: () => {},
  renderList: () => {},
  keepResultsInView: () => {},
  changeUserSetting: async () => {},
  clearSearch: () => {},
  applyFilters: () => {},
  updateRailEdges: () => {},
  runShopSearch: () => {}
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
  if (panelOpen() && !e.target.closest('.np')) setPanel(false);
  const el = e.target.closest('[data-act]');
  if (!el) return;
  if (el.closest('.pm-pop') && profileMenuOpen()) setProfileMenu(false, { focus: true });
  actions[el.dataset.act]?.(el, e);
}

async function onChange(e) {
  const target = e.target;
  if (target.matches('[data-log-action]')) { eventHooks.setLogAction(target); return; }
  if (target.matches('[data-prod-category]')) { eventHooks.setProductCategory(target); return; }
  if (target.matches('[data-photo-input]')) { await handlePhotoInput(target); return; }
  if (target.matches('[data-proof-input]')) { await eventHooks.uploadProof(target); return; }
  if (target.matches('[data-addr-pick]')) { eventHooks.pickCheckoutAddress(target); return; }
  if (target.matches('[data-co-pick]')) { eventHooks.updateCheckout(target.closest('form')); return; }

  if (target.matches('[data-sort]')) {
    state.sort = target.value;
    eventHooks.renderList();
    eventHooks.keepResultsInView();
    return;
  }

  const el = target.closest('[data-change]');
  if (el) await eventHooks.changeUserSetting(el);
}

function syncDigitsInput(target) {
  const digits = target.closest('[data-digits]');
  if (!digits) return;
  const clean = digits.value.replace(/\D/g, '').slice(0, 6);
  if (clean !== digits.value) digits.value = clean;
  const otp = digits.closest('[data-otp]');
  if (otp) eventHooks.onOtpInput(otp);
}

function syncPasswordChecks(target) {
  const form = target.closest('form[data-pwcheck]');
  if (!form) return;
  eventHooks.updatePasswordChecks(form);
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
  searchDebounce = setTimeout(isShop ? eventHooks.runShopSearch : applyProductFilter, SEARCH_DEBOUNCE_MS);
}

function onInput(e) {
  const target = e.target;
  if (target.matches('[data-log-q]')) { eventHooks.typeLogSearch(target); return; }
  if (target.classList?.contains('invalid')) clearFieldError(target);
  syncDigitsInput(target);
  syncPasswordChecks(target);
  syncSearchInput(target);
}

function handleEscape(modalOpen) {
  if (panelOpen()) { setPanel(false, { focus: true }); return; }
  if (profileMenuOpen()) { setProfileMenu(false, { focus: true }); return; }
  const active = document.activeElement;
  if (modalOpen) closeModal();
  else if (active?.matches?.('[data-input=shop-search]') && active.value) eventHooks.clearSearch();
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
  if (e.key === 'Enter' && e.target.matches?.('#f-min, #f-max')) { e.preventDefault(); eventHooks.applyFilters(); return; }
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
  document.addEventListener('scroll', e => { if (e.target.id === 'rail') eventHooks.updateRailEdges(); }, true);
  // Foto bukti yang sudah dihapus sesuai masa simpan: ganti gambar rusak dengan keterangan
  document.addEventListener('error', e => {
    const img = e.target;
    const link = img instanceof HTMLImageElement ? img.closest('.proof-img') : null;
    if (!link) return;
    const note = document.createElement('p');
    note.className = 'proof-note';
    note.textContent = 'Foto bukti tidak tersedia (mungkin sudah dihapus sesuai masa simpan).';
    link.replaceWith(note);
  }, true);
}

function bindEvents() {
  document.addEventListener('click', onClick);
  document.addEventListener('change', onChange);
  document.addEventListener('input', onInput);
  document.addEventListener('focusin', eventHooks.onOtpFocus);
  document.addEventListener('focusin', e => { if (profileMenuOpen() && !e.target.closest('.pm')) setProfileMenu(false); });
  document.addEventListener('focusin', e => { if (panelOpen() && !e.target.closest('.np')) setPanel(false); });
  document.addEventListener('focusout', eventHooks.onOtpFocus);
  document.addEventListener('pointerup', eventHooks.onOtpPointer);
  document.addEventListener('keydown', onModalKeydown);
  document.addEventListener('keydown', onSearchShortcut);
  document.addEventListener('submit', onSubmit);
  initDrawerSwipe();
  initShopScroll();

  addEventListener('offline', () => toast('Koneksi terputus. Pesanan baru bisa dibuat setelah tersambung.', 'err'));
  addEventListener('online', () => toast('Tersambung kembali', 'ok'));
}

export {
  clearErrors,
  showErrors,
  clearFieldError,
  bindEvents
};
