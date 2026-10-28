import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { adminApi } from "../../api/endpoints";
import { DataTable } from "../../components/DataTable";
import { OrderPipeline } from "../../components/OrderPipeline";
import {
  BACK_LINK,
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorMessage,
  Eyebrow,
  ID_LINK,
  LoadMore,
  NoticeIcon,
  PAGE_HEAD,
  PAGE_TITLE,
  QUIET_EMPTY,
  SECTION_TITLE,
  StatusBadge,
  TableSkeleton,
  noticeClass,
} from "../../components/ui";
import { useToast } from "../../contexts/ToastContext";
import { useAsync, usePolling } from "../../hooks/useAsync";
import type { Order, OrderStatus, RetryDecision } from "../../types";
import { formatDateTime, formatMoney, isSettled, shortId, statusLabel, timeAgo } from "../../utils/format";
import { OrderItemsTable, OrderTimeline } from "../OrderPages";

const STATUSES: (OrderStatus | "")[] = ["", "PENDING", "PROCESSING", "CONFIRMED", "FAILED", "CANCELLED"];

export function RefreshIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-3.5" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 8a5 5 0 1 1-1.5-3.5M13 2.5v2.5h-2.5" />
    </svg>
  );
}

export function ClearIcon() {
  return (
    <span className="grid size-7 shrink-0 place-items-center rounded-full bg-emerald-50 text-emerald-600 ring-1 ring-emerald-100" aria-hidden="true">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.2" className="size-3.5">
        <path strokeLinecap="round" strokeLinejoin="round" d="m3.5 8.5 3 3 6-7" />
      </svg>
    </span>
  );
}

export function CountChip({ n }: { n: number }) {
  return <span className="rounded-full bg-slate-900/6 px-2 py-0.5 font-mono text-xs font-medium text-slate-600 tabular-nums">{n}</span>;
}

export function RetryHint({ retry }: { retry?: RetryDecision | null }) {
  if (!retry) return <span className="text-slate-400">—</span>;
  if (!retry.retryable && retry.reason.startsWith("Order is still being processed")) return <span className="text-[0.8125rem] text-slate-600">In progress</span>;
  return retry.retryable ? (
    <span className="inline-flex items-center gap-1 text-[0.8125rem] font-semibold whitespace-nowrap text-emerald-700">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" className="size-3.5" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 8a5 5 0 1 1-1.5-3.5M13 2.5v2.5h-2.5" />
      </svg>
      Can retry
    </span>
  ) : (
    <span className="text-[0.8125rem] whitespace-nowrap text-slate-600" title={retry.reason}>
      {retry.category === "PAYMENT_DECLINED" ? "Declined" : retry.category === "BUSINESS" ? "Needs restock" : "Not retryable"}
    </span>
  );
}

export function AdminOrdersPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") ?? "") as OrderStatus | "";
  const [more, setMore] = useState<Order[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { data, error, loading, reload } = useAsync(async () => {
    const page = await adminApi.orders(status);
    setMore([]);
    setNext(page.nextToken);
    return page.items;
  }, [status]);
  const rows = [...(data ?? []), ...more];

  async function loadMore() {
    setBusy(true);
    try {
      const page = await adminApi.orders(status, next);
      setMore((m) => [...m, ...page.items]);
      setNext(page.nextToken);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className={PAGE_HEAD}>
        <div>
          <Eyebrow>Fulfilment</Eyebrow>
          <h1 className={`${PAGE_TITLE} mt-3 font-bold`}>Orders</h1>
        </div>
        <div className="glass flex flex-wrap items-center gap-2 rounded-2xl p-1.5 pl-4">
          <label htmlFor="status-filter" className="eyebrow">
            Status
          </label>
          <select id="status-filter" className="min-h-10 w-auto min-w-40 border-transparent bg-white" value={status} onChange={(e) => setParams(e.target.value ? { status: e.target.value } : {})}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s ? statusLabel(s) : "All statuses"}
              </option>
            ))}
          </select>
          <Button variant="secondary" className="min-h-10" onClick={reload}>
            <RefreshIcon />
            Refresh
          </Button>
        </div>
      </div>
      {loading && <TableSkeleton label="Loading orders" />}
      {error && <ErrorMessage error={error} onRetry={reload} />}
      {!loading && !error && rows.length === 0 && <EmptyState title="No orders match this filter" art="orders" />}
      {rows.length > 0 && (
        <DataTable
          caption="Orders"
          rows={rows}
          rowKey={(o) => o.orderId}
          onRowClick={(o) => navigate(`/admin/orders/${o.orderId}`)}
          columns={[
            { key: "id", header: "Order", render: (o) => <Link to={`/admin/orders/${o.orderId}`} className={ID_LINK}>{shortId(o.orderId)}</Link> },
            { key: "customer", header: "Customer", render: (o) => <span className="font-mono text-[0.8125rem] whitespace-nowrap text-slate-600">{shortId(o.customerId)}</span> },
            { key: "created", header: "Created", render: (o) => <span className="whitespace-nowrap text-slate-600">{formatDateTime(o.createdAt)}</span> },
            { key: "total", header: "Total", align: "right", render: (o) => <span className="font-semibold text-ink">{formatMoney(o.totalMinor, o.currency)}</span> },
            { key: "status", header: "Order", render: (o) => <StatusBadge status={o.status} /> },
            { key: "inv", header: "Stock", render: (o) => <StatusBadge status={o.inventoryStatus} /> },
            { key: "pay", header: "Payment", render: (o) => <StatusBadge status={o.paymentStatus} /> },
            { key: "retry", header: "Action", render: (o) => <RetryHint retry={o.retry} /> },
          ]}
        />
      )}
      <LoadMore nextToken={next} loading={busy} onClick={loadMore} />
    </>
  );
}

