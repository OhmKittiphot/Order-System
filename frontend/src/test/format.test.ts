import { describe, expect, it } from "vitest";
import type { Order } from "../types";
import { formatMoney, isSettled, pipeline, shortId, timeAgo } from "../utils/format";

const base: Order = {
  orderId: "ord_1234567890abcdef",
  customerId: "c",
  items: [],
  totalMinor: 129000,
  currency: "THB",
  itemCount: 1,
  status: "PENDING",
  inventoryStatus: "PENDING",
  paymentStatus: "PENDING",
  notificationStatus: "PENDING",
  createdAt: "2026-10-27T08:00:00.000Z",
  updatedAt: "2026-10-27T08:00:00.000Z",
  retryCount: 0,
};

describe("formatting", () => {
  it("formats minor units as money", () => {
    expect(formatMoney(129000, "THB")).toContain("1,290.00");
  });
  it("shortens ids and computes relative time", () => {
    expect(shortId("ord_1234567890abcdef")).toBe("…90abcdef");
    expect(timeAgo("2026-10-27T08:00:00Z", Date.parse("2026-10-27T08:02:00Z"))).toBe("2 min ago");
  });
});

describe("order pipeline", () => {
  it("shows stock as active for a new order", () => {
    const steps = pipeline(base);
    expect(steps.map((s) => s.state)).toEqual(["done", "active", "waiting", "waiting"]);
    expect(isSettled(base)).toBe(false);
  });
  it("marks a confirmed and notified order as done", () => {
    const o: Order = { ...base, status: "CONFIRMED", inventoryStatus: "COMMITTED", paymentStatus: "SUCCEEDED", notificationStatus: "SENT" };
    expect(pipeline(o).every((s) => s.state === "done")).toBe(true);
    expect(isSettled(o)).toBe(true);
  });
  it("shows out-of-stock and declined failures on the right step", () => {
    const oos: Order = { ...base, status: "FAILED", inventoryStatus: "OUT_OF_STOCK", paymentStatus: "SKIPPED" };
    expect(pipeline(oos).map((s) => s.state)).toEqual(["done", "failed", "skipped", "active"]);
    const declined: Order = { ...base, status: "FAILED", inventoryStatus: "RELEASED", paymentStatus: "FAILED", notificationStatus: "SENT" };
    expect(pipeline(declined)[2]!.state).toBe("failed");
    expect(isSettled(declined)).toBe(true);
  });
});
