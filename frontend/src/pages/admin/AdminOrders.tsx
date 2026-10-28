import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { adminApi } from "../../api/endpoints";
import { DataTable } from "../../components/DataTable";
import { OrderPipeline } from "../../components/OrderPipeline";
import { Button, ConfirmDialog, EmptyState, ErrorMessage, LoadMore, Spinner, StatusBadge } from "../../components/ui";
import { useToast } from "../../contexts/ToastContext";
import { useAsync, usePolling } from "../../hooks/useAsync";
import type { Order, OrderStatus, RetryDecision } from "../../types";
import { formatDateTime, formatMoney, isSettled, shortId, statusLabel, timeAgo } from "../../utils/format";
import { OrderItemsTable, OrderTimeline } from "../OrderPages";

const STATUSES: (OrderStatus | "")[] = ["", "PENDING", "PROCESSING", "CONFIRMED", "FAILED", "CANCELLED"];

export function RetryHint({ retry }: { retry?: RetryDecision | null }) {
  if (!retry) return <span className="muted">—</span>;
  if (!retry.retryable && retry.reason.startsWith("Order is still being processed")) return <span className="muted small">In progress</span>;
  return retry.retryable ? (
    <span className="retry-yes">Can retry</span>
  ) : (
    <span className="muted small" title={retry.reason}>
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
      <div className="page-head">
        <h1>Orders</h1>
        <div className="toolbar">
          <label htmlFor="status-filter" className="muted small">
            Status
          </label>
          <select id="status-filter" value={status} onChange={(e) => setParams(e.target.value ? { status: e.target.value } : {})}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s ? statusLabel(s) : "All statuses"}
              </option>
            ))}
          </select>
          <Button variant="secondary" onClick={reload}>
            Refresh
          </Button>
        </div>
      </div>
      {loading && <Spinner label="Loading orders" />}
      {error && <ErrorMessage error={error} onRetry={reload} />}
      {!loading && !error && rows.length === 0 && <EmptyState title="No orders match this filter" />}
      {rows.length > 0 && (
        <DataTable
          caption="Orders"
          rows={rows}
          rowKey={(o) => o.orderId}
          onRowClick={(o) => navigate(`/admin/orders/${o.orderId}`)}
          columns={[
            { key: "id", header: "Order", render: (o) => <Link to={`/admin/orders/${o.orderId}`}>{shortId(o.orderId)}</Link> },
            { key: "customer", header: "Customer", render: (o) => <span className="muted nowrap">{shortId(o.customerId)}</span> },
            { key: "created", header: "Created", render: (o) => <span className="nowrap">{formatDateTime(o.createdAt)}</span> },
            { key: "total", header: "Total", align: "right", render: (o) => formatMoney(o.totalMinor, o.currency) },
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

  if (loading && !order) return <Spinner label="Loading order" />;
  if (error && !order) return <ErrorMessage error={error} onRetry={reload} />;
  if (!order) return null;
  const cancellable = !["CONFIRMED", "CANCELLED"].includes(order.status);

  return (
    <article>
      <Link to="/admin/orders" className="back">
        ‹ Orders
      </Link>
      <header className="order-head">
        <div>
          <h1 className="mono-id">{order.orderId}</h1>
          <p className="muted">
            {order.customer.displayName ?? "Customer"} ({shortId(order.customerId)}) · created {formatDateTime(order.createdAt)} ·
            updated {timeAgo(order.updatedAt)}
          </p>
        </div>
        <StatusBadge status={order.status} />
      </header>
      <OrderPipeline order={order} />

      <section className="panel">
        <h2>Recovery</h2>
        <p>{order.retry.reason}</p>
        {order.failureReason && <p className="muted">Failure: {order.failureReason}</p>}
        <dl className="facts">
          <div>
            <dt>Attempt</dt>
            <dd>{order.retryCount}</dd>
          </div>
          <div>
            <dt>Worker runs</dt>
            <dd>{order.processingAttempts ?? 0}</dd>
          </div>
          <div>
            <dt>Last retry</dt>
            <dd>{order.lastRetryAt ? formatDateTime(order.lastRetryAt) : "—"}</dd>
          </div>
        </dl>
        {result && (
          <div className="notice notice-info" role="status">
            <p>{result}</p>
          </div>
        )}
        <div className="actions">
          <Button disabled={!order.retry.retryable} onClick={() => setDialog("retry")}>
            Retry order
          </Button>
          <Button variant="danger" disabled={!cancellable} onClick={() => setDialog("cancel")}>
            Cancel order
          </Button>
        </div>
      </section>

      <div className="two-col">
        <section>
          <h2>Items</h2>
          <OrderItemsTable order={order} />
          <h2>Payments</h2>
          {order.payments.length === 0 ? (
            <p className="muted">No payment attempts.</p>
          ) : (
            <ul className="plain-list">
              {order.payments.map((p) => (
                <li key={`${p.attempt}`}>
                  Attempt {p.attempt}: <StatusBadge status={p.status} /> {formatMoney(p.amountMinor, p.currency)} · {p.provider}
                  {p.reason && <span className="muted"> · {p.reason}</span>}
                </li>
              ))}
            </ul>
          )}
        </section>
        <section>
          <h2>History</h2>
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
      <div className="page-head">
        <h1>Failed orders</h1>
        <Button
          variant="secondary"
          onClick={() => {
            failed.reload();
            ops.reload();
          }}
        >
          Refresh
        </Button>
      </div>
      <p className="muted lead">
        Out-of-stock orders can be retried after restocking. Declined payments can't be retried. Orders stuck in processing
        (usually because a message reached a dead-letter queue) can be retried after a short wait.
      </p>

      <h2>Stuck in processing</h2>
      {ops.loading && <Spinner />}
      {ops.error && <ErrorMessage error={ops.error} onRetry={ops.reload} />}
      {ops.data && ops.data.stuckOrders.length === 0 && <p className="muted">No orders are stuck right now.</p>}
      {ops.data && ops.data.stuckOrders.length > 0 && (
        <DataTable
          rows={ops.data.stuckOrders}
          rowKey={(o) => o.orderId}
          onRowClick={(o) => navigate(`/admin/orders/${o.orderId}`)}
          columns={[
            { key: "id", header: "Order", render: (o) => <Link to={`/admin/orders/${o.orderId}`}>{shortId(o.orderId)}</Link> },
            { key: "status", header: "Status", render: (o) => <StatusBadge status={o.status} /> },
            { key: "since", header: "No progress since", render: (o) => timeAgo(o.updatedAt) },
            { key: "retry", header: "Action", render: (o) => <RetryHint retry={o.retry} /> },
          ]}
        />
      )}

      <h2>Failed</h2>
      {failed.loading && <Spinner />}
      {failed.error && <ErrorMessage error={failed.error} onRetry={failed.reload} />}
      {failed.data && failed.data.items.length === 0 && <p className="muted">No failed orders.</p>}
      {failed.data && failed.data.items.length > 0 && (
        <DataTable
          rows={failed.data.items}
          rowKey={(o) => o.orderId}
          onRowClick={(o) => navigate(`/admin/orders/${o.orderId}`)}
          columns={[
            { key: "id", header: "Order", render: (o) => <Link to={`/admin/orders/${o.orderId}`}>{shortId(o.orderId)}</Link> },
            { key: "when", header: "Failed", render: (o) => formatDateTime(o.updatedAt) },
            { key: "reason", header: "Reason", render: (o) => o.failureReason ?? "—" },
            { key: "retry", header: "Retry", render: (o) => <RetryHint retry={o.retry} /> },
          ]}
        />
      )}
    </>
  );
}
