// TokoBiru - Halaman ringkasan/dashboard admin & statistik penjualan
import { STATUS } from '../core/constants.js';
import { state } from '../core/state.js';
import { $, escapeHtml, formatDate, formatRupiah, icon, miniHtml, statusTag, stockInfo } from '../core/format.js';
import { api } from '../api/client.js';
import { show } from '../core/router.js';
import { applyProductFilter } from '../components/products-grid.js';

function factHtml({ value, label, note = '', tone = '', wide = false, go = null }) {
  const cls = `fact${tone ? ' ' + tone : ''}${wide ? ' wide' : ''}`;
  const inner = `<b class="num">${value}</b><span>${label}${note ? `<small>${note}</small>` : ''}</span>`;
  if (!go) return `<div class="${cls}">${inner}</div>`;
  const attrs = Object.entries(go).map(([key, val]) => ` data-${key}="${escapeHtml(val)}"`).join('');
  return `<button type="button" class="${cls}" data-act="dash-go"${attrs}>${inner}<i class="go-arrow" aria-hidden="true">${icon('right', 16)}</i></button>`;
}

function dashboardFactsHtml(stats) {
  const today = stats.today || { orders: 0, revenue: 0 };
  const pending = stats.orders.pending;
  const stockTotal = stats.low_stock_total ?? stats.low_stock.length;
  const outCount = stats.out_of_stock_total ?? stats.low_stock.filter(product => product.stock === 0).length;
  const lowCount = stockTotal - outCount;
  const totals = state.user.role === 'master' ? stats.users : null;
  const userTotal = totals ? totals.user + totals.admin + totals.master : 0;

  return `<div class="facts">
      ${factHtml({ value: today.orders, label: 'Pesanan hari ini', tone: today.orders ? '' : 'zero' })}
      ${factHtml({ value: formatRupiah(today.revenue), label: 'Pendapatan hari ini', tone: today.revenue ? '' : 'zero' })}
      ${factHtml({ value: pending, label: 'Menunggu pembayaran', tone: pending ? 'attn' : 'zero',
        go: pending ? { view: 'orders', status: 'pending' } : null })}
      ${factHtml({ value: stockTotal, label: 'Stok menipis', note: outCount ? `${outCount} sudah habis` : '', tone: stockTotal ? 'attn' : 'zero',
        go: stockTotal ? { view: 'products', group: lowCount ? 'low' : 'out' } : null })}
      ${factHtml({ value: stats.products, label: 'Produk di katalog', wide: !totals, go: { view: 'products' } })}
      ${totals ? factHtml({ value: userTotal, label: 'Pengguna', note: `${totals.user} pelanggan, ${totals.admin} admin, ${totals.master} master`, go: { view: 'users' } }) : ''}
    </div>`;
}

function revenueHeroHtml(stats) {
  const paidOrders = stats.paid_orders ?? (stats.orders.paid + stats.orders.shipped + stats.orders.completed);
  const average = paidOrders ? Math.round(stats.revenue / paidOrders) : 0;
  return `<div class="revenue">
      <div><span>Total pendapatan dari pesanan yang sudah dibayar</span><strong class="num">${formatRupiah(stats.revenue)}</strong></div>
      <div class="hstats">
        <div class="hstat"><b class="num">${paidOrders}</b><span>Pesanan dibayar</span></div>
        <div class="hstat"><b class="num">${formatRupiah(average)}</b><span>Rata-rata per pesanan</span></div>
        <div class="hstat"><b class="num">${stats.orders.total}</b><span>Semua pesanan</span></div>
      </div>
    </div>`;
}

function orderStatusBarsHtml(stats) {
  const keys = Object.keys(STATUS);
  const max = Math.max(1, ...keys.map(key => stats.orders[key]));
  return keys.map(key => {
    const count = stats.orders[key];
    const width = Math.round(count / max * 100);
    const inner = `<span>${STATUS[key][0]}</span><span class="track"><span class="fill" style="width:${width}%"></span></span><span class="right num">${count}</span>`;
    return count
      ? `<button type="button" class="bar s-${key}" data-act="dash-go" data-view="orders" data-status="${key}" aria-label="${STATUS[key][0]}: ${count} pesanan, buka daftar">${inner}</button>`
      : `<div class="bar s-${key} zero">${inner}</div>`;
  }).join('');
}

const recentOrdersHtml = stats => stats.recent.length
  ? stats.recent.map(order => `<div class="line"><span class="l-main"><b class="num">${escapeHtml(order.code)}</b><span class="muted small">${escapeHtml(order.username)}${order.created_at ? ', ' + escapeHtml(formatDate(order.created_at)) : ''}</span></span><span class="l-end">${statusTag(order.status, order)} <b class="num">${formatRupiah(order.total)}</b></span></div>`).join('')
  : '<p class="muted">Belum ada pesanan masuk.</p>';

