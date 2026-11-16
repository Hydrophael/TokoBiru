import { $, $$, MAX_TOASTS, escapeHtml, formatRupiah } from './core.js';

export const EASE = 'cubic-bezier(.2,.8,.2,1)';

export function toast(message, type = '', action) {
  const box = $('#toasts');
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  // Pembaca layar mengumumkan toast: kesalahan langsung, selebihnya menunggu giliran
  el.setAttribute('role', type === 'err' ? 'alert' : 'status');

  const text = document.createElement('span');
  text.textContent = message;
  el.appendChild(text);

  let timer = null;
  const dismiss = () => {
    clearTimeout(timer);
    if (el.classList.contains('out')) return;
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

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'toast-x';
    close.setAttribute('aria-label', 'Tutup');
    close.textContent = '×';
    close.onclick = dismiss;
    el.appendChild(close);
  }

  while (box.children.length >= MAX_TOASTS) box.firstChild.remove();
  box.appendChild(el);

  // Toast biasa hilang sendiri; yang punya tombol aksi diberi waktu jauh lebih lama.
  // Waktu berhenti saat toast disorot kursor atau difokus, supaya sempat dibaca.
  const duration = action ? 30000 : type === 'err' ? 6000 : 4000;
  const arm = () => { clearTimeout(timer); timer = setTimeout(dismiss, duration); };
  const hold = () => clearTimeout(timer);
  el.addEventListener('pointerenter', hold);
  el.addEventListener('pointerleave', arm);
  el.addEventListener('focusin', hold);
  el.addEventListener('focusout', arm);
  arm();
}

let modalResolve = null;
let modalReturnFocus = null;

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

  if (!overlay || reducedMotion.matches) { root.innerHTML = ''; return; }
  overlay.classList.add('leaving');
  setTimeout(() => { if (overlay.isConnected && overlay.classList.contains('leaving')) overlay.remove(); }, 170);
}

export function confirmDialog(title, message, okLabel, danger = false) {
  return new Promise(resolve => {
    modalResolve = resolve;
    openModal(`<h3>${escapeHtml(title)}</h3><p class="sub">${escapeHtml(message)}</p>
      <div class="foot"><button class="btn" data-act="close-modal">Batal</button>
      <button class="btn ${danger ? 'solid-danger' : 'primary'}" data-act="ask-ok">${escapeHtml(okLabel)}</button></div>`);
  });
}

const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');
// Ikut pengaturan perangkat atau pilihan "Kurangi animasi" di Pengaturan
export const reducedMotion = { get matches() { return motionQuery.matches || document.documentElement.classList.contains('calm'); } };

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

export const withTransition = update =>
  (!reducedMotion.matches && document.startViewTransition) ? document.startViewTransition(update) : update();

export function flyToCart(from) {
  if (reducedMotion.matches || !from) return;

  const target = [$('#cartbar:not([hidden])'), $('.cart-btn')].find(el => el && el.getClientRects().length);
  if (!target) return;

  const isPhoto = from instanceof HTMLImageElement;
  const fromBox = from.getBoundingClientRect();
  const size = 56;
  const startBox = isPhoto
    ? { left: fromBox.left + fromBox.width / 2 - size / 2, top: fromBox.top + fromBox.height / 2 - size / 2, width: size, height: size }
    : fromBox;
  const targetBox = target.getBoundingClientRect();
  const dot = document.createElement('div');
  dot.className = isPhoto ? 'fly photo' : 'fly';
  if (isPhoto) dot.style.backgroundImage = `url("${from.currentSrc || from.src}")`;
  else dot.textContent = from.textContent;
  dot.setAttribute('aria-hidden', 'true');
  Object.assign(dot.style, { left: startBox.left + 'px', top: startBox.top + 'px', width: startBox.width + 'px', height: startBox.height + 'px' });
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

  if (navigator.vibrate && !document.documentElement.classList.contains('no-haptic')) navigator.vibrate(8);
}

export function animateDashboard(root) {
  if (reducedMotion.matches) return;

  $$('.bar .fill', root).forEach(fill => {
    const width = fill.style.width;
    fill.style.width = '0';
    requestAnimationFrame(() => requestAnimationFrame(() => { fill.style.width = width; }));
  });

  $$('.revenue strong, .fact b, .hstat b', root).forEach(el => {
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

// Cegah closeModal() meresolve false saat dialog diterima
export function confirmAccepted() {
  const resolve = modalResolve;
  modalResolve = null;
  closeModal();
  if (resolve) resolve(true);
}

export function burst(el, count = 18) {
  if (reducedMotion.matches || !el || !el.isConnected) return;

  const box = el.getBoundingClientRect();
  const originX = box.left + box.width / 2;
  const originY = box.top + box.height / 2;
  const colors = ['var(--accent)', 'var(--blue)', 'var(--mark-a)', 'var(--accent)', 'var(--ok)'];

  for (let i = 0; i < count; i++) {
    const piece = document.createElement('i');
    piece.className = 'confetti';
    piece.setAttribute('aria-hidden', 'true');
    piece.style.cssText = `left:${originX}px;top:${originY}px;background:${colors[i % colors.length]}`;
    document.body.appendChild(piece);

    const angle = (Math.PI * 2 * i) / count + Math.random() * 0.4;
    const distance = 70 + Math.random() * 70;
    const dx = Math.cos(angle) * distance;
    const dy = Math.sin(angle) * distance;
    piece.animate([
      { transform: 'translate(-50%,-50%) scale(1) rotate(0deg)', opacity: 1 },
      { transform: `translate(calc(-50% + ${dx}px),calc(-50% + ${dy + 36}px)) scale(.55) rotate(${Math.round(Math.random() * 540 - 270)}deg)`, opacity: 0 }
    ], { duration: 750 + Math.random() * 350, easing: 'cubic-bezier(.2,.8,.2,1)' }).onfinish = () => piece.remove();
  }
}