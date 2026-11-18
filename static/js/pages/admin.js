// TokoBiru - Halaman manajemen produk, pengguna, & log aktivitas
import {
  LOG_GROUPS,
  LOG_SEARCH_DEBOUNCE_MS,
  PRODUCT_GROUPS,
  ROLE_LABEL,
  emptyLogFilter,
  emptyProductFilter
} from '../core/constants.js';
import {
  filteredLogs,
  managedProducts,
  productGroupCount,
  state
} from '../core/state.js';
import {
  $,
  $$,
  actionLabel,
  detailLabel,
  emptyState,
  escapeHtml,
  formatDate,
  formatRupiah,
  icon,
  logTone,
  miniHtml,
  stockFlag,
  stockInfo
} from '../core/format.js';
import { api } from '../api/client.js';
import { closeModal, confirmDialog, openModal, toast } from '../components/ui.js';
import { avatarHtml } from '../components/shell.js';
import { PHOTO_HINT, choosePhoto, clearPhoto, photoPreviewHtml } from '../components/photo.js';
import {
  actionTagHtml,
  actorHtml,
  applyLogFilter,
  logEmptyHtml,
  mountLogGrid,
  refreshLogGrid,
  visibleLogIds
} from '../components/logs-grid.js';
import {
  applyProductFilter,
  mountProductGrid,
  productActionsHtml,
  productCountHtml,
  productNameHtml,
  productResetHtml
} from '../components/products-grid.js';
import { reload } from '../core/router.js';

let logSearchTimer = 0;

function productRowHtml(product, index = 0) {
  return `<tr style="--i:${Math.min(index, 10)}"${product.stock === 0 ? ' class="prod-out"' : ''}>
    <td data-label="Produk">${productNameHtml(product)}</td>
    <td data-label="Kategori"><span class="tag">${escapeHtml(product.category)}</span></td>
    <td data-label="Harga" class="num-cell"><b class="num">${formatRupiah(product.price)}</b></td>
    <td data-label="Stok">${stockInfo(product)}</td>
    <td data-label="Aksi">${productActionsHtml(product)}</td></tr>`;
}

const productAddButton = () => `<button type="button" class="btn primary" data-act="product-new">${icon('plus', 15)} Tambah produk</button>`;

export function productRows() {
  const list = managedProducts();

  if (!list.length) {
    const hasProducts = state.products.length > 0;
    return `<tr><td colspan="5">${hasProducts
      ? emptyState('Tidak ada produk yang cocok', 'Ubah kata kunci atau lepas filter yang aktif.', productResetHtml())
      : emptyState('Belum ada produk', 'Tambahkan produk pertama agar pelanggan bisa mulai belanja.', productAddButton())}</td></tr>`;
  }
  return list.map(productRowHtml).join('');
}

function productToolsHtml() {
  const { group, category } = state.productFilter;
  const categories = [...new Set(state.products.map(product => product.category))].sort((a, b) => a.localeCompare(b, 'id'));
  const chips = PRODUCT_GROUPS.map(item =>
    `<button type="button" class="log-chip${item.id === 'out' ? ' is-alert' : ''}" data-act="prod-group" data-group="${item.id}" aria-pressed="${item.id === group}">${item.label}${item.id ? `<span class="log-chip-n">${productGroupCount(item.id)}</span>` : ''}</button>`
  ).join('');
  return `
  <div class="log-tools prod-tools">
    <div class="log-find">
      <div class="log-search">
        ${icon('search', 18)}
        <input type="search" data-input="prod-search" value="${escapeHtml(state.query)}" placeholder="Cari nama produk atau kategori" aria-label="Cari produk" maxlength="50" autocomplete="off" spellcheck="false">
        <button type="button" class="log-q-clear" data-act="prod-q-clear" aria-label="Hapus kata kunci"${state.query ? '' : ' hidden'}>${icon('x', 16)}</button>
      </div>
      <select class="select log-action" data-prod-category aria-label="Saring menurut kategori">
        <option value="">Semua kategori</option>
        ${categories.map(name => `<option value="${escapeHtml(name)}"${name === category ? ' selected' : ''}>${escapeHtml(name)}</option>`).join('')}
      </select>
    </div>
    <div class="log-groups" role="group" aria-label="Status stok">${chips}</div>
    <div class="log-status" id="prod-status" role="status" aria-live="polite">${productCountHtml(managedProducts().length)}</div>
  </div>`;
}

