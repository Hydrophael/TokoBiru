// TokoBiru - Halaman katalog belanja, filter, pencarian, & detail produk
import { MIN_SERVER_SEARCH, SHOP_PAGE_SIZE, STORAGE_KEYS, emptyFilters } from '../core/constants.js';
import { cartQty, state, storage } from '../core/state.js';
import {
  $,
  $$,
  descriptionHtml,
  emptyState,
  escapeHtml,
  formatRupiah,
  hashString,
  icon,
  priceHtml,
  productImage,
  stockFlag,
  stockInfo,
  stockNote,
  tileVisualHtml
} from '../core/format.js';
import { api } from '../api/client.js';
import { closeModal, flyToCart, openModal, withTransition } from '../components/ui.js';
import { cardFoot, setCartQty } from '../components/cart.js';
import { firstName } from '../components/shell.js';

let searchSeq = 0;

export const truncationNotice = () => state.productsTotal > state.products.length
  ? `<p class="muted small" role="status">Katalog sangat besar: hanya ${state.products.length} dari ${state.productsTotal} produk yang dimuat.</p>`
  : '';

const hasPriceFilter = () => state.filters.min !== null || state.filters.max !== null;
export const activeFilterCount = () => (hasPriceFilter() ? 1 : 0) + (state.filters.inStock ? 1 : 0);
export const hasAnyFilter = () => Boolean(state.category || state.query.trim() || activeFilterCount());

function matchingProducts(skipCategory = false) {
  const query = state.query.trim().toLowerCase();
  const { inStock, min, max } = state.filters;
  const rank = query && state.searchIds ? new Map(state.searchIds.map((id, index) => [id, index])) : null;
  const matchesQuery = p => rank ? rank.has(p.id) : (!query || p.name.toLowerCase().includes(query));

  const list = state.products.filter(p =>
    (skipCategory || !state.category || p.category === state.category) &&
    matchesQuery(p) &&
    (!inStock || p.stock > 0) &&
    (min === null || p.price >= min) &&
    (max === null || p.price <= max));
  return { list, rank };
}

function filteredProducts() {
  const { list, rank } = matchingProducts();
  const sort = state.sort;

  const compare = (a, b) => {
    if (sort === 'low') return a.price - b.price;
    if (sort === 'high') return b.price - a.price;
    if (sort === 'auto' && rank) return rank.get(a.id) - rank.get(b.id);
    return a.name.localeCompare(b.name, 'id');
  };

  return list.sort((a, b) => (a.stock === 0) - (b.stock === 0) || compare(a, b));
}

const countLabel = total =>
  total > SHOP_PAGE_SIZE ? `${Math.min(state.shopLimit, total)} dari ${total} produk` : `${total} produk`;

export function aisleHtml() {
  const aisleNumber = state.categories.indexOf(state.category) + 1;
  return `<span class="aisle-sign"><span class="a-no">${aisleNumber ? 'Lorong ' + aisleNumber : 'Seluruh toko'}</span><b>${state.category ? escapeHtml(state.category) : 'Semua kategori'}</b></span>`;
}

function categoryCounts() {
  const counts = {};
  matchingProducts(true).list.forEach(p => { counts[p.category] = (counts[p.category] || 0) + 1; });
  return counts;
}

export function categoryRailHtml() {
  const counts = categoryCounts();
  const total = Object.values(counts).reduce((sum, n) => sum + n, 0);
  const chip = (value, label, count) =>
    `<button type="button" class="${state.category === value ? 'active' : ''}${count ? '' : ' zero'}" data-act="cat" data-cat="${escapeHtml(value)}" aria-pressed="${state.category === value}">${escapeHtml(label)}<span class="n num">${count}</span></button>`;
  return chip('', 'Semua', total) + state.categories.map(category => chip(category, category, counts[category] || 0)).join('');
}

export function updateRailEdges() {
  const rail = $('#rail');
  const wrap = $('#rail-wrap');
  if (!rail || !wrap) return;
  const maxScroll = rail.scrollWidth - rail.clientWidth;
  wrap.classList.toggle('can-prev', rail.scrollLeft > 4);
  wrap.classList.toggle('can-next', rail.scrollLeft < maxScroll - 4);
}

