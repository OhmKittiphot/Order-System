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
      {busy && (
        <span
          className="size-3.5 animate-spin rounded-full border-2 border-current/30 border-t-current motion-reduce:animate-none"
          aria-hidden="true"
        />
      )}
      {children}
    </button>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-sm text-slate-600" role="status">
      <span className="relative flex size-5" aria-hidden="true">
        <span className="absolute inset-0 animate-spin rounded-full border-2 border-cobalt-100 border-t-cobalt-600 motion-reduce:animate-none" />
        <span className="absolute inset-1.5 rounded-full bg-ember-400/70" />
      </span>
      <span>{label}…</span>
    </div>
  );
}

/** Shimmering placeholder; wrap groups in <SkeletonGroup> so screen readers hear one status. */
export function Skeleton({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return <div className={`skeleton ${className}`} style={style} aria-hidden="true" />;
}
export function SkeletonGroup({ label, className = "", children }: { label: string; className?: string; children: ReactNode }) {
  return (
    <div role="status" className={className}>
      <span className="sr-only">{label}…</span>
      {children}
    </div>
  );
}

export function TableSkeleton({ label, rows = 5 }: { label: string; rows?: number }) {
  return (
    <SkeletonGroup label={label} className="surface overflow-hidden rounded-3xl">
      <div className="flex gap-6 border-b border-slate-100 bg-slate-50/70 px-6 py-4">
        {[16, 24, 20, 12].map((w, i) => (
          <Skeleton key={i} className="h-2.5 rounded-full" style={{ width: `${w * 4}px` }} />
        ))}
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-6 border-b border-slate-50 px-6 py-4 last:border-0" style={{ opacity: 1 - i * 0.14 }}>
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-4 flex-1" />
          <Skeleton className="h-6 w-24 rounded-full" />
          <Skeleton className="h-4 w-16 max-sm:hidden" />
        </div>
      ))}
    </SkeletonGroup>
  );
}

/* ---------- shared class strings ---------- */
export const BACK_LINK =
  "group/back mb-8 inline-flex min-h-9 items-center gap-2 rounded-full border border-slate-200 bg-white/70 py-1 pr-4 pl-2 text-sm font-medium text-slate-700 no-underline backdrop-blur transition-[border-color,color,box-shadow] duration-200 hover:border-cobalt-300 hover:text-cobalt-700 hover:shadow-[0_6px_20px_-10px_rgb(42_77_255/0.5)]";
export const PAGE_TITLE = "text-[2rem] leading-[1.05] tracking-[-0.03em] sm:text-[2.75rem]";
export const PAGE_HEAD = "mb-10 flex flex-wrap items-end justify-between gap-4";
export const SECTION_TITLE = "mb-4 flex items-center gap-2.5 text-lg tracking-tight";
export const PANEL = "surface p-5 sm:p-7";
export const QUIET_EMPTY =
  "flex items-center gap-3 rounded-2xl border border-dashed border-slate-300 bg-white/50 px-5 py-6 text-sm text-slate-600";
export const TEXT_LINK = "font-semibold text-cobalt-700 underline decoration-cobalt-200 decoration-2 hover:decoration-cobalt-600";
export const ID_LINK =
  "font-mono text-[0.8125rem] font-medium text-ink underline decoration-slate-300 decoration-1 hover:text-cobalt-700 hover:decoration-cobalt-600";

export function Eyebrow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <p className={`eyebrow inline-flex items-center gap-2.5 ${className}`}>
      <span className="h-px w-6 bg-linear-to-r from-cobalt-600 to-ember-500" aria-hidden="true" />
      {children}
    </p>
  );
}

/* ---------- notices ---------- */
export const NOTICE = {
  error: "border-red-200/80 bg-red-50/90 text-red-950",
  warn: "border-amber-200/80 bg-amber-50/90 text-amber-950",
  info: "border-cobalt-100 bg-cobalt-50/80 text-slate-800",
} as const;
export const noticeClass = (tone: keyof typeof NOTICE) =>
  `my-5 flex gap-3.5 rounded-2xl border px-4 py-4 text-sm leading-relaxed backdrop-blur animate-rise ${NOTICE[tone]}`;

