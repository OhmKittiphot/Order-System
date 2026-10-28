/**
 * One idempotency key per checkout attempt. The key is kept until the order
 * is accepted, so a double click, a network retry or a reload of the
 * checkout page re-sends the same key and the API returns the same order
 * instead of creating a second one.
 */
import { uuid } from "./uuid";

const KEY = "kc.checkoutKey";

export function checkoutKey(cartSignature: string): string {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw) {
      const saved = JSON.parse(raw) as { sig: string; key: string };
      if (saved.sig === cartSignature) return saved.key;
    }
    const key = `chk-${uuid()}`;
    sessionStorage.setItem(KEY, JSON.stringify({ sig: cartSignature, key }));
    return key;
  } catch {
    return `chk-${uuid()}`;
  }
}

export function clearCheckoutKey(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

export function cartSignature(lines: { productId: string; quantity: number }[]): string {
  return lines
    .map((l) => `${l.productId}:${l.quantity}`)
    .sort()
    .join("|");
}
