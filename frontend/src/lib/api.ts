/** Thin fetch wrapper. All requests go to the FastAPI backend under /api (proxied by Vite in dev). */

export class ApiError extends Error {
  status: number;
  /** Machine-readable reason from the server (e.g. AI error categories such as "timeout" or "rate_limit"). */
  category?: string;
  constructor(message: string, status: number, category?: string) {
    super(message);
    this.status = status;
    this.category = category;
  }
}

/** Options for one request: a caller's AbortSignal cancels it (e.g. when newer inputs arrive). */
export interface RequestOpts { signal?: AbortSignal; timeoutMs?: number }

export const isAbort = (e: unknown) => e instanceof DOMException && e.name === 'AbortError';

/** Fired when the server says the session is missing or expired; the auth provider listens for it. */
export const UNAUTHORIZED_EVENT = 'fis:unauthorized';
function signalUnauthorized(path: string) {
  if (!path.startsWith('/api/auth/')) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
}

const BACKEND_DOWN = 'The app\'s backend is not answering. It restarts by itself within a few seconds, so try again shortly. If the "Finance Studio - BACKEND" window is closed, run start-windows.bat again; if it shows a red error, send a screenshot of it.';
const DEFAULT_TIMEOUT_MS = 60_000;

async function once<T>(path: string, init: RequestInit, opts: RequestOpts): Promise<T> {
  const ctl = new AbortController();
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; ctl.abort(); }, timeoutMs);
  const forward = () => ctl.abort();
  if (opts.signal?.aborted) ctl.abort();
  opts.signal?.addEventListener('abort', forward);
  try {
    let res: Response;
    let text: string;
    try {
      res = await fetch(path, { ...init, signal: ctl.signal });
      text = await res.text();
    } catch (e) {
      if (opts.signal?.aborted) throw new DOMException('Request cancelled', 'AbortError');
      if (timedOut) throw new ApiError(`The server did not answer within ${Math.round(timeoutMs / 1000)} seconds. Try again.`, 0, 'timeout');
      throw new ApiError(BACKEND_DOWN, 0, isAbort(e) ? 'aborted' : 'network');
    }
    let body: unknown = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      // non-JSON (e.g. proxy error page)
    }
    if (res.status === 401) signalUnauthorized(path);
    if (!res.ok) {
      const detail = (body as { detail?: unknown } | null)?.detail;
      if (detail && typeof detail === 'object' && 'message' in detail) {
        const d = detail as { message: string; category?: string };
        throw new ApiError(d.message, res.status, d.category);
      }
      const msg = typeof detail === 'string' ? detail : (res.status === 502 || res.status === 504 || res.status === 500) && !body
        ? BACKEND_DOWN
        : `Request failed (${res.status}).`;
      throw new ApiError(msg, res.status);
    }
    return body as T;
  } finally {
    clearTimeout(timer);
    opts.signal?.removeEventListener('abort', forward);
  }
}

async function request<T>(path: string, init: RequestInit = {}, opts: RequestOpts = {}): Promise<T> {
  const idempotent = !init.method || init.method === 'GET';
  try {
    return await once<T>(path, init, opts);
  } catch (e) {
    // One retry for reads that failed on the network or a gateway hiccup; writes are never repeated.
    const retryable = e instanceof ApiError && (e.category === 'network' || e.status === 502 || e.status === 503);
    if (!idempotent || !retryable || opts.signal?.aborted) throw e;
    await new Promise((r) => setTimeout(r, 400));
    return once<T>(path, init, opts);
  }
}

export const api = {
  get: <T>(path: string, opts?: RequestOpts) => request<T>(path, {}, opts),
  post: <T>(path: string, data: unknown, opts?: RequestOpts) =>
    request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }, opts),
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
    try { const b = await res.json(); if (typeof b?.detail === 'string') msg = b.detail; else if (typeof b?.detail?.message === 'string') msg = b.detail.message; } catch { /* not JSON */ }
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
