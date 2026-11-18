// TokoBiru - Halaman daftar pesanan, detail pesanan, & perubahan status
import { ORDER_FLOW, SHIPPING_LABEL } from '../core/constants.js';
import { isCustomer, isEwallet, isStaff, state } from '../core/state.js';
import { $, emptyState, escapeHtml, formatDate, formatRupiah, icon, statusTag } from '../core/format.js';
import { api } from '../api/client.js';
import { closeModal, confirmDialog, openModal, toast, withTransition } from '../components/ui.js';
import { reorder } from '../components/cart.js';
import {
  autoReadProof,
  orderPaymentActions,
  orderPaymentHooks,
  paymentBoxHtml,
  pollQris,
  proofBoxHtml,
  qrisPaidHtml,
  showOrderSuccess,
  tickTimers,
  uploadProof
} from '../components/order-payment.js';
import { reload } from '../core/router.js';

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

const isPickup = order => order.shipping_method === 'pickup';
// QRIS dan e-wallet dilunasi otomatis oleh Xendit; staf tidak boleh menandainya "Dibayar" (server juga menolak)
const isGatewayPayment = order => order.payment_method === 'qris' || isEwallet(order.payment_method);

function staffOrderActions(order) {
  const cancel = statusButton(order, 'cancelled', 'Batalkan', 'danger');
  const ship = statusButton(order, 'shipped', isPickup(order) ? 'Tandai siap diambil' : 'Tandai dikirim', 'primary');
  switch (order.status) {
    case 'pending':
      if (order.cod) return ship + cancel;
      if (isGatewayPayment(order)) return cancel;
      return statusButton(order, 'paid', 'Konfirmasi pembayaran', 'primary') + cancel;
    case 'paid':    return ship + cancel;
    // Setelah dikirim/siap diambil staf masih bisa membatalkan (retur); pesanan non-COD yang dibatalkan ditandai perlu refund
    case 'shipped': return order.cod
      ? statusButton(order, 'completed', 'Selesai, uang diterima', 'primary') + cancel
      : statusButton(order, 'completed', isPickup(order) ? 'Sudah diambil' : 'Tandai selesai', 'primary') + (isPickup(order) ? cancel : statusButton(order, 'cancelled', 'Batalkan / retur', 'danger'));
    default:        return '';
  }
}

function customerOrderActions(order) {
  switch (order.status) {
    // Setelah bukti transfer dikirim, pembatalan diputuskan toko (server juga menolak)
    case 'pending':   return order.proof_at
      ? (order.cancel_requested_at
        ? '<span class="muted small">Permintaan batal terkirim. Toko sedang mengecek pembayaran Anda.</span>'
        : '<span class="muted small">Bukti transfer sudah dikirim, jadi pembatalan diputuskan toko.</span>'
          + `<button class="btn sm danger" data-act="order-cancel-request" data-id="${order.id}">Minta dibatalkan</button>`)
      : statusButton(order, 'cancelled', 'Batalkan pesanan', 'danger');
    case 'shipped':   return order.cod ? '' : statusButton(order, 'completed', isPickup(order) ? 'Sudah saya ambil' : 'Pesanan sudah diterima', 'primary');
    case 'completed':
    case 'cancelled': return `<button class="btn sm primary" data-act="reorder" data-id="${order.id}">Beli lagi</button>`;
    default:          return '';
  }
}

const orderActions = order => (isStaff() ? staffOrderActions(order) : customerOrderActions(order));

const orderPaymentHtml = order => paymentBoxHtml(order, 'Cara bayar');

// Hasil baca otomatis bukti transfer (hanya staf). Selalu berupa saran: keputusan tetap di tangan staf.

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
const paymentFlagTitle = order => order.needs_refund ? 'Perlu refund'
  : order.payment_issue === 'proof_cancelled' ? 'Cek bukti transfer' : 'Nominal tidak cocok';
const paymentFlagText = order => order.needs_refund
  ? 'Uang pelanggan sudah masuk tetapi pesanan dibatalkan. Kembalikan dana: lewat Dashboard Xendit untuk QRIS/e-wallet, atau transfer balik untuk transfer bank.'
  : order.payment_issue === 'proof_cancelled'
    ? 'Pesanan dibatalkan karena akun pelanggan diubah, padahal bukti transfer sudah diunggah. Cek mutasi rekening; bila uang sudah masuk, transfer balik ke pelanggan.'
    : order.payment_issue ? 'Nominal pembayaran tidak sama dengan total pesanan. Periksa di Dashboard Xendit.' : '';
const paymentFlagBrief = order => paymentFlagText(order)
  ? `<p class="r-hint"><b>⚠ ${paymentFlagTitle(order)}</b></p>` : '';
