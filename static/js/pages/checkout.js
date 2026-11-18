// TokoBiru - Modal checkout, alamat pengiriman, metode bayar, & pembuatan pesanan
import {
  ADDRESS_LIMIT,
  CHECKOUT_KEY_TTL_MS,
  EWALLET_GROUP,
  PAYMENT_LABEL,
  PHONE_ERROR,
  PHONE_RE,
  RECIPIENT_ERROR,
  SHIPPING_LABEL
} from '../core/constants.js';
import {
  chosenPayment,
  ewalletChoices,
  isEwallet,
  paymentChoices,
  shippingFeeFor,
  state
} from '../core/state.js';
import {
  $,
  $$,
  cleanText,
  escapeHtml,
  ewalletBadgeHtml,
  formatRupiah,
  newRequestKey,
  normalizePhone,
  productEmoji,
  shortText,
  validationError
} from '../core/format.js';
import { api } from '../api/client.js';
import { closeModal, openModal, toast } from '../components/ui.js';
import { cartLines, cartTotal, closeCart, drawCart, openCart } from '../components/cart.js';
import { offerPush } from '../components/push.js';
import { loadProducts, reload, show } from '../core/router.js';
import { showOrderSuccess } from './orders.js';

const myAddresses = () => state.user.addresses || [];
const findAddress = id => myAddresses().find(item => item.id === id);

function addressPickerHtml(addresses, picked) {
  if (!addresses.length) return '';
  const options = addresses.map(item =>
    `<option value="${escapeHtml(item.id)}"${item === picked ? ' selected' : ''}>${escapeHtml(item.label)}${item.main ? ' (utama)' : ''}: ${escapeHtml(shortText(item.address))}</option>`).join('');
  return `<div class="field"><label>Kirim ke</label><select class="select" data-addr-pick>${options}<option value="">Alamat lain…</option></select></div>`;
}

function saveAddressHtml(addresses) {
  const first = addresses.length === 0;
  return `<label class="save-addr" data-save-addr${first ? '' : ' hidden'}><input type="checkbox" class="tick" name="save_address" value="1"${first ? ' checked' : ''}> Simpan alamat ini di akun saya</label>`;
}