const lowStockHtml = stats => stats.low_stock.length
  ? `<div class="restock">${stats.low_stock.map(product => `<div class="line"><span class="cell">${miniHtml(product)}<span><b>${escapeHtml(product.name)}</b><br><span class="muted small">${escapeHtml(product.category)}</span></span></span>${stockInfo(product)}</div>`).join('')}</div>`
  : `<p class="all-good">${icon('check', 20)} Semua stok masih aman.</p>`;

// ---------- Laporan penjualan (data dari /api/stats/sales) ----------
const SALES_PRESETS = [[7, '7 hari'], [30, '30 hari'], [90, '90 hari'], [365, '12 bulan']];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
const sales = { from: '', to: '', group: 'day', asked: 'day', data: null, error: '', loading: false, token: 0 };
const countText = value => Number(value || 0).toLocaleString('id-ID');

// Tanggal hari ini menurut WIB (UTC+7), format TTTT-BB-HH
const todayWib = () => new Date(Date.now() + 7 * 3600 * 1000).toISOString().slice(0, 10);
function shiftDay(iso, days) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

function salesLabel(key, group) {
  const [y, m, d] = key.split('-');
  return group === 'month' ? `${MONTHS[Number(m) - 1]} ${y}` : `${Number(d)} ${MONTHS[Number(m) - 1]}`;
}

function salesChartHtml(data) {
  const series = data.series;
  const max = Math.max(1, ...series.map(point => point.revenue));
  const cols = series.map(point => {
    const label = salesLabel(point.key, data.group);
    const height = Math.round(point.revenue / max * 100);
    return `<div class="sr-col" title="${escapeHtml(`${label}: ${formatRupiah(point.revenue)}, ${point.orders} pesanan`)}"><i class="${point.revenue ? 'has' : ''}" style="height:${height}%"></i></div>`;
  }).join('');
  const first = salesLabel(series[0].key, data.group);
  const last = salesLabel(series[series.length - 1].key, data.group);
  const aria = `Grafik omzet per ${data.group === 'month' ? 'bulan' : 'hari'}, ${first} sampai ${last}, tertinggi ${formatRupiah(max)}`;
  return `<div class="sr-chart${series.length > 45 ? ' dense' : ''}" role="img" aria-label="${escapeHtml(aria)}">${cols}</div>
    <div class="sr-axis"><span>${escapeHtml(first)}</span><span>Tertinggi ${formatRupiah(max)}</span><span>${escapeHtml(last)}</span></div>`;
}

function salesTopHtml(top) {
  if (!top.length) return '<p class="muted">Belum ada produk terjual.</p>';
  return top.map((item, index) => `<div class="line"><span class="l-main"><b>${index + 1}. ${escapeHtml(item.name)}</b><span class="muted small">${countText(item.qty)} terjual</span></span><span class="l-end num">${formatRupiah(item.revenue)}</span></div>`).join('');
}

function salesResultHtml() {
  if (sales.error) return `<p class="sr-err" role="alert">${escapeHtml(sales.error)}</p>`;
  const data = sales.data;
  if (!data) return '<p class="muted">Memuat laporan...</p>';
  const sum = data.summary;
  const switched = sales.asked === 'day' && data.group === 'month'
    ? '<p class="muted small sr-note">Rentang cukup panjang, jadi grafik ditampilkan per bulan.</p>' : '';
  const stats = [
    [formatRupiah(sum.revenue), 'Omzet'],
    [countText(sum.orders), 'Pesanan dibayar'],
    [countText(sum.items), 'Barang terjual'],
    [formatRupiah(sum.average), 'Rata-rata per pesanan'],
    [formatRupiah(sum.shipping), 'Ongkir (tidak dihitung)']
  ].map(([value, label]) => `<div class="sr-stat"><b class="num">${value}</b><span>${label}</span></div>`).join('');
  const body = sum.orders
    ? `<div class="sr-cols"><div><h4>Omzet per ${data.group === 'month' ? 'bulan' : 'hari'}</h4>${salesChartHtml(data)}</div>
        <div><h4>Produk terlaris</h4>${salesTopHtml(data.top_products)}</div></div>`
    : '<p class="muted">Belum ada pesanan dibayar pada rentang ini.</p>';
  return `${switched}<div class="sr-stats">${stats}</div>${body}`;
}

