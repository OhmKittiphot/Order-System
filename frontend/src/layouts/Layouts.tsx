import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useCart } from "../contexts/CartContext";

function Brand({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className="brand">
      <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
        <rect width="32" height="32" rx="7" fill="currentColor" />
        <path d="M7 16h6l3-6 3 12 3-6h3" stroke="#fff" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span>Kit &amp; Cable</span>
    </Link>
  );
}

function AccountMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) {
    return (
      <div className="account">
        <NavLink to="/login">Sign in</NavLink>
        <NavLink to="/register" className="btn btn-secondary btn-small">
          Create account
        </NavLink>
      </div>
    );
  }
  return (
    <div className="account">
      <span className="muted small account-name">{user.displayName || user.email}</span>
      <button
        className="btn btn-ghost btn-small"
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

export function CustomerLayout() {
  const { user } = useAuth();
  const { count } = useCart();
  const [open, setOpen] = useState(false);
  return (
    <div className="shell-customer">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="topbar">
        <Brand />
        <button className="menu-toggle btn btn-ghost btn-small" aria-expanded={open} aria-controls="main-nav" onClick={() => setOpen(!open)}>
          Menu
        </button>
        <nav id="main-nav" className={`topnav ${open ? "open" : ""}`} aria-label="Main" onClick={() => setOpen(false)}>
          <NavLink to="/" end>
            Shop
          </NavLink>
          {user && <NavLink to="/orders">My orders</NavLink>}
          {user && <NavLink to="/notifications">Notifications</NavLink>}
          {user?.role === "admin" && <NavLink to="/admin">Admin</NavLink>}
          <NavLink to="/cart" className="cart-link">
            Cart{count > 0 && <span className="cart-count" aria-label={`${count} items`}>{count}</span>}
          </NavLink>
        </nav>
        <AccountMenu />
      </header>
      <main id="main" className="page">
        <Outlet />
      </main>
      <footer className="footer muted small">
        Kit &amp; Cable is a demo store. Payments are simulated; no card details are collected.
      </footer>
    </div>
  );
}

export function AdminLayout() {
  return (
    <div className="shell-admin">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <aside className="rail">
        <Brand to="/admin" />
        <p className="rail-tag muted small">Operations</p>
        <nav className="railnav" aria-label="Admin">
          <NavLink to="/admin" end>
            Overview
          </NavLink>
          <NavLink to="/admin/orders">Orders</NavLink>
          <NavLink to="/admin/failed">Failed orders</NavLink>
          <NavLink to="/admin/inventory">Products &amp; stock</NavLink>
          <NavLink to="/admin/operations">Queues &amp; alarms</NavLink>
        </nav>
        <div className="rail-foot">
          <Link to="/" className="small">
            View store
          </Link>
          <AccountMenu />
        </div>
      </aside>
      <main id="main" className="admin-main">
        <Outlet />
      </main>
    </div>
  );
}
