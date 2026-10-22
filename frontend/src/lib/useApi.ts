import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, isAbort } from './api';

/** Run an async API call, tracking loading/error. A newer call aborts the older one (passed in as
 * `signal`), and a late answer to an older call can never overwrite a newer one. */
export function useAsync<T>(fn: (signal: AbortSignal) => Promise<T>, deps: unknown[], enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(enabled);
  const seq = useRef(0);
  const ctl = useRef<AbortController | null>(null);

  const run = useCallback(() => {
    const id = ++seq.current;
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    setLoading(true);
    fn(c.signal)
      .then((d) => { if (id === seq.current) { setData(d); setError(null); } })
      .catch((e: unknown) => {
        if (isAbort(e) || id !== seq.current) return;
        setError(e instanceof ApiError || e instanceof Error ? e.message : 'Unexpected error');
      })
      .finally(() => { if (id === seq.current) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (enabled) run();
  }, [run, enabled]);

  useEffect(() => () => ctl.current?.abort(), []);

  return { data, error, loading, reload: run, setData };
}

/** Debounce a changing value (used to recalculate models as assumptions are typed). */
export function useDebounced<T>(value: T, ms = 150): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
