export const ROLE_LABEL = { user: 'Pelanggan', admin: 'Admin', master: 'Master' };

export const ADDRESS_LIMIT = 5;
export const ADDRESS_LABELS = ['Rumah', 'Kantor', 'Kos', 'Lainnya'];

export const APP_INFO = {
  name: 'TokoBiru',
  version: '1.1.0',
  tagline: 'Belanja kebutuhan harian, pantau pesanan, kelola toko.',
  stack: 'Flask, MongoDB, JavaScript'
};

export const STATUS = {
  pending:   ['Menunggu bayar', 'warn'],
  paid:      ['Dibayar', 'info'],
  shipped:   ['Dikirim', 'blue'],
  completed: ['Selesai', 'ok'],
  cancelled: ['Dibatalkan', 'err']
};

const ACTION_LABEL = {
  register: 'Daftar Akun', login: 'Login', login_gagal: 'Login Gagal', logout: 'Logout',
  password_ubah: 'Password Diubah', password_gagal: 'Ganti Password Gagal', reset_minta: 'Minta Reset Password',
  password_reset: 'Password Direset', reset_gagal: 'Reset Gagal',
  produk_tambah: 'Produk Ditambah', produk_ubah: 'Produk Diubah', produk_hapus: 'Produk Dihapus',
  pesanan_buat: 'Pesanan Dibuat', pesanan_status: 'Status Pesanan Berubah', pesanan_kedaluwarsa: 'Pesanan Kedaluwarsa',
  pesanan_hapus: 'Pesanan Dihapus', pesanan_bersihkan: 'Riwayat Dibersihkan',
  user_buat: 'Pengguna Dibuat', user_ubah: 'Pengguna Diubah', user_hapus: 'Pengguna Dihapus',
  profil_ubah: 'Profil Diubah', alamat_ubah: 'Alamat Diubah',
  akses_ditolak: 'Akses Ditolak',
  pesanan_bayar_gagal: 'Pembayaran E-Wallet Gagal', pesanan_gagal_gateway: 'Pesanan Gagal Dibuat',
  pembayaran_tidak_cocok: 'Nominal Bayar Tidak Cocok', pembayaran_terlambat: 'Dibayar Setelah Batal',
  pembayaran_tak_dikenal: 'Pembayaran Tak Dikenal', pembayaran_masalah_selesai: 'Masalah Bayar Selesai'
};

