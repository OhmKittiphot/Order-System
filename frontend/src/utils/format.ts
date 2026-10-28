import type { Order, OrderStatus } from "../types";

export function formatMoney(minor: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, minimumFractionDigits: 2 }).format(minor / 100);
  } catch {
    return `${(minor / 100).toFixed(2)} ${currency}`;
  }
}

export function formatDateTime(iso: string | undefined | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function timeAgo(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86400)} d ago`;
}

export function shortId(id: string): string {
  return id.length > 12 ? `…${id.slice(-8)}` : id;
}

/** Statuses that will not change without admin action. */
export function isSettled(order: Pick<Order, "status" | "notificationStatus">): boolean {
  const terminal: OrderStatus[] = ["CONFIRMED", "FAILED", "CANCELLED"];
  return terminal.includes(order.status) && order.notificationStatus !== "PENDING";
}

export type StepState = "done" | "active" | "waiting" | "failed" | "skipped";

export interface PipelineStep {
  key: "received" | "stock" | "payment" | "notified";
  label: string;
  state: StepState;
  note: string;
}

/** Turns the order's status fields into the 4-stage pipeline shown in the UI. */
export function pipeline(order: Order): PipelineStep[] {
  const cancelled = order.status === "CANCELLED";
  const stock: PipelineStep = { key: "stock", label: "Stock", state: "waiting", note: "Waiting" };
  switch (order.inventoryStatus) {
    case "RESERVED":
    case "COMMITTED":
      stock.state = "done";
      stock.note = order.inventoryStatus === "COMMITTED" ? "Items set aside" : "Reserved";
      break;
    case "OUT_OF_STOCK":
      stock.state = "failed";
      stock.note = "Not enough stock";
      break;
    case "RELEASED":
      stock.state = cancelled ? "skipped" : "done";
      stock.note = "Reservation released";
      break;
    default:
      stock.state = cancelled ? "skipped" : "active";
      stock.note = cancelled ? "Cancelled" : "Checking stock";
  }

  const payment: PipelineStep = { key: "payment", label: "Payment", state: "waiting", note: "Waiting" };
  switch (order.paymentStatus) {
    case "SUCCEEDED":
      payment.state = "done";
      payment.note = "Approved";
      break;
    case "FAILED":
      payment.state = "failed";
      payment.note = "Declined";
      break;
    case "SKIPPED":
      payment.state = "skipped";
      payment.note = "Not charged";
      break;
    default:
      if (stock.state === "done" && !cancelled) {
        payment.state = "active";
        payment.note = "Processing";
      }
  }

  const notified: PipelineStep = { key: "notified", label: "Notified", state: "waiting", note: "Waiting" };
  if (order.notificationStatus === "SENT") {
    notified.state = "done";
    notified.note = "Notification sent";
  } else if (order.notificationStatus === "SKIPPED") {
    notified.state = "skipped";
    notified.note = "Not sent";
  } else if (order.status === "CONFIRMED" || order.status === "FAILED") {
    notified.state = "active";
    notified.note = "Sending";
  }

  return [{ key: "received", label: "Received", state: "done", note: "Order accepted" }, stock, payment, notified];
}

export function statusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase().replace(/_/g, " ");
}
