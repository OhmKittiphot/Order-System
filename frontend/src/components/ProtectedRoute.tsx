import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import type { Role } from "../types";

/**
 * Usability only: hides pages the user cannot use. Real enforcement is on
 * the server (JWT authorizer + role checks in every admin handler).
 */
export function ProtectedRoute({ role, children }: { role?: Role; children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (role && user.role !== role) {
    return (
      <div className="page">
        <div className="notice notice-error" role="alert">
          <p>This area is for administrators. You are signed in as {user.email}.</p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
