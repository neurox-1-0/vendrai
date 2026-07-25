"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Keycloak from "keycloak-js";
import { createContext, useContext, useEffect, useState } from "react";

import { setAccessToken } from "@/lib/auth-token";

interface AuthContextValue {
  roles: ReadonlySet<string>;
}

const AuthContext = createContext<AuthContextValue>({
  roles: new Set(),
});

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [authReady, setAuthReady] = useState(process.env.NEXT_PUBLIC_AUTH_MODE !== "keycloak");
  const [roles, setRoles] = useState<ReadonlySet<string>>(
    () => new Set(
      process.env.NEXT_PUBLIC_AUTH_MODE === "keycloak"
        ? []
        : ["requester", "analyst", "approver", "auditor", "admin"],
    ),
  );
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: { staleTime: 5_000, refetchInterval: 10_000, retry: 2 },
      mutations: { retry: 0 },
    },
  }));
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_AUTH_MODE !== "keycloak") return;
    const keycloak = new Keycloak({
      url: process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? "http://localhost:8080",
      realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? "neurox",
      clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ?? "neurox-web",
    });
    let refreshTimer: number | undefined;
    keycloak.init({ onLoad: "login-required", pkceMethod: "S256", checkLoginIframe: false }).then((authenticated) => {
      if (!authenticated) return keycloak.login();
      setAccessToken(keycloak.token ?? null);
      const claims = keycloak.tokenParsed as {
        realm_access?: { roles?: string[] };
        resource_access?: Record<string, { roles?: string[] }>;
      } | undefined;
      setRoles(
        new Set([
          ...(claims?.realm_access?.roles ?? []),
          ...(claims?.resource_access?.["neurox-api"]?.roles ?? []),
        ]),
      );
      setAuthReady(true);
      refreshTimer = window.setInterval(() => {
        keycloak.updateToken(60)
          .then(() => setAccessToken(keycloak.token ?? null))
          .catch(() => {
            setAccessToken(null);
            void keycloak.login();
          });
      }, 30_000);
    }).catch(() => setAuthReady(false));
    return () => {
      if (refreshTimer !== undefined) window.clearInterval(refreshTimer);
      setAccessToken(null);
      setRoles(new Set());
      keycloak.clearToken();
    };
  }, []);
  if (!authReady) return <main className="grid min-h-screen place-items-center" aria-live="polite">Connecting to secure identity provider…</main>;
  return (
    <AuthContext.Provider value={{ roles }}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </AuthContext.Provider>
  );
}
