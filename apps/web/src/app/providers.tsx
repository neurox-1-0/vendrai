"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { setAccessToken } from "@/lib/auth-token";
import { ApplicationCopilot } from "@/components/application-copilot";
import { AssistanceProvider } from "@/components/assistance-registry";
import { CopilotProvider } from "@/components/copilot-provider";
import { LoginScreen } from "@/components/auth/login-screen";

interface AuthContextValue {
  roles: ReadonlySet<string>;
  displayName: string;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  roles: new Set(),
  displayName: "there",
  logout: () => {},
});

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

const KEYCLOAK_MODE = process.env.NEXT_PUBLIC_AUTH_MODE === "keycloak";
const KEYCLOAK_URL = process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? "http://localhost:8080";
const REALM = process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? "neurox";
const CLIENT_ID = process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ?? "neurox-web";
const TOKEN_URL = `${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token`;
const LOGOUT_URL = `${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/logout`;
const REFRESH_TOKEN_KEY = "neurox.refresh_token";
const REFRESH_INTERVAL_MS = 30_000;

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

interface TokenClaims {
  name?: string;
  preferred_username?: string;
  realm_access?: { roles?: string[] };
  resource_access?: Record<string, { roles?: string[] }>;
}

function decodeJwtClaims(token: string): TokenClaims | null {
  try {
    const payload = token.split(".")[1];
    const base64 = payload
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(payload.length + ((4 - (payload.length % 4)) % 4), "=");
    return JSON.parse(atob(base64)) as TokenClaims;
  } catch {
    return null;
  }
}

class TokenRequestError extends Error {
  constructor(message: string, public readonly invalidCredentials: boolean) {
    super(message);
  }
}

async function requestToken(body: URLSearchParams): Promise<TokenResponse> {
  let response: Response;
  try {
    response = await fetch(TOKEN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
  } catch {
    throw new TokenRequestError("Unable to reach the identity provider.", false);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { error?: string } | null;
    throw new TokenRequestError("Authentication failed", payload?.error === "invalid_grant");
  }
  return response.json() as Promise<TokenResponse>;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [authReady, setAuthReady] = useState(!KEYCLOAK_MODE);
  const [authenticated, setAuthenticated] = useState(!KEYCLOAK_MODE);
  const [roles, setRoles] = useState<ReadonlySet<string>>(
    () => new Set(KEYCLOAK_MODE ? [] : ["requester", "analyst", "approver", "auditor", "admin"]),
  );
  const [displayName, setDisplayName] = useState("there");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginPending, setLoginPending] = useState(false);
  const refreshTokenRef = useRef<string | null>(null);
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: { staleTime: 5_000, refetchInterval: 10_000, retry: 2 },
      mutations: { retry: 0 },
    },
  }));

  const applySession = useCallback((tokens: TokenResponse) => {
    setAccessToken(tokens.access_token);
    refreshTokenRef.current = tokens.refresh_token;
    sessionStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
    const claims = decodeJwtClaims(tokens.access_token);
    setRoles(
      new Set([
        ...(claims?.realm_access?.roles ?? []),
        ...(claims?.resource_access?.["neurox-api"]?.roles ?? []),
      ]),
    );
    setDisplayName(claims?.name ?? claims?.preferred_username ?? "there");
    setAuthenticated(true);
  }, []);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    refreshTokenRef.current = null;
    sessionStorage.removeItem(REFRESH_TOKEN_KEY);
    setRoles(new Set());
    setDisplayName("there");
    setAuthenticated(false);
  }, []);

  const login = useCallback((username: string, password: string) => {
    setLoginPending(true);
    setLoginError(null);
    requestToken(
      new URLSearchParams({ grant_type: "password", client_id: CLIENT_ID, username, password }),
    )
      .then(applySession)
      .catch((error: unknown) => {
        const invalidCredentials = error instanceof TokenRequestError && error.invalidCredentials;
        setLoginError(
          invalidCredentials
            ? "Invalid username or password."
            : "Unable to reach the identity provider. Please try again.",
        );
      })
      .finally(() => setLoginPending(false));
  }, [applySession]);

  const logout = useCallback(() => {
    const refreshToken = refreshTokenRef.current;
    if (refreshToken) {
      const body = new URLSearchParams({ client_id: CLIENT_ID, refresh_token: refreshToken });
      void fetch(LOGOUT_URL, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body }).catch(() => {});
    }
    clearSession();
  }, [clearSession]);

  useEffect(() => {
    if (!KEYCLOAK_MODE) return;
    async function resume() {
      const storedRefreshToken = sessionStorage.getItem(REFRESH_TOKEN_KEY);
      if (!storedRefreshToken) return;
      try {
        const tokens = await requestToken(new URLSearchParams({ grant_type: "refresh_token", client_id: CLIENT_ID, refresh_token: storedRefreshToken }));
        applySession(tokens);
      } catch {
        sessionStorage.removeItem(REFRESH_TOKEN_KEY);
      }
    }
    resume().finally(() => setAuthReady(true));
  }, [applySession]);

  useEffect(() => {
    if (!KEYCLOAK_MODE || !authenticated) return;
    const timer = window.setInterval(() => {
      const refreshToken = refreshTokenRef.current;
      if (!refreshToken) return;
      requestToken(new URLSearchParams({ grant_type: "refresh_token", client_id: CLIENT_ID, refresh_token: refreshToken }))
        .then(applySession)
        .catch(() => clearSession());
    }, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [authenticated, applySession, clearSession]);

  if (!authReady) {
    return <main className="grid min-h-screen place-items-center" aria-live="polite">Connecting to secure identity provider…</main>;
  }

  if (KEYCLOAK_MODE && !authenticated) {
    return <LoginScreen onSubmit={login} error={loginError} pending={loginPending} />;
  }

  return (
    <AuthContext.Provider value={{ roles, displayName, logout }}>
      <QueryClientProvider client={queryClient}>
        <AssistanceProvider>
          <CopilotProvider>
            {children}
            <ApplicationCopilot />
          </CopilotProvider>
        </AssistanceProvider>
      </QueryClientProvider>
    </AuthContext.Provider>
  );
}
