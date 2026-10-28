import { createContext, useContext, useEffect, useMemo, useReducer, type ReactNode } from "react";
import type { CartLine, Product } from "../types";

export const MAX_QTY = 99;
const STORAGE_KEY = "kc.cart";

export type CartAction =
  | { type: "add"; product: Product; quantity?: number }
  | { type: "setQty"; productId: string; quantity: number }
  | { type: "remove"; productId: string }
  | { type: "refreshStock"; products: Product[] }
  | { type: "clear" };

/** Pure reducer (unit-tested). Quantities are clamped to 1..min(stock, 99). */
export function cartReducer(lines: CartLine[], action: CartAction): CartLine[] {
  switch (action.type) {
    case "add": {
      const { product } = action;
      const add = action.quantity ?? 1;
      const limit = Math.min(product.available, MAX_QTY);
      if (limit <= 0) return lines;
      const existing = lines.find((l) => l.productId === product.productId);
      if (existing) {
        return lines.map((l) =>
          l.productId === product.productId
            ? { ...l, quantity: Math.min(l.quantity + add, limit), available: product.available, priceMinor: product.priceMinor }
            : l,
        );
      }
      return [
        ...lines,
        {
          productId: product.productId,
          name: product.name,
          priceMinor: product.priceMinor,
          currency: product.currency,
          quantity: Math.min(add, limit),
          available: product.available,
        },
      ];
    }
    case "setQty": {
      if (!Number.isFinite(action.quantity)) return lines;
      return lines.map((l) =>
        l.productId === action.productId
          ? { ...l, quantity: Math.max(1, Math.min(Math.floor(action.quantity), l.available, MAX_QTY)) }
          : l,
      );
    }
    case "remove":
      return lines.filter((l) => l.productId !== action.productId);
    case "refreshStock": {
      const byId = new Map(action.products.map((p) => [p.productId, p]));
      return lines.map((l) => {
        const p = byId.get(l.productId);
        return p ? { ...l, available: p.available, priceMinor: p.priceMinor } : l;
      });
    }
    case "clear":
      return [];
  }
}

export function estimatedTotal(lines: CartLine[]): number {
  return lines.reduce((sum, l) => sum + l.priceMinor * l.quantity, 0);
}

export function cartProblems(lines: CartLine[]): string[] {
  return lines
    .filter((l) => l.quantity > l.available)
    .map((l) => (l.available === 0 ? `${l.name} is out of stock` : `Only ${l.available} × ${l.name} available`));
}

interface CartState {
  lines: CartLine[];
  count: number;
  dispatch: (a: CartAction) => void;
}

const CartContext = createContext<CartState | null>(null);

function load(): CartLine[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as CartLine[]) : [];
  } catch {
    return [];
  }
}

export function CartProvider({ children }: { children: ReactNode }) {
  const [lines, dispatch] = useReducer(cartReducer, undefined, load);
  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(lines));
    } catch {
      /* ignore */
    }
  }, [lines]);
  const value = useMemo(() => ({ lines, count: lines.reduce((n, l) => n + l.quantity, 0), dispatch }), [lines]);
  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartState {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used inside CartProvider");
  return ctx;
}