export function scrollRail(direction) {
  const rail = $('#rail');
  if (rail) rail.scrollBy({ left: direction * rail.clientWidth * 0.7, behavior: 'smooth' });
}

addEventListener('resize', updateRailEdges);
if (document.fonts && document.fonts.ready) document.fonts.ready.then(updateRailEdges);

function chipsHtml() {
  const chips = [];
  const query = state.query.trim();
  const { min, max, inStock } = state.filters;

  if (query) chips.push(['q', `Cari “${query}”`]);
  if (hasPriceFilter()) {
    const label = min !== null && max !== null ? `${formatRupiah(min)} – ${formatRupiah(max)}`
      : min !== null ? `Mulai ${formatRupiah(min)}` : `Sampai ${formatRupiah(max)}`;
    chips.push(['price', label]);
  }
  if (inStock) chips.push(['stock', 'Stok tersedia']);
  if (!chips.length) return '';

  const items = chips.map(([key, label]) =>
    `<button type="button" class="chip" data-act="rm-filter" data-f="${key}" aria-label="Hapus filter ${escapeHtml(label)}"><span>${escapeHtml(label)}</span>${icon('x', 14)}</button>`
  ).join('');
  const clearAll = chips.length + (state.category ? 1 : 0) > 1
    ? '<button type="button" class="chip clear-all" data-act="clear-all">Hapus semua</button>' : '';
  return items + clearAll;
}

const sortOptionHtml = (value, label) =>
  `<option value="${value}"${state.sort === value ? ' selected' : ''}>${label}</option>`;

function sortOptionsHtml() {
  const searching = Boolean(state.query.trim());
  return sortOptionHtml('auto', searching ? 'Paling relevan' : 'Nama A–Z') +
    (searching ? sortOptionHtml('name', 'Nama A–Z') : '') +
    sortOptionHtml('low', 'Harga terendah') + sortOptionHtml('high', 'Harga tertinggi');
}

function syncSortOptions() {
  const select = $('[data-sort]');
  if (!select) return;
  const searching = Boolean(state.query.trim());
  if (select.dataset.q === String(searching)) return;
  if (!searching && state.sort === 'name') state.sort = 'auto';
  select.dataset.q = String(searching);
  select.innerHTML = sortOptionsHtml();
}

function productCardHtml(product, index) {
  const description = String(product.description ?? '').trim();
  return `
    <article class="label${product.stock === 0 ? ' soldout' : ''}" data-card="${product.id}" style="--i:${Math.min(index, 8)}">
      <div class="tile p${hashString(product.id) % 4}${productImage(product) ? ' has-photo' : ''}" data-act="detail" data-id="${product.id}"><span class="cat tag">${escapeHtml(product.category)}</span>${stockFlag(product)}${tileVisualHtml(product)}</div>
      <div class="lbody"><h3><button type="button" class="plink" data-act="detail" data-id="${product.id}" title="${escapeHtml(product.name)}">${escapeHtml(product.name)}</button></h3>${description ? `<p class="ldesc" data-act="detail" data-id="${product.id}">${escapeHtml(description)}</p>` : ''}${stockNote(product)}</div>
      ${cardFoot(product)}
    </article>`;
}

function moreHtml(total) {
  if (total <= SHOP_PAGE_SIZE) return '';
  const shown = Math.min(state.shopLimit, total);
  if (shown >= total) return `<p class="muted small num">Semua ${total} produk sudah tampil</p>`;

  const next = Math.min(SHOP_PAGE_SIZE, total - shown);
  return `<p class="muted small num">Menampilkan ${shown} dari ${total} produk</p>
    <div class="more-bar" aria-hidden="true"><i style="width:${Math.round(shown / total * 100)}%"></i></div>
    <button type="button" class="btn" data-act="more">Tampilkan ${next} lagi</button>`;
}

