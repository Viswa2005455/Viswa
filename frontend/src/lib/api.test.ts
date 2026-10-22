import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, isAbort } from './api';

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('api client', () => {
  it('reads structured error details (category + message) instead of reporting the backend as down', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(429, { detail: { category: 'rate_limit', message: 'Slow down' } })));
    const e = (await api.post('/api/ai/chat', {}).catch((x: unknown) => x)) as ApiError;
    expect(e).toBeInstanceOf(ApiError);
    expect(e.message).toBe('Slow down');
    expect(e.category).toBe('rate_limit');
  });

  it('retries a GET once after a gateway error, but never repeats a POST', async () => {
    const f = vi.fn(async () => json(502, null));
    vi.stubGlobal('fetch', f);
    await api.get('/api/x').catch(() => null);
    expect(f).toHaveBeenCalledTimes(2);
    f.mockClear();
    await api.post('/api/x', {}).catch(() => null);
    expect(f).toHaveBeenCalledTimes(1);
  });

  it('cancels when the caller aborts and times out slow requests', async () => {
    const hang = vi.fn((_: string, init: RequestInit) => new Promise<Response>((_r, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
    }));
    vi.stubGlobal('fetch', hang);
    const c = new AbortController();
    const p = api.post('/api/x', {}, { signal: c.signal });
    c.abort();
    expect(isAbort(await p.catch((x) => x))).toBe(true);

    const t = (await api.post('/api/x', {}, { timeoutMs: 20 }).catch((x: unknown) => x)) as ApiError;
    expect(t).toBeInstanceOf(ApiError);
    expect(t.category).toBe('timeout');
  });
});
