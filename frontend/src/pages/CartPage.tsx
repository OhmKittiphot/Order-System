import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { orderApi, productApi } from "../api/endpoints";
import { Button, EmptyState, ErrorMessage } from "../components/ui";
import { useAuth } from "../contexts/AuthContext";
import { MAX_QTY, cartProblems, estimatedTotal, useCart } from "../contexts/CartContext";
import { cartSignature, checkoutKey, clearCheckoutKey } from "../utils/idempotency";
import { formatMoney } from "../utils/format";

export function CartPage() {
  const { lines, dispatch } = useCart();
  const [checking, setChecking] = useState(false);

  // Refresh stock and prices for items already in the cart.
  useEffect(() => {
    if (lines.length === 0) return;
    let cancelled = false;
    setChecking(true);
    Promise.all(lines.map((l) => productApi.get(l.productId).catch(() => null)))
      .then((products) => {
        if (!cancelled) dispatch({ type: "refreshStock", products: products.filter((p) => p !== null) });
      })
      .finally(() => !cancelled && setChecking(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (lines.length === 0) {
    return (
      <EmptyState title="Your cart is empty" action={<Link className="btn btn-primary" to="/">Browse products</Link>}>
        Add something from the shop to get started.
      </EmptyState>
    );
  }
  const currency = lines[0]!.currency;
  const problems = cartProblems(lines);

  return (
    <div className="two-col">
      <section>
        <h1>Cart</h1>
        <ul className="lines">
          {lines.map((l) => (
            <li key={l.productId} className="line">
              <div>
                <Link to={`/products/${l.productId}`} className="line-name">
                  {l.name}
                </Link>
                <div className="muted small">{formatMoney(l.priceMinor, l.currency)} each</div>
              </div>
              <label className="sr-only" htmlFor={`q-${l.productId}`}>
                Quantity of {l.name}
              </label>
              <input
                id={`q-${l.productId}`}
                className="qty"
                type="number"
                min={1}
                max={Math.max(1, Math.min(l.available, MAX_QTY))}
                value={l.quantity}
                onChange={(e) => dispatch({ type: "setQty", productId: l.productId, quantity: Number(e.target.value) })}
              />
              <div className="num line-total">{formatMoney(l.priceMinor * l.quantity, l.currency)}</div>
              <button className="btn btn-ghost btn-small" onClick={() => dispatch({ type: "remove", productId: l.productId })}>
                Remove
              </button>
            </li>
          ))}
        </ul>
        {checking && <p className="muted small">Checking current stock…</p>}
      </section>
      <CheckoutSummary currency={currency} problems={problems} />
    </div>
  );
}

function CheckoutSummary({ currency, problems }: { currency: string; problems: string[] }) {
  const { lines, dispatch } = useCart();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const total = estimatedTotal(lines);

  async function placeOrder() {
    if (submitting) return; // guard against double clicks
    setSubmitting(true);
    setError(null);
    const items = lines.map((l) => ({ productId: l.productId, quantity: l.quantity }));
    const key = checkoutKey(cartSignature(items));
    try {
      const order = await orderApi.create(items, key);
      clearCheckoutKey();
      dispatch({ type: "clear" });
      navigate(`/orders/${order.orderId}`, { state: { justPlaced: true } });
    } catch (e) {
      // Keep the same idempotency key so "Try again" cannot create a duplicate order.
      setError(e as ApiError);
      setSubmitting(false);
    }
  }

  return (
    <aside className="summary" aria-labelledby="summary-title">
      <h2 id="summary-title">Order summary</h2>
      <dl className="summary-rows">
        <div>
          <dt>Items</dt>
          <dd className="num">{lines.reduce((n, l) => n + l.quantity, 0)}</dd>
        </div>
        <div className="summary-total">
          <dt>Estimated total</dt>
          <dd className="num">{formatMoney(total, currency)}</dd>
        </div>
      </dl>
      <p className="muted small">
        The final amount is calculated by the store from current prices when you place the order. Payment is simulated.
      </p>
      {problems.length > 0 && (
        <div className="notice notice-warn" role="alert">
          {problems.map((p) => (
            <p key={p}>{p}</p>
          ))}
        </div>
      )}
      {error && <ErrorMessage error={error} />}
      {user ? (
        <Button className="btn-block" onClick={placeOrder} busy={submitting} disabled={problems.length > 0}>
          {submitting ? "Placing order" : "Place order"}
        </Button>
      ) : (
        <Link className="btn btn-primary btn-block" to="/login" state={{ from: "/cart" }}>
          Sign in to place your order
        </Link>
      )}
    </aside>
  );
}
