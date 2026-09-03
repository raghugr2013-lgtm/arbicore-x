# BOOTSTRAP SECURITY DESIGN

## Threat model

- **Adversary:** anonymous internet visitor who can reach the public API before any
  administrator exists (fresh deploy / reset DB).
- **Asset:** the sole administrator account, which controls execution mode, kill
  switch, wallet registry, scanner controls, and all privileged surfaces.
- **Goal:** ensure creation of the first admin requires a credential that only the
  legitimate operator possesses, independent of DB state.

## Mechanism chosen: deployment-time bootstrap token

`ARBICORE_BOOTSTRAP_TOKEN` — a high-entropy secret provisioned in the deployment
environment (never committed, `.env` is gitignored). Presented by the operator via
the `X-Bootstrap-Token` request header on `POST /api/auth/setup`.

Rationale vs. alternatives:
- **Localhost-only bootstrap** — rejected: the app is fronted by an ingress; "local"
  is ambiguous in the container/k8s topology.
- **One-time DB-seeded token** — equivalent security but adds a migration and a
  distribution problem; the env token is simpler and already fits the 12-factor
  `.env` model the repo uses.
- **Env-provisioned admin only** (`ARBICORE_ADMIN_PASS`) — retained as a secondary
  path, but insufficient alone because it is optional (fail-open when unset).

## Properties

| Property | Guarantee |
|---|---|
| Fail-closed | No token provisioned ⇒ `503`, bootstrap disabled. |
| Independent authorization | Token check is orthogonal to "does an admin exist". |
| Constant-time compare | `hmac.compare_digest` — no timing oracle. |
| Atomic | Unique-indexed sentinel lock ⇒ exactly one admin under concurrency. |
| Permanent lock | After success the lock + admin row both persist; repeats `403`. |
| No secret exposure | Token never returned by any endpoint, never logged. |
| Not in frontend | Operator enters it at runtime; not baked into JS bundle. |

## Operator runbook

1. Set `ARBICORE_BOOTSTRAP_TOKEN=<48+ random bytes>` in the backend environment.
2. Open the app → "Create administrator" card → enter operator username, passphrase,
   and the bootstrap token.
3. On success the admin is created, cookies are set, and bootstrap **locks
   permanently**. Rotate/remove the token from the environment afterward if desired
   (it is only consulted while `setup_complete=false`).
