/**
 * The seven role-separated identities.
 *
 * Development auth combines every role into one principal, which cannot
 * demonstrate segregation of duties: every approval it performs is one it
 * could also have granted itself. These are the Keycloak users the acceptance
 * bootstrap provisions, one role each, matching the database identities the
 * product bootstrap creates.
 */
export const ROLES = [
  "requester",
  "analyst",
  "procurement",
  "compliance",
  "finance",
  "auditor",
  "admin",
] as const;

export type Role = (typeof ROLES)[number];

/** Where each role's authenticated browser state is cached. */
export function storageStatePath(role: Role): string {
  return `e2e/.auth/${role}.json`;
}

export const KEYCLOAK_URL =
  process.env.NEUROX_KEYCLOAK_URL ?? "http://localhost:8080";

export const API_URL = process.env.NEUROX_API_URL ?? "http://localhost:8000";

/**
 * Shared across all seven acceptance users. Provisioned by
 * infra/keycloak/bootstrap-acceptance.sh; never a production credential.
 */
export const ACCEPTANCE_PASSWORD =
  process.env.KEYCLOAK_E2E_USER_PASSWORD ?? "";