function productCards(firstRender = false, list = filteredProducts()) {
  if (!state.products.length) return emptyState('Katalog masih kosong', 'Toko belum menambahkan produk. Silakan cek lagi nanti.');
  if (!list.length) {
    return emptyState('Tidak ada produk yang cocok', 'Coba kata kunci lain, ubah rentang harga, atau pilih kategori Semua.',
      hasAnyFilter() ? '<button class="btn primary" data-act="clear-all">Hapus semua filter</button>' : '');
  }
  const layout = state.layout === 'rows' ? ' rows' : '';
  const photos = list.some(product => productImage(product)) ? ' photos' : '';
  return `<div class="shelf${firstRender ? ' stagger' : ''}${layout}${photos}">${list.slice(0, state.shopLimit).map(productCardHtml).join('')}</div>
    <div class="more" id="more">${moreHtml(list.length)}</div>`;
}

let moreObserver = null;

export function watchMore() {
  if (moreObserver) moreObserver.disconnect();
  const sentinel = $('#more');
  if (!sentinel || typeof IntersectionObserver === 'undefined') return;

  moreObserver = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) appendCards();
  }, { rootMargin: '0px 0px 480px 0px' });
  moreObserver.observe(sentinel);
}

export function appendCards() {
  const shelf = $('#plist .shelf');
  if (!shelf) return;

  const list = filteredProducts();
  const from = shelf.children.length;
  if (from >= list.length) return;

  state.shopLimit = from + SHOP_PAGE_SIZE;
  shelf.insertAdjacentHTML('beforeend', list.slice(from, state.shopLimit).map(productCardHtml).join(''));
  $('#more').innerHTML = moreHtml(list.length);
  const counter = $('#rcount');
  if (counter) counter.textContent = countLabel(list.length);
  watchMore();
}

function syncShopControls(total) {
  const setHtml = (selector, html) => { const el = $(selector); if (el) el.innerHTML = html; };

  const counter = $('#rcount');
  if (counter) counter.textContent = countLabel(total);
  setHtml('#rail', categoryRailHtml());
  setHtml('#aisle', aisleHtml());
  setHtml('#chips', chipsHtml());

  const clearButton = $('.search .clear');
  if (clearButton) clearButton.hidden = !state.query;

  const filterButton = $('.filter-btn');
  if (filterButton) {
    const count = activeFilterCount();
    const badge = $('.fcount', filterButton);
    filterButton.classList.toggle('on', count > 0);
    badge.hidden = !count;
    badge.textContent = count;
  }
  syncSortOptions();
  updateRailEdges();
}

export function renderList() {
  state.shopLimit = SHOP_PAGE_SIZE;
  const list = filteredProducts();
  $('#plist').innerHTML = productCards(false, list);
  syncShopControls(list.length);
  watchMore();
}

export function afterShopRender() {
  watchMore();
  updateRailEdges();
}

export function filterModal() {
  const { inStock, min, max } = state.filters;
  const prices = state.products.map(p => p.price);
  const range = prices.length
    ? `Harga produk saat ini berkisar ${formatRupiah(Math.min(...prices))} sampai ${formatRupiah(Math.max(...prices))}.`
    : '';

  openModal(`<h3>Filter produk</h3>
    <p class="sub">${range}</p>
    <div class="row2">
      <div class="field"><label>Harga terendah (Rp)</label><input class="input num" id="f-min" inputmode="numeric" autocomplete="off" placeholder="0" value="${min ?? ''}"></div>
      <div class="field"><label>Harga tertinggi (Rp)</label><input class="input num" id="f-max" inputmode="numeric" autocomplete="off" placeholder="Tanpa batas" value="${max ?? ''}"></div>
    </div>
    <label class="showpw"><input type="checkbox" id="f-stock"${inStock ? ' checked' : ''}> Sembunyikan produk yang habis</label>
    <div class="foot"><button class="btn" data-act="reset-filters">Atur ulang</button><button class="btn primary" data-act="apply-filter">Tampilkan hasil</button></div>`);
}

const layoutButton = (layout, label, iconName) =>
  `<button type="button" data-act="layout" data-layout="${layout}" aria-pressed="${state.layout === layout}" aria-label="${label}" title="${label}">${icon(iconName, 18)}</button>`;

