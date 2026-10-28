import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { Button, ErrorMessage, Eyebrow, Field, TEXT_LINK } from "../components/ui";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../contexts/ToastContext";

/** Split card: a dark story panel beside the form (panel hides on small screens). */
function AuthShell({ story, children }: { story: { eyebrow: string; title: ReactNode; points: string[] }; children: ReactNode }) {
  return (
    <div className="mx-auto grid w-full max-w-5xl animate-rise overflow-hidden rounded-4xl border border-white/80 bg-white/70 shadow-[0_40px_100px_-40px_rgb(11_13_20/0.45)] backdrop-blur-xl lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <div className="relative isolate hidden flex-col justify-between overflow-hidden bg-ink p-10 text-white lg:flex" aria-hidden="true">
        <div className="absolute -top-32 -left-24 -z-10 size-96 rounded-full bg-cobalt-600/50 blur-3xl motion-safe:animate-aurora" />
        <div className="absolute -right-24 -bottom-32 -z-10 size-80 rounded-full bg-ember-500/30 blur-3xl motion-safe:animate-aurora [animation-delay:-8s]" />
        <div className="absolute inset-0 -z-10 [background-image:radial-gradient(rgb(255_255_255/0.07)_1px,transparent_1px)] [background-size:22px_22px]" />
        <p className="eyebrow text-slate-400">{story.eyebrow}</p>
        <div>
          <p className="font-display text-[2.5rem] leading-[1.02] font-bold tracking-[-0.035em]">{story.title}</p>
          <ul className="mt-8 space-y-3">
            {story.points.map((p, i) => (
              <li key={p} className="flex items-center gap-3 text-sm text-slate-300">
                <span className="grid size-6 place-items-center rounded-full bg-white/10 font-mono text-[0.625rem] text-white ring-1 ring-white/15">{i + 1}</span>
                {p}
              </li>
            ))}
          </ul>
        </div>
        <div className="glass flex items-center gap-3 rounded-2xl border-white/10 bg-white/5 p-3 shadow-none">
          <span className="grid size-9 place-items-center rounded-xl bg-emerald-500 text-white">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.4" className="size-4">
              <path strokeLinecap="round" strokeLinejoin="round" d="m3.5 8.5 3 3 6-7" />
            </svg>
          </span>
          <span className="text-sm">
            <span className="block font-semibold text-white">Your order is confirmed</span>
            <span className="block text-xs text-slate-400">Stock held · Payment taken · Notified</span>
          </span>
        </div>
      </div>
      <div className="p-6 sm:p-10 lg:p-12">{children}</div>
    </div>
  );
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(email.trim(), password);
      navigate(from ?? (user.role === "admin" ? "/admin" : "/"), { replace: true });
    } catch (err) {
      setError((err as ApiError).message);
      setBusy(false);
    }
  }

  return (
    <AuthShell
      story={{
        eyebrow: "Welcome back",
        title: (
          <>
            Pick up right <span className="text-gradient">where you left off.</span>
          </>
        ),
        points: ["Your cart is waiting", "Live status on every order", "Notifications the moment it's settled"],
      }}
    >
      <Eyebrow>Account</Eyebrow>
      <h1 className="mt-3 font-display text-3xl font-bold tracking-tight sm:text-4xl">Sign in</h1>
      <p className="mt-2 mb-8 text-[0.9375rem] text-slate-600">Use the email you registered with.</p>
      <form onSubmit={submit} noValidate>
        <Field label="Email">
          {(id) => <input id={id} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}
        </Field>
        <Field label="Password">
          {(id) => (
            <input id={id} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          )}
        </Field>
        {error && <ErrorMessage error={error} />}
        <Button type="submit" busy={busy} className="btn-block mt-3 min-h-12">
          Sign in
        </Button>
      </form>
      <p className="mt-8 text-sm text-slate-600">
        New here?{" "}
        <Link to="/register" className={TEXT_LINK}>
          Create an account
        </Link>
      </p>
    </AuthShell>
  );
}

const STRENGTH_RULES: [string, (p: string) => boolean][] = [
  ["8+ characters", (p) => p.length >= 8],
  ["Lowercase", (p) => /[a-z]/.test(p)],
  ["Uppercase", (p) => /[A-Z]/.test(p)],
  ["Number", (p) => /\d/.test(p)],
];

