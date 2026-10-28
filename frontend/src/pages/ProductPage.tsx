import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { productApi } from "../api/endpoints";
import { BACK_LINK, Button, ErrorMessage, Eyebrow, ProductArt, Skeleton, SkeletonGroup } from "../components/ui";
import { MAX_QTY, useCart } from "../contexts/CartContext";
import { useToast } from "../contexts/ToastContext";
import { useAsync } from "../hooks/useAsync";
import { formatMoney } from "../utils/format";
import { StockNote } from "./CatalogPage";

const ASSURANCES = [
  { t: "Checked live", d: "Stock is reserved before payment", i: "M3 8.5 6.5 12 13 4.5" },
  { t: "Charged once", d: "Never billed for what can't ship", i: "M2.5 5h11v7h-11zM2.5 7.5h11" },
  { t: "Tracked", d: "Follow every step of the order", i: "M2 8h3l2-4 2 8 2-4h3" },
];

function ProductSkeleton() {
  return (
    <SkeletonGroup label="Loading product" className="grid gap-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <Skeleton className="aspect-[4/3] w-full rounded-4xl" />
      <div className="space-y-4 pt-4">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-12 w-4/5" />
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full rounded-3xl" />
      </div>
    </SkeletonGroup>
  );
}

export function ProductPage() {
  const { productId = "" } = useParams();
  const { dispatch } = useCart();
  const toast = useToast();
  const [qty, setQty] = useState(1);
  const { data: p, error, loading, reload } = useAsync(() => productApi.get(productId), [productId]);

  if (loading) return <ProductSkeleton />;
  if (error) return <ErrorMessage error={error.status === 404 ? "This product is no longer available." : error} onRetry={error.status === 404 ? undefined : reload} />;
  if (!p) return null;
  const max = Math.min(p.available, MAX_QTY);

  return (
    <article>
      <Link to="/" className={BACK_LINK}>
        <span className="grid size-6 place-items-center rounded-full bg-slate-100 transition-transform duration-300 group-hover/back:-translate-x-0.5" aria-hidden="true">
          ‹
        </span>
        All products
      </Link>
      <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-14">
        <div className="relative lg:sticky lg:top-28">
          <div className="absolute -inset-6 -z-10 rounded-[3rem] bg-[conic-gradient(from_90deg,var(--color-cobalt-200),var(--color-ember-300),var(--color-cobalt-100),var(--color-cobalt-200))] opacity-50 blur-3xl" aria-hidden="true" />
          <div className="animate-rise overflow-hidden rounded-4xl border border-white/80 shadow-[0_40px_80px_-40px_rgb(11_13_20/0.4)]">
            <ProductArt name={p.name} category={p.category} imageUrl={p.imageUrl} />
          </div>
          <span className="glass absolute top-4 left-4 rounded-full px-3 py-1.5 font-mono text-[0.6875rem] tracking-[0.12em] text-slate-700 uppercase" aria-hidden="true">
            {p.category}
          </span>
        </div>

        <div className="animate-rise [animation-delay:100ms]">
          <Eyebrow>{p.category}</Eyebrow>
          <h1 className="mt-4 font-display text-4xl leading-[1.02] font-bold tracking-[-0.035em] sm:text-5xl">{p.name}</h1>
          <div className="mt-6 flex flex-wrap items-center gap-4">
            <p className="font-display text-4xl font-bold tracking-tight text-ink tabular-nums">{formatMoney(p.priceMinor, p.currency)}</p>
            <span className="rounded-full bg-white/80 px-3 py-1 ring-1 ring-slate-200">
              <StockNote available={p.available} />
            </span>
          </div>
          <p className="mt-8 max-w-prose text-[1.0625rem] leading-relaxed text-slate-700">{p.description}</p>

          <form
            className="glass mt-10 rounded-3xl p-5 sm:p-6"
            onSubmit={(e) => {
              e.preventDefault();
              dispatch({ type: "add", product: p, quantity: qty });
              toast(`Added ${qty} × ${p.name} to your cart.`, "success");
            }}
          >
            <div className="mb-5 flex items-center justify-between gap-3 text-xs text-slate-500">
              <span className="eyebrow">Availability</span>
              <span className="font-mono tabular-nums">{p.available} units</span>
            </div>
            <div className="mb-6 h-1.5 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
              <div
                className={`h-full rounded-full transition-[width] duration-1000 ease-out-expo ${
                  p.available <= 0 ? "bg-red-500" : p.available <= 5 ? "bg-linear-to-r from-amber-400 to-ember-500" : "bg-linear-to-r from-cobalt-600 to-emerald-400"
                }`}
                style={{ width: `${Math.max(4, Math.min(100, (p.available / 20) * 100))}%` }}
              />
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="qty" className="text-sm font-semibold text-slate-800">
                  Quantity
                </label>
                <input
                  className="w-24 text-center font-display text-lg font-semibold tabular-nums"
                  id="qty"
                  type="number"
                  min={1}
                  max={Math.max(1, max)}
                  value={qty}
                  disabled={!p.inStock}
                  onChange={(e) => setQty(Math.max(1, Math.min(max, Number(e.target.value) || 1)))}
                />
              </div>
              <Button type="submit" className="group min-h-12 flex-1 text-[0.9375rem]" disabled={!p.inStock}>
                Add to cart
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" className="size-4 transition-transform duration-300 group-hover:translate-x-0.5" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 8h10m-4-4 4 4-4 4" />
                </svg>
              </Button>
            </div>
          </form>

          <ul className="mt-6 grid gap-3 sm:grid-cols-3">
            {ASSURANCES.map((a) => (
              <li key={a.t} className="flex gap-3 rounded-2xl p-3 transition-colors hover:bg-white/60">
                <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-cobalt-50 text-cobalt-600 ring-1 ring-cobalt-100" aria-hidden="true">
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4">
                    <path strokeLinecap="round" strokeLinejoin="round" d={a.i} />
                  </svg>
                </span>
                <span>
                  <span className="block text-sm font-semibold text-ink">{a.t}</span>
                  <span className="block text-xs leading-snug text-slate-600">{a.d}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </article>
  );
}