const paymentFlagBox = order => paymentFlagText(order)
  ? `<div class="r-note"><b>⚠ ${paymentFlagTitle(order)}</b><br>${paymentFlagText(order)}<br>
      <button type="button" class="btn sm" data-act="issue-done" data-id="${order.id}">Sudah ditangani</button></div>` : '';
const orderAutoCancelHtml = order => AUTO_CANCEL_TEXT[order.cancel_reason]
  ? `<p class="r-auto">${AUTO_CANCEL_TEXT[order.cancel_reason]}</p>` : '';

function orderPayBoxHtml(order) {
  if (order.payment_method === 'cash') return cashNoteHtml(order);
  if (isEwallet(order.payment_method)) return ewalletBoxHtml(order);
  if (order.payment_method === 'qris') return qrisBoxHtml(order);
  return orderPaymentHtml(order) + proofBoxHtml(order, true);
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
      : `<p class="r-hint">${order.proof_at ? (order.cancel_requested_at ? 'Permintaan batal terkirim. Menunggu keputusan admin.' : 'Bukti terkirim. Menunggu konfirmasi admin.') : 'Belum dibayar. Buka untuk bayar.'}</p>`) : '';
  const acts = staff ? orderActions(order) : '';
  const proofHint = staff && order.status === 'pending' && order.proof_at ? `<p class="r-hint">Bukti transfer sudah diunggah${order.cancel_requested_at ? ' · <b>pelanggan minta batal</b>' : ''}</p>` : '';

  return `
    <article class="receipt st-${order.status}" style="--i:${Math.min(index, 8)}" data-act="order-open" data-id="${order.id}" role="button" tabindex="0" aria-label="Buka pesanan ${escapeHtml(order.code)}">
      <div class="r-top"><span class="r-code num">${escapeHtml(order.code)}</span>
        <span class="muted small r-date">${formatDate(order.created_at)}${owner}</span>
        <span class="stamp ${statusColor}${justUpdated}">${statusLabel}</span></div>
      <p class="r-sum">${orderSummaryHtml(order)}</p>
      ${hint}${proofHint}${staff ? paymentFlagBrief(order) : ''}
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
    ${orderInfoHtml(order)}${orderAutoCancelHtml(order)}${staff && order.status === 'pending' && order.cancel_requested_at ? '<div class="r-note"><b>Pelanggan minta pembatalan</b><br>Cek mutasi dulu. Bila uang sudah masuk, kembalikan dana setelah membatalkan.</div>' : ''}${staff ? paymentFlagBox(order) + proofBoxHtml(order, false) : ''}${payment}
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


function filterOrders(el) {
  state.orderFilter = el.dataset.s;
  withTransition(() => {
    $('#orail').innerHTML = orderRailHtml();
    $('#olist').innerHTML = orderCards();
    $('#orail .active')?.focus({ preventScroll: true });
  });
}

// Bukti transfer: foto dikecilkan di browser (sisi terpanjang 1600 px, sekitar 350 KB) lalu dikirim sebagai data URL.
// Jangan terlalu kecil: struk berisi angka kecil, dan pada 1000 px angka seperti 3/8 atau 1/7 mudah salah terbaca oleh AI.

function openOrder(el) {
  const order = state.orders.find(item => item.id === el.dataset.id);
  if (!order) return;
  orderDetailModal(order);
  autoReadProof(order);
}

async function deleteOrder(el) {
  const order = state.orders.find(item => item.id === el.dataset.id);
  if (!order) return;
  const ok = await confirmDialog(`Hapus pesanan ${order.code}?`, 'Pesanan hilang dari daftar Anda. Toko tetap menyimpan catatannya untuk laporan.', 'Hapus', true);
  if (!ok) { orderDetailModal(order); return; }
  try {
    await api('/orders/' + order.id, { method: 'DELETE', body: {} });
    toast('Pesanan dihapus', 'ok');
  } catch (err) {
    toast(err.message, 'err');
  }
  await reload();
}

async function clearOrderHistory() {
  const ok = await confirmDialog('Bersihkan riwayat?', 'Semua pesanan selesai atau dibatalkan dihapus dari daftar Anda. Pesanan yang masih berjalan tidak ikut terhapus.', 'Bersihkan', true);
  if (!ok) return;
  try {
    const { removed } = await api('/orders/clear-history', { method: 'POST', body: {} });
    toast(removed ? `${removed} pesanan dihapus` : 'Tidak ada riwayat untuk dibersihkan', 'ok');
  } catch (err) {
    toast(err.message, 'err');
  }
  await reload();
}

async function resolvePaymentIssue(el) {
  const confirmed = await confirmDialog('Sudah ditangani?', 'Pastikan dana sudah dikembalikan atau selisihnya sudah dibereskan di Dashboard Xendit. Penanda akan dihapus dari pesanan ini.', 'Ya, sudah');
  if (!confirmed) return;
  try {
    await api(`/orders/${el.dataset.id}/issue-resolved`, { method: 'POST', body: {} });
    if ($('#modal-root').firstChild) closeModal();
    toast('Penanda dihapus', 'ok');
    await reload();
  } catch (err) {
    toast(err.message, 'err');
  }
}

// Staf membatalkan pesanan yang sudah dibayar/dikirim: dialog menjelaskan stok, barang, dan refund
function cancelOrderMessage(order) {
  const parts = [];
  if (order?.status === 'shipped') parts.push('Pesanan sudah dikirim atau siap diambil. Pastikan barangnya sudah kembali ke toko, karena stok langsung dikembalikan.');
  else parts.push('Stok produk dikembalikan.');
  if (order?.status === 'pending' && order.proof_at) {
    parts.push('Pelanggan sudah mengunggah bukti transfer. Cek mutasi dulu; bila uangnya sudah masuk, kembalikan dana secara manual.');
  }
  if (order && !order.cod && ['paid', 'shipped'].includes(order.status)) {
    parts.push('Pesanan ini sudah dibayar, jadi akan ditandai "Perlu refund". Kembalikan dana pelanggan, lalu tekan "Sudah ditangani" di pesanan ini.');
  }
  parts.push('Pesanan tidak bisa dibuka lagi.');
  return parts.join(' ');
}

// Pelanggan: setelah bukti transfer dikirim, pembatalan diputuskan toko, jadi pelanggan mengirim permintaan
async function requestCancel(el) {
  const order = state.orders.find(item => item.id === el.dataset.id);
  if (!order) return;
  const ok = await confirmDialog('Minta pembatalan?', 'Bukti transfer Anda sudah dikirim, jadi toko mengecek pembayaran dulu lalu memutuskan. Bila disetujui dan uang sudah masuk, dana dikembalikan.', 'Kirim permintaan');
  if (!ok) { orderDetailModal(order); return; }
  try {
    await api(`/orders/${order.id}/cancel-request`, { method: 'POST', body: {} });
    toast('Permintaan batal terkirim. Toko akan menghubungi Anda.', 'ok');
  } catch (err) {
    toast(err.message, 'err');
  }
  await reload();
}

async function changeOrderStatus(el) {
  const { id, status } = el.dataset;

  if (status === 'cancelled') {
    const order = state.orders.find(item => item.id === id);
    const confirmed = await confirmDialog('Batalkan pesanan?', cancelOrderMessage(order), 'Batalkan pesanan', true);
    if (!confirmed) return;
  }

  el.classList.add('loading');
  el.disabled = true;
  try {
    await api(`/orders/${id}/status`, { method: 'PATCH', body: { status } });
    if ($('#modal-root').firstChild) closeModal();
    toast('Status pesanan diperbarui', 'ok');
    state.justUpdatedOrderId = id;
    await reload();
    state.justUpdatedOrderId = null;
  } catch (err) {
    toast(err.message, 'err');
    await reload();
  }
}


async function copyToClipboard(el) {
  try {
    await navigator.clipboard.writeText(el.dataset.text);
    toast(el.dataset.label + ' disalin');
  } catch {
    toast('Tidak bisa menyalin, salin manual', 'err');
  }
}


orderPaymentHooks.onOrderUpdated = order => {
  if ($(`#modal-root [data-order="${order.id}"]`)) orderDetailModal(order);
  if (state.view === 'orders' && $('#olist')) $('#olist').innerHTML = orderCards();
};

orderPaymentHooks.onReloadOrders = async id => {
  await reload();
  const fresh = $(`#modal-root [data-order="${id}"]`) && state.orders.find(item => item.id === id);
  if (fresh) orderDetailModal(fresh);
};

export const orderActions = {
  ofilter: filterOrders,
  copy: copyToClipboard,
  'order-open': openOrder,
  'order-del': deleteOrder,
  'orders-clear': clearOrderHistory,
  reorder,
  'order-status': changeOrderStatus,
  'order-cancel-request': requestCancel,
  'issue-done': resolvePaymentIssue,
  ...orderPaymentActions
};

export {
  ordersView,
  orderCards,
  orderRailHtml,
  orderDetailModal,
  qrisPaidHtml,
  showOrderSuccess,
  uploadProof,
  pollQris,
  tickTimers
};
