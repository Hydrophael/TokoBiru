// TokoBiru - Drawer keranjang belanja, perhitungan total, & sinkronisasi tombol kartu
import { MAX_CART_QTY, STORAGE_KEYS } from '../core/constants.js';
import { cartQty, state, storage } from '../core/state.js';
import { $, $$, emptyState, escapeHtml, formatRupiah, icon, miniHtml, priceHtml } from '../core/format.js';
import { EASE, flyToCart, closeModal, reducedMotion, toast, tweenNumber } from './ui.js';

let cartReturnFocus = null;

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


function addOneToCart(el) {
  const id = el.dataset.id;
  const product = state.productMap[id];
  const card = el.closest('[data-card]');
  const current = cartQty(id);

  if (product && card && current < product.stock) flyToCart($('.ini, .photo', card));
  setCartQty(id, current + 1);
}

function removeFromCart(el) {
  const id = el.dataset.id;
  const qty = state.cart[id];
  const name = state.productMap[id].name;

  setCartQty(id, 0);
  toast(`${name} dihapus dari keranjang`, '', { label: 'Urungkan', fn: () => setCartQty(id, qty) });
}

function openCart() {
  cartReturnFocus = document.activeElement;
  $('#drawer').classList.add('open');
  $('#scrim').classList.add('open');
  document.documentElement.classList.add('lock');

  if (!reducedMotion.matches) {
    $$('#cart-items .citem').slice(0, 8).forEach((el, index) => el.animate(
      [{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }],
      { duration: 380, delay: 140 + index * 45, easing: EASE, fill: 'backwards' }
    ));
  }

  $('#drawer .drawer-head button')?.focus();
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

function reorder(el) {
  const order = state.orders.find(o => o.id === el.dataset.id);
  if (!order) return;
  if ($('#modal-root').firstChild) closeModal();

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

export {
  addOneToCart,
  removeFromCart,
  openCart,
  closeCart,
  reorder
};

// Kaki kartu produk di halaman Belanja: harga + tombol Tambah / stepper jumlah / Habis
export function cardFoot(product) {
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