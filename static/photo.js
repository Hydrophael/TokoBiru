// TokoBiru - foto produk: kecilkan gambar di browser, pratinjau di form, dan pengelolaannya
//
// Foto dikecilkan di browser (WebP/JPEG, sisi terpanjang 800 px, sekitar 100 KB) lalu dikirim sebagai data URL
// di field `image` saat produk disimpan. Server menyimpannya di master_product dan menyajikannya lewat
// /api/products/<id>/image; daftar produk hanya membawa alamatnya (`photo`).

import { $, createError } from './core.js';
import { toast } from './ui.js';

const MAX_INPUT_BYTES = 15 * 1024 * 1024;   // foto asli dari kamera HP bisa beberapa MB
const MAX_SIDE = 800;                       // sisi terpanjang hasil (px)
const TARGET_BYTES = 100 * 1024;            // ukuran yang dituju
const LIMIT_BYTES = 200 * 1024;             // di atas ini ditolak (server membatasi 300.000 karakter)
const QUALITIES = [0.85, 0.75, 0.65, 0.55];

export const PHOTO_HINT = 'JPG, PNG, atau WebP. Foto dikecilkan otomatis.';

const dataUrlBytes = dataUrl => Math.round((dataUrl.length - dataUrl.indexOf(',') - 1) * 3 / 4);

// Safari lama tidak bisa menyimpan WebP dan diam-diam memberi PNG, jadi hasilnya dicek
let webpSupported = null;
function canEncodeWebp() {
  if (webpSupported === null) {
    webpSupported = document.createElement('canvas').toDataURL('image/webp').startsWith('data:image/webp');
  }
  return webpSupported;
}

async function decodeImage(file) {
  if (window.createImageBitmap) {
    try { return await createImageBitmap(file, { imageOrientation: 'from-image' }); } catch { /* coba cara lain */ }
  }
  const url = URL.createObjectURL(file);
  try {
    return await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}

function encode(source, side) {
  const width = source.naturalWidth || source.width;
  const height = source.naturalHeight || source.height;
  const scale = Math.min(1, side / Math.max(width, height));

  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff';                       // PNG transparan jadi berlatar putih
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(source, 0, 0, canvas.width, canvas.height);

  const type = canEncodeWebp() ? 'image/webp' : 'image/jpeg';
  let out = '';
  for (const quality of QUALITIES) {
    out = canvas.toDataURL(type, quality);
    if (dataUrlBytes(out) <= TARGET_BYTES) break;
  }
  return out;
}

// File gambar -> data URL kecil. Melempar error berpesan bahasa Indonesia bila gagal.
export async function compressImage(file) {
  if (!file.type.startsWith('image/')) throw createError('File harus berupa gambar (JPG, PNG, atau WebP)');
  if (file.size > MAX_INPUT_BYTES) throw createError('Foto terlalu besar (maksimal 15 MB)');

  let source;
  try { source = await decodeImage(file); } catch { throw createError('Foto tidak bisa dibaca. Coba format JPG, PNG, atau WebP.'); }

  let out = '';
  let side = MAX_SIDE;
  for (let attempt = 0; attempt < 3; attempt++) {
    out = encode(source, side);
    if (dataUrlBytes(out) <= TARGET_BYTES) break;
    side = Math.round(side * 0.8);
  }
  if (source.close) source.close();

  if (dataUrlBytes(out) > LIMIT_BYTES) throw createError('Foto terlalu rumit untuk dikecilkan. Coba foto lain.');
  return out;
}

// --- Bagian form produk ---

export const photoPreviewHtml = image =>
  image
    ? `<img src="${image}" alt="Pratinjau foto produk">`
    : '<span aria-hidden="true">📷</span>';

// Field `image` ikut terkirim hanya bila foto diubah: berisi foto baru, atau kosong untuk menghapus foto.
// Selama belum disentuh, field itu nonaktif (tidak masuk FormData), jadi foto lama tidak berubah.
const readState = form => ({
  value: $('input[name=image]', form).value,
  disabled: $('input[name=image]', form).disabled,
  preview: $('[data-photo-preview]', form).innerHTML,
  clearHidden: $('[data-act="photo-clear"]', form).hidden,
  note: $('[data-photo-note]', form).textContent
});

function writeState(form, state) {
  const field = $('input[name=image]', form);
  field.value = state.value;
  field.disabled = state.disabled;
  $('[data-photo-preview]', form).innerHTML = state.preview;
  $('[data-act="photo-clear"]', form).hidden = state.clearHidden;
  $('[data-photo-note]', form).textContent = state.note;
}

const applyPhoto = (form, image, note = PHOTO_HINT) =>
  writeState(form, { value: image, disabled: false, preview: photoPreviewHtml(image), clearHidden: !image, note });

export function clearPhoto(form) {
  if (form) applyPhoto(form, '');
}

export function choosePhoto(form) {
  $('input[data-photo-input]', form)?.click();
}

// Dipanggil saat file dipilih. Tombol simpan dikunci selama foto diproses.
export async function handlePhotoInput(input) {
  const file = input.files?.[0];
  input.value = '';                    // memilih file yang sama lagi tetap memicu change
  const form = input.closest('form');
  if (!file || !form) return;

  const before = readState(form);
  const submit = $('button[type=submit]', form);
  if (submit) submit.disabled = true;
  $('[data-photo-note]', form).textContent = 'Memproses foto…';

  try {
    const image = await compressImage(file);
    if (form.isConnected) applyPhoto(form, image, `Foto siap, ${Math.round(dataUrlBytes(image) / 1024)} KB`);
  } catch (err) {
    if (form.isConnected) writeState(form, before);   // kembali ke keadaan sebelumnya
    toast(err.message, 'err');
  } finally {
    if (submit && submit.isConnected) submit.disabled = false;
  }
}