function openCheckout() {
  const lines = cartLines();
  if (!lines.length) return;

  closeCart();
  const subtotal = cartTotal(lines);
  const fee = shippingFeeFor(subtotal, 'delivery');
  const addresses = myAddresses();
  const picked = addresses.find(item => item.main) || addresses[0] || null;
  const start = picked || { recipient: state.user.name, phone: '', address: '' };
  const summary = lines.map(({ product, qty }) =>
    `<li><span>${productEmoji(product)} ${escapeHtml(product.name)} <em>× ${qty}</em></span><b class="num">${formatRupiah(product.price * qty)}</b></li>`
  ).join('');
  const options = labels => Object.entries(labels).map(([value, text]) => `<option value="${value}">${text}</option>`).join('');
  const freeHint = state.shipping.fee && state.shipping.freeMin
    ? `<p class="muted small" style="margin:-6px 0 12px">Gratis ongkir untuk belanja mulai ${formatRupiah(state.shipping.freeMin)}.</p>` : '';
  const transferNote = state.payInfo
    ? `<div class="r-note" data-co-note="transfer">Bayar ke: <b>${escapeHtml(state.payInfo)}</b>. Pesanan diproses setelah admin mengonfirmasi pembayaran.</div>`
    : '';
  const cashNote = '<div class="r-note" data-co-note="cash" hidden>Bayar tunai saat pesanan diterima atau diambil. Siapkan uang pas bila bisa.</div>';
  const qrisNote = `<div class="r-note" data-co-note="qris" hidden>Kode QRIS tampil setelah pesanan dibuat. Bayar dalam ${state.qrisMinutes} menit; begitu pembayaran diterima, status pesanan otomatis menjadi dibayar.</div>`;

  const ewalletNote = Object.keys(PAYMENT_LABEL).filter(isEwallet).map(code =>
    `<div class="r-note" data-co-note="${code}" hidden>${code === 'ewallet_ovo' ? 'Setelah pesanan dibuat, segera buka aplikasi OVO (nomor HP di atas harus nomor OVO Anda) lalu setujui pembayaran. Permintaan OVO cepat kedaluwarsa.' : `Setelah pesanan dibuat, Anda diarahkan ke ${PAYMENT_LABEL[code]} untuk membayar.`} Bayar dalam ${state.ewalletMinutes[code] || 15} menit; status pesanan otomatis menjadi dibayar.</div>`).join('');

  openModal(`<h3>Buat pesanan</h3><p class="sub">${lines.length} produk, total <b class="num" data-co-total>${formatRupiah(subtotal + fee)}</b></p>
      <ul class="sum">${summary}<li><span data-co-ship-label>Ongkos kirim</span><b class="num" data-co-ship>${fee ? formatRupiah(fee) : 'Gratis'}</b></li></ul>
      <form data-form="checkout" novalidate><div class="form-alert" role="alert"></div>
        <div class="field"><label>Pengiriman</label><select class="select" name="shipping_method" data-co-pick>${options(SHIPPING_LABEL)}</select></div>
        ${freeHint}
        <div data-co-addr>${addressPickerHtml(addresses, picked)}</div>
        <div class="field"><label>Nama penerima</label><input class="input" name="recipient" required maxlength="50" autocomplete="name" value="${escapeHtml(start.recipient)}"></div>
        <div class="field"><label>Nomor HP / WhatsApp</label><input class="input" name="phone" type="tel" inputmode="tel" required maxlength="20" placeholder="Contoh: 081234567890" autocomplete="tel" value="${escapeHtml(start.phone)}"><div class="muted small" data-co-phone-hint hidden style="margin-top:6px">Untuk OVO, isi dengan nomor HP yang terdaftar di aplikasi OVO.</div></div>
        <div data-co-addr>
          <div class="field"><label>Alamat pengiriman</label><textarea class="input" name="address" required minlength="5" maxlength="160" placeholder="Nama jalan, nomor, kota" autocomplete="street-address">${escapeHtml(start.address)}</textarea></div>
          ${saveAddressHtml(addresses)}
        </div>
        <div class="field"><label>Catatan untuk penjual (opsional)</label><input class="input" name="note" maxlength="200"></div>
        <div class="field"><label>Pembayaran</label><select class="select" name="payment_method" data-co-pick>${options(paymentChoices())}</select></div>
        <div data-co-ewallet hidden><fieldset class="ew-pick"><legend>Pilih e-wallet</legend><div class="ew-grid">${Object.keys(ewalletChoices()).map((code, n) => `<label class="ew-opt"><input type="radio" name="ewallet_channel" value="${code}" data-co-pick${n ? '' : ' checked'} disabled>${ewalletBadgeHtml(code)}</label>`).join('')}</div></fieldset></div>
        ${transferNote}${cashNote}${qrisNote}${ewalletNote}
        <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Buat pesanan (${formatRupiah(subtotal + fee)})</button></div></form>`);
}

