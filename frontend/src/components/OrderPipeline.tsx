import type { Order } from "../types";
import { pipeline } from "../utils/format";

/**
 * The order's journey through the asynchronous services:
 * Received (Order Lambda) → Stock (Stock Lambda) → Payment (Payment Lambda)
 * → Notified (Notify Lambda). Fills in as each worker finishes.
 */
export function OrderPipeline({ order, compact = false }: { order: Order; compact?: boolean }) {
  const steps = pipeline(order);
  return (
    <ol className={`pipeline ${compact ? "pipeline-compact" : ""}`} aria-label="Order progress">
      {steps.map((s) => (
        <li key={s.key} className={`step step-${s.state}`}>
          <span className="step-dot" aria-hidden="true">
            {s.state === "done" ? "✓" : s.state === "failed" ? "!" : ""}
          </span>
          <span className="step-text">
            <span className="step-label">{s.label}</span>
            {!compact && <span className="step-note">{s.note}</span>}
          </span>
          <span className="sr-only">: {s.note}</span>
        </li>
      ))}
    </ol>
  );
}