const railArrow = (side, label) =>
  `<button type="button" class="rail-arrow ${side}" data-act="rail-${side === 'prev' ? 'prev' : 'next'}" aria-label="${label}" tabindex="-1">${icon(side === 'prev' ? 'left' : 'right', 18)}</button>`;

function shopView() {
  const list = filteredProducts();
  const filterCount = activeFilterCount();
  const searching = Boolean(state.query.trim());

  return `
  <section class="welcome" aria-label="Selamat datang">
    <div class="w-text"><h2>Halo, ${escapeHtml(firstName(state.user.name))}!</h2><p>Mau belanja apa hari ini? Pilih barang, masukkan ke keranjang, lalu buat pesanan.</p></div>
    <div class="w-side">
      <div class="w-facts"><span class="w-fact"><b class="num">${state.products.length}</b>produk</span><span class="w-fact"><b class="num">${state.categories.length}</b>kategori</span></div>
      <button type="button" class="btn yellow" id="w-cart" data-act="open-cart" hidden></button>
    </div>
  </section>
  <div class="tools" id="tools">
    <div class="tools-row">
      <label class="search">${icon('search')}<input data-input="shop-search" placeholder="Cari nama produk" maxlength="50" aria-label="Cari produk" autocomplete="off" value="${escapeHtml(state.query)}"><button type="button" class="clear" data-act="clear-search" aria-label="Hapus pencarian"${searching ? '' : ' hidden'}>${icon('x', 16)}</button></label>
      <button type="button" class="btn filter-btn${filterCount ? ' on' : ''}" data-act="open-filter" aria-label="Filter harga dan stok">${icon('sliders')}<span class="hide-m">Filter</span><b class="fcount num"${filterCount ? '' : ' hidden'}>${filterCount}</b></button>
    </div>
    <div class="rail-wrap" id="rail-wrap">
      ${railArrow('prev', 'Geser kategori ke kiri')}
      <div class="rail" id="rail">${categoryRailHtml()}</div>
      ${railArrow('next', 'Geser kategori ke kanan')}
    </div>
  </div>
  <div class="results-head">
    <div class="aisle" id="aisle" aria-hidden="true">${aisleHtml()}</div>
    <span class="muted small rcount" id="rcount" aria-live="polite">${countLabel(list.length)}</span>
    <div class="rh-tools">
      <label class="sortsel"><span class="hide-m">Urutkan</span><select class="select sm" data-sort data-q="${searching}" aria-label="Urutkan produk">${sortOptionsHtml()}</select></label>
      <div class="seg" role="group" aria-label="Tampilan daftar">${layoutButton('grid', 'Tampilan kartu', 'grid')}${layoutButton('rows', 'Tampilan daftar', 'list')}</div>
    </div>
  </div>
  <div class="chips" id="chips">${chipsHtml()}</div>
  ${truncationNotice()}
  <div id="plist">${productCards(state.fresh, list)}</div>
  <button type="button" class="to-top" data-act="to-top" aria-label="Kembali ke atas" hidden>${icon('up', 20)}</button>`;
}


function openProductDetail(el) {
  const product = state.productMap[el.dataset.id];
  if (!product) return;
  const inCart = cartQty(product.id);

  openModal(`<div class="dtile p${hashString(product.id) % 4}${productImage(product) ? ' has-photo' : ''}"><span class="tag">${escapeHtml(product.category)}</span>${tileVisualHtml(product)}</div>
      <h3>${escapeHtml(product.name)}</h3>
      <div class="ddesc">${descriptionHtml(product.description)}</div>
      <div class="dmeta">${priceHtml(product.price)}${stockInfo(product)}</div>
      ${inCart ? `<p class="muted small" style="margin-bottom:10px">Sudah ${inCart} di keranjang Anda.</p>` : ''}
      <div class="foot"><button class="btn" data-act="close-modal">Tutup</button>
      ${product.stock === 0 ? '' : `<button class="btn primary" data-act="detail-add" data-id="${product.id}">${icon('plus', 15)} Tambah ke keranjang</button>`}</div>`);
}

