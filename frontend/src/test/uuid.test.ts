import { afterEach, describe, expect, it } from "vitest";
import { uuid } from "../utils/uuid";

const V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("uuid", () => {
  afterEach(() => {
    // remove the own-property shadow; the prototype method is visible again
    delete (crypto as { randomUUID?: unknown }).randomUUID;
  });

  it("works without crypto.randomUUID (plain-HTTP S3 website)", () => {
    Object.defineProperty(crypto, "randomUUID", { value: undefined, configurable: true });
    expect(typeof crypto.randomUUID).toBe("undefined");
    const a = uuid();
    expect(a).toMatch(V4);
    expect(uuid()).not.toBe(a);
  });

  it("uses crypto.randomUUID when available", () => {
    expect(typeof crypto.randomUUID).toBe("function");
    expect(uuid()).toMatch(V4);
  });
});