export function AdminOrderDetailPage() {
  const { orderId = "" } = useParams();
  const toast = useToast();
  const [dialog, setDialog] = useState<"retry" | "cancel" | null>(null);
  const [acting, setActing] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const { data: order, error, loading, reload } = usePolling(
    (signal) => adminApi.order(orderId, signal),
    3000,
    (o) => !!o && !isSettled(o),
    [orderId],
  );

  async function act(kind: "retry" | "cancel") {
    setActing(true);
    try {
      if (kind === "retry") {
        const r = await adminApi.retry(orderId);
        setResult(`Retry started (attempt ${r.attempt}): ${r.message}.${r.eventPublished ? "" : " The event will be published by the outbox publisher shortly."}`);
        toast("Retry started", "success");
      } else {
        const r = await adminApi.cancel(orderId);
        setResult(`Order cancelled${r.stockReleased ? " and reserved stock released" : ""}.`);
        toast("Order cancelled", "success");
      }
      reload();
    } catch (e) {
      toast((e as ApiError).message, "error");
    } finally {
      setActing(false);
      setDialog(null);
    }
  }

  if (loading && !order) return <TableSkeleton label="Loading order" rows={6} />;
  if (error && !order) return <ErrorMessage error={error} onRetry={reload} />;
  if (!order) return null;
  const cancellable = !["CONFIRMED", "CANCELLED"].includes(order.status);

  return (
    <article>
      <Link to="/admin/orders" className={BACK_LINK}>
        <span className="grid size-6 place-items-center rounded-full bg-slate-100 transition-transform duration-300 group-hover/back:-translate-x-0.5" aria-hidden="true">
          ‹
        </span>
        Orders
      </Link>
      <header className="relative isolate animate-rise overflow-hidden rounded-4xl bg-ink p-6 text-white shadow-[0_30px_60px_-30px_rgb(11_13_20/0.6)] sm:p-8">
        <div className="absolute -top-28 -right-20 -z-10 size-80 rounded-full bg-cobalt-600/40 blur-3xl" aria-hidden="true" />
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(rgb(255_255_255/0.06)_1px,transparent_1px)] bg-size-[22px_22px]" aria-hidden="true" />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="eyebrow text-slate-400">Order record</p>
            <h1 className="mt-3 font-mono text-xl font-semibold tracking-tight break-all text-white sm:text-2xl">{order.orderId}</h1>
          </div>
          <StatusBadge status={order.status} />
        </div>
        <p className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-slate-300">
          <span className="inline-flex items-center gap-2">
            <span className="grid size-6 place-items-center rounded-full bg-linear-to-br from-cobalt-500 to-ember-500 text-[0.6875rem] font-bold text-white" aria-hidden="true">
              {(order.customer.displayName ?? "C").slice(0, 1)}
            </span>
            {order.customer.displayName ?? "Customer"} ({shortId(order.customerId)})
          </span>
          <span className="text-slate-500" aria-hidden="true">
            /
          </span>
          <span>created {formatDateTime(order.createdAt)}</span>
          <span className="text-slate-500" aria-hidden="true">
            /
          </span>
          <span>updated {timeAgo(order.updatedAt)}</span>
        </p>
      </header>
      <OrderPipeline order={order} />

      <section className="relative mb-12 rounded-4xl bg-linear-to-br from-cobalt-200 via-white to-ember-300/60 p-px shadow-[0_24px_50px_-30px_rgb(42_77_255/0.5)]">
        <div className="rounded-[calc(2rem-1px)] bg-white p-5 sm:p-7">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h2 className={`${SECTION_TITLE} mb-0`}>
            <span className="grid size-8 place-items-center rounded-xl bg-cobalt-50 text-cobalt-600 ring-1 ring-cobalt-100" aria-hidden="true">
              <RefreshIcon />
            </span>
            Recovery
          </h2>
          <RetryHint retry={order.retry} />
        </div>
        <p className="mt-4 text-[0.9375rem] text-slate-800">{order.retry.reason}</p>
        {order.failureReason && <p className="mt-1 text-sm text-slate-600">Failure: {order.failureReason}</p>}
        <dl className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-2xl bg-slate-50 px-4 py-3.5 ring-1 ring-slate-100">
            <dt className="eyebrow text-[0.625rem]">Attempt</dt>
            <dd className="mt-1 font-display text-2xl font-bold tabular-nums">{order.retryCount}</dd>
          </div>
          <div className="rounded-2xl bg-slate-50 px-4 py-3.5 ring-1 ring-slate-100">
            <dt className="eyebrow text-[0.625rem]">Worker runs</dt>
            <dd className="mt-1 font-display text-2xl font-bold tabular-nums">{order.processingAttempts ?? 0}</dd>
          </div>
          <div className="rounded-2xl bg-slate-50 px-4 py-3.5 ring-1 ring-slate-100">
            <dt className="eyebrow text-[0.625rem]">Last retry</dt>
            <dd className="mt-1.5 text-sm font-semibold tabular-nums">{order.lastRetryAt ? formatDateTime(order.lastRetryAt) : "—"}</dd>
          </div>
        </dl>
        {result && (
          <div className={noticeClass("info")} role="status">
            <NoticeIcon tone="info" />
            <p>{result}</p>
          </div>
        )}
        <div className="mt-6 flex flex-wrap gap-2 border-t border-slate-100 pt-6">
          <Button disabled={!order.retry.retryable} onClick={() => setDialog("retry")}>
            Retry order
          </Button>
          <Button variant="danger" disabled={!cancellable} onClick={() => setDialog("cancel")}>
            Cancel order
          </Button>
        </div>
        </div>
      </section>

      <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <section>
          <h2 className={SECTION_TITLE}>
            <span className="h-4 w-1 rounded-full bg-cobalt-600" aria-hidden="true" />
            Items
          </h2>
          <OrderItemsTable order={order} />
          <h2 className={`${SECTION_TITLE} mt-12`}>
            <span className="h-4 w-1 rounded-full bg-emerald-500" aria-hidden="true" />
            Payments
          </h2>
          {order.payments.length === 0 ? (
            <p className={QUIET_EMPTY}>No payment attempts.</p>
          ) : (
            <ul className="space-y-2">
              {order.payments.map((p) => (
                <li
                  key={`${p.attempt}`}
                  className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl border border-slate-200/80 bg-white px-4 py-3.5 text-sm tabular-nums shadow-[0_1px_2px_rgb(11_13_20/0.04)]"
                >
                  <span className="rounded-lg bg-slate-100 px-2 py-0.5 font-mono text-xs font-medium">Attempt {p.attempt}:</span> <StatusBadge status={p.status} />{" "}
                  <span className="font-display text-base font-bold">{formatMoney(p.amountMinor, p.currency)}</span>
                  <span className="text-slate-600">· {p.provider}</span>
                  {p.reason && <span className="text-slate-600"> · {p.reason}</span>}
                </li>
              ))}
            </ul>
          )}
        </section>
        <section>
          <h2 className={SECTION_TITLE}>
            <span className="h-4 w-1 rounded-full bg-ember-500" aria-hidden="true" />
            History
          </h2>
          <OrderTimeline order={order} />
        </section>
      </div>

      <ConfirmDialog
        open={dialog === "retry"}
        title="Retry this order?"
        confirmLabel="Retry order"
        busy={acting}
        onConfirm={() => act("retry")}
        onCancel={() => setDialog(null)}
      >
        <p>{order.retry.reason}. A new processing attempt starts and the customer is notified of the outcome.</p>
      </ConfirmDialog>
      <ConfirmDialog
        open={dialog === "cancel"}
        title="Cancel this order?"
        confirmLabel="Cancel order"
        tone="danger"
        busy={acting}
        onConfirm={() => act("cancel")}
        onCancel={() => setDialog(null)}
      >
        <p>The order stops processing. Reserved stock is returned. This can't be undone.</p>
      </ConfirmDialog>
    </article>
  );
}

