import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { orderApi } from "../api/endpoints";
import { DataTable } from "../components/DataTable";
import { OrderPipeline } from "../components/OrderPipeline";
import { EmptyState, ErrorMessage, LoadMore, Spinner, StatusBadge } from "../components/ui";
import { useToast } from "../contexts/ToastContext";
import { useAsync, usePolling } from "../hooks/useAsync";
import type { AppNotification, Order } from "../types";
import { formatDateTime, formatMoney, isSettled, shortId, statusLabel, timeAgo } from "../utils/format";

const HEADLINES: Record<string, string> = {
  PENDING: "We've received your order",
  PROCESSING: "Stock reserved, taking payment",
  CONFIRMED: "Your order is confirmed",
  FAILED: "This order could not be completed",
  CANCELLED: "This order was cancelled",
};

export function OrderTimeline({ order }: { order: Order }) {
  if (!order.history?.length) return null;
  return (
    <ol className="timeline">
      {[...order.history].reverse().map((h, i) => (
        <li key={`${h.at}-${i}`}>
          <time dateTime={h.at}>{formatDateTime(h.at)}</time>
          <div>
            <strong>{h.event.replace(/([a-z])([A-Z])/g, "$1 $2")}</strong>
            {h.detail && <p className="muted">{h.detail}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function OrderItemsTable({ order }: { order: Order }) {
  return (
    <table className="table items-table">
      <caption className="sr-only">Items</caption>
      <thead>
        <tr>
          <th scope="col">Item</th>
          <th scope="col" className="num">
            Qty
          </th>
          <th scope="col" className="num">
            Price
          </th>
          <th scope="col" className="num">
            Total
          </th>
        </tr>
      </thead>
      <tbody>
        {order.items.map((i) => (
          <tr key={i.productId}>
            <td data-label="Item">{i.name}</td>
            <td data-label="Qty" className="num">
              {i.quantity}
            </td>
            <td data-label="Price" className="num">
              {formatMoney(i.unitPriceMinor, order.currency)}
            </td>
            <td data-label="Total" className="num">
              {formatMoney(i.lineTotalMinor, order.currency)}
            </td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row" colSpan={3}>
            Total
          </th>
          <td className="num strong">{formatMoney(order.totalMinor, order.currency)}</td>
        </tr>
      </tfoot>
    </table>
  );
}

export function OrderDetailPage() {
  const { orderId = "" } = useParams();
  const location = useLocation();
  const justPlaced = Boolean((location.state as { justPlaced?: boolean } | null)?.justPlaced);
  const { data: order, error, loading, reload, lastUpdated } = usePolling(
    (signal) => orderApi.get(orderId, signal),
    2000,
    (o) => !!o && !isSettled(o),
    [orderId],
  );

  if (loading && !order) return <Spinner label="Loading order" />;
  if (error && !order) {
    return <ErrorMessage error={error.status === 404 ? "We couldn't find this order in your account." : error} onRetry={reload} />;
  }
  if (!order) return null;
  const settled = isSettled(order);

  return (
    <article className="order-page">
      <Link to="/orders" className="back">
        ‹ My orders
      </Link>
      {justPlaced && order.status === "PENDING" && (
        <div className="notice notice-info" role="status">
          <p>
            Order placed. Order number <strong>{order.orderId}</strong>. We'll update this page as stock and payment are
            checked — it isn't confirmed yet.
          </p>
        </div>
      )}
      <header className="order-head">
        <div>
          <h1>{HEADLINES[order.status]}</h1>
          <p className="muted">
            Order <span className="mono-id">{order.orderId}</span> · placed {formatDateTime(order.createdAt)}
          </p>
        </div>
        <StatusBadge status={order.status} />
      </header>

      <OrderPipeline order={order} />

      {order.failureReason && (
        <div className="notice notice-error">
          <p>{order.failureReason}</p>
          {order.failureCategory === "PAYMENT_DECLINED" && <p className="muted">You were not charged. Any reserved items were released.</p>}
          {order.failureCategory === "BUSINESS" && <p className="muted">Nothing was charged. You can place a new order for the items still in stock.</p>}
        </div>
      )}

      {!settled && Date.now() - new Date(order.updatedAt).getTime() > 60_000 && (
        <div className="notice notice-warn">
          <p>This is taking longer than usual. The store team is alerted automatically — you don't need to order again.</p>
        </div>
      )}

      <p className="muted small live-note" aria-live="polite">
        {settled
          ? "This order is final."
          : `Updating automatically${lastUpdated ? ` · checked ${timeAgo(new Date(lastUpdated).toISOString())}` : ""}`}
      </p>

      <div className="two-col">
        <section>
          <h2>Items</h2>
          <OrderItemsTable order={order} />
        </section>
        <section>
          <h2>History</h2>
          <OrderTimeline order={order} />
        </section>
      </div>
    </article>
  );
}

export function OrdersPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [more, setMore] = useState<Order[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { data, error, loading, reload } = useAsync(async () => {
    const page = await orderApi.list();
    setMore([]);
    setNext(page.nextToken);
    return page.items;
  }, []);
  const orders = [...(data ?? []), ...more];

  async function loadMore() {
    setBusy(true);
    try {
      const page = await orderApi.list(next);
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
      <h1>My orders</h1>
      {loading && <Spinner label="Loading orders" />}
      {error && <ErrorMessage error={error} onRetry={reload} />}
      {!loading && !error && orders.length === 0 && (
        <EmptyState title="No orders yet" action={<Link className="btn btn-primary" to="/">Start shopping</Link>}>
          Orders you place will appear here with their progress.
        </EmptyState>
      )}
      {orders.length > 0 && (
        <DataTable
          caption="Your orders"
          rows={orders}
          rowKey={(o) => o.orderId}
          onRowClick={(o) => navigate(`/orders/${o.orderId}`)}
          columns={[
            { key: "id", header: "Order", render: (o) => <Link to={`/orders/${o.orderId}`}>{shortId(o.orderId)}</Link> },
            { key: "date", header: "Placed", render: (o) => formatDateTime(o.createdAt) },
            { key: "items", header: "Items", align: "right", render: (o) => o.itemCount },
            { key: "total", header: "Total", align: "right", render: (o) => formatMoney(o.totalMinor, o.currency) },
            { key: "progress", header: "Progress", render: (o) => <OrderPipeline order={o} compact /> },
            { key: "status", header: "Status", render: (o) => <StatusBadge status={o.status} /> },
          ]}
        />
      )}
      <LoadMore nextToken={next} loading={busy} onClick={loadMore} />
    </>
  );
}

export function NotificationsPage() {
  const { data, error, loading, reload } = useAsync(() => orderApi.notifications(), []);
  const items: AppNotification[] = data?.items ?? [];
  return (
    <>
      <h1>Notifications</h1>
      {loading && <Spinner label="Loading notifications" />}
      {error && <ErrorMessage error={error} onRetry={reload} />}
      {!loading && !error && items.length === 0 && (
        <EmptyState title="Nothing here yet">You'll get a notification when an order is confirmed or can't be completed.</EmptyState>
      )}
      <ul className="notes">
        {items.map((n) => (
          <li key={n.notificationId} className={`note note-${n.type === "OrderConfirmed" ? "ok" : "bad"}`}>
            <div className="note-head">
              <strong>{n.title}</strong>
              <time className="muted small" dateTime={n.createdAt}>
                {formatDateTime(n.createdAt)}
              </time>
            </div>
            <p>{n.message}</p>
            <p className="muted small">
              <Link to={`/orders/${n.orderId}`}>View order</Link>
              {n.channels.includes("EMAIL") && ` · Email: ${statusLabel(n.emailStatus)} (sent to the mail service, delivery not guaranteed)`}
            </p>
          </li>
        ))}
      </ul>
    </>
  );
}
