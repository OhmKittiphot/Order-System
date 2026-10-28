import { useState } from "react";
import { Link } from "react-router-dom";
import { productApi } from "../api/endpoints";
import { Button, EmptyState, ErrorMessage, Eyebrow, LoadMore, ProductArt, Skeleton, SkeletonGroup } from "../components/ui";
import { useCart } from "../contexts/CartContext";
import { useToast } from "../contexts/ToastContext";
import { useAsync } from "../hooks/useAsync";
import type { Product } from "../types";
import { formatMoney } from "../utils/format";

export function StockNote({ available }: { available: number }) {
  const base = "inline-flex items-center gap-1.5 text-[0.8125rem] font-medium";
  const dot = "relative flex size-1.5";
  if (available <= 0)
    return (
      <span className={`${base} text-red-700`}>
        <span className={`${dot} rounded-full bg-red-500`} aria-hidden="true" />
        Out of stock
      </span>
    );
  if (available <= 5)
    return (
      <span className={`${base} text-amber-800`}>
        <span className={dot} aria-hidden="true">
          <span className="absolute inset-0 animate-ping rounded-full bg-amber-400 opacity-75 motion-reduce:animate-none" />
          <span className="relative size-1.5 rounded-full bg-amber-500" />
        </span>
        Only {available} left
      </span>
    );
  return (
    <span className={`${base} text-slate-600`}>
      <span className={`${dot} rounded-full bg-emerald-500`} aria-hidden="true" />
      {available} in stock
    </span>
  );
}

const PROMISES = [
  { k: "01", t: "Live stock check", d: "Reserved the moment you order" },
  { k: "02", t: "Pay once it's held", d: "No charge for what we can't ship" },
  { k: "03", t: "Every step, in view", d: "Watch your order move in real time" },
];

/** Decorative: a floating order card that previews the tracking experience. */
function HeroOrderCard() {
  const steps = [
    { l: "Received", c: "bg-emerald-500" },
    { l: "Stock", c: "bg-emerald-500" },
    { l: "Payment", c: "bg-amber-400 animate-pulse motion-reduce:animate-none" },
    { l: "Notified", c: "bg-slate-200" },
  ];
  return (
    <div className="relative mx-auto w-full max-w-sm lg:mx-0" aria-hidden="true">
      <div className="absolute -inset-8 rounded-full bg-[conic-gradient(from_120deg,var(--color-cobalt-300),var(--color-ember-300),var(--color-cobalt-100),var(--color-cobalt-300))] opacity-50 blur-3xl" />
      <div className="glass relative rotate-[2deg] rounded-[1.75rem] p-5 motion-safe:animate-float">
        <div className="flex items-center justify-between">
          <span className="eyebrow">Order · 7F3A91C2</span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2 py-0.5 text-[0.6875rem] font-semibold text-amber-800 ring-1 ring-amber-500/30">
            <span className="size-1.5 animate-pulse rounded-full bg-amber-500 motion-reduce:animate-none" />
            Processing
          </span>
        </div>
        <p className="mt-4 font-display text-xl font-semibold tracking-tight text-ink">Stock reserved, taking payment</p>
        <div className="mt-5 grid grid-cols-4 gap-1.5">
          {steps.map((s) => (
            <div key={s.l} className="space-y-2">
              <div className={`h-1.5 rounded-full ${s.c}`} />
              <p className="text-[0.6875rem] font-medium text-slate-500">{s.l}</p>
            </div>
          ))}
        </div>
        <div className="mt-5 flex items-center gap-3 rounded-2xl bg-white/70 p-3 ring-1 ring-slate-900/5">
          <div className="grid size-11 place-items-center rounded-xl bg-linear-to-br from-cobalt-100 to-ember-300/60 font-display text-sm font-bold text-cobalt-700">MK</div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink">Mechanical Keyboard</p>
            <p className="text-xs text-slate-500">Qty 1</p>
          </div>
          <p className="font-display text-sm font-semibold text-ink">$129.00</p>
        </div>
      </div>
      <div className="glass absolute -bottom-6 -left-4 flex items-center gap-2 rounded-2xl px-3 py-2 motion-safe:animate-float [animation-delay:-3.5s] sm:-left-10">
        <span className="grid size-7 place-items-center rounded-lg bg-emerald-500 text-white">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.4" className="size-3.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="m3.5 8.5 3 3 6-7" />
          </svg>
        </span>
        <span className="text-xs font-semibold text-ink">2 units held for you</span>
      </div>
    </div>
  );
}

function CatalogSkeleton() {
  return (
    <SkeletonGroup label="Loading products" className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="surface group overflow-hidden p-0 lg:first:col-span-2">
          <Skeleton className="aspect-[4/3] w-full rounded-none lg:group-first:aspect-[2/1]" />
          <div className="space-y-3 p-5">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-3 w-full" />
            <div className="flex items-center justify-between pt-2">
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-10 w-28" />
            </div>
          </div>
        </div>
      ))}
    </SkeletonGroup>
  );
}