const capitalizeWords = text => String(text ?? '').replace(/(^|\s)(\S+)/g, (_, space, word) =>
  space + (word.includes('@') ? word : word.replace(/^([(\["“]*)(\p{Ll})/u, (_m, open, ch) => open + ch.toUpperCase())));

export const actionLabel = action => ACTION_LABEL[action] || capitalizeWords(String(action ?? '').replace(/_/g, ' '));

const DETAIL_KEY = { role: 'peran', active: 'status' };
const DETAIL_VALUE = { user: 'Pelanggan', admin: 'Admin', master: 'Master', True: 'Aktif', False: 'Nonaktif' };
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

export const LOG_GROUPS = [
  { id: '',        label: 'Semua',            test: () => true },
  { id: 'alert',   label: 'Perlu dicek',      test: action => /gagal|ditolak|^pembayaran_(tidak_cocok|terlambat|tak_dikenal)$/.test(action) },
  { id: 'auth',    label: 'Login & password', test: action => /^(register|login|logout|password_|reset_|profil_|alamat_)/.test(action) },
  { id: 'order',   label: 'Pesanan',          test: action => action.startsWith('pesanan_') || action.startsWith('pembayaran_') },
  { id: 'product', label: 'Produk',           test: action => action.startsWith('produk_') },
  { id: 'user',    label: 'Pengguna',         test: action => action.startsWith('user_') }
];

export function filteredLogs() {
  const { q, group, action } = state.logFilter;
  const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const inGroup = (LOG_GROUPS.find(item => item.id === group) || LOG_GROUPS[0]).test;
  return state.logs.filter(log => {
    if (!inGroup(log.action) || (action && log.action !== action)) return false;
    if (!words.length) return true;
    const haystack = `${log.actor} ${ROLE_LABEL[log.role] || ''} ${actionLabel(log.action)} ${detailLabel(log)} ${log.ip}`.toLowerCase();
    return words.every(word => haystack.includes(word));
  });
}

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
  profile: userId => 'tb_profile_' + userId,
  legacyProfile: 'tb_profile',
  cart: userId => 'tb_cart_' + userId,
  layout: 'tb_shop_layout',
  settings: 'tb_settings'
};

export const MAX_CART_QTY = 99;

export const SHIPPING_LABEL = { delivery: 'Antar ke alamat', pickup: 'Ambil di toko' };
// Kode harus sama dengan PAYMENT_METHODS di app.py
export const PAYMENT_LABEL = {
  transfer: 'Transfer bank', cash: 'Bayar tunai', qris: 'QRIS',
  ewallet_dana: 'DANA', ewallet_shopeepay: 'ShopeePay', ewallet_ovo: 'OVO'
};
export const isEwallet = method => String(method).startsWith('ewallet_');
// Penanda visual per e-wallet: warna merek + nama. Untuk memakai logo resmi, simpan filenya di /static/icons/pay/ dan isi `logo`, mis. '/static/icons/pay/dana.svg'
export const EWALLET_BRAND = {
  ewallet_dana:      { logo: '/static/icons/pay/dana.png' },
  ewallet_shopeepay: { logo: '/static/icons/pay/shopeepay.png' },
  ewallet_ovo:       { logo: '/static/icons/pay/ovo.png' }
};
export const ewalletBadgeHtml = code => {
  const name = escapeHtml(PAYMENT_LABEL[code] || 'E-wallet');
  const cls = 'ew-badge ew-' + String(code).replace('ewallet_', '');
  const logo = EWALLET_BRAND[code]?.logo;
  return logo ? `<span class="${cls} has-logo"><img src="${escapeHtml(logo)}" alt="${name}" height="24" decoding="async"></span>` : `<span class="${cls}">${name}</span>`;
};
// Di form checkout, DANA/ShopeePay/OVO digabung jadi satu pilihan "E-Wallet"; pilihan rincinya muncul setelah itu
export const EWALLET_GROUP = 'ewallet';
export const ewalletChoices = () => Object.fromEntries(Object.entries(PAYMENT_LABEL).filter(([code]) => isEwallet(code)));
export const paymentChoices = () => {
  const choices = Object.fromEntries(Object.entries(PAYMENT_LABEL).filter(([code]) =>
    !isEwallet(code) && (code !== 'qris' || state.dummyQris)));
  if (state.ewalletOn) choices[EWALLET_GROUP] = 'E-Wallet';
  return choices;
};
// Kode metode yang dikirim ke server: bila memilih E-Wallet, pakai kanal yang dipilih (mis. ewallet_dana)
export const chosenPayment = data => data.payment_method === EWALLET_GROUP ? (data.ewallet_channel || '') : data.payment_method;

// Aturan sama dengan shipping_fee_for() di app.py; total akhir tetap dihitung server
export function shippingFeeFor(subtotal, method) {
  const { fee, freeMin } = state.shipping;
  if (method === 'pickup' || !fee) return 0;
  return freeMin && subtotal >= freeMin ? 0 : fee;
}
const LOW_STOCK_LIMIT = 5;
const STOCK_BAR_FULL = 40;
export const MAX_TOASTS = 2;
export const SHOP_PAGE_SIZE = 12;

const EMOJI_RULES = [
  [/beras|padi/i, '🌾'], [/minyak/i, '🫒'], [/telur/i, '🥚'], [/kopi/i, '☕'],
  [/\bteh\b/i, '🍵'], [/susu/i, '🥛'], [/roti|kue|biskuit/i, '🍞'], [/madu/i, '🍯'],
  [/sabun|shampo|deterjen|pembersih/i, '🧼'], [/tisu|tissue/i, '🧻'],
  [/gula|permen|cokelat|coklat/i, '🍬'], [/garam|bumbu|kecap|saus/i, '🧂'],
  [/\bmie\b|mi instan|pasta/i, '🍜'], [/\bair\b|mineral/i, '💧'],
  [/buah|apel|jeruk|pisang/i, '🍎'], [/sayur|bayam|wortel|tomat|cabai/i, '🥬'],
  [/daging|ayam|sapi|ikan/i, '🍗'], [/snack|keripik|camilan/i, '🍿'],
  [/jus|soda|sirup|minuman/i, '🧃'], [/obat|vitamin/i, '💊'], [/bayi|popok/i, '🍼'],
  [/laptop|notebook|lenovo|asus|acer|macbook|komputer|\bpc\b/i, '💻'],
  [/\bhp\b|ponsel|smartphone|iphone|samsung|xiaomi|oppo|vivo|realme/i, '📱'],
  [/headset|headphone|earphone|speaker|audio/i, '🎧'], [/\btv\b|televisi|monitor/i, '📺'],
  [/kamera|camera/i, '📷'], [/jam tangan|smartwatch/i, '⌚'], [/kipas|\bac\b/i, '🌀'],
  [/kabel|charger|baterai|powerbank|elektronik/i, '🔌']
];
const DEFAULT_EMOJI = '🛒';

const ICONS = {
  sliders: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
  grid:    '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
  up:      '<line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>',
  left:    '<polyline points="15 18 9 12 15 6"/>',
  right:   '<polyline points="9 18 15 12 9 6"/>',
  bell:    '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
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
  key:     '<path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>',
  user:    '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  chevron: '<polyline points="6 9 12 15 18 9"/>',
  gear:    '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  pin:     '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
  download:'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  info:    '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>'
};

export const brandHtml = (style = '') =>
  `<div class="brand"${style ? ` style="${style}"` : ''}><span class="mark"></span><span>TokoBiru</span></div>`;

export const state = {
  user: null,
  csrf: '',
  payInfo: '',
  dummyQris: false,
  ewalletOn: false,
  qrisMinutes: 60,
  ewalletMinutes: {},
  clockSkew: 0,
  shipping: { fee: 0, freeMin: 0 },
  resetEnabled: false,
  reset: null,
  view: 'shop',
  authTab: 'login',

  products: [],
  productsTotal: 0,
  productMap: {},
  categories: [],
  category: '',
  query: '',
  searchIds: null,
  sort: 'auto',
  filters: { inStock: false, min: null, max: null },
  layout: 'grid',
  shopLimit: SHOP_PAGE_SIZE,
  cart: {},

  orders: [],
  orderFilter: '',
  justUpdatedOrderId: null,
  fresh: false,
  checkout: null,
  stats: null,
  users: [],
  logs: [],
  selectedLogs: new Set(),
  logFilter: { q: '', group: '', action: '' },
  productFilter: { group: '', category: '' }
};

export const isCustomer = () => state.user?.role === 'user';
export const isStaff = () => !isCustomer();
export const defaultView = () => (isCustomer() ? 'shop' : 'dashboard');
export const cartQty = id => state.cart[id] || 0;

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

export const storage = {
  get(key) {
    try { return JSON.parse(localStorage.getItem(key)); } catch { return null; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { }
  },
  remove(key) {
    try { localStorage.removeItem(key); } catch { }
  }
};

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
export const orderStatusText = (status, order) => (order?.cod && status === 'pending' ? 'Menunggu diproses' : STATUS[status][0]);
export const statusTag = (status, order) => `<span class="tag ${STATUS[status][1]}">${orderStatusText(status, order)}</span>`;

export function stockInfo(product) {
  const { stock } = product;
  const cls = stock === 0 ? 'out' : stock <= LOW_STOCK_LIMIT ? 'low' : '';
  const percent = Math.min(100, Math.round(stock / STOCK_BAR_FULL * 100));
  const label = stock === 0 ? 'Habis' : stock <= LOW_STOCK_LIMIT ? `Tinggal ${stock}` : `Stok ${stock}`;
  return `<div class="stock ${cls}"><span class="num">${label}</span><i><b style="width:${percent}%"></b></i></div>`;
}

export const PRODUCT_GROUPS = [
  { id: '',    label: 'Semua',        test: () => true },
  { id: 'low', label: 'Stok menipis', test: product => product.stock > 0 && product.stock <= LOW_STOCK_LIMIT },
  { id: 'out', label: 'Habis',        test: product => product.stock === 0 }
];

export const productGroupCount = id =>
  state.products.filter((PRODUCT_GROUPS.find(item => item.id === id) || PRODUCT_GROUPS[0]).test).length;

export function managedProducts() {
  const query = state.query.trim().toLowerCase();
  const { group, category } = state.productFilter;
  const inGroup = (PRODUCT_GROUPS.find(item => item.id === group) || PRODUCT_GROUPS[0]).test;
  return state.products.filter(product =>
    inGroup(product) &&
    (!category || product.category === category) &&
    (!query || product.name.toLowerCase().includes(query) || product.category.toLowerCase().includes(query))
  );
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
  try { data = await response.json(); } catch { }

  if (!response.ok) {
    const sessionExpired = response.status === 401 && !path.startsWith('/auth/');
    if (sessionExpired) hooks.onSessionExpired();
    throw createError(data.error || 'Terjadi kesalahan', { status: response.status, fields: data.fields });
  }
  return data;
}