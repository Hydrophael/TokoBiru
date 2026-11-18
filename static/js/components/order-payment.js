// TokoBiru - Komponen pembayaran QRIS/e-wallet, polling status, & bukti transfer AI
import { PAYMENT_LABEL } from '../core/constants.js';
import { isEwallet, isStaff, state } from '../core/state.js';
import { $, $$, countdownText, escapeHtml, ewalletBadgeHtml, formatDate, formatRupiah, icon, msLeft, payRow } from '../core/format.js';
import { api } from '../api/client.js';
import { qrSvg } from '../../vendor/qr.js';
import { burst, openModal, toast } from './ui.js';
import { compressImage } from './photo.js';
import { reload } from '../core/router.js';

export const orderPaymentHooks = {
  onOrderUpdated: () => {},
  onReloadOrders: async () => {}
};

function paymentBoxHtml(order, title = '') {
  // Transfer yang sudah ada buktinya tidak kedaluwarsa sendiri (lihat is_overdue di app.py), jadi batas bayar tidak ditampilkan lagi
  const deadline = order.expires_at && !order.proof_at ? `Bayar sebelum <b>${formatDate(order.expires_at)}</b>` : '';
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
    ? `<a class="btn primary" style="text-decoration:none" href="${escapeHtml(order.ewallet_url)}" target="_blank" rel="noopener">Bayar dengan ${name}</a>`
    : `<p class="qris-hint">Buka aplikasi ${name} lalu setujui pembayaran yang masuk.</p>`;
  return `<section class="qris" data-qris="${escapeHtml(order.id)}" aria-label="Bayar dengan ${name}">
    <div class="qris-head">${ewalletBadgeHtml(order.payment_method)}<span>TokoBiru</span></div>
    <div class="qris-total num">${formatRupiah(order.total)}</div>
    ${action}
    <p class="qris-hint">Status berubah otomatis setelah dibayar.</p>
    ${deadline}
  </section>`;
}

export const cashNoteHtml = order =>
  `<div class="r-note">Siapkan uang tunai <b>${formatRupiah(order.total)}</b> ${order.shipping_method === 'pickup' ? 'saat mengambil pesanan di toko' : 'saat pesanan diterima'}. Kode pesanan: <b>${escapeHtml(order.code)}</b>.${order.status === 'pending' && order.expires_at ? ` Pesanan dibatalkan otomatis bila belum diproses sebelum <b>${formatDate(order.expires_at)}</b>.` : ''}</div>`;

export function showOrderSuccess(order) {
  if (!order) return;
  openModal(`<div class="done"><svg class="done-ic" viewBox="0 0 52 52" aria-hidden="true"><circle cx="26" cy="26" r="24"/><path d="M15 27l8 8 14-19"/></svg>
    <h3>Pesanan berhasil dibuat</h3><p class="sub">${order.payment_method === 'cash' ? 'Pesanan Anda segera diproses.' : 'Satu langkah lagi: bayar agar pesanan segera diproses.'}</p></div>
    ${order.payment_method === 'cash' ? cashNoteHtml(order) : order.payment_method === 'qris' ? qrisBoxHtml(order) : isEwallet(order.payment_method) ? ewalletBoxHtml(order) : paymentBoxHtml(order)}
    <div class="foot"><button class="btn primary" data-act="close-modal">Mengerti</button></div>`);
}



const PROOF_VERDICT = { match: ['ok', 'Cocok'], mismatch: ['err', 'Tidak cocok'], suspicious: ['err', 'Mencurigakan'], unclear: ['warn', 'Perlu dicek'] };
const PROOF_STATUS = { ok: ['ok', 'Cocok'], bad: ['err', 'Bermasalah'], unknown: ['warn', 'Tidak terbaca'], skip: ['warn', 'Tidak diperiksa'] };

const PROOF_ICON = { ok: 'check', err: 'x', warn: 'info' };
const PROOF_SORT = { bad: 0, unknown: 1, skip: 2, ok: 3 };   // yang bermasalah tampil paling atas

