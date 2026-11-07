// TokoBiru - komponen UI umum: toast, modal, dan animasi

import { $, $$, MAX_TOASTS, escapeHtml, formatRupiah } from './core.js';

export const EASE = 'cubic-bezier(.2,.8,.2,1)';

// === Komponen UI ===

// --- Toast ---
export function toast(message, type = '', action) {
  const box = $('#toasts');
  const el = document.createElement('div');
  el.className = 'toast ' + type;

  const text = document.createElement('span');
  text.textContent = message;
  el.appendChild(text);

  const dismiss = () => {
    el.classList.add('out');
    setTimeout(() => el.remove(), 220);
  };

  if (action) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'toast-act';
    button.textContent = action.label;
    button.onclick = () => { action.fn(); dismiss(); };
    el.appendChild(button);
  }

  while (box.children.length >= MAX_TOASTS) box.firstChild.remove();
  box.appendChild(el);
  setTimeout(dismiss, type === 'err' || action ? 6000 : 4000);
}

// --- Modal ---
let modalResolve = null;      // resolver milik confirmDialog yang sedang terbuka
let modalReturnFocus = null;  // elemen yang fokusnya dikembalikan saat modal ditutup

// hubungkan <label> dengan input di .field (aksesibilitas)
export function linkLabels(root) {
  let counter = 0;
  $$('.field', root).forEach(field => {
    const label = $('label', field);
    const input = $('input:not([type=radio]):not([type=checkbox]), select, textarea', field);
    if (!label || !input || label.htmlFor) return;
    if (!input.id) input.id = 'fld-' + Math.random().toString(36).slice(2, 8) + (counter++);
    label.htmlFor = input.id;
  });
}

export function openModal(html) {
  const root = $('#modal-root');
  if (!root.querySelector('.overlay:not(.leaving)')) modalReturnFocus = document.activeElement;
  document.documentElement.classList.add('lock');
  root.innerHTML = `<div class="overlay" data-act="overlay"><div class="modal" role="dialog" aria-modal="true">${html}</div></div>`;

  const modal = $('#modal-root .modal');
  const heading = $('h3', modal);
  if (heading) {
    heading.id = 'modal-title';
    heading.tabIndex = -1;
    modal.setAttribute('aria-labelledby', 'modal-title');
  }
  linkLabels(modal);

  const firstFocusable =
    $('#modal-root input:not([type=radio]), #modal-root textarea, #modal-root select') ||
    $('#modal-root .btn.primary, #modal-root .btn');
  if (firstFocusable) firstFocusable.focus();
}

export function closeModal() {
  const root = $('#modal-root');
  const overlay = root.querySelector('.overlay:not(.leaving)');
  document.documentElement.classList.remove('lock');

  if (modalReturnFocus && modalReturnFocus.isConnected && typeof modalReturnFocus.focus === 'function') {
    modalReturnFocus.focus();
  }
  modalReturnFocus = null;

  if (modalResolve) {
    const resolve = modalResolve;
    modalResolve = null;
    resolve(false);
  }

  // Modal menutup dengan animasi singkat, lalu dilepas dari halaman
  if (!overlay || reducedMotion.matches) { root.innerHTML = ''; return; }
  overlay.classList.add('leaving');
  setTimeout(() => { if (overlay.isConnected && overlay.classList.contains('leaving')) overlay.remove(); }, 170);
}

// resolve true bila OK, false bila batal/ditutup
export function confirmDialog(title, message, okLabel, danger = false) {
  return new Promise(resolve => {
    modalResolve = resolve;
    openModal(`<h3>${escapeHtml(title)}</h3><p class="sub">${escapeHtml(message)}</p>
      <div class="foot"><button class="btn" data-act="close-modal">Batal</button>
      <button class="btn ${danger ? 'solid-danger' : 'primary'}" data-act="ask-ok">${escapeHtml(okLabel)}</button></div>`);
  });
}

// --- Gerak dan animasi ---
export const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');

// Angka berjalan dari nilai lama ke nilai baru (mis. total keranjang)
const tweens = new WeakMap();
export function tweenNumber(el, to, format) {
  const from = Number(el.dataset.value ?? to);
  el.dataset.value = to;
  cancelAnimationFrame(tweens.get(el));
  if (reducedMotion.matches || from === to) { el.textContent = format(to); return; }

  const startedAt = performance.now();
  const step = now => {
    const progress = Math.min(1, (now - startedAt) / 380);
    el.textContent = format(Math.round(from + (to - from) * (1 - Math.pow(1 - progress, 3))));
    if (progress < 1) tweens.set(el, requestAnimationFrame(step));
  };
  tweens.set(el, requestAnimationFrame(step));
}

// pakai View Transition bila didukung
export const withTransition = update =>
  (!reducedMotion.matches && document.startViewTransition) ? document.startViewTransition(update) : update();

export function flyToCart(from) {
  if (reducedMotion.matches || !from) return;

  const target = [$('#cartbar:not([hidden])'), $('.cart-btn')].find(el => el && el.getClientRects().length);
  if (!target) return;

  const fromBox = from.getBoundingClientRect();
  const targetBox = target.getBoundingClientRect();
  const dot = document.createElement('div');
  dot.className = 'fly';
  dot.textContent = from.textContent;
  dot.setAttribute('aria-hidden', 'true');
  dot.style.cssText = `left:${fromBox.left}px;top:${fromBox.top}px;width:${fromBox.width}px;height:${fromBox.height}px`;
  document.body.appendChild(dot);

  const dx = targetBox.left + targetBox.width / 2 - (fromBox.left + fromBox.width / 2);
  const dy = targetBox.top + targetBox.height / 2 - (fromBox.top + fromBox.height / 2);

  dot.animate([
    { transform: 'translate(0,0) scale(1)', opacity: 1 },
    { transform: `translate(${dx * .55}px,${dy * .3 - 70}px) scale(.85)`, opacity: 1, offset: .5 },
    { transform: `translate(${dx}px,${dy}px) scale(.25)`, opacity: .5 }
  ], { duration: 560, easing: 'cubic-bezier(.4,0,.2,1)' }).onfinish = () => {
    dot.remove();
    target.animate(
      [{ transform: 'scale(1)' }, { transform: 'scale(1.08)' }, { transform: 'scale(1)' }],
      { duration: 240, easing: 'ease-out' }
    );
  };

  if (navigator.vibrate) navigator.vibrate(8);
}

export function animateDashboard(root) {
  if (reducedMotion.matches) return;

  $$('.bar .fill', root).forEach(fill => {
    const width = fill.style.width;
    fill.style.width = '0';
    requestAnimationFrame(() => requestAnimationFrame(() => { fill.style.width = width; }));
  });

  $$('.revenue strong, .fact b', root).forEach(el => {
    const text = el.textContent;
    const target = parseInt(text.replace(/\D/g, ''), 10);
    const isMoney = text.startsWith('Rp');
    if (!target || target < 2) return;

    const startedAt = performance.now();
    const step = now => {
      const progress = Math.min(1, (now - startedAt) / 700);
      const value = Math.round(target * (1 - Math.pow(1 - progress, 3)));
      el.textContent = isMoney ? formatRupiah(value) : String(value);
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

export function confirmAccepted() {
  const resolve = modalResolve;
  modalResolve = null; // cegah closeModal() meresolve false
  closeModal();
  if (resolve) resolve(true);
}