const productsView = () => {
  const { category } = state.productFilter;
  if (category && !state.products.some(product => product.category === category)) state.productFilter.category = '';
  const hasProducts = state.products.length > 0;
  return `
  <div class="page-head"><div><h2>Produk</h2><p class="muted">Tambah produk, ubah harga dan stok, atau hapus dari katalog.</p></div>
    ${productAddButton()}</div>
  ${truncationNotice()}
  ${hasProducts ? productToolsHtml() : ''}
  <div class="tbl-wrap prod-table${state.fresh ? ' stagger' : ''}" id="product-host">${hasProducts
    ? `<table><thead><tr><th>Produk</th><th>Kategori</th><th class="right">Harga</th><th>Stok</th><th class="right">Aksi</th></tr></thead><tbody id="prows">${productRows()}</tbody></table>`
    : emptyState('Belum ada produk', 'Tambahkan produk pertama agar pelanggan bisa mulai belanja.', productAddButton())}</div>`;
};

export const afterProductsRender = () => mountProductGrid(productRows);

export function productModal(product) {
  const isEdit = Boolean(product);
  const values = product || { name: '', category: '', price: '', stock: '', description: '' };
  const image = productImage(product);
  const categoryOptions = state.categories.map(c => `<option value="${escapeHtml(c)}">`).join('');

  openModal(`
    <h3>${isEdit ? 'Ubah produk' : 'Tambah produk'}</h3>${isEdit ? '<p class="sub">Perubahan langsung tampil di katalog pelanggan.</p>' : ''}
    <form data-form="product" data-id="${isEdit ? product.id : ''}" autocomplete="off" novalidate>
      <div class="form-alert" role="alert"></div>
      ${isEdit ? `<input type="hidden" name="base_stock" value="${escapeHtml(product.stock)}">` : ''}
      <div class="field photo-field"><label>Foto produk (opsional)</label>
        <div class="photo-row">
          <div class="photo-preview" data-photo-preview>${photoPreviewHtml(image)}</div>
          <div class="photo-side">
            <input type="file" class="sr-only" accept="image/*" data-photo-input>
            <input type="hidden" name="image" value="" disabled>
            <div class="acts"><button type="button" class="btn sm" data-act="photo-pick">${icon('plus', 14)} Pilih foto</button>
              <button type="button" class="btn sm danger" data-act="photo-clear"${image ? '' : ' hidden'}>${icon('trash', 13)} Hapus foto</button></div>
            <p class="muted small" data-photo-note>${PHOTO_HINT}</p>
          </div>
        </div></div>
      <div class="field"><label>Nama produk</label><input class="input" name="name" required maxlength="80" autocomplete="off" value="${escapeHtml(values.name)}"></div>
      <div class="row2">
        <div class="field"><label>Kategori</label><input class="input" name="category" list="cats" required maxlength="30" placeholder="Contoh: Sembako" value="${escapeHtml(values.category)}"><datalist id="cats">${categoryOptions}</datalist></div>
        <div class="field"><label>Harga (Rp)</label><input class="input" name="price" type="number" placeholder="Contoh: 38000" min="100" max="100000000" step="1" required value="${escapeHtml(values.price)}"></div>
      </div>
      <div class="field"><label>Stok</label><input class="input" name="stock" type="number" placeholder="Contoh: 20" min="0" max="100000" step="1" required value="${escapeHtml(values.stock)}"></div>
      <div class="field"><label>Deskripsi (opsional)</label><textarea class="input" name="description" maxlength="300" placeholder="Keterangan singkat produk">${escapeHtml(values.description)}</textarea></div>
      <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Simpan produk</button></div>
    </form>`);
}