export function CatalogPage() {
  const { dispatch, lines } = useCart();
  const toast = useToast();
  const [extra, setExtra] = useState<Product[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const { data, error, loading, reload } = useAsync(async () => {
    const page = await productApi.list();
    setExtra([]);
    setNext(page.nextToken);
    return page.items;
  }, []);

  const products = [...(data ?? []), ...extra];

  async function more() {
    setLoadingMore(true);
    try {
      const page = await productApi.list(next);
      setExtra((e) => [...e, ...page.items]);
      setNext(page.nextToken);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setLoadingMore(false);
    }
  }

  function add(p: Product) {
    const inCart = lines.find((l) => l.productId === p.productId)?.quantity ?? 0;
    if (inCart >= p.available) {
      toast(`All ${p.available} available ${p.name} are already in your cart.`, "info");
      return;
    }
    dispatch({ type: "add", product: p });
    toast(`Added ${p.name} to your cart.`, "success");
  }

  return (
    <>
      <section className="mb-20 grid items-center gap-14 lg:mb-24 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] lg:gap-10">
        <div className="animate-rise">
          <Eyebrow className="mb-6">Desk hardware · Live inventory</Eyebrow>
          <h1 className="font-display text-[2.75rem] leading-[0.98] font-bold tracking-[-0.045em] sm:text-6xl lg:text-[4.5rem]">
            Gear for the desk, shipped once it's <span className="text-gradient">really yours.</span>
          </h1>
          <p className="mt-7 max-w-xl text-lg leading-relaxed text-slate-600">
            Every order is checked against live stock and paid before we confirm it. You can follow each step on the order
            page.
          </p>
          <ul className="mt-10 grid gap-3 sm:grid-cols-3">
            {PROMISES.map((p, i) => (
              <li
                key={p.k}
                className="group rounded-2xl border border-white/80 bg-white/55 p-4 backdrop-blur transition-[transform,box-shadow] duration-300 hover:-translate-y-0.5 hover:shadow-[0_12px_30px_-14px_rgb(42_77_255/0.45)] motion-safe:animate-rise"
                style={{ animationDelay: `${150 + i * 80}ms` }}
              >
                <span className="font-mono text-[0.6875rem] font-medium text-cobalt-600">{p.k}</span>
                <p className="mt-1 text-sm font-semibold text-ink">{p.t}</p>
                <p className="mt-0.5 text-[0.8125rem] leading-snug text-slate-600">{p.d}</p>
              </li>
            ))}
          </ul>
        </div>
        <HeroOrderCard />
      </section>

      <div className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b border-slate-200/80 pb-5">
        <div>
          <Eyebrow>The collection</Eyebrow>
          <h2 className="mt-2 font-display text-3xl font-bold tracking-tight">Shop the range</h2>
        </div>
        {products.length > 0 && (
          <p className="font-mono text-xs tracking-wider text-slate-500 uppercase">
            {products.length} {products.length === 1 ? "item" : "items"}
          </p>
        )}
      </div>

      {loading && <CatalogSkeleton />}
      {error && <ErrorMessage error={error} onRetry={reload} />}
      {!loading && !error && products.length === 0 && (
        <EmptyState title="No products yet" art="box">
          An administrator can add products in Admin › Products &amp; stock.
        </EmptyState>
      )}

      <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {products.map((p, i) => (
          <li
            key={p.productId}
            className="group relative flex animate-rise flex-col overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgb(11_13_20/0.04)] transition-[transform,box-shadow,border-color] duration-500 ease-out-expo hover:-translate-y-1.5 hover:border-cobalt-200 hover:shadow-[0_28px_50px_-24px_rgb(42_77_255/0.45)] motion-reduce:hover:translate-y-0 lg:first:col-span-2"
            style={{ animationDelay: `${Math.min(i, 9) * 60}ms` }}
          >
            <Link to={`/products/${p.productId}`} className="flex flex-1 flex-col text-inherit no-underline focus-visible:-outline-offset-4">
              <div className="relative grid aspect-[4/3] place-items-center overflow-hidden bg-slate-100 lg:group-first:aspect-[2/1]">
                <div className="w-full transition-transform duration-700 ease-out-expo group-hover:scale-[1.06] motion-reduce:group-hover:scale-100">
                  <ProductArt name={p.name} category={p.category} imageUrl={p.imageUrl} />
                </div>
                <span className="glass absolute top-3 left-3 rounded-full px-2.5 py-1 font-mono text-[0.625rem] font-medium tracking-[0.12em] text-slate-700 uppercase">
                  {p.category}
                </span>
                <span
                  className="absolute right-3 bottom-3 grid size-10 translate-y-2 place-items-center rounded-full bg-ink text-white opacity-0 shadow-lg transition-all duration-300 group-hover:translate-y-0 group-hover:opacity-100 max-md:hidden"
                  aria-hidden="true"
                >
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4 -rotate-45">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 8h10m-4-4 4 4-4 4" />
                  </svg>
                </span>
              </div>
              <div className="flex flex-1 flex-col px-5 pt-5">
                <h2 className="font-display text-lg leading-snug font-semibold tracking-tight text-ink lg:group-first:text-2xl">{p.name}</h2>
                <p className="mt-1.5 line-clamp-2 flex-1 text-sm text-slate-600">{p.description}</p>
              </div>
            </Link>
            <div className="flex items-end justify-between gap-3 px-5 pt-4 pb-5">
              <div className="flex flex-col gap-1">
                <div className="font-display text-xl font-bold tracking-tight text-ink tabular-nums">{formatMoney(p.priceMinor, p.currency)}</div>
                <StockNote available={p.available} />
              </div>
              <Button variant="secondary" onClick={() => add(p)} disabled={!p.inStock} aria-label={`Add ${p.name} to cart`}>
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" className="size-3.5" aria-hidden="true">
                  <path strokeLinecap="round" d="M8 3v10M3 8h10" />
                </svg>
                Add to cart
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <LoadMore nextToken={next} loading={loadingMore} onClick={more} />
    </>
  );
}
