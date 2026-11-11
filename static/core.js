// TokoBiru - dasar aplikasi: konstanta, state, fungsi bantu, dan klien API

// === Konstanta ===

export const ROLE_LABEL = { user: 'Pelanggan', admin: 'Admin', master: 'Master' };

// status: [label, warna tag]
export const STATUS = {
  pending:   ['Menunggu bayar', 'warn'],
  paid:      ['Dibayar', 'info'],
  shipped:   ['Dikirim', 'blue'],
  completed: ['Selesai', 'ok'],
  cancelled: ['Dibatalkan', 'err']
};

// urutan langkah di timeline
export const ORDER_FLOW = ['pending', 'paid', 'shipped', 'completed'];

export const NAV = [
  { id: 'shop',      label: 'Belanja',   icon: 'home',    roles: ['user'] },
  { id: 'dashboard', label: 'Ringkasan', icon: 'chart',   roles: ['admin', 'master'] },
  { id: 'orders',    label: 'Pesanan',   icon: 'receipt', roles: ['user', 'admin', 'master'] },
  { id: 'products',  label: 'Produk',    icon: 'box',     roles: ['admin', 'master'] },
  { id: 'users',     label: 'Pengguna',  icon: 'users',   roles: ['master'] },
  { id: 'logs',      label: 'Log',       icon: 'list',    roles: ['master'] }
];

export const STORAGE_KEYS = {
  profile: userId => 'tb_profile_' + userId,   // per pengguna: perangkat bersama tidak membocorkan HP/alamat
  legacyProfile: 'tb_profile',                 // kunci lama tanpa ID pengguna, dibuang saat aplikasi dimuat
  cart: userId => 'tb_cart_' + userId
};

export const MAX_CART_QTY = 99;
const LOW_STOCK_LIMIT = 5;
const STOCK_BAR_FULL = 40;   // stok yang dianggap "penuh" pada bar stok
export const MAX_TOASTS = 2;

// emoji dipilih dari kata kunci di nama/kategori
const EMOJI_RULES = [
  [/beras|padi/i, '🌾'], [/minyak/i, '🫒'], [/telur/i, '🥚'], [/kopi/i, '☕'],
  [/\bteh\b/i, '🍵'], [/susu/i, '🥛'], [/roti|kue|biskuit/i, '🍞'], [/madu/i, '🍯'],
  [/sabun|shampo|deterjen|pembersih/i, '🧼'], [/tisu|tissue/i, '🧻'],
  [/gula|permen|cokelat|coklat/i, '🍬'], [/garam|bumbu|kecap|saus/i, '🧂'],
  [/\bmie\b|mi instan|pasta/i, '🍜'], [/\bair\b|mineral/i, '💧'],
  [/buah|apel|jeruk|pisang/i, '🍎'], [/sayur|bayam|wortel|tomat|cabai/i, '🥬'],
  [/daging|ayam|sapi|ikan/i, '🍗'], [/snack|keripik|camilan/i, '🍿'],
  [/jus|soda|sirup|minuman/i, '🧃'], [/obat|vitamin/i, '💊'], [/bayi|popok/i, '🍼']
];
const DEFAULT_EMOJI = '🛒';

const ICONS = {
  cart:    '<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>',
  out:     '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  plus:    '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  search:  '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  edit:    '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>',
  trash:   '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
  x:       '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  home:    '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
  receipt: '<path d="M4 2v20l3-2 3 2 3-2 3 2 3-2V2l-3 2-3-2-3 2-3-2z"/><line x1="8" y1="8" x2="16" y2="8"/><line x1="8" y1="12" x2="16" y2="12"/>',
  box:     '<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><polyline points="3.3 7 12 12 20.7 7"/><line x1="12" y1="22" x2="12" y2="12"/>',
  chart:   '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
  users:   '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  list:    '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="3" cy="6" r="1"/><circle cx="3" cy="12" r="1"/><circle cx="3" cy="18" r="1"/>',
  check:   '<polyline points="20 6 9 17 4 12"/>',
  key:     '<path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>'
};

// style opsional dipakai di halaman masuk (teks brand di atas latar biru)
export const brandHtml = (style = '') =>
  `<div class="brand"${style ? ` style="${style}"` : ''}><span class="mark"></span><span>TokoBiru</span></div>`;

// === State ===

export const state = {
  user: null,
  csrf: '',
  payInfo: '',
  resetEnabled: false,   // true bila server bisa mengirim kode reset password lewat email
  reset: null,           // alur Lupa password yang sedang berjalan: { email, sentTo, endAt, code }
  view: 'shop',
  authTab: 'login',

  // katalog dan keranjang
  products: [],
  productsTotal: 0,      // jumlah produk di server (bisa lebih besar dari yang dimuat)
  productMap: {},        // id produk -> produk
  categories: [],
  category: '',
  query: '',
  searchIds: null,       // id produk hasil pencarian server, urut menurut relevansi (null = pakai filter lokal)
  sort: 'name',
  cart: {},              // id produk -> jumlah

  // data per halaman
  orders: [],
  orderFilter: '',
  justUpdatedOrderId: null,
  fresh: false,          // true saat halaman baru dibuka (animasi masuk hanya saat itu)
  checkout: null,        // { signature, key, at }: kunci idempotensi untuk percobaan checkout yang sama
  stats: null,
  users: [],
  logs: []
};

