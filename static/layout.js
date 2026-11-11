// TokoBiru - tata letak kartu rapat (gaya masonry) untuk daftar kartu pesanan
// Kartu yang lebih rendah tidak lagi meninggalkan ruang kosong: kartu berikutnya otomatis naik mengisi celah.
// Caranya: grid dengan baris setinggi 1px, tiap kartu "membentang" sebanyak tingginya (grid-row-end: span N).
// Tanpa JavaScript, daftar tetap tampil sebagai grid biasa (kelas .rapat baru dipasang setelah tinggi dihitung).

function aturTinggi(grid) {
  const gap = parseFloat(getComputedStyle(grid).columnGap) || 0;   // jarak antar kartu = jarak antar kolom
  for (const card of grid.children) {
    card.style.gridRowEnd = 'span ' + Math.ceil(card.offsetHeight + gap);
  }
}

function pasang(grid) {
  grid.dataset.rapat = '1';
  aturTinggi(grid);
  grid.classList.add('rapat');

  // hitung ulang bila tinggi kartu berubah (jendela diubah ukurannya, font selesai dimuat, status berubah)
  // yang diamati hanya kartunya, bukan wadahnya, supaya tidak terjadi perulangan
  let queued = false;
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
  // daftar pesanan digambar ulang tiap filter/halaman berubah, jadi pantau DOM untuk daftar baru
  let pending = false;
  new MutationObserver(() => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; cariDaftar(); });
  }).observe(document.body, { childList: true, subtree: true });
  cariDaftar();
}