function updateCheckout(form) {
  const subtotal = cartTotal(cartLines());
  const shipping = form.elements.shipping_method.value;
  const group = form.elements.payment_method.value;
  const isWallet = group === EWALLET_GROUP;
  const picked = $('input[name=ewallet_channel]:checked', form);
  const payment = isWallet ? (picked ? picked.value : '') : group;
  const fee = shippingFeeFor(subtotal, shipping);
  const total = formatRupiah(subtotal + fee);
  const modal = form.closest('.modal');

  $('[data-co-total]', modal).textContent = total;
  $('[data-co-ship-label]', modal).textContent = shipping === 'pickup' ? 'Ambil di toko' : 'Ongkos kirim';
  $('[data-co-ship]', modal).textContent = fee ? formatRupiah(fee) : 'Gratis';
  $$('[data-co-addr]', form).forEach(el => { el.hidden = shipping === 'pickup'; });
  $('[data-co-ewallet]', form).hidden = !isWallet;
  $$('input[name=ewallet_channel]', form).forEach(radio => { radio.disabled = !isWallet; });
  $$('[data-co-note]', form).forEach(el => { el.hidden = el.dataset.coNote !== payment; });
  const phoneHint = $('[data-co-phone-hint]', form);
  if (phoneHint) phoneHint.hidden = payment !== 'ewallet_ovo';
  $('button[type=submit]', form).textContent = `Buat pesanan (${total})`;
}

function pickCheckoutAddress(select) {
  const form = select.closest('form');
  const item = findAddress(select.value);
  const set = (name, value) => { const input = form.elements[name]; if (input) input.value = value; };
  set('recipient', item ? item.recipient : state.user.name);
  set('phone', item ? item.phone : '');
  set('address', item ? item.address : '');

  const save = $('[data-save-addr]', form);
  if (save) {
    const offer = !item && myAddresses().length < ADDRESS_LIMIT;
    save.hidden = !offer;
    const box = $('input', save);
    if (box && !offer) box.checked = false;
  }
}

// Satu percobaan checkout memakai kunci yang sama, supaya klik ganda tidak membuat pesanan ganda
function checkoutKey(items, ...options) {
  const signature = JSON.stringify([items, ...options]);
  const current = state.checkout;
  const fresh = current && current.signature === signature && Date.now() - current.at < CHECKOUT_KEY_TTL_MS;
  if (!fresh) state.checkout = { signature, key: newRequestKey(), at: Date.now() };
  return state.checkout.key;
}

async function refreshAfterStockConflict(err) {
  closeModal();
  toast(err.message, 'err');
  if (state.view === 'shop') await reload();
  else await loadProducts();
  drawCart();
  openCart();
}

export const checkoutActions = {
  checkout: openCheckout
};

export const checkoutFormHandlers = {
  async checkout(form, data) {
    const phone = normalizePhone(data.phone);
    if (!PHONE_RE.test(phone)) throw validationError({ phone: PHONE_ERROR });

    const recipient = cleanText(data.recipient);
    if (recipient.length < 2) throw validationError({ recipient: RECIPIENT_ERROR });
    const pickup = data.shipping_method === 'pickup';
    const address = pickup ? '' : cleanText(data.address);
    if (!pickup && address.length < 5) throw validationError({ address: 'Alamat minimal 5 karakter' });

    // Harga ikut dikirim: server menolak (409) bila harga katalog sudah berubah
    const items = cartLines().map(line => ({ product_id: line.product.id, qty: line.qty, price: line.product.price }));
    const payment = chosenPayment(data);
    let result;
    try {
      result = await api('/orders', {
        method: 'POST',
        body: { items, phone, address, recipient, note: data.note, shipping_method: data.shipping_method, payment_method: payment },
        headers: { 'Idempotency-Key': checkoutKey(items, data.shipping_method, payment) }
      });
    } catch (err) {
      if (err.status === 409 || err.status === 404) return refreshAfterStockConflict(err);
      throw err;
    }

    state.checkout = null;
    state.cart = {};
    if (!pickup && data.save_address === '1' && myAddresses().length < ADDRESS_LIMIT) {
      try {
        const saved = await api('/auth/addresses', {
          method: 'POST',
          body: { label: 'Rumah', recipient, phone, address, main: !myAddresses().length }
        });
        state.user.addresses = saved.addresses;
      } catch { }
    }
    closeModal();
    await show('orders');
    showOrderSuccess(result.order);
    offerPush(true);
  }
};

export { openCheckout, updateCheckout, pickCheckoutAddress };
