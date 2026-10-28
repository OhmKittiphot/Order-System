import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, configureAuth, request } from "../api/client";

function respond(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "x-correlation-id": "cid-1" } }));
}

afterEach(() => {
  vi.restoreAllMocks();
  configureAuth(() => null, async () => false);
});

describe("api client", () => {
  it("unwraps data and sends the bearer token and correlation id", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => respond(200, { data: { ok: 1 } }));
    configureAuth(() => "tok", async () => false);
    await expect(request<{ ok: number }>("/orders")).resolves.toEqual({ ok: 1 });
    const headers = (fetchMock.mock.calls[0]![1] as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer tok");
    expect(headers["X-Correlation-Id"]).toMatch(/^web-/);
  });
  it("turns API errors into ApiError with code and correlation id", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => respond(409, { error: { code: "NOT_RETRYABLE", message: "Nope" } }));
    const err = (await request("/x").catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.code).toBe("NOT_RETRYABLE");
    expect(err.correlationId).toBe("cid-1");
  });
  it("refreshes once on 401 and retries", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => respond(401, { message: "Unauthorized" }))
      .mockImplementationOnce(() => respond(200, { data: "again" }));
    const refresh = vi.fn(async () => true);
    configureAuth(() => "tok", refresh);
    await expect(request("/orders")).resolves.toBe("again");
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it("reports network failures clearly", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.reject(new TypeError("failed")));
    const err = (await request("/x").catch((e) => e)) as ApiError;
    expect(err.isNetwork).toBe(true);
  });
});
