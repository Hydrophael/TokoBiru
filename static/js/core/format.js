// TokoBiru - Helper DOM, pemformatan teks/angka/tanggal, & potongan visual
import {
  ACTION_LABEL,
  DEFAULT_EMOJI,
  DETAIL_KEY,
  DETAIL_VALUE,
  EMOJI_RULES,
  EWALLET_BRAND,
  ICONS,
  LOW_STOCK_LIMIT,
  PAYMENT_LABEL,
  STATUS,
  STOCK_BAR_FULL
} from './constants.js';
import { state } from './state.js';

const capitalizeWords = text => String(text ?? '').replace(/(^|\s)(\S+)/g, (_, space, word) =>
  space + (word.includes('@') ? word : word.replace(/^([(\["“]*)(\p{Ll})/u, (_m, open, ch) => open + ch.toUpperCase())));

export const actionLabel = action => ACTION_LABEL[action] || capitalizeWords(String(action ?? '').replace(/_/g, ' '));

const plainChanges = text => text.replace(/\{([^{}]*)\}/g, (_, body) => body.split(',')
  .map(pair => {
    const [key, value] = pair.split(':').map(part => part.trim().replace(/^['"]|['"]$/g, ''));
    return value === undefined ? pair.trim() : `${DETAIL_KEY[key] || key} → ${DETAIL_VALUE[value] || value}`;
  }).join(', '));

export function detailLabel(log) {
  let text = plainChanges(String(log.detail ?? ''));
  if (log.action === 'pesanan_status') {
    const key = '(pending|paid|shipped|completed|cancelled)';
    // log lama tersimpan dengan "-" atau "->" karena ">" dulu dibuang sanitasi
    text = text.replace(new RegExp(`\\b${key} (?:->|-|→) ${key}\\b`), '$1 → $2')
      .replace(/\b(pending|paid|shipped|completed|cancelled)\b/g, word => STATUS[word][0]);
  }
  return capitalizeWords(text);
}

export function logTone(action) {
  if (/gagal|ditolak/.test(action)) return 'err';
  if (/^pembayaran_(tidak_cocok|terlambat|tak_dikenal)$/.test(action)) return 'warn';
  if (/_hapus$|kedaluwarsa/.test(action)) return 'warn';
  if (/^(register|produk_tambah|user_buat|pesanan_buat)$/.test(action)) return 'ok';
  if (/_ubah$|_status$|password_reset|reset_minta/.test(action)) return 'info';
  return '';
}

// Penanda visual per e-wallet: warna merek + nama. Untuk memakai logo resmi, simpan filenya di /static/icons/pay/ dan isi `logo`, mis. '/static/icons/pay/dana.svg'

export const ewalletBadgeHtml = code => {
  const name = escapeHtml(PAYMENT_LABEL[code] || 'E-wallet');
  const cls = 'ew-badge ew-' + String(code).replace('ewallet_', '');
  const logo = EWALLET_BRAND[code]?.logo;
  return logo ? `<span class="${cls} has-logo"><img src="${escapeHtml(logo)}" alt="${name}" height="24" decoding="async"></span>` : `<span class="${cls}">${name}</span>`;
};

export const brandHtml = (style = '') =>
  `<div class="brand"${style ? ` style="${style}"` : ''}><span class="mark"></span><span>TokoBiru</span></div>`;

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => HTML_ESCAPES[ch]);

const formatNumber = amount => Number(amount || 0).toLocaleString('id-ID');
const NBSP = '\u00a0';
export const formatRupiah = amount => 'Rp' + NBSP + formatNumber(amount);

// Sisa waktu dalam ms, memakai jam server (state.clockSkew diukur saat aplikasi dibuka)
export const msLeft = iso => Date.parse(iso) - (Date.now() + state.clockSkew);
export function countdownText(ms) {
  const total = Math.max(0, Math.ceil(ms / 1000));
  return String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
}
export const priceHtml = amount => `<span class="price num"><small>Rp</small>${formatNumber(amount)}</span>`;

const DATE_FORMAT = { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' };
export function formatDate(iso) {
  try { return new Date(iso).toLocaleString('id-ID', DATE_FORMAT); } catch { return ''; }
}

export const getInitials = name =>
  (String(name).trim().split(/\s+/).slice(0, 2).map(word => word[0]).join('') || '?').toUpperCase();

export const avatarTone = user => hashString(user?.username || user?.name || '') % 5;

export const hashString = text => [...String(text)].reduce((acc, ch) => (acc * 31 + ch.charCodeAt(0)) >>> 0, 7);

export const createError = (message, extra) => Object.assign(new Error(message), extra);

export function newRequestKey() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return [...crypto.getRandomValues(new Uint8Array(16))].map(byte => byte.toString(16).padStart(2, '0')).join('');
}

export function productEmoji(product) {
  const match = EMOJI_RULES.find(([pattern]) => pattern.test(product.name + ' ' + product.category));
  return match ? match[1] : DEFAULT_EMOJI;
}

const PHOTO_URL_PATTERN = /^\/api\/products\/[0-9a-f]{24}\/image\?v=\d+$/;
export function productImage(product) {
  const photo = product?.photo;
  return typeof photo === 'string' && PHOTO_URL_PATTERN.test(photo) ? photo : '';
}

export function tileVisualHtml(product) {
  const image = productImage(product);
  return image
    ? `<img class="photo" src="${image}" alt="" loading="lazy" decoding="async">`
    : `<span class="ini" aria-hidden="true">${productEmoji(product)}</span>`;
}

export function miniHtml(product) {
  const image = productImage(product);
  return `<span class="mini${image ? ' has-photo' : ''}" aria-hidden="true">${image ? `<img src="${image}" alt="" loading="lazy" decoding="async">` : productEmoji(product)}</span>`;
}

const SPEC_SPLIT = /\n+|\s+[-–•]\s+/;
const SPEC_PAIR = /^([^:]{2,28}):\s*(.+)$/;

export function descriptionHtml(text) {
  const raw = String(text ?? '').trim();
  if (!raw) return '<p class="sub">Belum ada deskripsi untuk produk ini.</p>';

  const parts = raw.split(SPEC_SPLIT).map(part => part.trim()).filter(Boolean);
  if (parts.length < 3) return `<p class="sub">${escapeHtml(raw)}</p>`;

  const intro = SPEC_PAIR.test(parts[0]) ? '' : parts.shift();
  const rows = parts.map(part => {
    const pair = part.match(SPEC_PAIR);
    return pair
      ? `<li><span class="k">${escapeHtml(pair[1])}</span><span class="v">${escapeHtml(pair[2])}</span></li>`
      : `<li class="plain"><span class="v">${escapeHtml(part)}</span></li>`;
  }).join('');

  return `${intro ? `<p class="sub dintro">${escapeHtml(intro)}</p>` : ''}<ul class="specs" aria-label="Spesifikasi">${rows}</ul>`;
}

export const icon = (name, size = 17) =>
  `<svg class="ic" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;

export const emptyState = (title, text = '', action = '') =>
  `<div class="empty"><b>${escapeHtml(title)}</b><p>${escapeHtml(text)}</p>${action}</div>`;

// Pesanan COD (cod=true) belum menunggu pembayaran: uang baru diterima saat barang sampai
// Pesanan ambil di toko tidak "dikirim": statusnya berarti barang siap diambil pelanggan
export const orderStatusText = (status, order) => {
  if (order?.cod && status === 'pending') return 'Menunggu diproses';
  if (order?.shipping_method === 'pickup' && status === 'shipped') return 'Siap diambil';
  return STATUS[status][0];
};
export const statusTag = (status, order) => `<span class="tag ${STATUS[status][1]}">${orderStatusText(status, order)}</span>`;

export function stockInfo(product) {
  const { stock } = product;
  const cls = stock === 0 ? 'out' : stock <= LOW_STOCK_LIMIT ? 'low' : '';
  const percent = Math.min(100, Math.round(stock / STOCK_BAR_FULL * 100));
  const label = stock === 0 ? 'Habis' : stock <= LOW_STOCK_LIMIT ? `Tinggal ${stock}` : `Stok ${stock}`;
  return `<div class="stock ${cls}"><span class="num">${label}</span><i><b style="width:${percent}%"></b></i></div>`;
}

export function stockNote(product) {
  const { stock } = product;
  if (stock === 0) return '<span class="stock-note out">Habis</span>';
  if (stock <= LOW_STOCK_LIMIT) return `<span class="stock-note low">Tinggal ${stock}</span>`;
  return `<span class="stock-note">Stok ${stock}</span>`;
}

export function stockFlag(product) {
  if (product.stock === 0) return '<span class="tile-flag out">Habis</span>';
  if (product.stock <= LOW_STOCK_LIMIT) return `<span class="tile-flag low">Tinggal ${product.stock}</span>`;
  return '';
}

export const payRow = (label, value, copyText, copyLabel = label) =>
  `<div class="pay-row"><span>${label}</span><b class="num">${escapeHtml(value)}</b><button class="btn sm" data-act="copy" data-label="${copyLabel}" data-text="${escapeHtml(copyText)}">Salin</button></div>`;

export const cleanText = value => String(value || '').trim();
export const normalizePhone = value => String(value || '').replace(/[\s.-]/g, '');
export const shortText = (text, max = 42) => {
  const flat = String(text).replace(/\s+/g, ' ').trim();
  return flat.length > max ? flat.slice(0, max - 1) + '?' : flat;
};
export const validationError = fields => createError('Periksa kembali isian Anda', { fields });