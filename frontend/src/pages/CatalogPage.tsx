import { useState } from "react";
import { Link } from "react-router-dom";
import { productApi } from "../api/endpoints";
import { Button, EmptyState, ErrorMessage, LoadMore, ProductArt, Spinner } from "../components/ui";
import { useCart } from "../contexts/CartContext";
import { useToast } from "../contexts/ToastContext";
import { useAsync } from "../hooks/useAsync";
import type { Product } from "../types";
import { formatMoney } from "../utils/format";

export function StockNote({ available }: { available: number }) {
  if (available <= 0) return <span className="stock stock-out">Out of stock</span>;
  if (available <= 5) return <span className="stock stock-low">Only {available} left</span>;
  return <span className="stock">{available} in stock</span>;
}

export function CatalogPage() {
  const { dispatch, lines } = useCart();
  const toast = useToast();
  const [extra, setExtra] = useState<Product[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const { data, error, loading, reload } = useAsync(async () => {
    const page = await productApi.list();
    setExtra([]);
    setNext(page.nextToken);
    return page.items;
  }, []);

  const products = [...(data ?? []), ...extra];

  async function more() {
    setLoadingMore(true);
    try {
      const page = await productApi.list(next);
      setExtra((e) => [...e, ...page.items]);
      setNext(page.nextToken);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setLoadingMore(false);
    }
  }

  function add(p: Product) {
    const inCart = lines.find((l) => l.productId === p.productId)?.quantity ?? 0;
    if (inCart >= p.available) {
      toast(`All ${p.available} available ${p.name} are already in your cart.`, "info");
      return;
    }
    dispatch({ type: "add", product: p });
    toast(`Added ${p.name} to your cart.`, "success");
  }

  return (
    <>
      <section className="intro">
        <h1>Gear for the desk, shipped once it's really yours.</h1>
        <p className="lead muted">
          Every order is checked against live stock and paid before we confirm it. You can follow each step on the order
          page.
        </p>
      </section>

      {loading && <Spinner label="Loading products" />}
      {error && <ErrorMessage error={error} onRetry={reload} />}
      {!loading && !error && products.length === 0 && (
        <EmptyState title="No products yet">An administrator can add products in Admin › Products &amp; stock.</EmptyState>
      )}

      <ul className="product-grid">
        {products.map((p) => (
          <li key={p.productId} className="product">
            <Link to={`/products/${p.productId}`} className="product-link">
              <ProductArt name={p.name} category={p.category} imageUrl={p.imageUrl} />
              <span className="product-cat muted small">{p.category}</span>
              <h2 className="product-name">{p.name}</h2>
            </Link>
            <p className="product-desc muted">{p.description}</p>
            <div className="product-foot">
              <div>
                <div className="price">{formatMoney(p.priceMinor, p.currency)}</div>
                <StockNote available={p.available} />
              </div>
              <Button variant="secondary" onClick={() => add(p)} disabled={!p.inStock} aria-label={`Add ${p.name} to cart`}>
                Add to cart
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <LoadMore nextToken={next} loading={loadingMore} onClick={more} />
    </>
  );
}
