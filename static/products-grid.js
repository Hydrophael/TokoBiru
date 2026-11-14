// TokoBiru - tabel Produk dengan Webix (admin dan master, layar lebar)
// Tidak ada edit harga/stok langsung di sel: server mengubah stok sebagai selisih (base_stock), dan itu hanya dijaga form modal.

import { $, $$, escapeHtml, formatRupiah, icon, managedProducts, miniHtml, state, stockInfo } from './core.js';
import { createGridController, gridHeight, sortHead } from './webix-core.js';

const ROW_HEIGHT = 64;
const HEADER_HEIGHT = 46;
const SLACK = 10;   // ruang tambahan agar isi tidak meluber 1-2px karena garis tepi

// Webix selalu menggambar jalur gulir vertikal (lebar 17px + kotak abu-abu di kepala) bila scrollY aktif, walau isinya muat.
// Jadi gulir hanya dinyalakan bila seluruh baris memang lebih tinggi dari sisa layar; bila layar mengecil, tabel dibangun ulang.
const allRowsHeight = () => HEADER_HEIGHT + state.products.length * ROW_HEIGHT;
let scrollable = true;
const DEFAULT_SORT = { by: 'name', dir: 'asc' };   // urutan dari server
const SORT_AS = { name: 'string', category: 'string', price: 'int', stock: 'int' };

// Halaman digambar ulang tiap simpan/hapus; urutan dan gulir dicatat agar tidak hilang
let saved = { ...DEFAULT_SORT, y: 0 };
let renderRows = null;   // productRows dari views.js, untuk tabel HTML

// Nama produk adalah tombol: satu klik membuka form ubah (target sentuh lebih besar daripada tombol kecil di kolom Aksi)
export const productNameHtml = product => {
  const description = String(product.description ?? '').replace(/\s+/g, ' ').trim().slice(0, 140);
  return `<div class="cell">${miniHtml(product)}<div class="prod-info">` +
    `<button type="button" class="prod-name" data-act="product-edit" data-id="${escapeHtml(product.id)}" title="Ubah ${escapeHtml(product.name)}">${escapeHtml(product.name)}</button>` +
    (description ? `<div class="muted small prod-desc" title="${escapeHtml(description)}">${escapeHtml(description)}</div>` : '') +
    `</div></div>`;
};

// "Ubah" tetap jelas; hapus dibuat tenang (ikon saja, merah saat disorot) supaya tidak bersaing dan tidak mudah terklik
export const productActionsHtml = product =>
  `<div class="acts end"><button type="button" class="btn sm" data-act="product-edit" data-id="${escapeHtml(product.id)}">${icon('edit', 14)} Ubah</button>` +
  `<button type="button" class="btn sm flat prod-del" data-act="product-del" data-id="${escapeHtml(product.id)}" aria-label="Hapus ${escapeHtml(product.name)}" title="Hapus produk">${icon('trash', 16)}</button></div>`;

export const productResetHtml = () => '<button type="button" class="btn sm" data-act="prod-reset">Hapus semua filter</button>';

export const productCountHtml = shown => {
  const total = state.products.length;
  return `<span class="log-count">${shown === total ? `${total} produk` : `Menampilkan <b>${shown}</b> dari ${total} produk`}</span>`;
};

const emptyHtml = () =>
  `<div class="log-empty-box"><b>Tidak ada produk yang cocok</b><span>Ubah kata kunci atau lepas filter yang aktif.</span>${productResetHtml()}</div>`;

let pendingScroll = 0;

function fitGrid(grid) {
  const host = $('#product-host');
  if (!scrollable && host && allRowsHeight() > gridHeight(host)) { controller.mount(); return; }
  grid.refresh();
  if (scrollable && pendingScroll > 0) {
    const y = pendingScroll;
    pendingScroll = 0;
    grid.scrollTo(0, y);
  }
}

