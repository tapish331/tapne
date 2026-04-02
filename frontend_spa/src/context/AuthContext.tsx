import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { apiGet, apiPatch, apiPost, apiUrl } from "@frontend/lib/api";
import { FrontendUser, getInitialUser } from "@frontend/lib/config";

type AuthContextValue = {
  user: FrontendUser | null;
  isAuthenticated: boolean;
  ready: boolean;
  login: (emailOrUsername: string, password: string) => Promise<boolean>;
  signup: (name: string, email: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  updateProfile: (updates: {
    display_name?: string;
    bio?: string;
    location?: string;
    website?: string;
  }) => Promise<boolean>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<FrontendUser | null>(() => getInitialUser());
  const [ready, setReady] = useState<boolean>(false);

  async function refresh() {
    const payload = await apiGet<{ authenticated: boolean; user: FrontendUser | null }>(apiUrl("session"));
    setUser(payload.user ?? null);
    setReady(true);
  }

  useEffect(() => {
    refresh().catch(() => {
      setReady(true);
    });
  }, []);

  async function login(emailOrUsername: string, password: string) {
    const payload = await apiPost<{ authenticated: boolean; user: FrontendUser | null }>(apiUrl("login"), {
      username: emailOrUsername,
      email: emailOrUsername,
      password,
    });
    setUser(payload.user ?? null);
    return payload.authenticated;
  }

  async function signup(name: string, email: string, password: string) {
    const nameParts = name.trim().split(/\s+/);
    const firstName = nameParts.slice(0, 1).join(" ");
    const lastName = nameParts.slice(1).join(" ");
    const usernameCandidate = email.includes("@") ? email.split("@")[0] : name.replace(/\s+/g, "").toLowerCase();
    const payload = await apiPost<{ authenticated: boolean; user: FrontendUser | null }>(apiUrl("signup"), {
      username: usernameCandidate,
      first_name: firstName,
      last_name: lastName,
      email,
      password1: password,
      password2: password,
    });
    setUser(payload.user ?? null);
    return payload.authenticated;
  }

  async function logout() {
    await apiPost(apiUrl("logout"));
    setUser(null);
  }

  async function updateProfile(updates: {
    display_name?: string;
    bio?: string;
    location?: string;
    website?: string;
  }) {
    const payload = await apiPatch<{ ok: boolean; profile: FrontendUser }>(apiUrl("profile_me"), updates);
    setUser(payload.profile);
    return payload.ok;
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: !!user,
      ready,
      login,
      signup,
      logout,
      refresh,
      updateProfile,
    }),
    [user, ready],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
