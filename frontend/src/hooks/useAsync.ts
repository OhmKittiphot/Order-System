import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";

export interface AsyncState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
  setData: (d: T | null) => void;
}

function toApiError(err: unknown): ApiError {
  return err instanceof ApiError ? err : new ApiError(0, "UNKNOWN", (err as Error)?.message ?? "Something went wrong");
}

/** Load data when deps change; exposes loading / error / reload. */
export function useAsync<T>(fn: (signal: AbortSignal) => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    fnRef
      .current(ctrl.signal)
      .then((d) => !ctrl.signal.aborted && setData(d))
      .catch((e) => {
        if ((e as Error).name !== "AbortError" && !ctrl.signal.aborted) setError(toApiError(e));
      })
      .finally(() => !ctrl.signal.aborted && setLoading(false));
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload, setData };
}

/**
 * Poll ``fn`` every ``intervalMs`` while ``active`` is true and the tab is
 * visible. Used for order status: processing is asynchronous, so the page
 * asks for the latest state instead of assuming it.
 */
export function usePolling<T>(
  fn: (signal: AbortSignal) => Promise<T>,
  intervalMs: number,
  active: (data: T | null) => boolean,
  deps: unknown[],
): AsyncState<T> & { lastUpdated: number | null } {
  const state = useAsync(fn, deps);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const activeRef = useRef(active);
  activeRef.current = active;
  const { data, setData } = state;

  useEffect(() => {
    if (data) setLastUpdated(Date.now());
  }, [data]);

  useEffect(() => {
    if (!activeRef.current(data)) return;
    const ctrl = new AbortController();
    const id = window.setInterval(async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const next = await fn(ctrl.signal);
        setData(next);
      } catch {
        /* keep the last good value; the next tick retries */
      }
    }, intervalMs);
    return () => {
      ctrl.abort();
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data === null ? "none" : activeRef.current(data), intervalMs, ...deps]);

  return { ...state, lastUpdated };
}