const controller = createGridController({
  name: 'Produk',
  view: 'products',
  hostSelector: '#product-host',
  toolsSelector: '.prod-tools',
  // tabel setinggi isinya (minimal 3 baris supaya pesan "tidak ada yang cocok" punya ruang), bukan setinggi layar
  maxHeight: () => HEADER_HEIGHT + Math.max(managedProducts().length, 3) * ROW_HEIGHT + SLACK,
  hasData: () => state.products.length > 0,
  create: buildGrid,
  settle: () => applyProductFilter(),
  onFit: fitGrid
});

function buildGrid(host) {
  // stok habis diberi kelas supaya fotonya diredupkan; teks tetap terbaca penuh
  const rows = state.products.map(product => ({ ...product, $css: product.stock === 0 ? 'prod-out' : '' }));
  const startY = saved.y;   // event gulir saat tabel dibuat tidak boleh menimpanya
  scrollable = allRowsHeight() > gridHeight(host);

  const grid = window.webix.ui({
    container: host,
    view: 'datatable',
    css: 'tb-grid',
    hover: 'tb-hover',
    rowHeight: ROW_HEIGHT,
    headerRowHeight: HEADER_HEIGHT,
    scrollX: false,
    scrollY: scrollable,
    select: false,
    columns: [
      { id: 'name', header: [sortHead('Produk')], fillspace: true, minWidth: 260, sort: 'string', template: productNameHtml },
      { id: 'category', header: [sortHead('Kategori')], width: 170, sort: 'string', template: product => `<span class="tag">${escapeHtml(product.category)}</span>` },
      { id: 'price', header: [sortHead('Harga', 'tb-right tb-numhead')], width: 150, sort: 'int', css: 'tb-num tb-endalign', template: product => `<b class="num">${formatRupiah(product.price)}</b>` },
      { id: 'stock', header: [sortHead('Stok')], width: 220, sort: 'int', template: product => stockInfo(product) },
      { id: 'act', header: [{ text: 'Aksi', css: 'tb-right' }], width: 176, css: 'tb-actions', template: productActionsHtml }
    ],
    data: rows
  });

  if (saved.by !== DEFAULT_SORT.by || saved.dir !== DEFAULT_SORT.dir) grid.sort(saved.by, saved.dir, SORT_AS[saved.by] || 'string');
  else grid.markSorting(DEFAULT_SORT.by, DEFAULT_SORT.dir);

  grid.attachEvent('onAfterSort', (by, dir) => {
    if (typeof by === 'string' && SORT_AS[by]) { saved.by = by; saved.dir = dir === 'desc' ? 'desc' : 'asc'; }
  });
  grid.attachEvent('onAfterScroll', () => {
    const position = grid.getScrollState();
    if (position && Number.isFinite(position.y)) saved.y = position.y;
  });

  pendingScroll = startY;
  return grid;
}

export function applyProductFilter() {
  const filter = state.productFilter;
  const shown = managedProducts();
  const ids = new Set(shown.map(product => product.id));

  $$('[data-act="prod-group"]').forEach(chip => chip.setAttribute('aria-pressed', String(chip.dataset.group === filter.group)));
  const select = $('[data-prod-category]');
  if (select && select.value !== filter.category) select.value = filter.category;
  const search = $('[data-input="prod-search"]');
  if (search && search.value !== state.query) search.value = state.query;
  const clear = $('[data-act="prod-q-clear"]');
  if (clear) clear.hidden = !state.query;
  const status = $('#prod-status');
  if (status) status.innerHTML = productCountHtml(shown.length);

  if (controller.live()) {
    const grid = controller.grid;
    grid.filter(row => ids.has(row.id));
    grid.refresh();
    if (shown.length) grid.hideOverlay(); else grid.showOverlay(emptyHtml());
    controller.refit();
  } else {
    const body = $('#prows');
    if (body && renderRows) body.innerHTML = renderRows();
  }
}

export function mountProductGrid(rows) {
  renderRows = rows;
  if (state.fresh) saved = { ...DEFAULT_SORT, y: 0 };
  return controller.mount();
}