const roleSelectHtml = user =>
  `<select class="select sm" data-change="user-role" data-id="${user.id}" aria-label="Role ${escapeHtml(user.username)}"><option value="user" ${user.role === 'user' ? 'selected' : ''}>Pelanggan</option><option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Admin</option></select>`;

const activeSwitchHtml = user =>
  `<label class="sw"><input type="checkbox" data-change="user-active" data-id="${user.id}" ${user.active ? 'checked' : ''} aria-label="Aktif ${escapeHtml(user.username)}"><span></span></label>`;

const userMiniHtml = user => {
  const photo = avatarPhoto(user);
  return `<span class="mini${photo ? ' has-photo' : ''}">${photo ? `<img src="${photo}" alt="" decoding="async">` : escapeHtml(getInitials(user.name))}</span>`;
};

function userRowHtml(user, index = 0) {
  const locked = user.role === 'master' || user.id === state.user.id;
  return `<tr style="--i:${Math.min(index, 10)}"><td data-label="Pengguna"><div class="cell">${userMiniHtml(user)}<div><b>${escapeHtml(user.name)}</b><div class="muted small">@${escapeHtml(user.username)}</div></div></div></td>
    <td data-label="Email">${escapeHtml(user.email)}</td>
    <td data-label="Role">${locked ? `<span class="tag ${user.role}">${ROLE_LABEL[user.role]}</span>` : roleSelectHtml(user)}</td>
    <td data-label="Aktif">${locked ? '<span class="tag ok">Aktif</span>' : activeSwitchHtml(user)}</td>
    <td data-label="Terdaftar" class="muted small">${formatDate(user.created_at)}</td>
    <td data-label="Aksi"><div class="acts end">${locked ? '<span class="muted small">Dilindungi</span>' : `<button class="btn sm danger" data-act="user-del" data-id="${user.id}" aria-label="Hapus ${escapeHtml(user.username)}">${icon('trash', 13)}</button>`}</div></td></tr>`;
}

const usersView = () => `
  <div class="page-head"><div><h2>Pengguna</h2></div>
    <button class="btn primary" data-act="user-new">${icon('plus', 15)} Tambah pengguna</button></div>
  <div class="tbl-wrap${state.fresh ? ' stagger' : ''}"><table><thead><tr><th>Pengguna</th><th>Email</th><th>Role</th><th>Aktif</th><th>Terdaftar</th><th class="right">Aksi</th></tr></thead><tbody>
  ${state.users.map(userRowHtml).join('')}</tbody></table></div>`;

export function userModal() {
  openModal(`<h3>Tambah pengguna</h3><p class="sub">Buat akun admin untuk staf, atau akun pelanggan.</p>
    <form data-form="user-create" novalidate><div class="form-alert" role="alert"></div>
      <div class="field"><label>Nama lengkap</label><input class="input" name="name" required maxlength="50" placeholder="Nama lengkap"></div>
      <div class="row2"><div class="field"><label>Username</label><input class="input" name="username" required maxlength="20" placeholder="Username unik"></div>
      <div class="field"><label>Role</label><select class="select" name="role"><option value="admin">Admin</option><option value="user">Pelanggan</option></select></div></div>
      <div class="field"><label>Email</label><input class="input" name="email" type="email" required maxlength="120" placeholder="nama@gmail.com"></div>
      <div class="field"><label>Password</label><input class="input" name="password" type="password" required minlength="8" maxlength="128" autocomplete="new-password" placeholder="Minimal 8 karakter"></div>
      <div class="foot"><button type="button" class="btn" data-act="close-modal">Batal</button><button type="submit" class="btn primary">Buat akun</button></div></form>`);
}


