import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { Button, ErrorMessage, Field } from "../components/ui";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../contexts/ToastContext";

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
    <div className="auth-card">
      <h1>Sign in</h1>
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
        <Button type="submit" busy={busy} className="btn-block">
          Sign in
        </Button>
      </form>
      <p className="muted small">
        New here? <Link to="/register">Create an account</Link>
      </p>
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
    <div className="auth-card">
      <h1>Create an account</h1>
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
        {error && <ErrorMessage error={error} />}
        <Button type="submit" busy={busy} className="btn-block" disabled={!form.displayName || !form.email || !form.password || weak}>
          Create account
        </Button>
      </form>
      <p className="muted small">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </div>
  );
}

export function NotFoundPage() {
  return (
    <div className="empty">
      <h1>Page not found</h1>
      <p className="muted">The address may be mistyped, or the page has moved.</p>
      <Link className="btn btn-primary" to="/">
        Go to the shop
      </Link>
    </div>
  );
}