export const isCustomer = () => state.user?.role === 'user';
export const isStaff = () => !isCustomer();
export const defaultView = () => (isCustomer() ? 'shop' : 'dashboard');
export const cartQty = id => state.cart[id] || 0;  // jumlah produk di keranjang

// === Util ===

// --- DOM ---
export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

// --- Format ---
const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => HTML_ESCAPES[ch]);

const formatNumber = amount => Number(amount || 0).toLocaleString('id-ID');
const NBSP = '\u00a0'; // spasi tak terputus: "Rp" dan angka tidak pernah pindah baris
export const formatRupiah = amount => 'Rp' + NBSP + formatNumber(amount);
export const priceHtml = amount => `<span class="price num"><small>Rp</small>${formatNumber(amount)}</span>`;

const DATE_FORMAT = { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' };
export function formatDate(iso) {
  try { return new Date(iso).toLocaleString('id-ID', DATE_FORMAT); } catch { return ''; }
}

export const getInitials = name =>
  (String(name).trim().split(/\s+/).slice(0, 2).map(word => word[0]).join('') || '?').toUpperCase();

export const hashString = text => [...String(text)].reduce((acc, ch) => (acc * 31 + ch.charCodeAt(0)) >>> 0, 7);

export const createError = (message, extra) => Object.assign(new Error(message), extra);

// Kunci acak untuk satu percobaan request (dikirim sebagai header Idempotency-Key)
export function newRequestKey() {
  if (crypto.randomUUID) return crypto.randomUUID();   // randomUUID hanya ada di konteks aman (https/localhost)
  return [...crypto.getRandomValues(new Uint8Array(16))].map(byte => byte.toString(16).padStart(2, '0')).join('');
}

// --- Penyimpanan lokal (aman terhadap error / mode privat) ---
export const storage = {
  get(key) {
    try { return JSON.parse(localStorage.getItem(key)); } catch { return null; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* abaikan */ }
  },
  remove(key) {
    try { localStorage.removeItem(key); } catch { /* abaikan */ }
  }
};

// --- Produk dan ikon ---
export function productEmoji(product) {
  const match = EMOJI_RULES.find(([pattern]) => pattern.test(product.name + ' ' + product.category));
  return match ? match[1] : DEFAULT_EMOJI;
}

export const icon = (name, size = 17) =>
  `<svg class="ic" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;

// --- Potongan HTML yang dipakai banyak tampilan ---
export const emptyState = (title, text = '', action = '') =>
  `<div class="empty"><b>${escapeHtml(title)}</b><p>${escapeHtml(text)}</p>${action}</div>`;

export const statusTag = status => `<span class="tag ${STATUS[status][1]}">${STATUS[status][0]}</span>`;

export function stockInfo(product) {
  const { stock } = product;
  const cls = stock === 0 ? 'out' : stock <= LOW_STOCK_LIMIT ? 'low' : '';
  const percent = Math.min(100, Math.round(stock / STOCK_BAR_FULL * 100));
  const label = stock === 0 ? 'Habis' : stock <= LOW_STOCK_LIMIT ? `Tinggal ${stock}` : `Stok ${stock}`;
  return `<div class="stock ${cls}"><span class="num">${label}</span><i><b style="width:${percent}%"></b></i></div>`;
}

export const payRow = (label, value, copyText, copyLabel = label) =>
  `<div class="pay-row"><span>${label}</span><b class="num">${escapeHtml(value)}</b><button class="btn sm" data-act="copy" data-label="${copyLabel}" data-text="${escapeHtml(copyText)}">Salin</button></div>`;

// === API ===

// Diisi oleh app.js supaya api() tidak perlu mengenal tampilan (menghindari import melingkar)
export const hooks = { onSessionExpired() {} };

export async function api(path, { method = 'GET', body, headers } = {}) {
  const options = {
    method,
    headers: { 'Accept': 'application/json', ...headers },
    credentials: 'same-origin'
  };
  if (method !== 'GET') {
    options.headers['Content-Type'] = 'application/json';
    options.headers['X-CSRF-Token'] = state.csrf;
  }
  if (body !== undefined) options.body = JSON.stringify(body);

  let response;
  try {
    response = await fetch('/api' + path, options);
  } catch {
    throw createError('Tidak dapat terhubung ke server', { status: 0 });
  }

  let data = {};
  try { data = await response.json(); } catch { /* respons tanpa body JSON */ }

  if (!response.ok) {
    const sessionExpired = response.status === 401 && !path.startsWith('/auth/');
    if (sessionExpired) hooks.onSessionExpired();
    throw createError(data.error || 'Terjadi kesalahan', { status: response.status, fields: data.fields });
  }
  return data;
}