function proofCheckHtml(order) {
  const check = order.proof_check;
  const pending = state.proofReader && order.status === 'pending';
  const id = escapeHtml(order.id);
  if (!check) {
    if (!pending) return '';
    return `<div class="pc-empty"><p class="proof-note">Bukti ini belum dibaca. Foto akan dikirim ke layanan AI dan hasilnya hanya saran.</p>
      <button type="button" class="btn sm" data-act="proof-check" data-id="${id}">${icon('search', 14)} Baca dengan AI</button></div>`;
  }
  const [tone, label] = PROOF_VERDICT[check.verdict] || PROOF_VERDICT.unclear;
  // Foto yang bukan bukti transfer: cukup pesan sarannya, deretan "Bermasalah" hanya membingungkan
  const rows = check.reason === 'not_proof' ? '' : (check.checks || [])
    .slice().sort((a, b) => (PROOF_SORT[a.status] ?? 1) - (PROOF_SORT[b.status] ?? 1))
    .map(item => {
      const [itemTone, itemLabel] = PROOF_STATUS[item.status] || PROOF_STATUS.unknown;
      const read = item.read == null || item.read === '' ? '—' : item.read;
      const expected = item.status === 'bad' && item.expected ? `<small class="pc-exp">Seharusnya ${escapeHtml(String(item.expected))}</small>` : '';
      const note = item.note ? `<small>${escapeHtml(item.note)}</small>` : '';
      return `<li class="pc-row ${itemTone}"><span class="pc-main"><b>${escapeHtml(item.label)}</b>: ${escapeHtml(String(read))}${expected}${note}</span><span class="pc-tag ${itemTone}">${itemLabel}</span></li>`;
    }).join('');
  // Hasil "Perlu dicek" boleh dicoba lagi (mis. bacaan meleset). Hasil yang menentukan tetapi baru dibaca sekali
  // (waktu unggah tidak cukup untuk bacaan kedua) boleh diverifikasi ulang. Jumlahnya dibatasi server per jam.
  const unconfirmed = check.verdict !== 'unclear' && check.confirmed === false;
  const canRetry = pending && (check.verdict === 'unclear' || unconfirmed);
  const retry = canRetry
    ? `<button type="button" class="btn sm" data-act="proof-check" data-force="1" data-id="${id}">${icon('search', 14)} ${unconfirmed ? 'Verifikasi ulang' : 'Coba baca lagi'}</button>`
    : '';
  const unconfirmedNote = unconfirmed ? '<p class="proof-note">Baru dibaca satu kali. "Verifikasi ulang" membacanya dua kali lalu membandingkan hasilnya.</p>' : '';
  const meta = [`Keyakinan baca ${Number(check.confidence) || 0}%`];
  if (check.model) meta.push(escapeHtml(check.model));
  if (check.read_at) meta.push(`Dibaca ${formatDate(check.read_at)}`);
  return `<div class="pc" aria-live="polite">
    <div class="pc-verdict ${tone}"><span class="pc-ic">${icon(PROOF_ICON[tone] || 'info', 16)}</span>
      <div><b>${label}</b>${check.advice ? `<p>${escapeHtml(check.advice)}</p>` : ''}</div></div>
    ${rows ? `<ul class="pc-list">${rows}</ul>` : ''}
    ${unconfirmedNote}
    <p class="pc-meta">${meta.map(item => `<span>${item}</span>`).join('')}</p>
    ${retry}
    <p class="proof-note pc-foot">Hanya saran. Cek mutasi rekening sebelum menandai dibayar.</p></div>`;
}