function addFromProductDetail(el) {
  const id = el.dataset.id;
  const product = state.productMap[id];
  const current = cartQty(id);

  if (product && current < product.stock) flyToCart($('.dtile .ini, .dtile .photo'));
  closeModal();
  setCartQty(id, current + 1);
}

function keepResultsInView() {
  const head = $('.results-head');
  if (!head) return;
  const top = head.getBoundingClientRect().top + scrollY - ($('#tools')?.offsetHeight || 0) - 80;
  if (scrollY > top) window.scrollTo({ top: Math.max(0, top), behavior: 'auto' });
}

const rerenderShop = () => withTransition(() => { renderList(); keepResultsInView(); });

function filterByCategory(el) {
  state.category = el.dataset.cat;
  withTransition(() => {
    renderList();
    keepResultsInView();

    const active = $('#rail .active');
    if (active) {
      active.focus({ preventScroll: true });
      active.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
    }
  });
}

function resetShopQuery() {
  
  searchSeq++;
  state.query = '';
  state.searchIds = null;
  const input = $('[data-input=shop-search]');
  if (input) input.value = '';
}

function clearSearch() {
  resetShopQuery();
  $('[data-input=shop-search]')?.focus();
  rerenderShop();
}

function clearAllFilters() {
  resetShopQuery();
  state.category = '';
  state.filters = emptyFilters();
  rerenderShop();
}

function removeFilter(el) {
  const kind = el.dataset.f;
  if (kind === 'q') return clearSearch();
  if (kind === 'price') { state.filters.min = null; state.filters.max = null; }
  if (kind === 'stock') state.filters.inStock = false;
  rerenderShop();
}

function applyFilters() {
  const readPrice = selector => {
    const digits = ($(selector).value || '').replace(/\D/g, '').slice(0, 12);
    return digits ? Number(digits) : null;
  };
  let min = readPrice('#f-min');
  let max = readPrice('#f-max');
  if (min !== null && max !== null && min > max) [min, max] = [max, min];

  state.filters = { inStock: $('#f-stock').checked, min, max };
  closeModal();
  rerenderShop();
}

function resetFilters() {
  state.filters = emptyFilters();
  closeModal();
  rerenderShop();
}

function setLayout(el) {
  state.layout = el.dataset.layout === 'rows' ? 'rows' : 'grid';
  storage.set(STORAGE_KEYS.layout, state.layout);
  $$('[data-act=layout]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.layout === state.layout)));
  $('#plist .shelf')?.classList.toggle('rows', state.layout === 'rows');
}

function loadMoreProducts() {
  const hadFocus = document.activeElement?.matches?.('[data-act=more]');
  const before = $$('#plist [data-card]').length;
  appendCards();

  const firstNew = $$('#plist [data-card]')[before];
  if (hadFocus && firstNew) $('.plink', firstNew).focus({ preventScroll: true });
}

async function searchOnServer(raw) {
  const query = raw.trim();
  const seq = ++searchSeq;
  if (query.length < MIN_SERVER_SEARCH) return;

  try {
    const result = await api('/products?q=' + encodeURIComponent(query));
    if (seq !== searchSeq || state.view !== 'shop' || state.query.trim() !== query) return;
    state.searchIds = result.products.map(product => product.id);
    renderList();
  } catch {
    if (seq === searchSeq) state.searchIds = null;
  }
}

function runShopSearch() {
  state.searchIds = null;
  renderList();
  keepResultsInView();
  searchOnServer(state.query);
}

export const shopActions = {
  cat: filterByCategory,
  'open-filter': filterModal,
  'apply-filter': applyFilters,
  'reset-filters': resetFilters,
  'rm-filter': removeFilter,
  'clear-all': clearAllFilters,
  'clear-search': clearSearch,
  layout: setLayout,
  more: loadMoreProducts,
  'to-top': () => window.scrollTo({ top: 0, behavior: 'smooth' }),
  'rail-prev': () => scrollRail(-1),
  'rail-next': () => scrollRail(1),
  detail: openProductDetail,
  'detail-add': addFromProductDetail
};

export {
  shopView,
  keepResultsInView,
  clearSearch,
  applyFilters,
  runShopSearch
};