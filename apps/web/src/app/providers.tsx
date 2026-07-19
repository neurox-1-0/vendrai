"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { useEffect } from "react";
import Keycloak from "keycloak-js";

export function Providers({ children }: { children: React.ReactNode }) {
  const [authReady, setAuthReady] = useState(process.env.NEXT_PUBLIC_AUTH_MODE !== "keycloak");
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
    keycloak.init({ onLoad: "login-required", pkceMethod: "S256", checkLoginIframe: false }).then((authenticated) => {
      if (!authenticated) return keycloak.login();
      if (keycloak.token) window.sessionStorage.setItem("neurox_access_token", keycloak.token);
      setAuthReady(true);
      window.setInterval(() => keycloak.updateToken(60).then((refreshed) => {
        if (refreshed && keycloak.token) window.sessionStorage.setItem("neurox_access_token", keycloak.token);
      }), 30_000);
    }).catch(() => setAuthReady(false));
  }, []);
  if (!authReady) return <main className="grid min-h-screen place-items-center" aria-live="polite">Connecting to secure identity provider…</main>;
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
