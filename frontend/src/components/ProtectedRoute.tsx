import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import type { Role } from "../types";
import { NoticeIcon, noticeClass } from "./ui";

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
      <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6 lg:px-8">
        <div className={noticeClass("error")} role="alert">
          <NoticeIcon tone="error" />
          <p>This area is for administrators. You are signed in as {user.email}.</p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
