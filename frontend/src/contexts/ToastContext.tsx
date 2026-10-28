import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type Tone = "success" | "error" | "info";
interface Toast {
  id: number;
  tone: Tone;
  text: string;
}

const ToastContext = createContext<((text: string, tone?: Tone) => void) | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const notify = useCallback((text: string, tone: Tone = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, tone, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "error" ? 8000 : 4500);
  }, []);
  const value = useMemo(() => notify, [notify]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-4 bottom-4 z-50 grid gap-2 sm:inset-x-auto sm:right-6 sm:bottom-6 sm:w-96"
        role="status"
        aria-live="polite"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto relative flex animate-pop items-start gap-3 overflow-hidden rounded-2xl bg-ink/90 py-3.5 pr-2 pl-3.5 text-sm text-white shadow-[0_20px_50px_-12px_rgb(11_13_20/0.55)] ring-1 ring-white/10 backdrop-blur-xl"
          >
            <span
              className={`grid size-6 shrink-0 place-items-center rounded-lg ${
                t.tone === "success" ? "bg-emerald-500/20 text-emerald-300" : t.tone === "error" ? "bg-red-500/20 text-red-300" : "bg-cobalt-500/25 text-cobalt-200"
              }`}
              aria-hidden="true"
            >
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.2" className="size-3.5">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d={t.tone === "success" ? "m3.5 8.5 3 3 6-7" : t.tone === "error" ? "M8 4.5V9M8 11.5h.01" : "M8 7.5V11M8 5h.01"}
                />
              </svg>
            </span>
            <span className="flex-1 py-0.5 leading-snug">{t.text}</span>
            <button
              className="grid size-7 shrink-0 cursor-pointer place-items-center rounded-lg text-lg leading-none text-slate-400 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-white"
              aria-label="Dismiss"
              onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}
            >
              ×
            </button>
            <span
              className={`toast-timer absolute inset-x-0 bottom-0 h-0.5 ${
                t.tone === "success" ? "bg-emerald-400" : t.tone === "error" ? "bg-red-400" : "bg-linear-to-r from-cobalt-400 to-ember-400"
              }`}
              style={{ animationDuration: t.tone === "error" ? "8000ms" : "4500ms" }}
              aria-hidden="true"
            />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