export function FailedOrdersPage() {
  const navigate = useNavigate();
  const failed = useAsync(() => adminApi.orders("FAILED", null, 50), []);
  const ops = useAsync(() => adminApi.ops(), []);
  return (
    <>
      <div className={PAGE_HEAD}>
        <div>
          <Eyebrow>Exceptions</Eyebrow>
          <h1 className={`${PAGE_TITLE} mt-3 font-bold`}>Failed orders</h1>
        </div>
        <Button
          variant="secondary"
          onClick={() => {
            failed.reload();
            ops.reload();
          }}
        >
          <RefreshIcon />
          Refresh
        </Button>
      </div>
      <div className="-mt-4 mb-12 grid gap-3 sm:grid-cols-3" aria-hidden="true">
        {[
          { t: "Out of stock", d: "Retry after restocking", c: "bg-amber-500" },
          { t: "Payment declined", d: "Can't be retried", c: "bg-red-500" },
          { t: "Stuck in processing", d: "Retry after a short wait", c: "bg-cobalt-600" },
        ].map((x) => (
          <div key={x.t} className="glass flex items-center gap-3 rounded-2xl px-4 py-3">
            <span className={`h-8 w-1 rounded-full ${x.c}`} />
            <span>
              <span className="block text-sm font-semibold text-ink">{x.t}</span>
              <span className="block text-xs text-slate-600">{x.d}</span>
            </span>
          </div>
        ))}
      </div>
      <p className="sr-only">
        Out-of-stock orders can be retried after restocking. Declined payments can't be retried. Orders stuck in processing
        (usually because a message reached a dead-letter queue) can be retried after a short wait.
      </p>

      <h2 className={SECTION_TITLE}>
        <span className="relative flex size-2.5" aria-hidden="true">
          <span className="absolute inset-0 animate-ping rounded-full bg-amber-400 opacity-60 motion-reduce:animate-none" />
          <span className="relative size-2.5 rounded-full bg-amber-500" />
        </span>
        Stuck in processing
        {ops.data && <CountChip n={ops.data.stuckOrders.length} />}
      </h2>
      {ops.loading && <TableSkeleton label="Loading" rows={2} />}
      {ops.error && <ErrorMessage error={ops.error} onRetry={ops.reload} />}
      {ops.data && ops.data.stuckOrders.length === 0 && (
        <p className={QUIET_EMPTY}>
          <ClearIcon />
          No orders are stuck right now.
        </p>
      )}
      {ops.data && ops.data.stuckOrders.length > 0 && (
        <DataTable
          rows={ops.data.stuckOrders}
          rowKey={(o) => o.orderId}
          onRowClick={(o) => navigate(`/admin/orders/${o.orderId}`)}
          columns={[
            { key: "id", header: "Order", render: (o) => <Link to={`/admin/orders/${o.orderId}`} className={ID_LINK}>{shortId(o.orderId)}</Link> },
            { key: "status", header: "Status", render: (o) => <StatusBadge status={o.status} /> },
            { key: "since", header: "No progress since", render: (o) => <span className="font-medium text-amber-800">{timeAgo(o.updatedAt)}</span> },
            { key: "retry", header: "Action", render: (o) => <RetryHint retry={o.retry} /> },
          ]}
        />
      )}

      <h2 className={`${SECTION_TITLE} mt-14`}>
        <span className="size-2.5 rounded-full bg-red-500" aria-hidden="true" />
        Failed
        {failed.data && <CountChip n={failed.data.items.length} />}
      </h2>
      {failed.loading && <TableSkeleton label="Loading" rows={3} />}
      {failed.error && <ErrorMessage error={failed.error} onRetry={failed.reload} />}
      {failed.data && failed.data.items.length === 0 && (
        <p className={QUIET_EMPTY}>
          <ClearIcon />
          No failed orders.
        </p>
      )}
      {failed.data && failed.data.items.length > 0 && (
        <DataTable
          rows={failed.data.items}
          rowKey={(o) => o.orderId}
          onRowClick={(o) => navigate(`/admin/orders/${o.orderId}`)}
          columns={[
            { key: "id", header: "Order", render: (o) => <Link to={`/admin/orders/${o.orderId}`} className={ID_LINK}>{shortId(o.orderId)}</Link> },
            { key: "when", header: "Failed", render: (o) => <span className="whitespace-nowrap text-slate-600">{formatDateTime(o.updatedAt)}</span> },
            { key: "reason", header: "Reason", render: (o) => <span className="text-slate-800">{o.failureReason ?? "—"}</span> },
            { key: "retry", header: "Retry", render: (o) => <RetryHint retry={o.retry} /> },
          ]}
        />
      )}
    </>
  );
}
