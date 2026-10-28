import type { Order } from "../types";
import { pipeline, type StepState } from "../utils/format";

const DOT: Record<StepState, string> = {
  done: "bg-emerald-500 text-white shadow-[0_6px_18px_-6px_rgb(16_185_129/0.8)]",
  failed: "bg-red-600 text-white shadow-[0_6px_18px_-6px_rgb(220_38_38/0.8)]",
  active: "bg-white text-amber-600 ring-2 ring-amber-400 shadow-[0_0_0_6px_rgb(251_191_36/0.18)]",
  waiting: "bg-white text-slate-400 ring-1 ring-slate-200",
  skipped: "border-[1.5px] border-dashed border-slate-300 bg-slate-50 text-slate-400",
};

const BAR: Record<StepState, string> = {
  done: "bg-emerald-500",
  failed: "bg-red-500",
  active:
    "bg-[linear-gradient(90deg,var(--color-amber-300),var(--color-amber-500),var(--color-amber-300))] bg-[length:200%_100%] animate-shimmer motion-reduce:animate-none",
  waiting: "bg-slate-200",
  skipped: "bg-[repeating-linear-gradient(135deg,var(--color-slate-200)_0_3px,transparent_3px_6px)]",
};

function DotIcon({ state, n }: { state: StepState; n: number }) {
  if (state === "done")
    return (
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.4" className="size-4">
        <path strokeLinecap="round" strokeLinejoin="round" d="m3.5 8.5 3 3 6-7" />
      </svg>
    );
  if (state === "failed")
    return (
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.4" className="size-4">
        <path strokeLinecap="round" d="M5 5l6 6M11 5l-6 6" />
      </svg>
    );
  if (state === "active")
    return (
      <span className="relative flex size-3">
        <span className="absolute inset-0 animate-ping rounded-full bg-amber-400 opacity-70 motion-reduce:animate-none" />
        <span className="relative size-3 rounded-full bg-amber-500" />
      </span>
    );
  return <span className="font-mono text-xs font-semibold">{n}</span>;
}

/**
 * The order's journey through the asynchronous services:
 * Received (Order Lambda) → Stock (Stock Lambda) → Payment (Payment Lambda)
 * → Notified (Notify Lambda). Fills in as each worker finishes.
 */
export function OrderPipeline({ order, compact = false }: { order: Order; compact?: boolean }) {
  const steps = pipeline(order);
  if (compact) {
    return (
      <ol className="flex w-36 gap-1" aria-label="Order progress">
        {steps.map((s) => (
          <li key={s.key} className={`h-1.5 flex-1 overflow-hidden rounded-full ${BAR[s.state]}`}>
            <span className="sr-only">
              {s.label}: {s.note}
            </span>
          </li>
        ))}
      </ol>
    );
  }
  // Visual only: how far along the rail to fill.
  const reached = steps.reduce((n, s, i) => (s.state === "done" || s.state === "failed" || s.state === "active" ? i : n), 0);
  const pct = (reached / (steps.length - 1)) * 100;
  const failed = steps.some((s) => s.state === "failed");
  const fill = failed ? "from-emerald-500 to-red-500" : "from-emerald-500 via-emerald-400 to-amber-400";
  return (
    <div className="surface relative my-8 overflow-hidden px-5 py-6 sm:px-8 sm:py-8">
      <div className="dot-grid pointer-events-none absolute inset-0 opacity-60 [mask-image:linear-gradient(to_bottom,black,transparent)]" aria-hidden="true" />
      {/* rails */}
      <div className="absolute top-11 right-[12.5%] left-[12.5%] h-1 rounded-full bg-slate-100 max-md:hidden sm:top-13" aria-hidden="true">
        <div
          className={`h-full rounded-full bg-linear-to-r ${fill} transition-[width] duration-1000 ease-out-expo`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="absolute top-11.5 bottom-11.5 left-10 w-1 rounded-full bg-slate-100 md:hidden sm:top-13.5 sm:bottom-13.5 sm:left-13" aria-hidden="true">
        <div className={`w-full rounded-full bg-linear-to-b ${fill} transition-[height] duration-1000`} style={{ height: `${pct}%` }} />
      </div>
      <ol className="relative grid gap-6 md:grid-cols-4 md:gap-2" aria-label="Order progress">
        {steps.map((s, i) => (
          <li
            key={s.key}
            className="flex animate-rise items-center gap-4 md:flex-col md:gap-3 md:text-center"
            style={{ animationDelay: `${i * 90}ms` }}
          >
            <span className={`relative z-10 grid size-11 shrink-0 place-items-center rounded-full transition-all duration-500 ${DOT[s.state]}`} aria-hidden="true">
              <DotIcon state={s.state} n={i + 1} />
            </span>
            <span className="flex min-w-0 flex-col">
              <span className="eyebrow text-[0.625rem]">Step 0{i + 1}</span>
              <span
                className={`font-display text-base font-semibold tracking-tight ${
                  s.state === "waiting" || s.state === "skipped" ? "text-slate-400" : "text-ink"
                }`}
              >
                {s.label}
              </span>
              <span className={`text-[0.8125rem] ${s.state === "failed" ? "font-semibold text-red-700" : s.state === "active" ? "font-medium text-amber-800" : "text-slate-500"}`}>
                {s.note}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
