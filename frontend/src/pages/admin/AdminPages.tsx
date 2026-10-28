import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { adminApi, type ProductInput } from "../../api/endpoints";
import { DataTable } from "../../components/DataTable";
import {
  Button,
  ConfirmDialog,
  ErrorMessage,
  Eyebrow,
  Field,
  ID_LINK,
  NoticeIcon,
  PAGE_HEAD,
  PAGE_TITLE,
  ProductArt,
  QUIET_EMPTY,
  SECTION_TITLE,
  Skeleton,
  SkeletonGroup,
  StatusBadge,
  TEXT_LINK,
  TableSkeleton,
  noticeClass,
} from "../../components/ui";
import { useToast } from "../../contexts/ToastContext";
import { useAsync } from "../../hooks/useAsync";
import type { AdminProduct, OrderStatus } from "../../types";
import { formatDateTime, formatMoney, statusLabel } from "../../utils/format";
import { RefreshIcon } from "./AdminOrders";

const LOW = "font-semibold text-amber-800";
const LIST = "divide-y divide-slate-100 overflow-hidden rounded-3xl border border-slate-200/80 bg-white text-sm shadow-[0_1px_2px_rgb(11_13_20/0.04)]";

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------
const TILE_DOT: Record<string, string> = { ok: "bg-emerald-500", wait: "bg-amber-400", bad: "bg-red-500" };
const TILE_VALUE: Record<string, string> = { ok: "text-emerald-700", wait: "text-amber-700", bad: "text-red-700" };
const TILE_RING: Record<string, string> = {
  ok: "border-emerald-200/80 hover:shadow-[0_18px_40px_-24px_rgb(16_185_129/0.6)]",
  wait: "border-amber-200/80 hover:shadow-[0_18px_40px_-24px_rgb(245_158_11/0.6)]",
  bad: "border-red-200/80 hover:shadow-[0_18px_40px_-24px_rgb(239_68_68/0.6)]",
};
/** Status mix bar on the hero tile (visual only). */
const MIX: { label: string; keys: OrderStatus[]; c: string }[] = [
  { label: "Confirmed", keys: ["CONFIRMED"], c: "bg-emerald-400" },
  { label: "In flight", keys: ["PENDING", "PROCESSING"], c: "bg-amber-400" },
  { label: "Failed", keys: ["FAILED"], c: "bg-red-400" },
  { label: "Cancelled", keys: ["CANCELLED"], c: "bg-slate-500" },
];

/** Stock level against the low-stock threshold (visual only). */
function StockMeter({ value, threshold }: { value: number; threshold: number }) {
  const pct = Math.max(3, Math.min(100, (value / Math.max(1, threshold * 4)) * 100));
  const tone = value <= 0 ? "bg-red-500" : value <= threshold ? "bg-linear-to-r from-amber-400 to-ember-500" : "bg-linear-to-r from-cobalt-500 to-emerald-400";
  return (
    <span className="mt-3 block h-1.5 w-full overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
      <span className={`block h-full rounded-full transition-[width] duration-700 ease-out-expo ${tone}`} style={{ width: `${pct}%` }} />
    </span>
  );
}

