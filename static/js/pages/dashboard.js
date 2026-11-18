// TokoBiru - Halaman ringkasan/dashboard admin & statistik penjualan
import { STATUS } from '../core/constants.js';
import { state } from '../core/state.js';
import { escapeHtml, formatDate, formatRupiah, icon, miniHtml, statusTag, stockInfo } from '../core/format.js';
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

function dashboardView() {
  const stats = state.stats;
  const restockTotal = stats.low_stock_total ?? stats.low_stock.length;
  const restockBadge = restockTotal ? `<span class="tag warn">${restockTotal} produk</span>` : '';
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
  'dash-go': dashboardGo
};

export {
  dashboardView
};