export function NoticeIcon({ tone }: { tone: keyof typeof NOTICE }) {
  const color = tone === "error" ? "bg-red-600" : tone === "warn" ? "bg-amber-500" : "bg-cobalt-600";
  return (
    <span className={`grid size-6 shrink-0 place-items-center rounded-lg text-white ${color}`} aria-hidden="true">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" className="size-3.5">
        {tone === "info" ? <path strokeLinecap="round" d="M8 7.5V11M8 5h.01" /> : <path strokeLinecap="round" d="M8 4.5V9M8 11.5h.01" />}
      </svg>
    </span>
  );
}

export function ErrorMessage({ error, onRetry }: { error: ApiError | Error | string; onRetry?: () => void }) {
  const message = typeof error === "string" ? error : error.message;
  const cid = typeof error === "object" && "correlationId" in error ? error.correlationId : undefined;
  return (
    <div className={noticeClass("error")} role="alert">
      <NoticeIcon tone="error" />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-medium">{message}</p>
        {cid && <p className="font-mono text-xs break-all text-red-900/70">Reference: {cid}</p>}
        {onRetry && (
          <div className="pt-2">
            <Button variant="secondary" className="btn-small" onClick={onRetry}>
              Try again
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------- empty states ---------- */
type Art = "cart" | "orders" | "bell" | "box" | "clear";
const ART_PATH: Record<Art, string> = {
  cart: "M5 8h14l-1.2 10.2a2 2 0 0 1-2 1.8H8.2a2 2 0 0 1-2-1.8L5 8Zm4 0V7a3 3 0 0 1 6 0v1",
  orders: "M4 7.5 12 3l8 4.5v9L12 21l-8-4.5v-9Zm0 0 8 4.5m0 0 8-4.5M12 12v9M8 5.3l8 4.5",
  bell: "M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15L6 16Zm4 4a2 2 0 0 0 4 0",
  box: "M4 7h16v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7Zm-1-3h18v3H3V4Zm7 7h4",
  clear: "M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3Zm-3 9 2 2 4-4",
};

export function EmptyState({ title, children, action, art = "box" }: { title: string; children?: ReactNode; action?: ReactNode; art?: Art }) {
  return (
    <div className="mx-auto flex max-w-md animate-rise flex-col items-center px-4 py-16 text-center sm:py-20">
      <div className="relative mb-8 size-32" aria-hidden="true">
        <div className="absolute inset-0 rounded-full bg-[conic-gradient(from_200deg,var(--color-cobalt-200),var(--color-ember-300),var(--color-cobalt-100),var(--color-cobalt-200))] opacity-60 blur-2xl" />
        <div className="glass absolute inset-5 grid rotate-[-8deg] place-items-center rounded-[1.75rem] motion-safe:animate-float">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="size-10 rotate-[8deg] text-cobalt-600">
            <path strokeLinecap="round" strokeLinejoin="round" d={ART_PATH[art]} />
          </svg>
        </div>
        <span className="absolute top-2 right-3 size-2.5 rounded-full bg-ember-500 motion-safe:animate-float [animation-delay:-2s]" />
        <span className="absolute bottom-4 left-1 size-1.5 rounded-full bg-cobalt-500 motion-safe:animate-float [animation-delay:-4s]" />
      </div>
      <h3 className="text-2xl tracking-tight">{title}</h3>
      {children && <p className="mt-2 text-[0.9375rem] text-slate-600">{children}</p>}
      {action && <div className="mt-8">{action}</div>}
    </div>
  );
}

/* ---------- status ---------- */
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

const TONE_CLASS: Record<string, { pill: string; dot: string }> = {
  ok: { pill: "bg-emerald-50 text-emerald-800 ring-emerald-600/20", dot: "bg-emerald-500" },
  bad: { pill: "bg-red-50 text-red-800 ring-red-600/20", dot: "bg-red-500" },
  wait: { pill: "bg-amber-50 text-amber-900 ring-amber-500/30", dot: "bg-amber-500" },
  info: { pill: "bg-cobalt-50 text-cobalt-700 ring-cobalt-600/20", dot: "bg-cobalt-600" },
  mute: { pill: "bg-slate-100 text-slate-700 ring-slate-500/20", dot: "bg-slate-400" },
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = TONES[status] ?? "mute";
  const t = TONE_CLASS[tone]!;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full py-0.5 pr-2.5 pl-2 text-xs font-semibold whitespace-nowrap ring-1 ring-inset ${t.pill}`}>
      <span className="relative flex size-1.5" aria-hidden="true">
        {tone === "wait" && <span className={`absolute inset-0 animate-ping rounded-full opacity-75 motion-reduce:animate-none ${t.dot}`} />}
        <span className={`relative size-1.5 rounded-full ${t.dot}`} />
      </span>
      {label ?? statusLabel(status)}
    </span>
  );
}

/* ---------- forms ---------- */
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
    <div className="group/field mb-5 has-[textarea]:col-span-full">
      <label htmlFor={id} className="mb-1.5 block text-sm font-semibold text-slate-800 transition-colors group-focus-within/field:text-cobalt-700">
        {label}
      </label>
      {children(id, hintId)}
      {(error || hint) && (
        <p id={hintId} className={`mt-1.5 text-[0.8125rem] ${error ? "font-medium text-red-700" : "text-slate-500"}`}>
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
    <dialog
      ref={ref}
      className="w-[calc(100vw-2rem)] max-w-md overflow-hidden rounded-3xl border border-white/70 bg-white/95 p-0 text-slate-900 shadow-[0_30px_80px_-20px_rgb(11_13_20/0.45)] backdrop:bg-ink/45 backdrop:backdrop-blur-sm"
      onCancel={onCancel}
      aria-labelledby="dialog-title"
      open={open}
    >
      <div className={`h-1 bg-linear-to-r ${tone === "danger" ? "from-red-500 to-ember-500" : "from-cobalt-600 to-ember-500"}`} aria-hidden="true" />
      <div className="p-6 sm:p-7">
        <h2 id="dialog-title" className="text-xl">
          {title}
        </h2>
        <div className="mt-2 text-sm leading-relaxed text-slate-600">{children}</div>
      </div>
      <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 bg-slate-50/80 px-6 py-4 sm:px-7">
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
    <div className="mt-10 flex items-center gap-4">
      <span className="h-px flex-1 bg-linear-to-r from-transparent to-slate-200" aria-hidden="true" />
      <Button variant="secondary" busy={loading} onClick={onClick} className="rounded-full">
        Show more
      </Button>
      <span className="h-px flex-1 bg-linear-to-l from-transparent to-slate-200" aria-hidden="true" />
    </div>
  );
}

export function ProductArt({ name, category, imageUrl }: { name: string; category: string; imageUrl?: string | null }) {
  const base = "block aspect-[4/3] w-full";
  if (imageUrl) return <img className={`${base} bg-slate-100 object-cover`} src={imageUrl} alt="" loading="lazy" />;
  // Deterministic placeholder: initials on a tint derived from the category.
  const hue = [...category].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 210);
  const initials = name
    .split(/\s+/)
    .filter((w) => /[A-Za-z0-9]/.test(w[0] ?? ""))
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
  return (
    <div
      className={`${base} relative grid place-items-center overflow-hidden bg-[radial-gradient(120%_90%_at_20%_10%,hsl(var(--hue)_70%_93%),hsl(var(--hue)_35%_84%))] font-display text-5xl font-semibold tracking-tighter text-[hsl(var(--hue)_40%_28%)]`}
      style={{ "--hue": hue } as CSSProperties}
      aria-hidden="true"
    >
      <span className="absolute -right-8 -bottom-10 size-40 rounded-full bg-[hsl(calc(var(--hue)+40)_80%_75%/0.45)] blur-2xl" />
      <span className="absolute inset-0 bg-[radial-gradient(hsl(var(--hue)_40%_30%/0.12)_1px,transparent_1px)] bg-size-[14px_14px]" />
      <span className="relative">{initials}</span>
    </div>
  );
}