export function AdminDashboardPage() {
  const { data, error, loading, reload } = useAsync(() => adminApi.stats(), []);
  if (loading)
    return (
      <SkeletonGroup label="Loading overview" className="space-y-6">
        <Skeleton className="h-14 w-64" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Skeleton className="h-64 rounded-4xl sm:col-span-2 lg:row-span-2" />
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-32 rounded-3xl" />
          ))}
        </div>
      </SkeletonGroup>
    );
  if (error || !data) return <ErrorMessage error={error ?? "No data"} onRetry={reload} />;
  const s = data.orders.byStatus;
  const tiles: { label: string; value: number; to: string; tone?: string }[] = [
    { label: "Total orders", value: data.orders.total, to: "/admin/orders" },
    { label: "Pending", value: s.PENDING + s.PROCESSING, to: "/admin/orders?status=PENDING", tone: "wait" },
    { label: "Confirmed", value: s.CONFIRMED, to: "/admin/orders?status=CONFIRMED", tone: "ok" },
    { label: "Failed", value: s.FAILED, to: "/admin/failed", tone: s.FAILED ? "bad" : undefined },
    { label: "Products", value: data.products.total, to: "/admin/inventory" },
    { label: "Low stock", value: data.products.lowStock, to: "/admin/inventory", tone: data.products.lowStock ? "wait" : undefined },
  ];
  return (
    <>
      <div className={PAGE_HEAD}>
        <div>
          <Eyebrow>Command center</Eyebrow>
          <h1 className={`${PAGE_TITLE} mt-3 font-bold`}>Overview</h1>
        </div>
        <div className="flex items-center gap-2">
          <span className="glass hidden items-center gap-2 rounded-full px-3 py-1.5 font-mono text-[0.6875rem] text-slate-600 sm:inline-flex">
            <span className="size-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgb(16_185_129)]" aria-hidden="true" />
            {formatDateTime(data.generatedAt)}
          </span>
          <Button variant="secondary" onClick={reload}>
            <RefreshIcon />
            Refresh
          </Button>
        </div>
      </div>
      <ul className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map((t, i) =>
          i === 0 ? (
            <li key={t.label} className="col-span-2 animate-rise lg:row-span-2">
              <Link
                to={t.to}
                className="group relative isolate flex h-full min-h-56 flex-col justify-between overflow-hidden rounded-4xl bg-ink p-6 text-white no-underline shadow-[0_30px_60px_-30px_rgb(11_13_20/0.7)] transition-transform duration-500 ease-out-expo hover:-translate-y-1 focus-visible:outline-cobalt-600 motion-reduce:hover:translate-y-0 sm:p-8"
              >
                <span className="absolute -top-24 -right-16 -z-10 size-72 rounded-full bg-cobalt-600/50 blur-3xl transition-transform duration-700 group-hover:scale-110" aria-hidden="true" />
                <span className="absolute -bottom-24 -left-10 -z-10 size-56 rounded-full bg-ember-500/25 blur-3xl" aria-hidden="true" />
                <span className="flex items-center justify-between">
                  <span className="eyebrow text-slate-400">{t.label}</span>
                  <span className="grid size-9 place-items-center rounded-full bg-white/10 transition-colors group-hover:bg-white group-hover:text-ink" aria-hidden="true">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4 -rotate-45">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3 8h10m-4-4 4 4-4 4" />
                    </svg>
                  </span>
                </span>
                <span className="font-display text-7xl leading-none font-bold tracking-tighter tabular-nums sm:text-8xl">{t.value}</span>
                <span className="block">
                  <span className="flex h-2 overflow-hidden rounded-full bg-white/10" aria-hidden="true">
                    {MIX.map((m) => {
                      const v = m.keys.reduce((n, k) => n + s[k], 0);
                      return v > 0 ? <span key={m.label} className={`${m.c} h-full`} style={{ width: `${(v / Math.max(1, data.orders.total)) * 100}%` }} /> : null;
                    })}
                  </span>
                  <span className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
                    {MIX.map((m) => (
                      <span key={m.label} className="inline-flex items-center gap-1.5">
                        <span className={`size-1.5 rounded-full ${m.c}`} aria-hidden="true" />
                        {m.label} <span className="font-mono text-white tabular-nums">{m.keys.reduce((n, k) => n + s[k], 0)}</span>
                      </span>
                    ))}
                  </span>
                </span>
              </Link>
            </li>
          ) : (
            <li key={t.label} className="animate-rise" style={{ animationDelay: `${i * 60}ms` }}>
              <Link
                to={t.to}
                className={`group relative flex h-full min-h-32 flex-col justify-between gap-4 overflow-hidden rounded-3xl border bg-white p-5 no-underline shadow-[0_1px_2px_rgb(11_13_20/0.04)] transition-[transform,box-shadow,border-color] duration-300 ease-out-expo hover:-translate-y-0.5 motion-reduce:hover:translate-y-0 ${
                  t.tone ? TILE_RING[t.tone] : "border-slate-200/80 hover:border-cobalt-200 hover:shadow-[0_18px_40px_-24px_rgb(42_77_255/0.5)]"
                }`}
              >
                {t.tone && <span className={`absolute -top-10 -right-10 size-28 rounded-full opacity-40 blur-2xl ${TILE_DOT[t.tone]}`} aria-hidden="true" />}
                <span className="relative flex items-center gap-2 text-[0.8125rem] font-semibold text-slate-600">
                  {t.tone && <span className={`size-2 rounded-full ${TILE_DOT[t.tone]}`} aria-hidden="true" />}
                  {t.label}
                </span>
                <span className={`relative font-display text-4xl font-bold tracking-tight tabular-nums ${t.tone ? TILE_VALUE[t.tone] : "text-ink"}`}>{t.value}</span>
              </Link>
            </li>
          ),
        )}
      </ul>
      <p className="mt-4 text-[0.8125rem] text-slate-600">
        Pending includes {s.PENDING} waiting for stock and {s.PROCESSING} waiting for payment. Updated {formatDateTime(data.generatedAt)}.
      </p>

      <div className="mt-14 mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className={`${SECTION_TITLE} mb-0`}>
          <span className="h-4 w-1 rounded-full bg-amber-500" aria-hidden="true" />
          Low stock (≤ {data.products.lowStockThreshold})
        </h2>
        <Link to="/admin/inventory" className={TEXT_LINK}>
          Manage inventory
        </Link>
      </div>
      {data.lowStockProducts.length === 0 ? (
        <p className={QUIET_EMPTY}>All active products are above the threshold.</p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.lowStockProducts.map((p, i) => (
            <li
              key={p.productId}
              className="animate-rise rounded-3xl border border-amber-200/70 bg-linear-to-br from-white to-amber-50/60 p-5"
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <div className="flex items-start justify-between gap-3">
                <span className="font-display font-semibold tracking-tight text-ink">{p.name}</span>
                <Link to="/admin/inventory" className={`${TEXT_LINK} text-sm`}>
                  Restock
                </Link>
              </div>
              <div className="mt-4 flex items-end justify-between text-sm">
                <span>
                  <span className="font-display text-3xl font-bold text-amber-700 tabular-nums">{p.available}</span>
                  <span className="ml-1 text-slate-500">available</span>
                </span>
                <span className="text-slate-600 tabular-nums">{p.reserved} reserved</span>
              </div>
              <StockMeter value={p.available} threshold={data.products.lowStockThreshold} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Products & stock
// ---------------------------------------------------------------------------
const EMPTY_FORM = { name: "", description: "", price: "", category: "General", imageUrl: "", active: true, initialStock: "0", testBehavior: "" };
type FormState = typeof EMPTY_FORM;

function toForm(p: AdminProduct): FormState {
  return {
    name: p.name,
    description: p.description,
    price: (p.priceMinor / 100).toFixed(2),
    category: p.category,
    imageUrl: p.imageUrl ?? "",
    active: p.active,
    initialStock: String(p.available),
    testBehavior: p.testBehavior ?? "",
  };
}

function validate(f: FormState, creating: boolean): string | null {
  if (!f.name.trim()) return "Enter a product name.";
  const price = Number(f.price);
  if (!Number.isFinite(price) || price <= 0) return "Enter a price greater than 0.";
  if (creating && (!/^\d+$/.test(f.initialStock) || Number(f.initialStock) > 1_000_000)) return "Initial stock must be a whole number from 0.";
  if (f.imageUrl && !/^https:\/\//.test(f.imageUrl)) return "Image URL must start with https://";
  return null;
}

function ProductForm({ editing, onDone }: { editing: AdminProduct | null; onDone: () => void }) {
  const toast = useToast();
  const [f, setF] = useState<FormState>(editing ? toForm(editing) : EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const creating = !editing;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const problem = validate(f, creating);
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    const input: ProductInput = {
      name: f.name.trim(),
      description: f.description.trim(),
      priceMinor: Math.round(Number(f.price) * 100),
      category: f.category.trim() || "General",
      imageUrl: f.imageUrl.trim() || null,
      active: f.active,
      testBehavior: f.testBehavior || null,
    };
    try {
      if (creating) await adminApi.createProduct({ ...input, initialStock: Number(f.initialStock) });
      else await adminApi.updateProduct(editing.productId, input);
      toast(creating ? "Product created" : "Product saved", "success");
      onDone();
    } catch (err) {
      setError((err as ApiError).message);
      setBusy(false);
    }
  }

  return (
    <form
      className="relative mb-12 grid animate-drop grid-cols-1 gap-x-5 overflow-hidden rounded-4xl border border-cobalt-100 bg-white/90 p-6 shadow-[0_30px_60px_-30px_rgb(42_77_255/0.45)] backdrop-blur-xl sm:p-8 md:grid-cols-2"
      onSubmit={submit}
      noValidate
    >
      <span className="absolute inset-x-0 top-0 h-1 bg-linear-to-r from-cobalt-600 via-cobalt-400 to-ember-500" aria-hidden="true" />
      <div className="col-span-full mb-7 flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-2xl bg-cobalt-50 text-cobalt-600 ring-1 ring-cobalt-100" aria-hidden="true">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4">
            <path strokeLinecap="round" strokeLinejoin="round" d={creating ? "M8 3v10M3 8h10" : "M10.5 3.5l2 2L6 12H4v-2l6.5-6.5Z"} />
          </svg>
        </span>
        <h2 className="text-xl">{creating ? "New product" : `Edit ${editing.name}`}</h2>
      </div>
      <Field label="Name">{(id) => <input id={id} value={f.name} maxLength={120} onChange={(e) => setF({ ...f, name: e.target.value })} />}</Field>
      <Field label="Price">
        {(id) => <input id={id} inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} />}
      </Field>
      <Field label="Category">{(id) => <input id={id} value={f.category} maxLength={60} onChange={(e) => setF({ ...f, category: e.target.value })} />}</Field>
      {creating && (
        <Field label="Initial stock">
          {(id) => <input id={id} inputMode="numeric" value={f.initialStock} onChange={(e) => setF({ ...f, initialStock: e.target.value })} />}
        </Field>
      )}
      <Field label="Description" >
        {(id) => <textarea id={id} rows={3} maxLength={1000} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />}
      </Field>
      <Field label="Image URL" hint="Optional, https only.">
        {(id, d) => <input id={id} aria-describedby={d} value={f.imageUrl} onChange={(e) => setF({ ...f, imageUrl: e.target.value })} />}
      </Field>
      <Field label="Test scenario" hint="Demo only. Applies when test scenarios are enabled on the backend.">
        {(id, d) => (
          <select id={id} aria-describedby={d} value={f.testBehavior} onChange={(e) => setF({ ...f, testBehavior: e.target.value })}>
            <option value="">None</option>
            <option value="PAYMENT_DECLINE">Payment is declined</option>
            <option value="PAYMENT_TRANSIENT_ONCE">Payment times out on the first attempt</option>
          </select>
        )}
      </Field>
      <label className="col-span-full flex min-h-12 cursor-pointer items-center gap-3 rounded-2xl bg-slate-50 px-4 text-sm font-semibold text-slate-800 ring-1 ring-slate-100 transition-colors hover:bg-cobalt-50/60">
        <input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /> Show in the shop
      </label>
      {error && (
        <div className="col-span-full">
          <ErrorMessage error={error} />
        </div>
      )}
      <div className="col-span-full mt-6 flex flex-wrap gap-2 border-t border-slate-100 pt-6">
        <Button type="submit" busy={busy}>
          {creating ? "Create product" : "Save changes"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Close
        </Button>
      </div>
    </form>
  );
}

function StockEditor({ product, onSaved }: { product: AdminProduct; onSaved: () => void }) {
  const toast = useToast();
  const [mode, setMode] = useState<"adjust" | "set">("adjust");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const qty = Number(value);
  const invalid =
    value === "" || !Number.isInteger(qty) || (mode === "set" ? qty < 0 : qty === 0 || product.available + qty < 0);
  const resulting = mode === "set" ? qty : product.available + qty;

  async function save(e: FormEvent) {
    e.preventDefault();
    if (invalid) return;
    setBusy(true);
    try {
      await adminApi.changeStock(product.productId, mode, qty, "admin console");
      toast(`${product.name}: ${resulting} available`, "success");
      setValue("");
      onSaved();
    } catch (err) {
      toast((err as ApiError).message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="flex min-w-72 flex-wrap items-center gap-1 rounded-xl bg-slate-50 p-1 ring-1 ring-slate-100 transition-shadow focus-within:ring-cobalt-200 max-md:justify-end"
      onSubmit={save}
    >
      <label className="sr-only" htmlFor={`mode-${product.productId}`}>
        Change type for {product.name}
      </label>
      <select id={`mode-${product.productId}`} className="min-h-9 w-auto py-1 text-[0.8125rem]" value={mode} onChange={(e) => setMode(e.target.value as "adjust" | "set")}>
        <option value="adjust">Add / remove</option>
        <option value="set">Set to</option>
      </select>
      <label className="sr-only" htmlFor={`qty-${product.productId}`}>
        Quantity for {product.name}
      </label>
      <input
        id={`qty-${product.productId}`}
        className="min-h-9 w-18 py-1 text-[0.8125rem] tabular-nums"
        inputMode="numeric"
        placeholder={mode === "adjust" ? "+10" : "0"}
        value={value}
        aria-invalid={(value !== "" && invalid) || undefined}
        onChange={(e) => setValue(e.target.value.trim())}
      />
      <Button type="submit" variant="secondary" className="btn-small" busy={busy} disabled={invalid}>
        Update
      </Button>
      {value !== "" && invalid && <span className="basis-full px-1 pb-0.5 text-xs font-medium text-red-700">Stock can't go below 0.</span>}
    </form>
  );
}

export function InventoryPage() {
  const { data, error, loading, reload } = useAsync(() => adminApi.products(), []);
  const [editing, setEditing] = useState<AdminProduct | null | "new">(null);
  const threshold = data?.lowStockThreshold ?? 5;
  return (
    <>
      <div className={PAGE_HEAD}>
        <div>
          <Eyebrow>Catalogue</Eyebrow>
          <h1 className={`${PAGE_TITLE} mt-3 font-bold`}>Products &amp; stock</h1>
        </div>
        <Button onClick={() => setEditing("new")}>
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" className="size-3.5" aria-hidden="true">
            <path strokeLinecap="round" d="M8 3v10M3 8h10" />
          </svg>
          New product
        </Button>
      </div>
      {data && (
        <dl className="-mt-4 mb-10 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { k: "Products", v: data.items.length },
            { k: "Units available", v: data.items.reduce((n, p) => n + p.available, 0) },
            { k: "Reserved", v: data.items.reduce((n, p) => n + p.reserved, 0) },
            { k: "Low stock", v: data.items.filter((p) => p.available <= threshold).length, warn: true },
          ].map((x) => (
            <div key={x.k} className="glass rounded-2xl px-4 py-3">
              <dt className="eyebrow text-[0.625rem]">{x.k}</dt>
              <dd className={`mt-1 font-display text-2xl font-bold tabular-nums ${x.warn && x.v > 0 ? "text-amber-700" : "text-ink"}`}>{x.v}</dd>
            </div>
          ))}
        </dl>
      )}
      {editing && (
        <ProductForm
          key={editing === "new" ? "new" : editing.productId}
          editing={editing === "new" ? null : editing}
          onDone={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
      {loading && <TableSkeleton label="Loading products" />}
      {error && <ErrorMessage error={error} onRetry={reload} />}
      {data && (
        <DataTable
          caption="Products and stock"
          rows={data.items}
          rowKey={(p) => p.productId}
          columns={[
            {
              key: "name",
              header: "Product",
              render: (p) => (
                <div className="flex min-w-0 items-center gap-3 text-left">
                  <span className="w-12 shrink-0 overflow-hidden rounded-xl max-md:hidden" aria-hidden="true">
                    <ProductArt name={p.name} category={p.category} imageUrl={p.imageUrl} />
                  </span>
                  <span className="min-w-0">
                  <strong className="font-semibold text-ink">{p.name}</strong>
                  <div className="mt-0.5 text-xs text-slate-600">
                    {p.category}
                    {!p.active && " · hidden"}
                    {p.testBehavior && ` · test: ${statusLabel(p.testBehavior)}`}
                  </div>
                  </span>
                </div>
              ),
            },
            { key: "price", header: "Price", align: "right", render: (p) => <span className="font-semibold">{formatMoney(p.priceMinor, p.currency)}</span> },
            {
              key: "avail",
              header: "Available",
              align: "right",
              render: (p) => (
                <span className="inline-flex min-w-16 flex-col items-end">
                  <span className={p.available <= threshold ? LOW : "font-semibold text-ink"}>{p.available}</span>
                  <span className="w-16">
                    <StockMeter value={p.available} threshold={threshold} />
                  </span>
                </span>
              ),
            },
            { key: "res", header: "Reserved", align: "right", render: (p) => p.reserved },
            { key: "sold", header: "Sold", align: "right", render: (p) => p.sold },
            { key: "stock", header: "Change stock", render: (p) => <StockEditor product={p} onSaved={reload} /> },
            {
              key: "edit",
              header: "",
              render: (p) => (
                <Button variant="ghost" className="btn-small" onClick={() => setEditing(p)}>
                  Edit
                </Button>
              ),
            },
          ]}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Queues & alarms
// ---------------------------------------------------------------------------
export function OperationsPage() {
  const toast = useToast();
  const { data, error, loading, reload } = useAsync(() => adminApi.ops(), []);
  const [redrive, setRedrive] = useState<"stock" | "payment" | "notify" | null>(null);
  const [busy, setBusy] = useState(false);

  async function doRedrive() {
    if (!redrive) return;
    setBusy(true);
    try {
      const r = await adminApi.redrive(redrive);
      toast(r.message, "success");
      reload();
    } catch (e) {
      toast((e as ApiError).message, "error");
    } finally {
      setBusy(false);
      setRedrive(null);
    }
  }

  return (
    <>
      <div className={PAGE_HEAD}>
        <div>
          <Eyebrow>Pipeline health</Eyebrow>
          <h1 className={`${PAGE_TITLE} mt-3 font-bold`}>Queues &amp; alarms</h1>
        </div>
        <Button variant="secondary" onClick={reload}>
          <RefreshIcon />
          Refresh
        </Button>
      </div>
      <div className={`${noticeClass("info")} -mt-4 mb-10`}>
        <NoticeIcon tone="info" />
        <p>
          Queue counts are approximate and CloudWatch alarm states can lag a few minutes. A message lands in a dead-letter
          queue after 3 failed attempts. Retrying the affected order (Failed orders) is usually safer than redriving.
        </p>
      </div>
      {loading && (
        <SkeletonGroup label="Reading queues" className="grid gap-4 md:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-52 rounded-3xl" />
          ))}
        </SkeletonGroup>
      )}
      {error && <ErrorMessage error={error} onRetry={reload} />}
      {data && (
        <>
          <ul className="grid gap-4 md:grid-cols-3" aria-label="Queues">
            {data.queues.map((q, i) => {
              const dlq = (q.dlqVisible ?? 0) > 0;
              return (
                <li
                  key={q.name}
                  className={`relative isolate flex animate-rise flex-col overflow-hidden rounded-3xl border bg-white p-5 shadow-[0_1px_2px_rgb(11_13_20/0.04)] transition-shadow duration-300 sm:p-6 ${
                    dlq ? "border-red-200 shadow-[0_20px_40px_-24px_rgb(239_68_68/0.55)]" : "border-slate-200/80 hover:shadow-[0_18px_40px_-24px_rgb(42_77_255/0.4)]"
                  }`}
                  style={{ animationDelay: `${i * 70}ms` }}
                >
                  {dlq && <span className="absolute -top-12 -right-12 -z-10 size-36 rounded-full bg-red-400/30 blur-2xl" aria-hidden="true" />}
                  <div className="flex items-center justify-between gap-3">
                    <strong className="font-display text-lg font-semibold tracking-tight text-ink">{statusLabel(q.name)}</strong>
                    <span className="relative flex size-2.5" aria-hidden="true">
                      {dlq && <span className="absolute inset-0 animate-ping rounded-full bg-red-400 opacity-75 motion-reduce:animate-none" />}
                      <span className={`relative size-2.5 rounded-full ${q.error ? "bg-slate-300" : dlq ? "bg-red-500" : "bg-emerald-500"}`} />
                    </span>
                  </div>
                  <dl className="mt-5 grid grid-cols-3 gap-2 tabular-nums">
                    <div>
                      <dt className="eyebrow text-[0.5625rem]">Waiting</dt>
                      <dd className="mt-1 font-display text-2xl font-bold text-ink">{q.queueVisible ?? "—"}</dd>
                    </div>
                    <div>
                      <dt className="eyebrow text-[0.5625rem]">In progress</dt>
                      <dd className="mt-1 font-display text-2xl font-bold text-ink">{q.queueInFlight ?? "—"}</dd>
                    </div>
                    <div className={`-m-2 rounded-xl p-2 ${dlq ? "bg-red-50" : ""}`}>
                      <dt className={`eyebrow text-[0.5625rem] ${dlq ? "text-red-700" : ""}`}>Dead-letter</dt>
                      <dd className={`mt-1 font-display text-2xl font-bold ${dlq ? "text-red-700" : "text-ink"}`}>{q.dlqVisible ?? "—"}</dd>
                    </div>
                  </dl>
                  <div className="mt-auto pt-5">
                    {q.error ? (
                      <span className="text-xs font-medium text-red-700">{q.error}</span>
                    ) : (
                      <Button
                        variant={dlq ? "danger" : "secondary"}
                        className="btn-small btn-block"
                        disabled={!q.dlqVisible}
                        onClick={() => setRedrive(q.name as "stock" | "payment" | "notify")}
                      >
                        Redrive
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          <div className="mt-14 grid items-start gap-10 lg:grid-cols-2">
            <section>
              <h2 className={SECTION_TITLE}>
                <span className="h-4 w-1 rounded-full bg-cobalt-600" aria-hidden="true" />
                Alarms
              </h2>
              {data.alarms.length === 0 ? (
                <p className={QUIET_EMPTY}>No alarm data available.</p>
              ) : (
                <ul className={LIST}>
                  {data.alarms.map((a) => (
                    <li key={a.name} className={`flex items-center gap-3 px-4 py-3.5 ${a.state === "ALARM" ? "bg-red-50/60" : ""}`}>
                      <StatusBadge status={a.state === "ALARM" ? "FAILED" : a.state === "OK" ? "CONFIRMED" : "PENDING"} label={statusLabel(a.state)} />{" "}
                      <span className="min-w-0 font-mono text-[0.8125rem] break-all text-slate-800">{a.name}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section>
              <h2 className={SECTION_TITLE}>
                <span className="h-4 w-1 rounded-full bg-red-500" aria-hidden="true" />
                Recent failures
              </h2>
              {data.recentFailedOrders.length === 0 ? (
                <p className={QUIET_EMPTY}>None.</p>
              ) : (
                <ul className={LIST}>
                  {data.recentFailedOrders.map((o) => (
                    <li key={o.orderId} className="flex items-baseline gap-3 px-4 py-3">
                      <Link to={`/admin/orders/${o.orderId}`} className={ID_LINK}>
                        {o.orderId.slice(-8)}
                      </Link>{" "}
                      <span className="text-slate-700">— {o.failureReason ?? statusLabel((o.failureCategory ?? "FAILED") as OrderStatus)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      )}
      <ConfirmDialog
        open={redrive !== null}
        title={`Redrive the ${redrive} dead-letter queue?`}
        confirmLabel="Redrive messages"
        busy={busy}
        onConfirm={doRedrive}
        onCancel={() => setRedrive(null)}
      >
        <p>
          Messages move back to the {redrive} queue and are processed again. Messages from older attempts are ignored
          safely, so this never charges or reserves twice.
        </p>
      </ConfirmDialog>
    </>
  );
}
