/**
 * AuthContext override — wraps the Lovable AuthContext to fix CSRF token
 * rotation after login/signup. Django rotates the CSRF token when a session is
 * created; the token injected into window.TAPNE_RUNTIME_CONFIG at page load
 * becomes stale. This wrapper updates it from the login/signup API response so
 * that subsequent POST/PATCH/DELETE calls carry a valid token.
 *
 * All types and exports mirror lovable/src/contexts/AuthContext.tsx so the rest
 * of the app is unaffected.
 */
import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import { apiGet, apiPost, apiPatch } from "@/lib/api";
import type { SessionResponse, SessionUser } from "@/types/api";
import {
  useAuthStore,
  sessionUserToAuthUser,
  type AuthUser,
} from "@/features/auth/store/useAuthStore";

export type User = AuthUser;

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  login: (identifier: string, password: string) => Promise<boolean>;
  signup: (name: string, email: string, password: string) => Promise<boolean>;
  logout: () => void;
  updateProfile: (updates: Partial<User>) => Promise<any>;
  lastAuthError: string;
  requireAuth: (onSuccess?: () => void) => void;
  loginModalOpen: boolean;
  setLoginModalOpen: (open: boolean) => void;
  pendingAuthAction: (() => void) | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function _refreshCsrf(token: string) {
  if (token && window.TAPNE_RUNTIME_CONFIG?.csrf) {
    (window.TAPNE_RUNTIME_CONFIG as any).csrf.token = token;
  }
}

function _clearRuntimeSessionSnapshot() {
  if (!window.TAPNE_RUNTIME_CONFIG?.session) {
    return;
  }
  (window.TAPNE_RUNTIME_CONFIG as any).session.authenticated = false;
  (window.TAPNE_RUNTIME_CONFIG as any).session.user = null;
}

export const AuthProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  const store = useAuthStore();
  const [lastAuthError, setLastAuthError] = useState("");
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [pendingAuthAction, setPendingAuthAction] = useState<
    (() => void) | null
  >(null);

  // Hydrate from runtime config on mount
  useEffect(() => {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    if (cfg?.session?.authenticated && cfg.session.user && !store.user) {
      store.setAuth(sessionUserToAuthUser(cfg.session.user), cfg.csrf?.token || "session");
    }
  }, []);

  // Hydrate session from API on mount
  useEffect(() => {
    const cfg = window.TAPNE_RUNTIME_CONFIG;
    if (!cfg?.api?.session) return;
    apiGet<SessionResponse>(cfg.api.session)
      .then((data) => {
        if (data.csrf_token) _refreshCsrf(data.csrf_token);
        if (data.authenticated && data.user) {
          store.setAuth(sessionUserToAuthUser(data.user), data.csrf_token || "session");
        }
      })
      .catch(() => {});
  }, []);

  const login = useCallback(
    async (identifier: string, password: string): Promise<boolean> => {
      setLastAuthError("");
      try {
        const cfg = window.TAPNE_RUNTIME_CONFIG;
        const data = await apiPost<{ user: SessionUser; csrf_token?: string }>(
          cfg.api.login,
          { username: identifier, password }
        );
        if (data.csrf_token) _refreshCsrf(data.csrf_token);
        const authUser = sessionUserToAuthUser(data.user);
        store.setAuth(authUser, data.csrf_token || "session-token");
        return true;
      } catch (err: any) {
        setLastAuthError(err?.error || "Invalid credentials");
        return false;
      }
    },
    []
  );

  const signup = useCallback(
    async (
      name: string,
      email: string,
      password: string
    ): Promise<boolean> => {
      setLastAuthError("");
      try {
        const cfg = window.TAPNE_RUNTIME_CONFIG;
        const data = await apiPost<{ user: SessionUser; csrf_token?: string }>(
          cfg.api.signup,
          { first_name: name, email, password }
        );
        if (data.csrf_token) _refreshCsrf(data.csrf_token);
        const authUser = sessionUserToAuthUser(data.user);
        store.setAuth(authUser, data.csrf_token || "session-token");
        return true;
      } catch (err: any) {
        setLastAuthError(err?.error || "Something went wrong");
        return false;
      }
    },
    []
  );

  const logout = useCallback(async () => {
    // Clear local auth state before the network round trip so post-logout
    // redirects do not briefly mount authenticated-only fetches.
    store.logout();
    _clearRuntimeSessionSnapshot();
    try {
      const cfg = window.TAPNE_RUNTIME_CONFIG;
      await apiPost(cfg.api.logout, {});
    } catch {}
  }, []);

  const updateProfile = useCallback(async (updates: Partial<User>) => {
    try {
      const cfg = window.TAPNE_RUNTIME_CONFIG;
      const payload: Record<string, unknown> = {};
      if (updates.name !== undefined) payload.display_name = updates.name;
      if (updates.bio !== undefined) payload.bio = updates.bio;
      if (updates.location !== undefined) payload.location = updates.location;
      if (updates.website !== undefined) payload.website = updates.website;
      if (updates.avatar !== undefined) payload.avatar_url = updates.avatar;
      if (updates.travel_tags !== undefined) payload.travel_tags = updates.travel_tags;
      const data = await apiPatch<{ profile?: any; member_profile?: any }>(cfg.api.profile_me, payload);
      const profile = data.profile || data.member_profile || {};
      store.updateUser({
        name: profile.display_name ?? updates.name ?? store.user?.name,
        bio: profile.bio ?? updates.bio ?? store.user?.bio,
        location: profile.location ?? updates.location ?? store.user?.location,
        website: profile.website ?? updates.website ?? store.user?.website,
        avatar: profile.avatar_url ?? updates.avatar ?? store.user?.avatar,
        travel_tags: profile.travel_tags ?? updates.travel_tags ?? store.user?.travel_tags,
      });
      return profile;
    } catch (err: any) {
      setLastAuthError(err?.message || "Could not update profile");
      return null;
    }
  }, []);

  const requireAuth = useCallback(
    (onSuccess?: () => void) => {
      if (store.user) {
        onSuccess?.();
        return;
      }
      setPendingAuthAction(() => onSuccess || null);
      setLoginModalOpen(true);
    },
    [store.user]
  );

  return (
    <AuthContext.Provider
      value={{
        user: store.user,
        isAuthenticated: !!store.user,
        login,
        signup,
        logout,
        updateProfile,
        lastAuthError,
        requireAuth,
        loginModalOpen,
        setLoginModalOpen: (open: boolean) => {
          setLoginModalOpen(open);
          if (!open) setPendingAuthAction(null);
        },
        pendingAuthAction,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
