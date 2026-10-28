# Frontend – Kit & Cable (React + TypeScript + Vite)

Customer storefront and admin console for the Order Management System.
Every page talks to the real API; there is no mock data in the app.

## Run locally

```bash
# terminal 1 – backend simulation (Python stdlib only)
cd backend && python3 local/dev_server.py          # http://127.0.0.1:8000

# terminal 2 – frontend
cd frontend
cp .env.example .env.local                          # VITE_API_BASE_URL=http://127.0.0.1:8000
npm install
npm run dev                                         # http://localhost:5173
```

Local accounts: `customer@example.com / Customer123!`, `admin@example.com / Admin123!`.

To run the UI against the deployed API instead, put the `api_url` Terraform output
in `.env.local` (`http://localhost:5173` is allowed by the default CORS settings).

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Vite dev server on port 5173 |
| `npm run typecheck` | `tsc --noEmit` |
| `npm test` | Vitest unit tests (`src/test`) |
| `npm run build` | Type-check and build to `dist/` |

Deployment is done by `scripts/deploy-frontend.sh`, which writes `.env.production.local`
from Terraform outputs, builds, and syncs `dist/` to the S3 bucket.

## Structure

```
src/
  api/         client.ts (fetch wrapper, tokens, correlation ids, errors) · endpoints.ts
  components/  ui.tsx (Button, StatusBadge, Field, ConfirmDialog, …) · DataTable · OrderPipeline · ProtectedRoute
  contexts/    AuthContext (Cognito tokens) · CartContext (reducer) · ToastContext
  hooks/       useAsync / usePolling
  layouts/     CustomerLayout (top bar) · AdminLayout (side rail)
  pages/       Catalog, Product, Cart & checkout, Orders, Order tracking, Notifications, Sign in/up
  pages/admin/ Overview, Orders, Order detail (retry/cancel), Failed orders, Products & stock, Queues & alarms
  types/       API types
  utils/       formatting, order pipeline mapping, idempotency keys
  test/        unit tests
```

## Security notes

* No AWS credentials or secrets exist in the frontend. `VITE_*` values are public.
* Access/ID tokens (60 min) live in memory and `sessionStorage` (per tab, cleared on close);
  the refresh token is kept in memory only. See `docs/security.md`.
* Route guards only improve usability – the API enforces authentication (JWT authorizer)
  and the admin role (Cognito group) on every request.
* Prices and totals shown in the cart are estimates; the API recalculates them.
* Checkout sends an `Idempotency-Key` that is reused until the order is accepted, so a
  double click or retry can't create two orders.
