import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthProvider } from "./contexts/AuthContext";
import { CartProvider } from "./contexts/CartContext";
import { ToastProvider } from "./contexts/ToastContext";
import { AdminLayout, CustomerLayout } from "./layouts/Layouts";
import { LoginPage, NotFoundPage, RegisterPage } from "./pages/AuthPages";
import { CartPage } from "./pages/CartPage";
import { CatalogPage } from "./pages/CatalogPage";
import { NotificationsPage, OrderDetailPage, OrdersPage } from "./pages/OrderPages";
import { ProductPage } from "./pages/ProductPage";
import { AdminOrderDetailPage, AdminOrdersPage, FailedOrdersPage } from "./pages/admin/AdminOrders";
import { AdminDashboardPage, InventoryPage, OperationsPage } from "./pages/admin/AdminPages";

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <CartProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<CustomerLayout />}>
                <Route index element={<CatalogPage />} />
                <Route path="products/:productId" element={<ProductPage />} />
                <Route path="cart" element={<CartPage />} />
                <Route path="login" element={<LoginPage />} />
                <Route path="register" element={<RegisterPage />} />
                <Route path="orders" element={<ProtectedRoute><OrdersPage /></ProtectedRoute>} />
                <Route path="orders/:orderId" element={<ProtectedRoute><OrderDetailPage /></ProtectedRoute>} />
                <Route path="notifications" element={<ProtectedRoute><NotificationsPage /></ProtectedRoute>} />
                <Route path="*" element={<NotFoundPage />} />
              </Route>
              <Route path="admin" element={<ProtectedRoute role="admin"><AdminLayout /></ProtectedRoute>}>
                <Route index element={<AdminDashboardPage />} />
                <Route path="orders" element={<AdminOrdersPage />} />
                <Route path="orders/:orderId" element={<AdminOrderDetailPage />} />
                <Route path="failed" element={<FailedOrdersPage />} />
                <Route path="inventory" element={<InventoryPage />} />
                <Route path="operations" element={<OperationsPage />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </CartProvider>
      </AuthProvider>
    </ToastProvider>
  );
}