/** Visual echo of the password rule below; purely presentational. */
function StrengthMeter({ password }: { password: string }) {
  const met = STRENGTH_RULES.map(([, test]) => test(password));
  const score = met.filter(Boolean).length;
  const color = score <= 1 ? "bg-red-500" : score <= 3 ? "bg-amber-400" : "bg-emerald-500";
  return (
    <div className="-mt-3 mb-5" aria-hidden="true">
      <div className="grid grid-cols-4 gap-1.5">
        {met.map((_, i) => (
          <div key={i} className="h-1 overflow-hidden rounded-full bg-slate-100">
            <div className={`h-full rounded-full transition-[width,background-color] duration-500 ease-out-expo ${color}`} style={{ width: i < score ? "100%" : "0%" }} />
          </div>
        ))}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        {STRENGTH_RULES.map(([label], i) => (
          <li key={label} className={`flex items-center gap-1 text-xs transition-colors ${met[i] ? "text-emerald-700" : "text-slate-500"}`}>
            <span className={`size-1.5 rounded-full transition-colors ${met[i] ? "bg-emerald-500" : "bg-slate-300"}`} />
            {label}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RegisterPage() {
  const { register, login } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [form, setForm] = useState({ displayName: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const weak =
    form.password.length > 0 &&
    (form.password.length < 8 || !/[a-z]/.test(form.password) || !/[A-Z]/.test(form.password) || !/\d/.test(form.password));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (weak) return;
    setBusy(true);
    setError(null);
    try {
      await register(form.email.trim(), form.password, form.displayName.trim());
      await login(form.email.trim(), form.password);
      toast("Account created. You're signed in.", "success");
      navigate("/", { replace: true });
    } catch (err) {
      setError((err as ApiError).message);
      setBusy(false);
    }
  }

  return (
    <AuthShell
      story={{
        eyebrow: "New account",
        title: (
          <>
            Every order, <span className="text-gradient">every step,</span> in view.
          </>
        ),
        points: ["Stock reserved before you pay", "Never charged for what can't ship", "Follow each step as it happens"],
      }}
    >
      <Eyebrow>Get started</Eyebrow>
      <h1 className="mt-3 font-display text-3xl font-bold tracking-tight sm:text-4xl">Create an account</h1>
      <p className="mt-2 mb-8 text-[0.9375rem] text-slate-600">Track every order from stock check to confirmation.</p>
      <form onSubmit={submit} noValidate>
        <Field label="Name">
          {(id) => (
            <input id={id} autoComplete="name" required maxLength={80} value={form.displayName} onChange={(e) => setForm({ ...form, displayName: e.target.value })} />
          )}
        </Field>
        <Field label="Email">
          {(id) => (
            <input id={id} type="email" autoComplete="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          )}
        </Field>
        <Field
          label="Password"
          hint="At least 8 characters with upper- and lowercase letters and a number."
          error={weak ? "Use at least 8 characters with upper- and lowercase letters and a number." : undefined}
        >
          {(id, describedBy) => (
            <input
              id={id}
              type="password"
              autoComplete="new-password"
              required
              aria-describedby={describedBy}
              aria-invalid={weak || undefined}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          )}
        </Field>
        {form.password.length > 0 && <StrengthMeter password={form.password} />}
        {error && <ErrorMessage error={error} />}
        <Button type="submit" busy={busy} className="btn-block mt-3 min-h-12" disabled={!form.displayName || !form.email || !form.password || weak}>
          Create account
        </Button>
      </form>
      <p className="mt-8 text-sm text-slate-600">
        Already have an account?{" "}
        <Link to="/login" className={TEXT_LINK}>
          Sign in
        </Link>
      </p>
    </AuthShell>
  );
}

export function NotFoundPage() {
  return (
    <div className="relative mx-auto max-w-2xl py-12 text-center sm:py-20">
      <p
        className="pointer-events-none font-display text-[clamp(7rem,28vw,15rem)] leading-none font-bold tracking-tighter text-transparent select-none [-webkit-text-stroke:1.5px_rgb(42_77_255/0.35)] motion-safe:animate-float"
        aria-hidden="true"
      >
        404
      </p>
      <div className="relative -mt-10 sm:-mt-16">
        <h1 className="font-display text-4xl font-bold tracking-tight sm:text-5xl">Page not found</h1>
        <p className="mx-auto mt-4 mb-10 max-w-sm text-lg text-slate-600">The address may be mistyped, or the page has moved.</p>
        <Link className="btn btn-primary min-h-12 px-7" to="/">
          Go to the shop
        </Link>
      </div>
    </div>
  );
}
