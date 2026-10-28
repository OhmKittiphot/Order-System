import { useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useCart } from "../contexts/CartContext";

const SKIP_LINK =
  "sr-only z-[60] rounded-xl bg-white px-4 py-2 text-sm font-semibold text-ink shadow-lg focus:not-sr-only focus:fixed focus:top-3 focus:left-3";

function Mark({ dark = false }: { dark?: boolean }) {
  return (
    <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true" className="shrink-0 transition-transform duration-500 ease-spring group-hover/brand:rotate-[-8deg]">
      <defs>
        <linearGradient id={dark ? "mk-d" : "mk-l"} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2a4dff" />
          <stop offset="1" stopColor="#ff6a3d" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={dark ? "#fff" : "#0b0d14"} />
      <path d="M9.5 22V10m0 6.5L16.5 10m-4 4.4L17.5 22" stroke={dark ? "#0b0d14" : "#fff"} strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="22.5" cy="19.5" r="3" fill={`url(#${dark ? "mk-d" : "mk-l"})`} />
    </svg>
  );
}

function Brand({ to = "/", dark = false }: { to?: string; dark?: boolean }) {
  return (
    <Link
      to={to}
      className={`group/brand inline-flex items-center gap-2.5 font-display text-[1.0625rem] font-bold tracking-tight no-underline ${dark ? "text-white" : "text-ink"}`}
    >
      <Mark dark={dark} />
      <span>Kit &amp; Cable</span>
    </Link>
  );
}

function AccountMenu({ dark = false }: { dark?: boolean }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) {
    return (
      <div className="flex items-center gap-1.5">
        <NavLink to="/login" className="btn btn-ghost btn-small">
          Sign in
        </NavLink>
        <NavLink to="/register" className="btn btn-primary btn-small max-sm:hidden">
          Create account
        </NavLink>
      </div>
    );
  }
  const name = user.displayName || user.email;
  return (
    <div className={`flex min-w-0 items-center gap-2 ${dark ? "justify-between" : ""}`}>
      <span className="flex min-w-0 items-center gap-2.5">
        <span
          className="grid size-8 shrink-0 place-items-center rounded-full bg-linear-to-br from-cobalt-500 to-ember-500 font-display text-xs font-bold text-white uppercase ring-2 ring-white/80"
          aria-hidden="true"
        >
          {name.slice(0, 1)}
        </span>
        <span className={`truncate text-sm font-medium max-lg:sr-only ${dark ? "text-slate-300 lg:not-sr-only" : "text-slate-700"}`}>{name}</span>
      </span>
      <button
        className={`btn btn-ghost btn-small ${dark ? "text-slate-400 hover:bg-white/10 hover:text-white focus-visible:outline-white" : ""}`}
        onClick={() => {
          logout();
          navigate("/");
        }}
      >
        Sign out
      </button>
    </div>
  );
}

const topLink = ({ isActive }: { isActive: boolean }) =>
  `relative flex items-center gap-2 rounded-xl px-3.5 py-2 text-sm font-semibold no-underline transition-[color,background-color] duration-200 max-md:min-h-11 ${
    isActive
      ? "bg-ink text-white shadow-[0_6px_16px_-8px_rgb(11_13_20/0.6)]"
      : "text-slate-600 hover:bg-white hover:text-ink"
  }`;