// Bukti transfer: pelanggan mengunggah selama pesanan belum dibayar; admin melihatnya untuk mencocokkan dengan mutasi rekening
function proofBoxHtml(order, canUpload) {
  if (order.payment_method !== 'transfer') return '';
  const has = Boolean(order.proof_at);
  if (!has && !canUpload) return '';
  const src = `/api/orders/${escapeHtml(order.id)}/proof?v=${encodeURIComponent(order.proof_at || '')}`;
  const image = has
    ? `<a class="proof-img" href="${src}" target="_blank" rel="noopener" aria-label="Buka bukti transfer"><img src="${src}" alt="Bukti transfer ${escapeHtml(order.code)}" loading="lazy"></a>
       <p class="proof-note">Diunggah ${formatDate(order.proof_at)}${canUpload ? '. Admin akan mengecek pembayaran Anda.' : ''}</p>`
    : '<p class="proof-note">Sudah transfer? Unggah foto atau tangkapan layar bukti transfernya supaya admin bisa mengecek.</p>';
  // Pelanggan diberi tahu sebelum mengunggah bahwa fotonya dibaca layanan AI pihak ketiga
  const privacy = canUpload && state.proofReader
    ? `<p class="proof-note">Foto bukti dibaca otomatis oleh layanan AI dari Google untuk membantu admin memeriksa. Hasilnya hanya saran; admin yang memutuskan.${state.proofRetentionDays ? ` Foto dihapus otomatis ${state.proofRetentionDays} hari setelah diunggah.` : ''}</p>`
    : '';
  const action = canUpload
    ? `<button type="button" class="btn sm" data-act="proof-pick">${has ? 'Ganti bukti' : 'Unggah bukti transfer'}</button><input type="file" accept="image/*" hidden data-proof-input data-id="${escapeHtml(order.id)}">`
    : '';
  return `<section class="r-proof" aria-label="Bukti transfer"><b class="proof-title">Bukti transfer</b>${image}${privacy}${action}${canUpload ? '' : proofCheckHtml(order)}</section>`;
}


async function uploadProof(input) {
  const file = input.files?.[0];
  const id = input.dataset.id;
  input.value = '';
  if (!file || !id) return;

  const button = input.closest('.r-proof')?.querySelector('[data-act="proof-pick"]');
  const label = button?.textContent;
  const busy = text => { if (button) { button.disabled = true; button.classList.add('reading'); button.innerHTML = `<i class="spin" aria-hidden="true"></i> ${text}`; } };
  busy('Menyiapkan foto…');
  try {
    const image = await compressImage(file, { side: 1600, target: 350 * 1024, limit: 480 * 1024 });
    busy('Mengunggah…');
    const { order } = await api(`/orders/${id}/proof`, { method: 'POST', body: { image } });
    const index = state.orders.findIndex(item => item.id === id);
    if (index >= 0) state.orders[index] = order;
    toast('Bukti transfer terkirim. Admin akan mengecek pembayaran Anda.', 'ok');
    orderPaymentHooks.onOrderUpdated(order);
  } catch (err) {
    toast(err.fields?.image || err.message, 'err');
    if (button && button.isConnected) { button.disabled = false; button.classList.remove('reading'); button.textContent = label; }
  }
}

// Staf: baca ulang bukti transfer secara manual (cadangan bila pembacaan saat unggah gagal). Hasilnya saran saja.
async function checkProof(el) {
  const id = el.dataset.id;
  if (!id || el.disabled) return;
  const label = el.innerHTML;
  const box = el.closest('.r-proof');
  box?.querySelector('.proof-error')?.remove();
  // Pembacaan AI bisa makan puluhan detik: tampilkan penghitung waktu supaya staf tahu proses masih berjalan
  let seconds = 0;
  const paint = () => {
    el.innerHTML = `<i class="spin" aria-hidden="true"></i> Membaca bukti… ${seconds} dtk`;
  };
  el.disabled = true;
  el.classList.add('reading');
  paint();
  const timer = setInterval(() => { seconds += 1; if (el.isConnected) paint(); }, 1000);
  try {
    const { order } = await api(`/orders/${id}/proof/check`, { method: 'POST', body: el.dataset.force ? { force: true } : {} });
    const index = state.orders.findIndex(item => item.id === id);
    if (index >= 0) state.orders[index] = order;
    orderPaymentHooks.onOrderUpdated(order);
    toast('Bukti selesai dibaca', 'ok');
  } catch (err) {
    // Pesan galat ditaruh di kotak bukti (toast hilang sendiri), tombol berubah menjadi "Coba lagi"
    if (el.isConnected) {
      el.disabled = false;
      el.classList.remove('reading');
      el.innerHTML = `${icon('search', 14)} Coba lagi`;
      const note = document.createElement('p');
      note.className = 'proof-error';
      note.setAttribute('role', 'alert');
      note.textContent = err.message;
      el.before(note);
    } else {
      toast(err.message, 'err');
    }
  } finally {
    clearInterval(timer);
  }
}

