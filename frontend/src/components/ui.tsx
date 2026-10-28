import { useEffect, useId, useRef, type ButtonHTMLAttributes, type CSSProperties, type ReactNode } from "react";
import type { ApiError } from "../api/client";
import { statusLabel } from "../utils/format";

type Variant = "primary" | "secondary" | "danger" | "ghost";

export function Button({
  variant = "primary",
  busy = false,
  children,
  disabled,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean }) {
  return (
    <button
      {...rest}
      className={`btn btn-${variant} ${className}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
    >
      {busy && <span className="spinner spinner-sm" aria-hidden="true" />}
      {children}
    </button>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{label}…</span>
    </div>
  );
}

export function ErrorMessage({ error, onRetry }: { error: ApiError | Error | string; onRetry?: () => void }) {
  const message = typeof error === "string" ? error : error.message;
  const cid = typeof error === "object" && "correlationId" in error ? error.correlationId : undefined;
  return (
    <div className="notice notice-error" role="alert">
      <p>{message}</p>
      {cid && <p className="muted small">Reference: {cid}</p>}
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children && <p className="muted">{children}</p>}
      {action}
    </div>
  );
}

const TONES: Record<string, string> = {
  PENDING: "wait",
  PROCESSING: "wait",
  RESERVED: "info",
  CONFIRMED: "ok",
  SUCCEEDED: "ok",
  COMMITTED: "ok",
  SENT: "ok",
  FAILED: "bad",
  OUT_OF_STOCK: "bad",
  CANCELLED: "mute",
  RELEASED: "mute",
  SKIPPED: "mute",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return <span className={`badge badge-${TONES[status] ?? "mute"}`}>{label ?? statusLabel(status)}</span>;
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: (id: string, describedBy: string | undefined) => ReactNode;
}) {
  const id = useId();
  const hintId = hint || error ? `${id}-hint` : undefined;
  return (
    <div className={`field ${error ? "field-error" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children(id, hintId)}
      {(error || hint) && (
        <p id={hintId} className={error ? "field-msg error-text" : "field-msg muted"}>
          {error ?? hint}
        </p>
      )}
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  tone = "primary",
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  tone?: "primary" | "danger";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal?.();
    if (!open && d.open) d.close?.();
  }, [open]);
  if (!open) return null;
  return (
    <dialog ref={ref} className="dialog" onCancel={onCancel} aria-labelledby="dialog-title" open={open}>
      <h2 id="dialog-title">{title}</h2>
      <div className="dialog-body">{children}</div>
      <div className="dialog-actions">
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          Keep as is
        </Button>
        <Button variant={tone} onClick={onConfirm} busy={busy} autoFocus>
          {confirmLabel}
        </Button>
      </div>
    </dialog>
  );
}

export function LoadMore({ nextToken, loading, onClick }: { nextToken: string | null; loading: boolean; onClick: () => void }) {
  if (!nextToken) return null;
  return (
    <div className="load-more">
      <Button variant="secondary" busy={loading} onClick={onClick}>
        Show more
      </Button>
    </div>
  );
}

export function ProductArt({ name, category, imageUrl }: { name: string; category: string; imageUrl?: string | null }) {
  if (imageUrl) return <img className="product-art" src={imageUrl} alt="" loading="lazy" />;
  // Deterministic placeholder: initials on a tint derived from the category.
  const hue = [...category].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 210);
  const initials = name
    .split(/\s+/)
    .filter((w) => /[A-Za-z0-9]/.test(w[0] ?? ""))
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
  return (
    <div className="product-art product-art-placeholder" style={{ "--hue": hue } as CSSProperties} aria-hidden="true">
      {initials}
    </div>
  );
}