function logRowHtml(log, index = 0) {
  const picked = state.selectedLogs.has(log.id);
  const alert = logTone(log.action) === 'err';
  return `<tr data-log="${log.id}" class="${picked ? 'picked' : ''}${alert ? ' log-alert' : ''}" style="--i:${Math.min(index, 10)}">
    <td data-label="Pilih" class="pick"><input type="checkbox" class="tick" data-act="log-pick" data-id="${log.id}"${picked ? ' checked' : ''} aria-label="Pilih log ${escapeHtml(actionLabel(log.action))}"></td>
    <td data-label="Waktu" class="muted small log-time">${formatDate(log.ts)}</td><td data-label="Pengguna">${actorHtml(log)}</td>
    <td data-label="Aksi">${actionTagHtml(log)}</td><td data-label="Detail">${escapeHtml(detailLabel(log))}</td><td data-label="IP" class="muted small log-ip">${escapeHtml(log.ip)}</td>
    <td data-label="Hapus" class="row-del"><button type="button" class="btn sm flat log-del" data-act="log-del" data-id="${log.id}" aria-label="Hapus log ${escapeHtml(actionLabel(log.action))}" title="Hapus log ini">${icon('trash', 16)}</button></td></tr>`;
}

function logActionsHtml() {
  const count = state.selectedLogs.size;
  if (!count) {
    const shown = visibleLogIds().length;
    const total = state.logs.length;
    return `<span class="log-count">${shown === total ? `${total} log` : `Menampilkan <b>${shown}</b> dari ${total} log`}</span>`;
  }
  return `<span class="log-count"><b>${count}</b> dipilih</span>
    <button type="button" class="btn sm" data-act="log-clear">Batal pilih</button>
    <button type="button" class="btn sm solid-danger" data-act="log-del-selected">${icon('trash', 15)} Hapus ${count} log</button>`;
}

export function syncLogSelection() {
  const boxes = $$('[data-act="log-pick-all"]');
  const actions = $('#log-actions');
  if (!boxes.length || !actions) return;

  const visible = visibleLogIds();
  const pickedVisible = visible.filter(id => state.selectedLogs.has(id)).length;
  for (const box of boxes) {
    box.checked = pickedVisible > 0 && pickedVisible === visible.length;
    box.indeterminate = pickedVisible > 0 && pickedVisible < visible.length;
    box.disabled = !visible.length;
  }
  actions.innerHTML = logActionsHtml();
  actions.classList.toggle('is-bulk', state.selectedLogs.size > 0);
  $$('#content tr[data-log]').forEach(row => {
    const picked = state.selectedLogs.has(row.dataset.log);
    row.classList.toggle('picked', picked);
    $('.tick', row).checked = picked;
  });
  refreshLogGrid();
}

export const afterLogsRender = () => mountLogGrid(syncLogSelection);

function logToolsHtml() {
  const { q, group, action } = state.logFilter;
  const actions = [...new Set(state.logs.map(log => log.action))]
    .sort((a, b) => actionLabel(a).localeCompare(actionLabel(b), 'id'));
  const countIn = test => state.logs.filter(log => test(log.action)).length;
  return `
  <div class="log-tools">
    <div class="log-find">
      <div class="log-search">
        ${icon('search', 18)}
        <input type="search" data-log-q value="${escapeHtml(q)}" placeholder="Cari pengguna, aksi, detail, atau IP" aria-label="Cari log" autocomplete="off" spellcheck="false">
        <button type="button" class="log-q-clear" data-act="log-q-clear" aria-label="Hapus kata kunci"${q ? '' : ' hidden'}>${icon('x', 16)}</button>
      </div>
      <select class="select log-action" data-log-action aria-label="Saring menurut aksi">
        <option value="">Semua aksi</option>
        ${actions.map(code => `<option value="${escapeHtml(code)}"${code === action ? ' selected' : ''}>${escapeHtml(actionLabel(code))}</option>`).join('')}
      </select>
    </div>
    <div class="log-groups" role="group" aria-label="Kelompok log">
      ${LOG_GROUPS.map(item => `<button type="button" class="log-chip${item.id === 'alert' ? ' is-alert' : ''}" data-act="log-group" data-group="${item.id}" aria-pressed="${item.id === group}">${item.label}${item.id === 'alert' ? `<span class="log-chip-n">${countIn(item.test)}</span>` : ''}</button>`).join('')}
    </div>
    <label class="pickall log-all-m"><input type="checkbox" class="tick" data-act="log-pick-all" aria-label="Pilih semua log yang tampil"> Pilih semua yang tampil</label>
    <div class="log-status" id="log-actions" role="status" aria-live="polite">${logActionsHtml()}</div>
  </div>`;
}

