import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { orderApi } from "../api/endpoints";
import { TABLE } from "../components/DataTable";
import { OrderPipeline } from "../components/OrderPipeline";
import {
  BACK_LINK,
  EmptyState,
  ErrorMessage,
  Eyebrow,
  LoadMore,
  NoticeIcon,
  PAGE_TITLE,
  PANEL,
  SECTION_TITLE,
  Skeleton,
  SkeletonGroup,
  StatusBadge,
  TEXT_LINK,
  noticeClass,
} from "../components/ui";
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

/** Ambient glow behind the order hero, keyed by status. */
const HERO_GLOW: Record<string, string> = {
  PENDING: "from-cobalt-300/60 via-cobalt-100/40 to-amber-200/50",
  PROCESSING: "from-amber-200/70 via-cobalt-100/40 to-cobalt-300/50",
  CONFIRMED: "from-emerald-200/70 via-emerald-50/40 to-cobalt-200/50",
  FAILED: "from-red-200/70 via-red-50/40 to-ember-300/40",
  CANCELLED: "from-slate-200/80 via-slate-50/40 to-slate-200/60",
};

export function OrderTimeline({ order }: { order: Order }) {
  if (!order.history?.length) return null;
  return (
    <ol className={PANEL}>
      {[...order.history].reverse().map((h, i) => (
        <li key={`${h.at}-${i}`} className="group relative grid animate-rise gap-0.5 pb-6 pl-8 last:pb-0" style={{ animationDelay: `${i * 50}ms` }}>
          <span className="absolute top-3 bottom-0 left-[0.4375rem] w-px bg-linear-to-b from-slate-200 to-slate-100 group-last:hidden" aria-hidden="true" />
          <span
            className={`absolute top-1 left-0 grid size-4 place-items-center rounded-full ${
              i === 0 ? "bg-cobalt-600 shadow-[0_0_0_4px_rgb(42_77_255/0.15)]" : "bg-white ring-2 ring-slate-200"
            }`}
            aria-hidden="true"
          >
            {i === 0 && <span className="size-1.5 rounded-full bg-white" />}
          </span>
          <time dateTime={h.at} className="font-mono text-[0.6875rem] tracking-wide text-slate-500 tabular-nums">
            {formatDateTime(h.at)}
          </time>
          <div>
            <strong className="text-sm font-semibold text-ink">{h.event.replace(/([a-z])([A-Z])/g, "$1 $2")}</strong>
            {h.detail && <p className="mt-0.5 text-[0.8125rem] text-slate-600">{h.detail}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function OrderItemsTable({ order }: { order: Order }) {
  return (
    <div className={TABLE.wrap}>
      <table className={TABLE.table}>
        <caption className="sr-only">Items</caption>
        <thead className={TABLE.thead}>
          <tr>
            <th scope="col" className={TABLE.th}>
              Item
            </th>
            <th scope="col" className={`${TABLE.th} text-right`}>
              Qty
            </th>
            <th scope="col" className={`${TABLE.th} text-right`}>
              Price
            </th>
            <th scope="col" className={`${TABLE.th} text-right`}>
              Total
            </th>
          </tr>
        </thead>
        <tbody className={TABLE.tbody}>
          {order.items.map((i) => (
            <tr key={i.productId} className={`${TABLE.tr} hover:bg-slate-50/60`}>
              <td data-label="Item" className={`${TABLE.td} font-semibold text-ink`}>
                {i.name}
              </td>
              <td data-label="Qty" className={`${TABLE.td} ${TABLE.num}`}>
                <span className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-xs">×{i.quantity}</span>
              </td>
              <td data-label="Price" className={`${TABLE.td} ${TABLE.num} text-slate-600`}>
                {formatMoney(i.unitPriceMinor, order.currency)}
              </td>
              <td data-label="Total" className={`${TABLE.td} ${TABLE.num} font-medium`}>
                {formatMoney(i.lineTotalMinor, order.currency)}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot className="max-md:block">
          <tr className="bg-ink text-white max-md:flex max-md:justify-between">
            <th scope="row" colSpan={3} className="px-6 py-4 text-left font-mono text-[0.6875rem] font-medium tracking-[0.14em] text-slate-300 uppercase">
              Total
            </th>
            <td className="px-6 py-4 text-right font-display text-xl font-bold whitespace-nowrap">{formatMoney(order.totalMinor, order.currency)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function OrderDetailSkeleton() {
  return (
    <SkeletonGroup label="Loading order" className="space-y-6">
      <Skeleton className="h-9 w-32 rounded-full" />
      <Skeleton className="h-44 w-full rounded-4xl" />
      <Skeleton className="h-36 w-full rounded-3xl" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-56 rounded-3xl" />
        <Skeleton className="h-56 rounded-3xl" />
      </div>
    </SkeletonGroup>
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

  if (loading && !order) return <OrderDetailSkeleton />;
  if (error && !order) {
    return <ErrorMessage error={error.status === 404 ? "We couldn't find this order in your account." : error} onRetry={reload} />;
  }
  if (!order) return null;
  const settled = isSettled(order);

  return (
    <article>
      <Link to="/orders" className={BACK_LINK}>
        <span className="grid size-6 place-items-center rounded-full bg-slate-100 transition-transform duration-300 group-hover/back:-translate-x-0.5" aria-hidden="true">
          ‹
        </span>
        My orders
      </Link>
      {justPlaced && order.status === "PENDING" && (
        <div className={noticeClass("info")} role="status">
          <NoticeIcon tone="info" />
          <p>
            Order placed. Order number <strong className="font-mono text-[0.8125rem] break-all">{order.orderId}</strong>. We'll update this page as stock and payment are
            checked — it isn't confirmed yet.
          </p>
        </div>
      )}

      <header className="relative isolate animate-rise overflow-hidden rounded-4xl border border-white/80 bg-white/60 p-6 backdrop-blur-xl sm:p-10">
        <div
          className={`absolute -top-1/2 -right-1/4 -z-10 size-[36rem] rounded-full bg-linear-to-br blur-3xl transition-colors duration-1000 motion-safe:animate-aurora ${
            HERO_GLOW[order.status] ?? HERO_GLOW.PENDING
          }`}
          aria-hidden="true"
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Eyebrow>Order tracking</Eyebrow>
          <StatusBadge status={order.status} />
        </div>
        <h1 className="mt-5 max-w-3xl font-display text-[2.25rem] leading-[1.02] font-bold tracking-[-0.035em] sm:text-[3.25rem]">{HEADLINES[order.status]}</h1>
        <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-slate-600">
          <span>
            Order <span className="rounded-lg bg-white/80 px-2 py-0.5 font-mono text-[0.8125rem] break-all text-ink ring-1 ring-slate-200">{order.orderId}</span>
          </span>
          <span>placed {formatDateTime(order.createdAt)}</span>
        </div>
        <p className="mt-6 inline-flex items-center gap-2 rounded-full bg-white/80 px-3 py-1.5 text-[0.8125rem] text-slate-600 ring-1 ring-slate-200/80" aria-live="polite">
          <span className="relative flex size-2" aria-hidden="true">
            {!settled && <span className="absolute inset-0 animate-ping rounded-full bg-emerald-400 opacity-75 motion-reduce:animate-none" />}
            <span className={`relative size-2 rounded-full ${settled ? "bg-slate-400" : "bg-emerald-500"}`} />
          </span>
          {settled
            ? "This order is final."
            : `Updating automatically${lastUpdated ? ` · checked ${timeAgo(new Date(lastUpdated).toISOString())}` : ""}`}
        </p>
      </header>

      <OrderPipeline order={order} />

      {order.failureReason && (
        <div className={noticeClass("error")}>
          <NoticeIcon tone="error" />
          <div className="space-y-1">
            <p className="font-semibold">{order.failureReason}</p>
            {order.failureCategory === "PAYMENT_DECLINED" && <p className="text-red-900/80">You were not charged. Any reserved items were released.</p>}
            {order.failureCategory === "BUSINESS" && <p className="text-red-900/80">Nothing was charged. You can place a new order for the items still in stock.</p>}
          </div>
        </div>
      )}

      {!settled && Date.now() - new Date(order.updatedAt).getTime() > 60_000 && (
        <div className={noticeClass("warn")}>
          <NoticeIcon tone="warn" />
          <p>This is taking longer than usual. The store team is alerted automatically — you don't need to order again.</p>
        </div>
      )}

      <div className="mt-10 grid items-start gap-10 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <section>
          <h2 className={SECTION_TITLE}>
            <span className="h-4 w-1 rounded-full bg-cobalt-600" aria-hidden="true" />
            Items
          </h2>
          <OrderItemsTable order={order} />
        </section>
        <section>
          <h2 className={SECTION_TITLE}>
            <span className="h-4 w-1 rounded-full bg-ember-500" aria-hidden="true" />
            History
          </h2>
          <OrderTimeline order={order} />
        </section>
      </div>
    </article>
  );
}

function OrdersSkeleton() {
  return (
    <SkeletonGroup label="Loading orders" className="space-y-3">
      {Array.from({ length: 4 }, (_, i) => (
        <Skeleton key={i} className="h-24 w-full rounded-3xl" />
      ))}
    </SkeletonGroup>
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
      <div className="mb-10 animate-rise">
        <Eyebrow>Your account</Eyebrow>
        <h1 className={`${PAGE_TITLE} mt-3 font-bold`}>My orders</h1>
      </div>
      {loading && <OrdersSkeleton />}
      {error && <ErrorMessage error={error} onRetry={reload} />}
      {!loading && !error && orders.length === 0 && (
        <EmptyState title="No orders yet" art="orders" action={<Link className="btn btn-primary" to="/">Start shopping</Link>}>
          Orders you place will appear here with their progress.
        </EmptyState>
      )}
      {orders.length > 0 && (
        <ul className="space-y-3" aria-label="Your orders">
          {orders.map((o, i) => (
            <li
              key={o.orderId}
              onClick={() => navigate(`/orders/${o.orderId}`)}
              className="group relative grid animate-rise cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-x-6 gap-y-4 rounded-3xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgb(11_13_20/0.04)] transition-[transform,border-color,box-shadow] duration-300 ease-out-expo hover:-translate-y-0.5 hover:border-cobalt-200 hover:shadow-[0_20px_40px_-24px_rgb(42_77_255/0.5)] motion-reduce:hover:translate-y-0 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto_auto] sm:px-6"
              style={{ animationDelay: `${Math.min(i, 10) * 50}ms` }}
            >
              <div className="min-w-0">
                <Link
                  to={`/orders/${o.orderId}`}
                  className="font-mono text-sm font-semibold text-ink no-underline after:absolute after:inset-0 after:rounded-3xl after:content-[''] group-hover:text-cobalt-700"
                  onClick={(e) => e.stopPropagation()}
                >
                  #{shortId(o.orderId)}
                </Link>
                <p className="mt-1 text-[0.8125rem] text-slate-500">
                  {formatDateTime(o.createdAt)} · {o.itemCount} {o.itemCount === 1 ? "item" : "items"}
                </p>
              </div>
              <div className="flex flex-col gap-2 max-sm:order-last max-sm:col-span-2">
                <span className="eyebrow text-[0.625rem]">Progress</span>
                <OrderPipeline order={o} compact />
              </div>
              <div className="flex flex-col items-end gap-1.5 sm:items-start">
                <StatusBadge status={o.status} />
                <span className="font-display text-lg font-bold text-ink tabular-nums">{formatMoney(o.totalMinor, o.currency)}</span>
              </div>
              <span
                className="grid size-10 place-items-center rounded-full bg-slate-100 text-slate-500 transition-all duration-300 group-hover:bg-ink group-hover:text-white max-sm:hidden"
                aria-hidden="true"
              >
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4 transition-transform duration-300 group-hover:translate-x-0.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 8h10m-4-4 4 4-4 4" />
                </svg>
              </span>
            </li>
          ))}
        </ul>
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
      <div className="mb-10 flex flex-wrap items-end justify-between gap-4 animate-rise">
        <div>
          <Eyebrow>Inbox</Eyebrow>
          <h1 className={`${PAGE_TITLE} mt-3 font-bold`}>Notifications</h1>
        </div>
        {items.length > 0 && (
          <span className="rounded-full bg-white/80 px-3 py-1 font-mono text-xs text-slate-600 ring-1 ring-slate-200">{items.length} updates</span>
        )}
      </div>
      {loading && (
        <SkeletonGroup label="Loading notifications" className="max-w-3xl space-y-4">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-3xl" />
          ))}
        </SkeletonGroup>
      )}
      {error && <ErrorMessage error={error} onRetry={reload} />}
      {!loading && !error && items.length === 0 && (
        <EmptyState title="Nothing here yet" art="bell">
          You'll get a notification when an order is confirmed or can't be completed.
        </EmptyState>
      )}
      <ul className="relative max-w-3xl space-y-4 before:absolute before:top-6 before:bottom-6 before:left-[1.4375rem] before:w-px before:bg-linear-to-b before:from-slate-200 before:via-slate-200 before:to-transparent before:content-[''] max-sm:before:hidden">
        {items.map((n, i) => {
          const ok = n.type === "OrderConfirmed";
          return (
            <li key={n.notificationId} className="relative flex animate-rise gap-4 sm:gap-5" style={{ animationDelay: `${Math.min(i, 10) * 60}ms` }}>
              <span
                className={`relative z-10 grid size-12 shrink-0 place-items-center rounded-2xl ring-4 ring-slate-50 max-sm:hidden ${
                  ok ? "bg-emerald-500 text-white shadow-[0_8px_20px_-8px_rgb(16_185_129/0.8)]" : "bg-red-500 text-white shadow-[0_8px_20px_-8px_rgb(239_68_68/0.8)]"
                }`}
                aria-hidden="true"
              >
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.2" className="size-4">
                  <path strokeLinecap="round" strokeLinejoin="round" d={ok ? "m3.5 8.5 3 3 6-7" : "M5 5l6 6M11 5l-6 6"} />
                </svg>
              </span>
              <div
                className={`min-w-0 flex-1 rounded-3xl border bg-white p-5 shadow-[0_1px_2px_rgb(11_13_20/0.04)] transition-shadow duration-300 hover:shadow-[0_18px_40px_-24px_rgb(11_13_20/0.3)] sm:p-6 ${
                  ok ? "border-emerald-100" : "border-red-100"
                }`}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <strong className="font-display text-base font-semibold tracking-tight text-ink">{n.title}</strong>
                  <time className="font-mono text-[0.6875rem] text-slate-500 tabular-nums" dateTime={n.createdAt}>
                    {formatDateTime(n.createdAt)}
                  </time>
                </div>
                <p className="mt-1.5 text-sm leading-relaxed text-slate-700">{n.message}</p>
                <p className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-slate-100 pt-3 text-[0.8125rem] text-slate-600">
                  <Link to={`/orders/${n.orderId}`} className={TEXT_LINK}>
                    View order
                  </Link>
                  {n.channels.includes("EMAIL") && ` · Email: ${statusLabel(n.emailStatus)} (sent to the mail service, delivery not guaranteed)`}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
    </>
  );
}