export function CustomerLayout() {
  const { user } = useAuth();
  const { count } = useCart();
  const [open, setOpen] = useState(false);
  return (
    <div className="relative isolate flex min-h-dvh flex-col">
      <div className="aurora" aria-hidden="true" />
      <a href="#main" className={SKIP_LINK}>
        Skip to content
      </a>
      <header className="sticky top-0 z-40 px-3 pt-3 sm:px-5">
        <div className="glass header-settle relative mx-auto flex h-16 w-full max-w-6xl items-center gap-3 rounded-2xl px-3 sm:px-4 lg:gap-6">
          <Brand />
          <nav
            id="main-nav"
            className={`${
              open ? "flex animate-drop" : "max-md:hidden"
            } flex-1 gap-1 max-md:absolute max-md:inset-x-0 max-md:top-[calc(100%+0.5rem)] max-md:flex-col max-md:rounded-2xl max-md:border max-md:border-white/70 max-md:bg-white/95 max-md:p-2 max-md:shadow-2xl max-md:shadow-ink/10 max-md:backdrop-blur-xl md:flex md:items-center`}
            aria-label="Main"
            onClick={() => setOpen(false)}
          >
            <NavLink to="/" end className={topLink}>
              Shop
            </NavLink>
            {user && (
              <NavLink to="/orders" className={topLink}>
                My orders
              </NavLink>
            )}
            {user && (
              <NavLink to="/notifications" className={topLink}>
                Notifications
              </NavLink>
            )}
            {user?.role === "admin" && (
              <NavLink to="/admin" className={topLink}>
                Admin
              </NavLink>
            )}
            <NavLink to="/cart" className={(s) => `${topLink(s)} md:ml-auto`}>
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" className="size-[1.125rem]" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 6.5h11l-1 9.2a1.5 1.5 0 0 1-1.5 1.3H7a1.5 1.5 0 0 1-1.5-1.3l-1-9.2Zm3 0V6a2.5 2.5 0 0 1 5 0v.5" />
              </svg>
              Cart
              {count > 0 && (
                <span
                  key={count}
                  className="min-w-5 animate-pop rounded-full bg-linear-to-r from-cobalt-600 to-ember-500 px-1.5 py-px text-center text-[0.6875rem] font-bold text-white tabular-nums"
                  aria-label={`${count} items`}
                >
                  {count}
                </span>
              )}
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-1 md:ml-0">
            <AccountMenu />
            <button className="btn btn-ghost btn-small md:hidden" aria-expanded={open} aria-controls="main-nav" onClick={() => setOpen(!open)}>
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-5 transition-transform duration-300" aria-hidden="true">
                <path strokeLinecap="round" d={open ? "M5 5l10 10M15 5 5 15" : "M3 7h14M3 13h9"} />
              </svg>
              <span className="max-sm:sr-only">Menu</span>
            </button>
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 pt-10 pb-24 sm:px-6 sm:pt-14 lg:px-8">
        <Outlet />
      </main>
      <footer className="relative overflow-hidden border-t border-slate-200/70 bg-white/40 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-10 sm:px-6 lg:px-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <Brand />
            <ol className="flex flex-wrap items-center gap-2 font-mono text-[0.6875rem] tracking-wider text-slate-500 uppercase" aria-hidden="true">
              {["Received", "Stock", "Payment", "Notified"].map((s, i) => (
                <li key={s} className="flex items-center gap-2">
                  {i > 0 && <span className="h-px w-4 bg-slate-300" />}
                  {s}
                </li>
              ))}
            </ol>
          </div>
          <p className="text-[0.8125rem] text-slate-600">Kit &amp; Cable is a demo store. Payments are simulated; no card details are collected.</p>
        </div>
        <p
          className="pointer-events-none -mb-[0.22em] text-center font-display text-[clamp(4rem,16vw,12rem)] leading-none font-bold tracking-tighter text-transparent select-none [-webkit-text-stroke:1px_rgb(11_13_20/0.07)]"
          aria-hidden="true"
        >
          Kit &amp; Cable
        </p>
      </footer>
    </div>
  );
}

function RailIcon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" className="size-[1.125rem] shrink-0" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  );
}

