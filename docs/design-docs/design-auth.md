# Design: Authentication and Organization Scope

**Status:** Accepted · **Date:** 2026-08-30 · **Issue:** 6 (`P2`)
**Related:** [`../product-specs/prd-tracer-bullet-goods-receipt.md`](../product-specs/prd-tracer-bullet-goods-receipt.md),
[`../research/research-core-architecture.md`](../research/research-core-architecture.md) §8,
[`../exec-plans/active/backlog-tracer-bullet.md`](../exec-plans/active/backlog-tracer-bullet.md)

Research §8 deliberately left token transport and session revocation open. This document
closes that question. It records a decision and its consequences — not a survey of options.

---

## 1. Decision

**Authentication uses an opaque, server-side session token delivered in an HTTP-only cookie.**

| Aspect | Decision |
|---|---|
| Credential | 256 bits from `secrets.token_urlsafe(32)` |
| Transport | Cookie `testvasja_session`; `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` outside local development |
| Server state | Row in `sessions`; the token is stored **hashed** (SHA-256), never in plaintext |
| Idle timeout | 8 hours since `last_used_at` |
| Absolute lifetime | 30 days since `created_at`, not extendable |
| Revocation | Delete the row — effective on the next request, with no denylist to maintain |
| Password hashing | Argon2id via `argon2-cffi`, library defaults, `needs_rehash` checked on every successful login |
| Organization scope | Resolved server-side from `memberships`; never trusted from a client-supplied body alone |

## 2. Why this and not a JWT

Three forces decide it, and they all point the same way.

**SSR is a stated PRD constraint.** The Nuxt server renders authenticated pages, so it must be
able to present the user's credential when it calls the API during SSR. A cookie is attached to
the SSR fetch automatically and is readable by the Nuxt server; a token in `localStorage` is not
reachable from the server at all. Choosing `localStorage` would mean either abandoning SSR for
authenticated pages or inventing a second, cookie-shaped channel purely to feed the renderer —
that is, arriving at a cookie by a longer road.

**Research §8 requires session revocation and session/device audit data.** A self-contained JWT
cannot be revoked before it expires. The standard remedy is a server-side denylist — which is a
session table with a worse name, plus token signing, key rotation, and a refresh dance on top.
Since the table is unavoidable, storing the session in it and handing out an opaque pointer is
strictly simpler for the same guarantee.

**Opaque tokens leak nothing.** A JWT is base64, not encryption: anyone holding one reads its
claims. An opaque token is a random string that means nothing away from our database.

**What we give up:** stateless verification. Every authenticated request costs one indexed
lookup by token hash. At this system's scale that is not a real cost, and it buys immediate
revocation. Should horizontal scale ever make it one, the session row can be cached — the
contract in this document does not change.

## 3. Session lifecycle

```
POST /api/v1/auth/login
  ├─ look up user by lowercased email
  ├─ verify password (Argon2id)          ── constant-time, and a dummy verify runs
  │                                          when the user does not exist, so response
  │                                          timing does not disclose registration
  ├─ if hash parameters are outdated → rehash and store
  ├─ create session row (token_hash, user_id, created_at, last_used_at, expires_at)
  └─ Set-Cookie: testvasja_session=<raw token>; HttpOnly; SameSite=Lax; Path=/

any authenticated request
  ├─ read cookie → SHA-256 → look up session
  ├─ reject when missing, past absolute expiry, or idle beyond 8h  → 401
  ├─ slide last_used_at (idle window only; absolute expiry never moves)
  └─ resolve current user

POST /api/v1/auth/logout
  └─ delete the session row and clear the cookie
```

Login failure returns one message — `Invalid email or password` — for both an unknown email and
a wrong password. Distinguishing them would turn the login form into a user-enumeration oracle.

## 4. CSRF posture

Cookie authentication is CSRF-exposed by construction, so the mitigation must be explicit.

1. **`SameSite=Lax`** stops the cookie from riding cross-site `POST`s, which covers the classic
   auto-submitting-form attack. Note that ports are not part of a *site*: `localhost:3000` and
   `localhost:8000` are same-site, so this works in development as well as production.
2. **JSON-only mutations.** Every mutating endpoint accepts `application/json` and nothing else.
   A cross-site HTML form can only send `application/x-www-form-urlencoded`, `multipart/form-data`
   or `text/plain`; it cannot set `application/json` without triggering a CORS preflight, which
   our origin allowlist rejects.
3. **CORS is an allowlist**, not `*`, and `allow_credentials` is on — a combination the browser
   only honours for explicitly named origins.

**This is a documented boundary, not a permanent guarantee.** If any cookie-authenticated
endpoint ever accepts a form content type, or the API is embedded cross-site, layers 1 and 2
both fall and a double-submit CSRF token becomes mandatory. That condition is written into the
design so a future change cannot silently cross it.

### Deployment constraint: the API must be same-site with the frontend

This is not a preference; it is what makes the design work at all.