function salesPanelHtml() {
  const presets = SALES_PRESETS.map(([days, label]) =>
    `<button type="button" class="btn sm" data-act="sales-preset" data-days="${days}">${label}</button>`).join('');
  return `<div class="panel sr${sales.loading ? ' loading' : ''}" id="sales-panel">
    <div class="panel-head"><h3>Laporan penjualan</h3></div>
    <p class="muted small" style="margin:0 0 14px">Omzet adalah nilai barang dari pesanan yang sudah dibayar, tanpa ongkir. Tanggal mengikuti tanggal bayar (WIB).</p>
    <div class="sr-bar">
      <div class="field"><label for="sales-from">Dari tanggal</label><input class="input" type="date" id="sales-from" value="${escapeHtml(sales.from)}"></div>
      <div class="field"><label for="sales-to">Sampai tanggal</label><input class="input" type="date" id="sales-to" value="${escapeHtml(sales.to)}"></div>
      <div class="field"><label for="sales-group">Grafik per</label><select class="select" id="sales-group">
        <option value="day"${sales.group === 'day' ? ' selected' : ''}>Hari</option>
        <option value="month"${sales.group === 'month' ? ' selected' : ''}>Bulan</option></select></div>
      <button type="button" class="btn primary" data-act="sales-apply"${sales.loading ? ' disabled' : ''}>Tampilkan</button>
      <div class="sr-presets">${presets}</div>
    </div>
    <div class="sr-result">${salesResultHtml()}</div>
  </div>`;
}

function drawSales() {
  const panel = $('#sales-panel');
  if (panel) panel.outerHTML = salesPanelHtml();   // bila halaman sudah berganti, panel tidak ada dan tidak terjadi apa-apa
}

async function loadSales() {
  const token = ++sales.token;
  const query = new URLSearchParams({ group: sales.group });
  if (sales.from) query.set('from', sales.from);
  if (sales.to) query.set('to', sales.to);
  sales.asked = sales.group;
  sales.loading = true;
  sales.error = '';
  drawSales();
  try {
    const data = await api('/stats/sales?' + query);
    if (token !== sales.token) return;   // ada permintaan yang lebih baru
    Object.assign(sales, { data, from: data.from, to: data.to, group: data.group });
  } catch (err) {
    if (token !== sales.token || err.status === 401) return;
    sales.error = err.message || 'Laporan belum bisa dimuat.';
  }
  sales.loading = false;
  drawSales();
}

function salesApply() {
  const from = $('#sales-from')?.value || '';
  const to = $('#sales-to')?.value || '';
  const group = $('#sales-group')?.value === 'month' ? 'month' : 'day';
  if (from && to && from > to) {
    sales.error = 'Tanggal awal tidak boleh setelah tanggal akhir.';
    drawSales();
    return;
  }
  Object.assign(sales, { from, to, group });
  return loadSales();
}

function salesPreset(el) {
  const days = Number(el.dataset.days) || 30;
  const to = todayWib();
  Object.assign(sales, { from: shiftDay(to, -(days - 1)), to, group: days > 92 ? 'month' : 'day' });
  return loadSales();
}

function dashboardView() {
  const stats = state.stats;
  const restockTotal = stats.low_stock_total ?? stats.low_stock.length;
  const restockBadge = restockTotal ? `<span class="tag warn">${restockTotal} produk</span>` : '';
  setTimeout(loadSales, 0);   // HTML ini dipasang ke halaman setelah fungsi selesai, baru laporan dimuat
  const updated = new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
  return `
  <div class="page-head"><div><h2>Ringkasan</h2><p class="muted">Penjualan, pesanan, dan stok. Angka &ldquo;hari ini&rdquo; dihitung sejak pukul 00.00 WIB.</p></div>
    <div class="head-act"><span class="updated">Diperbarui ${updated}</span><button class="btn" data-act="reload">Perbarui data</button></div></div>
  <div class="lead">
    ${revenueHeroHtml(stats)}
    ${dashboardFactsHtml(stats)}
  </div>
  <div class="two">
    <div class="panel"><div class="panel-head"><h3>Pesanan terbaru</h3>
        <button type="button" class="btn sm flat" data-act="nav" data-view="orders">Lihat semua ${icon('right', 14)}</button></div>
      ${recentOrdersHtml(stats)}
    </div>
    <div class="panel col"><div class="panel-head"><h3>Pesanan per status</h3></div>
      <div class="bars">${orderStatusBarsHtml(stats)}</div>
    </div>
  </div>
  ${salesPanelHtml()}
  <div class="panel"><div class="panel-head"><h3>Perlu restok</h3>${restockBadge}
      <button type="button" class="btn sm" data-act="nav" data-view="products">Atur stok produk</button></div>
    ${lowStockHtml(stats)}
    ${restockTotal > stats.low_stock.length ? `<p class="muted small" style="margin-top:12px">Menampilkan ${stats.low_stock.length} produk dengan stok paling sedikit dari ${restockTotal}.</p>` : ''}
  </div>`;
}


async function dashboardGo(el) {
  const { view, status, group } = el.dataset;
  if (status !== undefined) state.orderFilter = status;
  await show(view);
  if (group) { state.productFilter.group = group; applyProductFilter(); }
}

export const dashboardActions = {
  'dash-go': dashboardGo,
  'sales-apply': salesApply,
  'sales-preset': salesPreset
};

export {
  dashboardView
};