const railLink = ({ isActive }: { isActive: boolean }) =>
  `group/rail relative flex min-h-11 shrink-0 items-center gap-3 rounded-xl px-3 text-sm font-medium whitespace-nowrap no-underline transition-[color,background-color] duration-200 focus-visible:outline-white ${
    isActive
      ? "bg-white/[0.08] text-white before:absolute before:top-2.5 before:bottom-2.5 before:-left-3 before:w-1 before:rounded-r-full before:bg-linear-to-b before:from-cobalt-400 before:to-ember-400 before:shadow-[0_0_14px_rgb(112_136_255/0.9)] before:content-[''] max-lg:before:hidden"
      : "text-slate-400 hover:bg-white/[0.05] hover:text-white"
  }`;

function RailLink({ to, end, icon, children }: { to: string; end?: boolean; icon: string; children: ReactNode }) {
  return (
    <NavLink to={to} end={end} className={railLink}>
      <RailIcon d={icon} />
      {children}
    </NavLink>
  );
}

export function AdminLayout() {
  return (
    <div className="min-h-dvh bg-slate-50 lg:grid lg:grid-cols-[16rem_minmax(0,1fr)]">
      <a href="#main" className={SKIP_LINK}>
        Skip to content
      </a>
      <aside className="relative isolate flex flex-col gap-4 overflow-hidden bg-ink px-3 py-4 text-slate-300 lg:sticky lg:top-0 lg:h-dvh lg:gap-8 lg:px-4 lg:py-7">
        <div className="pointer-events-none absolute -top-24 -left-20 -z-10 size-72 rounded-full bg-cobalt-600/30 blur-3xl" aria-hidden="true" />
        <div className="pointer-events-none absolute -bottom-24 -right-24 -z-10 size-64 rounded-full bg-ember-500/15 blur-3xl max-lg:hidden" aria-hidden="true" />
        <div className="flex items-center justify-between gap-3 px-1">
          <Brand to="/admin" dark />
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 font-mono text-[0.625rem] tracking-[0.14em] text-slate-300 uppercase">
            <span className="size-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgb(52_211_153)]" aria-hidden="true" />
            Ops
          </span>
        </div>
        <div className="max-lg:hidden">
          <p className="eyebrow px-3 text-slate-500">Operations</p>
        </div>
        <nav className="-mx-3 flex gap-1 overflow-x-auto px-3 [scrollbar-width:none] lg:mx-0 lg:-mt-5 lg:flex-col lg:overflow-visible lg:px-0" aria-label="Admin">
          <RailLink to="/admin" end icon="M3 3h6v8H3zM11 3h6v4h-6zM11 9h6v8h-6zM3 13h6v4H3z">
            Overview
          </RailLink>
          <RailLink to="/admin/orders" icon="M5 3h10v14H5zM8 7h4M8 10h4M8 13h2">
            Orders
          </RailLink>
          <RailLink to="/admin/failed" icon="M10 3 2.5 16.5h15L10 3Zm0 5.5v3.5m0 2.5h.01">
            Failed orders
          </RailLink>
          <RailLink to="/admin/inventory" icon="M3 6.5 10 3l7 3.5v7L10 17l-7-3.5v-7Zm0 0L10 10m0 0 7-3.5M10 10v7">
            Products &amp; stock
          </RailLink>
          <RailLink to="/admin/operations" icon="M2.5 10h3l2-5 3 10 2-5h5">
            Queues &amp; alarms
          </RailLink>
        </nav>
        <div className="flex flex-col gap-3 border-t border-white/10 pt-4 max-lg:flex-row max-lg:items-center max-lg:justify-between lg:mt-auto">
          <Link
            to="/"
            className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-slate-400 no-underline transition-colors hover:bg-white/5 hover:text-white focus-visible:outline-white"
          >
            <RailIcon d="M8 5H4v11h11v-4M11 3h6v6M17 3l-8 8" />
            View store
          </Link>
          <div className="px-1">
            <AccountMenu dark />
          </div>
        </div>
      </aside>
      <main id="main" className="dot-grid relative min-w-0 px-4 pt-8 pb-24 sm:px-6 lg:px-12 lg:pt-12">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-linear-to-b from-cobalt-100/60 to-transparent" aria-hidden="true" />
        <div className="relative mx-auto max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
