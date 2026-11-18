// TokoBiru - Konstanta domain, label, navigasi, & ikon SVG
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

export const ACTION_LABEL = {
  register: 'Daftar Akun', login: 'Login', login_gagal: 'Login Gagal', logout: 'Logout',
  password_ubah: 'Password Diubah', password_gagal: 'Ganti Password Gagal', reset_minta: 'Minta Reset Password',
  password_reset: 'Password Direset', reset_gagal: 'Reset Gagal',
  produk_tambah: 'Produk Ditambah', produk_ubah: 'Produk Diubah', produk_hapus: 'Produk Dihapus',
  pesanan_buat: 'Pesanan Dibuat', pesanan_status: 'Status Pesanan Berubah', pesanan_kedaluwarsa: 'Pesanan Kedaluwarsa',
  pesanan_hapus: 'Pesanan Dihapus', pesanan_bersihkan: 'Riwayat Dibersihkan',
  user_buat: 'Pengguna Dibuat', user_ubah: 'Pengguna Diubah', user_hapus: 'Pengguna Dihapus',
  profil_ubah: 'Profil Diubah', alamat_ubah: 'Alamat Diubah',
  akses_ditolak: 'Akses Ditolak', log_hapus: 'Log Dihapus', pesanan_minta_batal: 'Minta Batal Pesanan',
  pesanan_bayar_gagal: 'Pembayaran E-Wallet Gagal', pesanan_gagal_gateway: 'Pesanan Gagal Dibuat',
  push_aktif: 'Notifikasi Diaktifkan', bukti_transfer: 'Bukti Transfer Diunggah', bukti_dibaca: 'Bukti Transfer Dibaca',
  webhook_diabaikan: 'Webhook Diabaikan',
  pembayaran_tidak_cocok: 'Nominal Bayar Tidak Cocok', pembayaran_terlambat: 'Dibayar Setelah Batal',
  pembayaran_tak_dikenal: 'Pembayaran Tak Dikenal', pembayaran_masalah_selesai: 'Masalah Bayar Selesai'
};

export const DETAIL_KEY = { role: 'peran', active: 'status' };
export const DETAIL_VALUE = { user: 'Pelanggan', admin: 'Admin', master: 'Master', True: 'Aktif', False: 'Nonaktif' };

export const LOG_GROUPS = [
  { id: '',        label: 'Semua',            test: () => true },
  { id: 'alert',   label: 'Perlu dicek',      test: action => /gagal|ditolak|^pembayaran_(tidak_cocok|terlambat|tak_dikenal)$/.test(action) },
  { id: 'auth',    label: 'Login & password', test: action => /^(register|login|logout|password_|reset_|profil_|alamat_)/.test(action) },
  { id: 'order',   label: 'Pesanan',          test: action => action.startsWith('pesanan_') || action.startsWith('pembayaran_') || action.startsWith('bukti_') },
  { id: 'product', label: 'Produk',           test: action => action.startsWith('produk_') },
  { id: 'user',    label: 'Pengguna',         test: action => action.startsWith('user_') }
];

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

export const EWALLET_BRAND = {
  ewallet_dana:      { logo: '/static/icons/pay/dana.png' },
  ewallet_shopeepay: { logo: '/static/icons/pay/shopeepay.png' },
  ewallet_ovo:       { logo: '/static/icons/pay/ovo.png' }
};

export const EWALLET_GROUP = 'ewallet';

export const LOW_STOCK_LIMIT = 5;
export const STOCK_BAR_FULL = 40;
export const MAX_TOASTS = 2;
export const SHOP_PAGE_SIZE = 12;

export const EMOJI_RULES = [
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
export const DEFAULT_EMOJI = '🛒';

export const ICONS = {
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

export const MIN_SERVER_SEARCH = 2;
export const SEARCH_DEBOUNCE_MS = 200;
export const LOG_SEARCH_DEBOUNCE_MS = 150;
export const CHECKOUT_KEY_TTL_MS = 10 * 60 * 1000;
export const QRIS_POLL_MS = 1500;

export const PHONE_RE = /^\+?\d{8,15}$/;
export const PHONE_ERROR = 'Isi nomor HP yang benar, contoh 081234567890';
export const RECIPIENT_ERROR = 'Nama penerima minimal 2 karakter';
export const CODE_REJECTED = 'Kode salah atau sudah kedaluwarsa. Periksa lagi, atau kirim ulang kode.';

export const emptyFilters = () => ({ inStock: false, min: null, max: null });
export const emptyLogFilter = () => ({ q: '', group: '', action: '' });
export const emptyProductFilter = () => ({ group: '', category: '' });

export const PRODUCT_GROUPS = [
  ['low', 'Stok menipis', ''],
  ['out', 'Stok habis', '']
];

export const isEwallet = method => Boolean(EWALLET_BRAND[method]);
