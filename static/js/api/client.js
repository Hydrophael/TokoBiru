// TokoBiru - Klien HTTP /api dengan token CSRF & deteksi sesi berakhir
import { state } from '../core/state.js';
import { createError } from '../core/format.js';

export const hooks = { onSessionExpired() {} };

export async function api(path, { method = 'GET', body, headers } = {}) {
  const options = {
    method,
    headers: { 'Accept': 'application/json', ...headers },
    credentials: 'same-origin'
  };
  if (method !== 'GET') {
    options.headers['Content-Type'] = 'application/json';
    options.headers['X-CSRF-Token'] = state.csrf;
  }
  if (body !== undefined) options.body = JSON.stringify(body);

  let response;
  try {
    response = await fetch('/api' + path, options);
  } catch {
    throw createError('Tidak ada sambungan internet, atau toko sedang sulit dihubungi. Coba lagi.', { status: 0 });
  }

  let data = {};
  try { data = await response.json(); } catch { }

  if (!response.ok) {
    const sessionExpired = response.status === 401 && !path.startsWith('/auth/');
    if (sessionExpired) hooks.onSessionExpired();
    throw createError(data.error || 'Terjadi kesalahan', { status: response.status, fields: data.fields });
  }
  return data;
}