// Pembacaan AI saat unggah sering tidak sempat selesai (model butuh beberapa detik). Karena itu, begitu staf membuka pesanan
// yang ada buktinya tetapi belum terbaca, bukti langsung dibaca di sini. Sekali per pesanan per sesi supaya kegagalan tidak
// berulang; bila gagal, tombol "Coba lagi" di kotak bukti tetap bisa dipakai.
const autoReadTried = new Set();
function autoReadProof(order) {
  if (!order || !state.proofReader || !isStaff()) return;
  if (order.status !== 'pending' || !order.proof_at || order.proof_check || autoReadTried.has(order.id)) return;
  const button = $(`#modal-root [data-order="${order.id}"] [data-act="proof-check"]`);
  if (!button) return;
  autoReadTried.add(order.id);
  checkProof(button);
}


let qrisBusy = false;

function showQrisResult(id, status) {
  const boxes = $$('[data-qris]').filter(box => box.dataset.qris === id);
  if (!boxes.length) return;

  for (const box of boxes) {
    if (status === 'cancelled') {
      box.innerHTML = '<div class="qris-ok bad"><b>Pesanan dibatalkan</b><span>Waktu bayar habis atau pesanan dibatalkan.</span></div>';
    } else {
      box.innerHTML = qrisPaidHtml();
      box.classList.add('paid');
      burst($('.done-ic', box));
    }
    // Setelah pembayaran selesai atau dibatalkan, ajakan "bayar" di modal sukses tidak relevan lagi
    box.closest('.modal')?.querySelector('.done .sub')?.remove();
    box.removeAttribute('data-qris');
  }
  const order = state.orders.find(item => item.id === id);
  if (order) order.status = status;
  if (state.view === 'orders') {
    setTimeout(async () => {
      if (state.view !== 'orders') return;
      await orderPaymentHooks.onReloadOrders(id);
    }, 1600);
  }
}


// Hitung mundur batas bayar: semua elemen [data-expires] diperbarui tiap detik
let lastExpiredReload = 0;
function tickTimers() {
  for (const el of $$('[data-expires]')) {
    const left = msLeft(el.dataset.expires);
    el.textContent = countdownText(left);
    el.classList.toggle('late', left < 5 * 60 * 1000);
    if (left > 0 || el.dataset.done) continue;
    el.dataset.done = '1';
    // Waktu habis: server memastikan statusnya, lalu tampilan ikut berubah
    if (el.closest('[data-qris]')) pollQris();
    else if (state.view === 'orders' && Date.now() - lastExpiredReload > 5000) { lastExpiredReload = Date.now(); reload(); }
  }
}

// Layar QR memantau status pesanan sampai dibayar atau dibatalkan
async function pollQris() {
  if (qrisBusy || document.hidden) return;
  const ids = [...new Set($$('[data-qris]').map(box => box.dataset.qris))];
  if (!ids.length) return;

  qrisBusy = true;
  try {
    for (const id of ids) {
      try {
        const { status } = await api(`/orders/${id}/status`);
        if (status !== 'pending') showQrisResult(id, status);
      } catch (err) {
        if (err.status === 401) return;
      }
    }
  } finally {
    qrisBusy = false;
  }
}


export const orderPaymentActions = {
  'proof-pick': el => el.closest('.r-proof')?.querySelector('[data-proof-input]')?.click(),
  'proof-check': checkProof
};

export {
  paymentBoxHtml,
  proofBoxHtml,
  uploadProof,
  autoReadProof,
  tickTimers,
  pollQris
};