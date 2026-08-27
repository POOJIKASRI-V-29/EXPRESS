"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api, setToken, getToken } from "./api";

interface AuthCtx {
  user: { id: string; email: string; name: string } | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void | Promise<void>;
}
const Ctx = createContext<AuthCtx>(null as any);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthCtx["user"]>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      if (getToken()) {
        try { setUser(await api.me()); } catch { setToken(null); }
      }
      setReady(true);
    })();
  }, []);

  const login = async (email: string, password: string) => {
    const { access_token } = await api.login(email, password);
    setToken(access_token);
    setUser(await api.me());
  };
  const logout = async () => {
    // Clear the server-side refresh cookie first; if that call fails we still
    // drop local state so the user is not stuck in a session they left.
    try { await api.logout(); } catch { /* logging out must always succeed locally */ }
    setToken(null);
    setUser(null);
    window.location.href = "/login";
  };

  return <Ctx.Provider value={{ user, ready, login, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);

export function useRequireAuth() {
  const { user, ready } = useAuth();
  const router = useRouter();
  useEffect(() => { if (ready && !user) router.replace("/login"); }, [ready, user, router]);
  return { user, ready };
}
