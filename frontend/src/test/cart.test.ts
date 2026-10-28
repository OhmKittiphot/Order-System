import { describe, expect, it } from "vitest";
import { cartProblems, cartReducer, estimatedTotal } from "../contexts/CartContext";
import type { Product } from "../types";
import { cartSignature } from "../utils/idempotency";

const mug: Product = {
  productId: "prd_mug", name: "Mug", description: "", priceMinor: 35000, currency: "THB",
  category: "Merch", available: 2, inStock: true,
};

describe("cart reducer", () => {
  it("adds items and never exceeds available stock", () => {
    let lines = cartReducer([], { type: "add", product: mug });
    lines = cartReducer(lines, { type: "add", product: mug, quantity: 5 });
    expect(lines).toHaveLength(1);
    expect(lines[0]!.quantity).toBe(2);
  });
  it("ignores out-of-stock products", () => {
    expect(cartReducer([], { type: "add", product: { ...mug, available: 0, inStock: false } })).toEqual([]);
  });
  it("clamps quantity edits and removes lines", () => {
    let lines = cartReducer([], { type: "add", product: mug });
    lines = cartReducer(lines, { type: "setQty", productId: "prd_mug", quantity: 0 });
    expect(lines[0]!.quantity).toBe(1);
    lines = cartReducer(lines, { type: "setQty", productId: "prd_mug", quantity: 50 });
    expect(lines[0]!.quantity).toBe(2);
    expect(estimatedTotal(lines)).toBe(70000);
    expect(cartReducer(lines, { type: "remove", productId: "prd_mug" })).toEqual([]);
  });
  it("flags lines that exceed refreshed stock", () => {
    let lines = cartReducer([], { type: "add", product: mug, quantity: 2 });
    lines = cartReducer(lines, { type: "refreshStock", products: [{ ...mug, available: 1 }] });
    expect(cartProblems(lines)).toEqual(["Only 1 × Mug available"]);
  });
  it("builds an order-independent cart signature for idempotency keys", () => {
    expect(cartSignature([{ productId: "b", quantity: 1 }, { productId: "a", quantity: 2 }])).toBe(
      cartSignature([{ productId: "a", quantity: 2 }, { productId: "b", quantity: 1 }]),
    );
  });
});
