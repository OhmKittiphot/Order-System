import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { orderApi, productApi } from "../api/endpoints";
import { Button, EmptyState, ErrorMessage, Eyebrow, NoticeIcon, PAGE_TITLE, ProductArt, noticeClass } from "../components/ui";
import { useAuth } from "../contexts/AuthContext";
import { MAX_QTY, cartProblems, estimatedTotal, useCart } from "../contexts/CartContext";
import { cartSignature, checkoutKey, clearCheckoutKey } from "../utils/idempotency";
import { formatMoney } from "../utils/format";

export function CartPage() {
  const { lines, dispatch } = useCart();
  const [checking, setChecking] = useState(false);

  // Refresh stock and prices for items already in the cart.
  useEffect(() => {
    if (lines.length === 0) return;
    let cancelled = false;
    setChecking(true);
    Promise.all(lines.map((l) => productApi.get(l.productId).catch(() => null)))
      .then((products) => {
        if (!cancelled) dispatch({ type: "refreshStock", products: products.filter((p) => p !== null) });
      })
      .finally(() => !cancelled && setChecking(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (lines.length === 0) {
    return (
      <EmptyState title="Your cart is empty" art="cart" action={<Link className="btn btn-primary" to="/">Browse products</Link>}>
        Add something from the shop to get started.
      </EmptyState>
    );
  }
  const currency = lines[0]!.currency;
  const problems = cartProblems(lines);

  return (
    <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_24rem] lg:gap-12">
      <section>
        <div className="mb-8 animate-rise">
          <Eyebrow>Checkout</Eyebrow>
          <h1 className={`${PAGE_TITLE} mt-3 font-bold`}>
            Cart{" "}
            <span className="align-top font-mono text-base font-medium tracking-normal text-slate-400 tabular-nums">
              ({lines.reduce((n, l) => n + l.quantity, 0)})
            </span>
          </h1>
        </div>
        <ul className="space-y-3">
          {lines.map((l, i) => (
            <li
              key={l.productId}
              className="group grid animate-rise grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-x-4 gap-y-3 rounded-3xl border border-slate-200/80 bg-white p-3 pr-4 shadow-[0_1px_2px_rgb(11_13_20/0.04)] transition-[border-color,box-shadow] duration-300 hover:border-cobalt-200 hover:shadow-[0_18px_40px_-24px_rgb(42_77_255/0.45)] sm:grid-cols-[5.5rem_minmax(0,1fr)_5.5rem_7.5rem_auto] sm:pr-5"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <div className="row-span-2 overflow-hidden rounded-2xl sm:row-span-1">
                <ProductArt name={l.name} category={l.name} />
              </div>
              <div className="min-w-0 max-sm:col-start-2 max-sm:row-start-1">
                <Link to={`/products/${l.productId}`} className="font-display text-base font-semibold tracking-tight text-ink no-underline hover:text-cobalt-700">
                  {l.name}
                </Link>
                <div className="mt-0.5 font-mono text-xs text-slate-500 tabular-nums">{formatMoney(l.priceMinor, l.currency)} each</div>
              </div>
              <label className="sr-only" htmlFor={`q-${l.productId}`}>
                Quantity of {l.name}
              </label>
              <input
                id={`q-${l.productId}`}
                className="min-h-10 w-20 text-center font-semibold tabular-nums max-sm:col-start-2 max-sm:row-start-2 sm:w-full"
                type="number"
                min={1}
                max={Math.max(1, Math.min(l.available, MAX_QTY))}
                value={l.quantity}
                onChange={(e) => dispatch({ type: "setQty", productId: l.productId, quantity: Number(e.target.value) })}
              />
              <div className="text-right font-display text-lg font-bold whitespace-nowrap text-ink tabular-nums max-sm:col-start-3 max-sm:row-start-1">
                {formatMoney(l.priceMinor * l.quantity, l.currency)}
              </div>
              <button
                className="btn btn-ghost btn-small text-slate-500 hover:bg-red-50 hover:text-red-700 max-sm:col-start-3 max-sm:row-start-2 max-sm:justify-self-end"
                onClick={() => dispatch({ type: "remove", productId: l.productId })}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
        {checking && (
          <p className="mt-4 inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1.5 text-[0.8125rem] text-slate-600 ring-1 ring-slate-200" role="status">
            <span className="size-3 animate-spin rounded-full border-2 border-cobalt-100 border-t-cobalt-600 motion-reduce:animate-none" aria-hidden="true" />
            Checking current stock…
          </p>
        )}
      </section>
      <CheckoutSummary currency={currency} problems={problems} />
    </div>
  );
}

const NEXT_STEPS = ["Received", "Stock held", "Payment", "Confirmed"];

function CheckoutSummary({ currency, problems }: { currency: string; problems: string[] }) {
  const { lines, dispatch } = useCart();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const total = estimatedTotal(lines);

  async function placeOrder() {
    if (submitting) return; // guard against double clicks
    setSubmitting(true);
    setError(null);
    const items = lines.map((l) => ({ productId: l.productId, quantity: l.quantity }));
    const key = checkoutKey(cartSignature(items));
    try {
      const order = await orderApi.create(items, key);
      clearCheckoutKey();
      dispatch({ type: "clear" });
      navigate(`/orders/${order.orderId}`, { state: { justPlaced: true } });
    } catch (e) {
      // Keep the same idempotency key so "Try again" cannot create a duplicate order.
      setError(e as ApiError);
      setSubmitting(false);
    }
  }

  return (
    <aside
      className="relative isolate animate-rise overflow-hidden rounded-4xl bg-ink p-6 text-white shadow-[0_40px_80px_-30px_rgb(11_13_20/0.6)] [animation-delay:120ms] sm:p-7 lg:sticky lg:top-28"
      aria-labelledby="summary-title"
    >
      <div className="pointer-events-none absolute -top-24 -right-16 -z-10 size-64 rounded-full bg-cobalt-600/50 blur-3xl" aria-hidden="true" />
      <div className="pointer-events-none absolute -bottom-28 -left-16 -z-10 size-56 rounded-full bg-ember-500/25 blur-3xl" aria-hidden="true" />
      <h2 id="summary-title" className="font-display text-lg font-semibold text-white">
        Order summary
      </h2>
      <dl className="mt-6 tabular-nums">
        <div className="flex justify-between border-b border-dashed border-white/15 pb-4 text-sm text-slate-300">
          <dt>Items</dt>
          <dd className="text-right font-semibold text-white">{lines.reduce((n, l) => n + l.quantity, 0)}</dd>
        </div>
        <div className="pt-5">
          <dt className="eyebrow text-slate-400">Estimated total</dt>
          <dd className="mt-1 font-display text-[2.75rem] leading-none font-bold tracking-tight text-white">{formatMoney(total, currency)}</dd>
        </div>
      </dl>
      <p className="mt-4 text-[0.8125rem] leading-relaxed text-slate-400">
        The final amount is calculated by the store from current prices when you place the order. Payment is simulated.
      </p>

      <ol className="mt-6 grid grid-cols-4 gap-1.5" aria-hidden="true">
        {NEXT_STEPS.map((s, i) => (
          <li key={s} className="space-y-2">
            <div className={`h-1 rounded-full ${i === 0 ? "bg-linear-to-r from-cobalt-400 to-ember-400" : "bg-white/15"}`} />
            <p className="text-[0.6875rem] text-slate-400">{s}</p>
          </li>
        ))}
      </ol>

      {problems.length > 0 && (
        <div className={noticeClass("warn")} role="alert">
          <NoticeIcon tone="warn" />
          <div className="space-y-1">
            {problems.map((p) => (
              <p key={p}>{p}</p>
            ))}
          </div>
        </div>
      )}
      <div className="mt-6" />
      {error && <ErrorMessage error={error} />}
      {user ? (
        <Button className="btn-block min-h-13 text-[0.9375rem] focus-visible:outline-white" onClick={placeOrder} busy={submitting} disabled={problems.length > 0}>
          {submitting ? "Placing order" : "Place order"}
        </Button>
      ) : (
        <Link className="btn btn-primary btn-block min-h-13 text-[0.9375rem] focus-visible:outline-white" to="/login" state={{ from: "/cart" }}>
          Sign in to place your order
        </Link>
      )}
      <p className="mt-4 flex items-center justify-center gap-1.5 text-xs text-slate-400">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="size-3.5" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 7V5a3.5 3.5 0 0 1 7 0v2M3.5 7h9v6.5h-9z" />
        </svg>
        Protected against duplicate orders
      </p>
    </aside>
  );
}
