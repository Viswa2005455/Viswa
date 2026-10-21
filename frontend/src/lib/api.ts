/** Thin fetch wrapper. All requests go to the FastAPI backend under /api (proxied by Vite in dev). */

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** Fired when the server says the session is missing or expired; the auth provider listens for it. */
export const UNAUTHORIZED_EVENT = 'fis:unauthorized';
function signalUnauthorized(path: string) {
  if (!path.startsWith('/api/auth/')) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
}

const BACKEND_DOWN = 'The app\'s backend is not answering. Check the "Finance Studio - BACKEND" window: if it is closed, run start-windows.bat again; if it shows an error, send a screenshot of it.';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(BACKEND_DOWN, 0);
  }
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    // non-JSON (e.g. proxy error page)
  }
  if (res.status === 401) signalUnauthorized(path);
  if (!res.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    const msg = typeof detail === 'string' ? detail : res.status === 502 || res.status === 504 || res.status === 500 && !body
      ? BACKEND_DOWN
      : `Request failed (${res.status}).`;
    throw new ApiError(msg, res.status);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data: unknown) =>
    request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  put: <T>(path: string, data: unknown) =>
    request<T>(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  patch: <T>(path: string, data: unknown) =>
    request<T>(path, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  /** POST multipart form fields and files (each field name maps to a string or a File). */
  form: <T>(path: string, fields: Record<string, string | File | null | undefined>) => {
    const fd = new FormData();
    Object.entries(fields).forEach(([k, v]) => { if (v instanceof File) fd.append(k, v, v.name); else if (v != null && v !== '') fd.append(k, v); });
    return request<T>(path, { method: 'POST', body: fd });
  },
  upload: <T>(path: string, files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append('files', f, f.name));
    return request<T>(path, { method: 'POST', body: fd });
  },
};

/** POST JSON and save the returned file (Excel, Word, …) under the server's suggested name. */
export async function downloadPost(path: string, data: unknown, fallbackName: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  } catch {
    throw new ApiError(BACKEND_DOWN, 0);
  }
  if (res.status === 401) signalUnauthorized(path);
  if (!res.ok) {
    let msg = `Request failed (${res.status}).`;
    try { const b = await res.json(); if (typeof b?.detail === 'string') msg = b.detail; } catch { /* not JSON */ }
    throw new ApiError(msg, res.status);
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Multipart upload with real byte-level progress (fetch cannot report upload progress). */
export function uploadWithProgress<T>(path: string, files: File[], onProgress: (fraction: number) => void, fields: Record<string, string | null | undefined> = {}): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const fd = new FormData();
    files.forEach((f) => fd.append('files', f, f.name));
    Object.entries(fields).forEach(([k, v]) => { if (v) fd.append(k, v); });
    xhr.open('POST', path);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    xhr.onerror = () => reject(new ApiError('Upload failed: cannot reach the backend.', 0));
    xhr.onload = () => {
      let body: { detail?: string } | null = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status === 401) signalUnauthorized(path);
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as T);
      else reject(new ApiError(body?.detail ?? `Upload failed (${xhr.status}).`, xhr.status));
    };
    xhr.send(fd);
  });
}