const logsView = () => {
  if (state.logFilter.action && !state.logs.some(log => log.action === state.logFilter.action)) state.logFilter.action = '';
  return `
  <div class="page-head"><div><h2>Log aktivitas</h2><p class="muted">${state.logs.length} aktivitas terakhir di toko.</p></div><button class="btn" data-act="reload">Perbarui data</button></div>
  ${state.logs.length ? logToolsHtml() : ''}
  <div class="tbl-wrap log-table${state.fresh ? ' stagger' : ''}" id="log-host"><table><thead><tr><th class="pick"><input type="checkbox" class="tick" data-act="log-pick-all" aria-label="Pilih semua log yang tampil"></th><th>Waktu</th><th>Pengguna</th><th>Aksi</th><th>Detail</th><th>IP</th><th><span class="sr-only">Hapus</span></th></tr></thead><tbody>
  ${state.logs.map(logRowHtml).join('') || `<tr><td colspan="7">${emptyState('Belum ada aktivitas')}</td></tr>`}
  </tbody></table><div class="log-empty" id="log-none" hidden>${logEmptyHtml()}</div></div>`;
};


async function confirmAndDelete({ title, message, okLabel, path, successMessage }) {
  const confirmed = await confirmDialog(title, message, okLabel, true);
  if (!confirmed) return;

  try {
    await api(path, { method: 'DELETE' });
    toast(successMessage, 'ok');
    await reload();
  } catch (err) {
    toast(err.message, 'err');
  }
}

function deleteProduct(el) {
  const product = state.productMap[el.dataset.id];
  return confirmAndDelete({
    title: 'Hapus produk?',
    message: `"${product.name}" dihapus dari katalog. Pesanan lama tetap menyimpan datanya.`,
    okLabel: 'Hapus produk',
    path: '/products/' + product.id,
    successMessage: 'Produk dihapus'
  });
}

function resetProductQuery() {
  
  state.query = '';
}

function clearProductSearch() {
  resetProductQuery();
  applyProductFilter();
  $('[data-input="prod-search"]')?.focus();
}

function resetProductFilter() {
  resetProductQuery();
  state.productFilter = emptyProductFilter();
  applyProductFilter();
}

function setProductGroup(el) {
  state.productFilter.group = el.dataset.group;
  applyProductFilter();
}

function setProductCategory(select) {
  state.productFilter.category = select.value;
  applyProductFilter();
}

function deleteUser(el) {
  const user = state.users.find(u => u.id === el.dataset.id);
  return confirmAndDelete({
    title: 'Hapus pengguna?',
    message: `Akun @${user.username} dihapus permanen. Pesanan yang belum dibayar ikut dibatalkan dan foto bukti transfernya dihapus. Akun yang masih punya pesanan berjalan tidak bisa dihapus: nonaktifkan saja.`,
    okLabel: 'Hapus akun',
    path: '/users/' + user.id,
    successMessage: 'Akun dihapus'
  });
}

function confirmMakeAdmin(id) {
  const target = state.users.find(user => user.id === id);
  const who = target ? '@' + target.username : 'Pengguna ini';
  return confirmDialog('Jadikan Admin?', `${who} akan bisa mengelola produk, pesanan, dan melihat pendapatan toko.`, 'Jadikan Admin');
}

