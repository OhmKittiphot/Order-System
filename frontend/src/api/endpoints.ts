import type {
  AdminOrderDetail,
  AdminProduct,
  AppNotification,
  OpsStatus,
  Order,
  OrderStatus,
  Page,
  Product,
  RetryResult,
  Session,
  Stats,
  User,
} from "../types";
import { request } from "./client";

export const authApi = {
  register: (email: string, password: string, displayName: string) =>
    request<{ userId: string; emailSubscription: string }>("/auth/register", {
      method: "POST",
      body: { email, password, displayName },
      auth: false,
    }),
  login: (email: string, password: string) =>
    request<Session>("/auth/login", { method: "POST", body: { email, password }, auth: false }),
  refresh: (refreshToken: string) =>
    request<Session>("/auth/refresh", { method: "POST", body: { refreshToken }, auth: false }),
  me: () => request<User>("/me"),
};

export const productApi = {
  list: (nextToken?: string | null, limit = 24) =>
    request<Page<Product>>("/products", { query: { limit, nextToken }, auth: false }),
  get: (productId: string) => request<Product>(`/products/${encodeURIComponent(productId)}`, { auth: false }),
};

export const orderApi = {
  /** Only ids and quantities are sent; the server prices the order. */
  create: (items: { productId: string; quantity: number }[], idempotencyKey: string) =>
    request<Order & { message: string }>("/orders", {
      method: "POST",
      body: { items },
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  get: (orderId: string, signal?: AbortSignal) => request<Order>(`/orders/${encodeURIComponent(orderId)}`, { signal }),
  list: (nextToken?: string | null, limit = 20) => request<Page<Order>>("/orders", { query: { limit, nextToken } }),
  notifications: (nextToken?: string | null) =>
    request<Page<AppNotification>>("/notifications", { query: { limit: 30, nextToken } }),
};

export interface ProductInput {
  name: string;
  description: string;
  priceMinor: number;
  category: string;
  imageUrl?: string | null;
  active: boolean;
  initialStock?: number;
  testBehavior?: string | null;
}

export const adminApi = {
  stats: () => request<Stats>("/admin/stats"),
  orders: (status: OrderStatus | "" , nextToken?: string | null, limit = 25) =>
    request<Page<Order>>("/admin/orders", { query: { status, nextToken, limit } }),
  order: (orderId: string, signal?: AbortSignal) =>
    request<AdminOrderDetail>(`/admin/orders/${encodeURIComponent(orderId)}`, { signal }),
  retry: (orderId: string) => request<RetryResult>(`/admin/orders/${encodeURIComponent(orderId)}/retry`, { method: "POST" }),
  cancel: (orderId: string) =>
    request<{ orderId: string; status: OrderStatus; stockReleased: boolean }>(
      `/admin/orders/${encodeURIComponent(orderId)}/cancel`,
      { method: "POST" },
    ),
  products: () => request<Page<AdminProduct> & { lowStockThreshold: number }>("/admin/products", { query: { limit: 100 } }),
  createProduct: (input: ProductInput) => request<AdminProduct>("/admin/products", { method: "POST", body: input }),
  updateProduct: (productId: string, changes: Partial<ProductInput>) =>
    request<AdminProduct>(`/admin/products/${encodeURIComponent(productId)}`, { method: "PATCH", body: changes }),
  changeStock: (productId: string, mode: "set" | "adjust", quantity: number, reason: string) =>
    request<AdminProduct>(`/admin/products/${encodeURIComponent(productId)}/stock`, {
      method: "PATCH",
      body: { mode, quantity, reason },
    }),
  ops: () => request<OpsStatus>("/admin/dlq-status"),
  redrive: (queue: "stock" | "payment" | "notify") =>
    request<{ queue: string; taskHandle: string; message: string }>(`/admin/dlq/${queue}/redrive`, { method: "POST" }),
};
