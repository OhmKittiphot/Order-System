// Single place for HTTP: base URL, auth header, correlation ids, JSON
// envelope unwrapping and error normalisation. No AWS credentials ever
// live in the browser — only the user's short-lived access token issued by the Auth Lambda.

import { uuid } from "../utils/uuid";

export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
    public correlationId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isNetwork(): boolean {
    return this.status === 0;
  }
}

type TokenProvider = () => string | null;
type UnauthorizedHandler = () => Promise<boolean>;

let tokenProvider: TokenProvider = () => null;
let onUnauthorized: UnauthorizedHandler = async () => false;

/** Wired by AuthContext so the client can attach tokens and refresh on 401. */
export function configureAuth(provider: TokenProvider, unauthorized: UnauthorizedHandler): void {
  tokenProvider = provider;
  onUnauthorized = unauthorized;
}

export function newCorrelationId(): string {
  return `web-${uuid()}`;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  query?: Record<string, string | number | undefined | null>;
  headers?: Record<string, string>;
  auth?: boolean;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(API_BASE_URL + path, window.location.origin);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  return API_BASE_URL ? url.toString() : url.pathname + url.search;
}

export async function request<T>(path: string, opts: RequestOptions = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Correlation-Id": newCorrelationId(),
    ...opts.headers,
  };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.auth !== false) {
    const token = tokenProvider();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "NETWORK_ERROR", "Can't reach the server. Check your connection and try again.");
  }

  const correlationId = res.headers.get("x-correlation-id") ?? headers["X-Correlation-Id"];
  let payload: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  const err = (payload as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error;
  // The Lambda Authorizer rejecting an expired/invalid token surfaces as a bare
  // gateway 403 (no error envelope); handler-level 403s always carry one.
  const sessionEnded = res.status === 401 || (res.status === 403 && !err);

  if (sessionEnded && opts.auth !== false && !retried) {
    if (await onUnauthorized()) return request<T>(path, opts, true);
  }

  if (!res.ok) {
    const fallback =
      sessionEnded
        ? "Your session has ended. Sign in again."
        : res.status === 403
          ? "You don't have permission to do that."
          : res.status === 429
            ? "Too many requests. Wait a moment and try again."
            : `Request failed (${res.status}).`;
    throw new ApiError(res.status, err?.code ?? `HTTP_${res.status}`, err?.message ?? fallback, err?.details, correlationId);
  }
  return (payload as { data: T }).data;
}