async function changeUserSetting(el) {
  const { id, change } = el.dataset;
  try {
    if (change === 'user-role') {
      if (el.value === 'admin' && !(await confirmMakeAdmin(id))) { await reload(); return; }
      await api('/users/' + id, { method: 'PATCH', body: { role: el.value } });
    } else if (change === 'user-active') {
      await api('/users/' + id, { method: 'PATCH', body: { active: el.checked } });
    }
    toast('Perubahan disimpan', 'ok');
    await reload();
  } catch (err) {
    toast(err.message, 'err');
    await reload();
  }
}

function pickLog(el) {
  if (el.checked) state.selectedLogs.add(el.dataset.id);
  else state.selectedLogs.delete(el.dataset.id);
  syncLogSelection();
}

function pickAllLogs(el) {
  state.selectedLogs.clear();
  if (el.checked) visibleLogIds().forEach(id => state.selectedLogs.add(id));
  syncLogSelection();
}

function clearLogSelection() {
  state.selectedLogs.clear();
  syncLogSelection();
}

async function deleteLogs(ids) {
  if (!ids.length) return;
  const many = ids.length > 1;
  const confirmed = await confirmDialog(
    many ? `Hapus ${ids.length} log?` : 'Hapus log ini?',
    'Log yang dihapus tidak bisa dikembalikan.',
    many ? `Hapus ${ids.length} log` : 'Hapus log',
    true
  );
  if (!confirmed) return;

  try {
    const { deleted } = await api('/logs/delete', { method: 'POST', body: { ids } });
    ids.forEach(id => state.selectedLogs.delete(id));
    toast(`${deleted} log dihapus`, 'ok');
    await reload();
  } catch (err) {
    toast(err.message, 'err');
  }
}

function typeLogSearch(input) {
  state.logFilter.q = input.value;
  const clear = $('.log-q-clear');
  if (clear) clear.hidden = !input.value;
  clearTimeout(logSearchTimer);
  logSearchTimer = setTimeout(applyLogFilter, LOG_SEARCH_DEBOUNCE_MS);
}

function setLogGroup(el) {
  state.logFilter.group = el.dataset.group;
  applyLogFilter();
}

function setLogAction(el) {
  state.logFilter.action = el.value;
  applyLogFilter();
}

function clearLogSearch() {
  state.logFilter.q = '';
  applyLogFilter();
  $('[data-log-q]')?.focus();
}

function resetLogFilter() {
  state.logFilter = emptyLogFilter();
  applyLogFilter();
}

export const adminActions = {
  'product-new': () => productModal(null),
  'product-edit': el => productModal(state.productMap[el.dataset.id]),
  'product-del': deleteProduct,
  'prod-group': setProductGroup,
  'prod-q-clear': clearProductSearch,
  'prod-reset': resetProductFilter,
  'photo-pick': el => choosePhoto(el.closest('form')),
  'photo-clear': el => clearPhoto(el.closest('form')),
  'user-new': userModal,
  'user-del': deleteUser,
  'log-pick': pickLog,
  'log-pick-all': pickAllLogs,
  'log-clear': clearLogSelection,
  'log-group': setLogGroup,
  'log-q-clear': clearLogSearch,
  'log-reset': resetLogFilter,
  'log-del': el => deleteLogs([el.dataset.id]),
  'log-del-selected': () => deleteLogs([...state.selectedLogs])
};

export const adminFormHandlers = {
  async product(form, data) {
    const id = form.dataset.id;
    await api(id ? '/products/' + id : '/products', { method: id ? 'PUT' : 'POST', body: data });
    closeModal();
    toast(id ? 'Produk diperbarui' : 'Produk ditambahkan', 'ok');
    await reload();
  },,

  async 'user-create'(form, data) {
    await api('/users', { method: 'POST', body: data });
    closeModal();
    toast('Akun dibuat', 'ok');
    await reload();
  },
};

export {
  productsView,
  productRows,
  afterProductsRender,
  usersView,
  logsView,
  syncLogSelection,
  afterLogsRender,
  changeUserSetting,
  typeLogSearch,
  setLogAction,
  setProductCategory
};
