import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { configureAuth } from "../api/client";
import { authApi } from "../api/endpoints";
import type { Session, User } from "../types";

/*
 * Token handling (see docs/security.md):
 * - The access token (60 min) is kept in memory and mirrored to
 *   sessionStorage so a page reload in the same tab keeps you signed in.
 *   sessionStorage is per-tab and cleared when the tab closes.
 * - The refresh token (1 day) is kept in memory only and is never written
 *   to localStorage/sessionStorage, limiting what an XSS bug could steal.
 * - The backend never trusts the role shown here; the Lambda Authorizer
 *   verifies the JWT and handlers check its role on every request.
 */

const STORAGE_KEY = "kc.session";

interface StoredSession {
  accessToken: string;
  expiresAt: number;
  user: User;
}

interface AuthState {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function readStored(): StoredSession | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredSession;
    return parsed.expiresAt > Date.now() + 30_000 ? parsed : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const stored = readStored();
  const [user, setUser] = useState<User | null>(stored?.user ?? null);
  const access = useRef<{ token: string; expiresAt: number } | null>(
    stored ? { token: stored.accessToken, expiresAt: stored.expiresAt } : null,
  );
  const refreshToken = useRef<string | null>(null);

  const apply = useCallback((session: Session) => {
    const expiresAt = Date.now() + session.tokens.expiresIn * 1000;
    access.current = { token: session.tokens.accessToken, expiresAt };
    if (session.tokens.refreshToken) refreshToken.current = session.tokens.refreshToken;
    setUser(session.user);
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ accessToken: session.tokens.accessToken, expiresAt, user: session.user } satisfies StoredSession),
      );
    } catch {
      /* storage unavailable (private mode): memory only */
    }
  }, []);

  const logout = useCallback(() => {
    access.current = null;
    refreshToken.current = null;
    setUser(null);
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  const tryRefresh = useCallback(async (): Promise<boolean> => {
    if (!refreshToken.current) {
      logout();
      return false;
    }
    try {
      apply(await authApi.refresh(refreshToken.current));
      return true;
    } catch {
      logout();
      return false;
    }
  }, [apply, logout]);

  useEffect(() => {
    configureAuth(
      () => (access.current && access.current.expiresAt > Date.now() ? access.current.token : null),
      tryRefresh,
    );
  }, [tryRefresh]);

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await authApi.login(email, password);
      apply(session);
      return session.user;
    },
    [apply],
  );

  const register = useCallback(async (email: string, password: string, displayName: string) => {
    await authApi.register(email, password, displayName);
  }, []);

  const value = useMemo(() => ({ user, ready: true, login, register, logout }), [user, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
