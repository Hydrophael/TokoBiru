// TokoBiru - tabel Log dengan Webix: urut kolom, pilih banyak, dan filter dari toolbar
// Template sel berupa fungsi (bukan string "#kolom#") karena mode strict, dan data pengguna di-escape.

import { $, $$, ROLE_LABEL, actionLabel, detailLabel, escapeHtml, filteredLogs, formatDate, icon, logTone, state } from './core.js';
import { createGridController, sortHead } from './webix-core.js';

const ROW_HEIGHT = 56;

let applied = new Set();   // id baris yang sudah diberi gaya "picked"
let onSelectionRef = null; // syncLogSelection dari views.js

// Webix mengukur teks Detail saja, jadi baris yang membungkus diberi ruang napas
function fitRows(grid) {
  grid.adjustRowHeight('detail', true);
  grid.eachRow(id => {
    const item = grid.getItem(id);
    if (item.$height > ROW_HEIGHT) item.$height += 14;
  }, true);
}

const controller = createGridController({
  name: 'Log',
  view: 'logs',
  hostSelector: '#log-host',
  toolsSelector: '.log-tools',
  hasData: () => state.logs.length > 0,
  create: buildGrid,
  settle: () => applyLogFilter(),
  onFit: grid => { fitRows(grid); grid.refresh(); if (onSelectionRef) onSelectionRef(); },
  onDestroy: () => { applied = new Set(); }
});

export const visibleLogIds = () => filteredLogs().map(log => log.id);

export function refreshLogGrid() {
  if (!controller.live()) return;
  const grid = controller.grid;

  let dirty = false;
  grid.eachRow(id => {
    const picked = state.selectedLogs.has(id);
    if (picked === applied.has(id)) return;
    if (picked) { grid.addRowCss(id, 'picked', true); applied.add(id); }
    else { grid.removeRowCss(id, 'picked', true); applied.delete(id); }
    dirty = true;
  }, true);
  if (!dirty) return;

  // menggambar ulang sel mengganti elemen, jadi fokus dikembalikan
  const active = document.activeElement;
  const keep = active && grid.$view.contains(active) ? active.dataset.id : '';
  grid.refresh();
  if (keep) grid.$view.querySelector(`input.tick[data-id="${CSS.escape(keep)}"]`)?.focus();
}

export const actorHtml = log => {
  if (log.actor === 'anonim' && log.role === '-') return '<span class="log-anon">Belum login</span>';
  const role = log.role !== '-'
    ? `<span class="tag ${escapeHtml(log.role)}">${escapeHtml(ROLE_LABEL[log.role] || log.role)}</span>`
    : '';
  return `<span class="log-who"><b>${escapeHtml(log.actor)}</b>${role}</span>`;
};

export const actionTagHtml = log => `<span class="tag ${logTone(log.action)}">${escapeHtml(actionLabel(log.action))}</span>`;

export const logEmptyHtml = () =>
  `<div class="log-empty-box"><b>Tidak ada log yang cocok</b><span>Ubah kata kunci atau lepas filter yang aktif.</span>` +
  `<button type="button" class="btn sm" data-act="log-reset">Hapus semua filter</button></div>`;

const pickCell = log =>
  `<input type="checkbox" class="tick" data-act="log-pick" data-id="${escapeHtml(log.id)}"${state.selectedLogs.has(log.id) ? ' checked' : ''} aria-label="Pilih log ${escapeHtml(actionLabel(log.action))}">`;

const deleteCell = log =>
  `<button type="button" class="btn sm flat log-del" data-act="log-del" data-id="${escapeHtml(log.id)}" aria-label="Hapus log ${escapeHtml(actionLabel(log.action))}" title="Hapus log ini">${icon('trash', 16)}</button>`;

const SELECT_ALL = '<input type="checkbox" class="tick" data-act="log-pick-all" aria-label="Pilih semua log yang tampil">';

export function applyLogFilter() {
  const filter = state.logFilter;
  const shown = filteredLogs();
  const ids = new Set(shown.map(log => log.id));

  // centang pada baris tersembunyi dilepas supaya tidak ikut terhapus
  state.selectedLogs.forEach(id => { if (!ids.has(id)) state.selectedLogs.delete(id); });

  $$('.log-chip').forEach(chip => chip.setAttribute('aria-pressed', String(chip.dataset.group === filter.group)));
  const clear = $('.log-q-clear');
  if (clear) clear.hidden = !filter.q;
  const search = $('[data-log-q]');
  if (search && search.value !== filter.q) search.value = filter.q;
  const select = $('[data-log-action]');
  if (select && select.value !== filter.action) select.value = filter.action;

  if (controller.live()) {
    const grid = controller.grid;
    grid.filter(row => ids.has(row.id));
    fitRows(grid);
    grid.refresh();
    if (shown.length) grid.hideOverlay(); else grid.showOverlay(logEmptyHtml());
  } else {
    $$('#content tr[data-log]').forEach(row => row.classList.toggle('is-hidden', !ids.has(row.dataset.log)));
    const none = $('#log-none');
    if (none) none.hidden = shown.length > 0;
  }
  if (onSelectionRef) onSelectionRef();
}

function buildGrid(host) {
  // Aksi dan detail disimpan dalam bentuk ramah baca, jadi urutan kolom memakai teks yang dilihat pengguna
  const rows = state.logs.map(log => ({
    ...log,
    label: actionLabel(log.action),
    detail: detailLabel(log),
    $css: logTone(log.action) === 'err' ? 'log-alert' : ''
  }));

  const grid = window.webix.ui({
    container: host,
    view: 'datatable',
    css: 'tb-grid',
    hover: 'tb-hover',
    fixedRowHeight: false,
    rowHeight: ROW_HEIGHT,
    minRowHeight: ROW_HEIGHT,
    headerRowHeight: 46,
    scrollX: false,
    select: false,
    columns: [
      { id: 'pick', header: [{ text: SELECT_ALL, css: 'tb-pickhead' }], width: 56, css: 'tb-edge', template: pickCell },
      { id: 'ts', header: [sortHead('Waktu')], width: 178, sort: 'string', template: log => escapeHtml(formatDate(log.ts)), css: 'tb-muted tb-nowrap' },
      { id: 'actor', header: [sortHead('Pengguna')], width: 220, sort: 'string', template: actorHtml },
      { id: 'label', header: [sortHead('Aksi')], width: 236, sort: 'string', template: actionTagHtml },
      { id: 'detail', header: [sortHead('Detail')], fillspace: true, minWidth: 220, sort: 'string', css: 'tb-wrap', template: log => escapeHtml(log.detail) },
      { id: 'ip', header: [sortHead('IP')], width: 132, sort: 'string', css: 'tb-muted tb-num', template: log => escapeHtml(log.ip) },
      { id: 'del', header: [''], width: 68, css: 'tb-end', template: deleteCell }
    ],
    data: rows
  });

  grid.markSorting('ts', 'desc');   // urutan dari server
  fitRows(grid);
  grid.refresh();
  return grid;
}

export function mountLogGrid(onSelection) {
  onSelectionRef = onSelection;
  return controller.mount();
}