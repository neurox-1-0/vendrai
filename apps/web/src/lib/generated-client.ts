import { getAccessToken } from "@/lib/auth-token";

const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1"
).replace(/\/$/, "");
const DEV_TENANT =
  process.env.NEXT_PUBLIC_DEV_TENANT_ID ??
  "00000000-0000-0000-0000-000000000001";
const DEV_USER =
  process.env.NEXT_PUBLIC_DEV_USER_ID ??
  "00000000-0000-0000-0000-000000000101";

export async function generatedClient<T>(
  path: string,
  options: RequestInit,
): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  } else if (process.env.NODE_ENV !== "production") {
    headers.set("X-Dev-Tenant-Id", DEV_TENANT);
    headers.set("X-Dev-User-Id", DEV_USER);
    headers.set(
      "X-Dev-Roles",
      "requester,analyst,approver,auditor,admin",
    );
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: { code?: string } | string;
    } | null;
    const code =
      typeof body?.detail === "object"
        ? body.detail.code
        : body?.detail;
    throw new Error(code || `Request failed (${response.status})`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