Ports are not part of a *site*, so `localhost:3000` and `localhost:8000` are same-site and the
cookie flows between them. **Hosts are.** `localhost:3000` and `127.0.0.1:8000` are *different*
sites even though they are the same machine: the cookie is never sent back, and every login
appears to succeed while nothing is authenticated afterwards.

In production this means serving the API under the frontend's registrable domain — behind one
proxy, or as `api.example.com` beside `app.example.com`. An API on an unrelated domain would
require `SameSite=None; Secure`, which discards CSRF layer 1 and makes the double-submit token
mandatory.

**This was found the hard way.** The E2E CI job set `NUXT_PUBLIC_API_BASE` to `127.0.0.1` while
the browser loaded the app from `localhost`, and every login test failed for what looked like an
application bug. The constraint is now stated here, asserted in a comment in
`playwright.config.ts`, and explained where the CI job would otherwise have re-broken it.

## 5. Data model

Three tables landed in Issue 6; `sessions` followed in Issue 7 alongside the login endpoint that
writes to it — no table lands before the code that uses it.

```
users(id, email UNIQUE, password_hash, is_active, created_at)
organizations(id, name, created_at)
memberships(id, user_id → users, organization_id → organizations, created_at)
    UNIQUE (user_id, organization_id)
sessions(id, user_id → users, token_hash UNIQUE,
         active_organization_id → organizations NULL,
         created_at, last_used_at, expires_at,
         user_agent, ip_address)
```

- **`email` is stored lowercased** and carries a unique constraint. Case-preserving storage plus
  a case-insensitive lookup is how duplicate accounts get created.
- **`password_hash` never leaves the database.** No Pydantic response schema includes it; the
  ORM attribute is not exposed through any serializer. This is asserted by a test, not by
  convention.
- **`memberships` is the scope table.** A user sees an organization only through a row here.
  It is deliberately a separate entity rather than a column on `users`: the PRD is
  single-company/multi-FOP, so one user legitimately belongs to several organizations.
- **No role column.** The PRD puts full RBAC out of scope and states one role suffices for this
  slice. Adding an unused column now would invite code to depend on a shape we have not designed.
- **`sessions.active_organization_id` is the scope, and it lives on the server.** A client names
  a candidate in the request body; membership decides. It is re-checked against `memberships` on
  every request rather than trusted from the row, so revoking a membership takes effect on the
  next request instead of at session expiry — the row caches an id, never a permission.
  `ON DELETE SET NULL`: deleting an organization must not delete its users' sessions.
- **`user_agent` and `ip_address`** satisfy research §621's session/device audit requirement.
  Recorded now, surfaced when a device-management view exists.

### Selecting the active organization

A user with **exactly one** membership has it selected at login: there is nothing to choose, so
a mandatory round-trip would be ceremony. With **two or more** the server does not guess and
returns `null`; scoped endpoints then answer `403 no_active_organization` until the client
chooses. Guessing here would post documents into the wrong legal entity, which is precisely the
error this system exists to prevent.

## 6. Error contract

Established here and reused by every later router.

| Status | Meaning | Example |
|---|---|---|
| 401 | Not authenticated | missing, unknown, or expired session cookie |
| 403 | Authenticated, but outside the organization scope | user of org A touching org B's data |
| 404 | Entity does not exist within the caller's scope | unknown product id |
| 409 | Stale version, already-posted document, idempotency conflict | — |
| 422 | Validation failure | empty document lines, non-positive quantity |

**401 versus 403 is a real distinction, not a formality.** 401 means *authenticate and retry*;
403 means *retrying will not help*. The frontend depends on it: research §218 requires exactly
one coordinated refresh for concurrent 401s, and **never** a refresh on 403.

A cross-organization request returns **403, not 404**. Hiding existence behind 404 is a defensible
pattern in general, but here the organizations a user may access are enumerable through
`GET /api/v1/organizations` anyway, so 404 would obscure the failure for the developer without
concealing anything from the attacker.

## 7. Security decisions worth stating

- **Argon2id, library defaults.** `argon2-cffi` tracks the RFC 9106 recommendations; pinning our
  own cost parameters would mean freezing them at 2026 values. `needs_rehash` on every successful
  login migrates existing hashes as those defaults rise.
- **Session tokens are hashed at rest.** A leaked database read gives an attacker password hashes
  they must crack and session hashes they cannot reverse into cookies.
- **`is_active` on the user, checked at authentication.** Deactivating a user must not require
  hunting down their live sessions; the flag is authoritative on every request.
- **Frontend route middleware is UX, never authorization** (research §624). Every endpoint
  enforces its own scope, and the tests assert this at the API, not through the UI.

## 8. Out of scope

Registration, password reset, email verification, multi-factor authentication, OAuth/social
login, RBAC beyond a single role, device management UI, and rate limiting on login. Rate
limiting in particular is a real gap: it belongs to a hardening pass with a shared throttling
mechanism, not to a hand-rolled counter on one endpoint.
