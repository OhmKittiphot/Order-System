import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { productApi } from "../api/endpoints";
import { Button, ErrorMessage, ProductArt, Spinner } from "../components/ui";
import { MAX_QTY, useCart } from "../contexts/CartContext";
import { useToast } from "../contexts/ToastContext";
import { useAsync } from "../hooks/useAsync";
import { formatMoney } from "../utils/format";
import { StockNote } from "./CatalogPage";

export function ProductPage() {
  const { productId = "" } = useParams();
  const { dispatch } = useCart();
  const toast = useToast();
  const [qty, setQty] = useState(1);
  const { data: p, error, loading, reload } = useAsync(() => productApi.get(productId), [productId]);

  if (loading) return <Spinner label="Loading product" />;
  if (error) return <ErrorMessage error={error.status === 404 ? "This product is no longer available." : error} onRetry={error.status === 404 ? undefined : reload} />;
  if (!p) return null;
  const max = Math.min(p.available, MAX_QTY);

  return (
    <article className="product-detail">
      <Link to="/" className="back">
        ‹ All products
      </Link>
      <div className="product-detail-grid">
        <ProductArt name={p.name} category={p.category} imageUrl={p.imageUrl} />
        <div>
          <p className="muted">{p.category}</p>
          <h1>{p.name}</h1>
          <p className="price price-lg">{formatMoney(p.priceMinor, p.currency)}</p>
          <StockNote available={p.available} />
          <p className="body-text">{p.description}</p>
          <form
            className="buy-row"
            onSubmit={(e) => {
              e.preventDefault();
              dispatch({ type: "add", product: p, quantity: qty });
              toast(`Added ${qty} × ${p.name} to your cart.`, "success");
            }}
          >
            <label htmlFor="qty">Quantity</label>
            <input
              id="qty"
              type="number"
              min={1}
              max={Math.max(1, max)}
              value={qty}
              disabled={!p.inStock}
              onChange={(e) => setQty(Math.max(1, Math.min(max, Number(e.target.value) || 1)))}
            />
            <Button type="submit" disabled={!p.inStock}>
              Add to cart
            </Button>
          </form>
        </div>
      </div>
    </article>
  );
}
