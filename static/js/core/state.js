// TokoBiru - State aplikasi, penyimpanan lokal, & selector data
import {
  LOG_GROUPS,
  PAYMENT_LABEL,
  PRODUCT_GROUPS,
  ROLE_LABEL,
  SHOP_PAGE_SIZE,
  EWALLET_GROUP,
  isEwallet
} from './constants.js';
import { actionLabel, detailLabel } from './format.js';

export const state = {
  user: null,
  csrf: '',
  payInfo: '',
  dummyQris: false,
  ewalletOn: false,
  proofReader: false,
  proofRetentionDays: 0,
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

export const ewalletChoices = () => Object.fromEntries(Object.entries(PAYMENT_LABEL).filter(([code]) => isEwallet(code)));
export const paymentChoices = () => {
  const choices = Object.fromEntries(Object.entries(PAYMENT_LABEL).filter(([code]) =>
    !isEwallet(code) && (code !== 'qris' || state.dummyQris) && (code !== 'transfer' || state.payInfo)));
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

export {
  isEwallet
};
