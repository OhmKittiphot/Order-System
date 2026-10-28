import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { adminApi, type ProductInput } from "../../api/endpoints";
import { DataTable } from "../../components/DataTable";
import { Button, ConfirmDialog, ErrorMessage, Field, Spinner, StatusBadge } from "../../components/ui";
import { useToast } from "../../contexts/ToastContext";
import { useAsync } from "../../hooks/useAsync";
import type { AdminProduct, OrderStatus } from "../../types";
import { formatDateTime, formatMoney, statusLabel } from "../../utils/format";

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------
export function AdminDashboardPage() {
  const { data, error, loading, reload } = useAsync(() => adminApi.stats(), []);
  if (loading) return <Spinner label="Loading overview" />;
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
      <div className="page-head">
        <h1>Overview</h1>
        <Button variant="secondary" onClick={reload}>
          Refresh
        </Button>
      </div>
      <ul className="tiles">
        {tiles.map((t) => (
          <li key={t.label} className={`tile ${t.tone ? `tile-${t.tone}` : ""}`}>
            <Link to={t.to}>
              <span className="tile-value">{t.value}</span>
              <span className="tile-label">{t.label}</span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="muted small">
        Pending includes {s.PENDING} waiting for stock and {s.PROCESSING} waiting for payment. Updated {formatDateTime(data.generatedAt)}.
      </p>

      <h2>Low stock (≤ {data.products.lowStockThreshold})</h2>
      {data.lowStockProducts.length === 0 ? (
        <p className="muted">All active products are above the threshold.</p>
      ) : (
        <DataTable
          rows={data.lowStockProducts}
          rowKey={(p) => p.productId}
          columns={[
            { key: "name", header: "Product", render: (p) => p.name },
            { key: "avail", header: "Available", align: "right", render: (p) => p.available },
            { key: "res", header: "Reserved", align: "right", render: (p) => p.reserved },
            { key: "go", header: "", render: () => <Link to="/admin/inventory">Restock</Link> },
          ]}
        />
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
    <form className="panel form-grid" onSubmit={submit} noValidate>
      <h2>{creating ? "New product" : `Edit ${editing.name}`}</h2>
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
      <label className="check">
        <input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /> Show in the shop
      </label>
      {error && <ErrorMessage error={error} />}
      <div className="actions">
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
    <form className="stock-form" onSubmit={save}>
      <label className="sr-only" htmlFor={`mode-${product.productId}`}>
        Change type for {product.name}
      </label>
      <select id={`mode-${product.productId}`} value={mode} onChange={(e) => setMode(e.target.value as "adjust" | "set")}>
        <option value="adjust">Add / remove</option>
        <option value="set">Set to</option>
      </select>
      <label className="sr-only" htmlFor={`qty-${product.productId}`}>
        Quantity for {product.name}
      </label>
      <input
        id={`qty-${product.productId}`}
        className="qty"
        inputMode="numeric"
        placeholder={mode === "adjust" ? "+10" : "0"}
        value={value}
        aria-invalid={(value !== "" && invalid) || undefined}
        onChange={(e) => setValue(e.target.value.trim())}
      />
      <Button type="submit" variant="secondary" className="btn-small" busy={busy} disabled={invalid}>
        Update
      </Button>
      {value !== "" && invalid && <span className="error-text small">Stock can't go below 0.</span>}
    </form>
  );
}

export function InventoryPage() {
  const { data, error, loading, reload } = useAsync(() => adminApi.products(), []);
  const [editing, setEditing] = useState<AdminProduct | null | "new">(null);
  const threshold = data?.lowStockThreshold ?? 5;
  return (
    <>
      <div className="page-head">
        <h1>Products &amp; stock</h1>
        <Button onClick={() => setEditing("new")}>New product</Button>
      </div>
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
      {loading && <Spinner label="Loading products" />}
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
                <div>
                  <strong>{p.name}</strong>
                  <div className="muted small">
                    {p.category}
                    {!p.active && " · hidden"}
                    {p.testBehavior && ` · test: ${statusLabel(p.testBehavior)}`}
                  </div>
                </div>
              ),
            },
            { key: "price", header: "Price", align: "right", render: (p) => formatMoney(p.priceMinor, p.currency) },
            {
              key: "avail",
              header: "Available",
              align: "right",
              render: (p) => <span className={p.available <= threshold ? "low" : undefined}>{p.available}</span>,
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
      <div className="page-head">
        <h1>Queues &amp; alarms</h1>
        <Button variant="secondary" onClick={reload}>
          Refresh
        </Button>
      </div>
      <div className="notice notice-info">
        <p>
          Queue counts are approximate and CloudWatch alarm states can lag a few minutes. A message lands in a dead-letter
          queue after 3 failed attempts. Retrying the affected order (Failed orders) is usually safer than redriving.
        </p>
      </div>
      {loading && <Spinner label="Reading queues" />}
      {error && <ErrorMessage error={error} onRetry={reload} />}
      {data && (
        <>
          <DataTable
            caption="Queues"
            rows={data.queues}
            rowKey={(q) => q.name}
            columns={[
              { key: "name", header: "Service", render: (q) => <strong>{statusLabel(q.name)}</strong> },
              { key: "waiting", header: "Waiting", align: "right", render: (q) => q.queueVisible ?? "—" },
              { key: "flight", header: "In progress", align: "right", render: (q) => q.queueInFlight ?? "—" },
              {
                key: "dlq",
                header: "Dead-letter",
                align: "right",
                render: (q) => <span className={(q.dlqVisible ?? 0) > 0 ? "low" : undefined}>{q.dlqVisible ?? "—"}</span>,
              },
              {
                key: "act",
                header: "",
                render: (q) =>
                  q.error ? (
                    <span className="error-text small">{q.error}</span>
                  ) : (
                    <Button
                      variant="ghost"
                      className="btn-small"
                      disabled={!q.dlqVisible}
                      onClick={() => setRedrive(q.name as "stock" | "payment" | "notify")}
                    >
                      Redrive
                    </Button>
                  ),
              },
            ]}
          />
          <h2>Alarms</h2>
          {data.alarms.length === 0 ? (
            <p className="muted">No alarm data available.</p>
          ) : (
            <ul className="plain-list">
              {data.alarms.map((a) => (
                <li key={a.name}>
                  <StatusBadge status={a.state === "ALARM" ? "FAILED" : a.state === "OK" ? "CONFIRMED" : "PENDING"} label={statusLabel(a.state)} />{" "}
                  {a.name}
                </li>
              ))}
            </ul>
          )}
          <h2>Recent failures</h2>
          {data.recentFailedOrders.length === 0 ? (
            <p className="muted">None.</p>
          ) : (
            <ul className="plain-list">
              {data.recentFailedOrders.map((o) => (
                <li key={o.orderId}>
                  <Link to={`/admin/orders/${o.orderId}`}>{o.orderId.slice(-8)}</Link> — {o.failureReason ?? statusLabel((o.failureCategory ?? "FAILED") as OrderStatus)}
                </li>
              ))}
            </ul>
          )}
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
