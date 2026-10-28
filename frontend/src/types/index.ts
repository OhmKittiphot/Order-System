// Shapes returned by the backend API (see backend/openapi.yaml).

export type Role = "customer" | "admin";
export type OrderStatus = "PENDING" | "PROCESSING" | "CONFIRMED" | "FAILED" | "CANCELLED";
export type InventoryStatus = "PENDING" | "RESERVED" | "OUT_OF_STOCK" | "COMMITTED" | "RELEASED";
export type PaymentStatus = "PENDING" | "SUCCEEDED" | "FAILED" | "SKIPPED";
export type NotificationStatus = "PENDING" | "SENT" | "SKIPPED";
export type FailureCategory = "BUSINESS" | "PAYMENT_DECLINED" | "TRANSIENT" | "PERMANENT";

export interface User {
  userId: string;
  email: string;
  displayName: string;
  role: Role;
}

export interface Tokens {
  accessToken: string;
  refreshToken: string | null;
  expiresIn: number;
}

export interface Session {
  tokens: Tokens;
  user: User;
}

export interface Product {
  productId: string;
  name: string;
  description: string;
  priceMinor: number;
  currency: string;
  category: string;
  imageUrl?: string | null;
  available: number;
  inStock: boolean;
}

export interface AdminProduct extends Product {
  active: boolean;
  reserved: number;
  sold: number;
  testBehavior?: string | null;
  createdAt?: string;
  updatedAt?: string;
}

export interface OrderItem {
  productId: string;
  name: string;
  unitPriceMinor: number;
  quantity: number;
  lineTotalMinor: number;
  testBehavior?: string;
}

export interface HistoryEntry {
  at: string;
  event: string;
  detail?: string;
  status?: OrderStatus;
}

export interface RetryDecision {
  retryable: boolean;
  action: string | null;
  reason: string;
  category: FailureCategory | null;
}

export interface Order {
  orderId: string;
  customerId: string;
  items: OrderItem[];
  totalMinor: number;
  currency: string;
  itemCount: number;
  status: OrderStatus;
  inventoryStatus: InventoryStatus;
  paymentStatus: PaymentStatus;
  notificationStatus: NotificationStatus;
  failureReason?: string;
  failureCategory?: FailureCategory;
  createdAt: string;
  updatedAt: string;
  history?: HistoryEntry[];
  retryCount: number;
  idempotentReplay?: boolean;
  // admin-only
  processingAttempts?: number;
  version?: number;
  lastRetryAt?: string;
  retry?: RetryDecision | null;
}

export interface Payment {
  orderId: string;
  attempt: number;
  paymentId: string;
  status: "SUCCEEDED" | "FAILED";
  amountMinor: number;
  currency: string;
  provider: string;
  reason?: string;
  createdAt: string;
}

export interface AdminOrderDetail extends Order {
  payments: Payment[];
  retry: RetryDecision;
  customer: { userId: string; displayName?: string | null };
}

export interface AppNotification {
  notificationId: string;
  orderId: string;
  type: "OrderConfirmed" | "OrderFailed";
  orderStatus: OrderStatus;
  title: string;
  message: string;
  createdAt: string;
  channels: string[];
  emailStatus: string;
}

export interface Page<T> {
  items: T[];
  nextToken: string | null;
}

export interface Stats {
  orders: { total: number; byStatus: Record<OrderStatus, number> };
  products: { total: number; lowStock: number; lowStockThreshold: number };
  lowStockProducts: AdminProduct[];
  generatedAt: string;
}

export interface QueueStatus {
  name: string;
  configured: boolean;
  queueVisible?: number;
  queueInFlight?: number;
  dlqVisible?: number;
  dlqInFlight?: number;
  error?: string;
}

export interface OpsStatus {
  queues: QueueStatus[];
  alarms: { name: string; state: string; reason: string; updatedAt: string }[];
  stuckOrders: { orderId: string; status: OrderStatus; updatedAt: string; retry: RetryDecision }[];
  recentFailedOrders: {
    orderId: string;
    failureCategory?: FailureCategory;
    failureReason?: string;
    updatedAt: string;
    retry: RetryDecision;
  }[];
  note: string;
  generatedAt: string;
}

export interface RetryResult {
  orderId: string;
  action: string;
  attempt: number;
  status: OrderStatus;
  eventPublished: boolean;
  message: string;
}

export interface CartLine {
  productId: string;
  name: string;
  priceMinor: number;
  currency: string;
  quantity: number;
  available: number;
}
