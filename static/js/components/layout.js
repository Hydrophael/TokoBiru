// Masonry: baris grid setinggi 1px, tiap kartu membentang sebanyak tingginya
function aturTinggi(grid) {
  const gap = parseFloat(getComputedStyle(grid).columnGap) || 0;
  for (const card of grid.children) {
    card.style.gridRowEnd = 'span ' + Math.ceil(card.offsetHeight + gap);
  }
}

function pasang(grid) {
  grid.dataset.rapat = '1';
  aturTinggi(grid);
  grid.classList.add('rapat');

  let queued = false;
  // Yang diamati hanya kartunya, bukan wadahnya, supaya tidak terjadi perulangan
  const observer = new ResizeObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      if (grid.isConnected) aturTinggi(grid);
    });
  });
  for (const card of grid.children) observer.observe(card);
}

function cariDaftar() {
  document.querySelectorAll('.receipts:not([data-rapat])').forEach(pasang);
}

if ('ResizeObserver' in window) {
  let pending = false;
  new MutationObserver(() => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; cariDaftar(); });
  }).observe(document.body, { childList: true, subtree: true });
  cariDaftar();
}