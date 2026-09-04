# Backlog: Tracer Bullet — Goods Receipt Vertical Slice

**Status:** Active
**Date:** 2026-08-30
**Related:** [`plan-tracer-bullet.md`](plan-tracer-bullet.md), [`../../product-specs/prd-tracer-bullet-goods-receipt.md`](../../product-specs/prd-tracer-bullet-goods-receipt.md), [`../../research/research-core-architecture.md`](../../research/research-core-architecture.md)

This file is the source of truth for the issue backlog. Each **Milestone** maps to a plan
phase; each **Issue** maps to one reviewable pull request. Issue bodies follow `AGENTS.md` §7
(Context / Scope / Acceptance Criteria / Modules / Tests / Out of Scope).

The plan lists ~50 fine-grained tasks. They are grouped here into 26 issues so that each issue
is a coherent unit of work with a single verification story, per the decision of 2026-08-30.

**Convention:** issue titles are prefixed `P<phase>` for sorting. Language is English to match
`AGENTS.md`, the plan, and the research document.

---

## Milestone 1 — Phase 1: Repository Scaffold & Baseline

Goal: both applications build and run locally, quality gates are enforced, database
connectivity is proven.

### Issue 1 — `P1: Backend scaffold and quality baseline`

**Status:** ✅ Done (implemented 2026-08-30, pending commit)

**Context.** Empty repository with docs only. The research document (§313) mandates
*synchronous* SQLAlchemy for the transactional core, so the scaffold must not introduce an
async session stack.

**Scope.**
- `uv`-managed Python project (`backend/pyproject.toml`), Python ≥ 3.12.
- FastAPI application factory with CORS for the Nuxt dev origin, OpenAPI at `/api/v1/openapi.json`.
- `Settings` via `pydantic-settings`, `DATABASE_URL` read from environment/`.env`.
- Declarative `Base`, synchronous `Engine`, `SessionLocal`, and a request-scoped
  `get_session` dependency whose transaction is owned by the service layer.
- `/api/v1/health/live` (no dependencies) and `/api/v1/health/ready` (probes the database).
- Tooling config: ruff (lint + format), pyright in **strict** mode, pytest.

**Acceptance criteria.**
- `uv run pytest` passes.
- `uv run ruff check .` and `uv run ruff format --check .` are clean.
- `uv run pyright` reports 0 errors in strict mode.
- `/api/v1/health/ready` returns `degraded` rather than crashing when Postgres is absent.

**Modules.** `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/core/{config,db}.py`,
`backend/app/api/v1/health.py`, `backend/.env.example`.

**Tests.** `backend/tests/test_health.py` — liveness contract, OpenAPI schema served.

**Out of scope.** Domain models, authentication, migrations content.

---

### Issue 2 — `P1: Alembic migration harness`

**Status:** ✅ Done (implemented 2026-08-30, pending commit)

**Context.** Research §383 prohibits automatic schema synchronization; all schema change goes
through Alembic. The harness must exist before the first model lands in Phase 2.

**Scope.**
- `alembic init migrations`, wired so the URL comes from application settings, never from
  `alembic.ini` (no credentials in version control).
- `target_metadata = Base.metadata`; `app.models` imported so autogenerate sees every table.
- `compare_type` and `compare_server_default` enabled to catch column drift.

**Acceptance criteria.**
- `uv run alembic upgrade head --sql` succeeds offline and reports `PostgresqlImpl`.
- No connection string is present in any committed file.
- `app/models/__init__.py` exists as the registration point for future models.

**Modules.** `backend/alembic.ini`, `backend/migrations/env.py`, `backend/app/models/__init__.py`.

**Tests.** Offline `--sql` render acts as the harness smoke check; a real `upgrade head` runs
under Issue 4 once Postgres is available.

**Out of scope.** Any actual migration revision (belongs to the phase that introduces the model).

---

### Issue 3 — `P1: Frontend scaffold — Nuxt 4 SSR baseline`

**Status:** ✅ Done (2026-08-30)

**Context.** The PRD requires SSR (`Out of Scope` explicitly defers offline mode; SSR is a
stated technical constraint). The frontend must build and typecheck before any page work.

**Scope.**
- Nuxt 4 project under `frontend/`, pnpm workspace, SSR enabled.
- TypeScript **strict**, `vue-tsc` typecheck script.
- PrimeVue 4 with a theme preset, Tailwind CSS 4.
- Pinia and TanStack Query registered as plugins/modules.
- Runtime config exposing the API base URL; a minimal index page that renders server-side.
- ESLint via `@nuxt/eslint`.

**Acceptance criteria.**
- `pnpm install && pnpm build` succeeds.
- `pnpm typecheck` (vue-tsc) reports 0 errors.
- `pnpm lint` is clean.
- `pnpm dev` serves a page whose markup is present in the initial HTML response (SSR proven,
  not client-only hydration).

**Modules.** `frontend/package.json`, `frontend/nuxt.config.ts`, `frontend/tsconfig.json`,
`frontend/app/app.vue`, `frontend/app/pages/index.vue`.

**Tests.** Build and typecheck are the gate. A `curl` of the dev server asserting server-rendered
markup is the SSR evidence.

**Out of scope.** Login, products, receipts pages; the generated OpenAPI client.

**Decisions taken during implementation** (deviations from the text above, recorded rather
than applied silently):

| Decision | Reason |
|---|---|
| PrimeVue pinned to **4.5.5** (`@primevue/nuxt-module` 4.5.5, `@primeuix/themes` 1.2.5) | Latest is 5.0.1, but the backlog and research both specify major 4. Moving to 5 is a scope change, not an implementation detail. |
| **TypeScript `~5.9.3`**, not the latest 7.0.2 | 7.x is the native-port rewrite. `vue-tsc` 3.3.11 declares peer `typescript >=5.0.0`, but the typecheck gate should not ride a brand-new major. |
| **Zod dropped from this issue** | It is not in Issue 3 scope — it first appears in Issue 8 (login form validation). `zod@4.5.4` was also 1 day old and failed pnpm's release-age policy; installing an unused fresh dependency is unjustifiable. |
| `pnpm-lock.yaml` **removed from `.gitignore`** | CI must install the exact tree that was audited. `uv.lock` was already committed; the two were inconsistent. |
| `pnpm-workspace.yaml` uses `allowBuilds` | pnpm 11 replaced `onlyBuiltDependencies`. Three packages are allowed install-time scripts: `esbuild`, `unrs-resolver`, `vue-demi` — each annotated in the file. |

**Provenance audit** (run before install, per the standing rule). SLSA provenance + npm
registry signature present for: `nuxt`, `@nuxt/eslint`, `tailwindcss`, `@tailwindcss/vite`,
`@tanstack/vue-query`, `pinia`, `@pinia/nuxt`, `vue-tsc`. Registry signature only, no
provenance attestation: `eslint`, `typescript`. **Weakest link: `primevue` and
`@primeuix/themes` — no provenance attestation and no `repository` field in npm metadata.**
`pnpm install` reported `Lockfile passes supply-chain policies`.

**Verification (2026-08-30).** `pnpm install` clean · `pnpm lint` clean · `pnpm typecheck`
0 errors · `pnpm build` complete (6.79 MB, 1.51 MB gzip) · `curl` of both `pnpm dev` and the
production preview returns `data-testid="render-origin">server` and the server-rendered
PrimeVue button in the initial HTML · Tailwind 4 utilities present in the emitted stylesheet
(`.text-2xl`, `.min-h-screen`) · `NUXT_PUBLIC_API_BASE` override reaches the rendered page.

**Known peer warning.** `@bomb.sh/tab` wants `cac@^6.7.14`, tree has `7.0.0` — transitive
dev-tooling of the Nuxt CLI, not ours to pin.

---

### Issue 4 — `P1: Local services — PostgreSQL via Docker Compose`

**Status:** ✅ Done (2026-08-30)

**Context.** Docker Desktop was installed on 2026-08-30 and requires a host reboot before the
engine is usable. Concurrency correctness (Phases 5 and 7) depends on real PostgreSQL
semantics — `SELECT … FOR UPDATE`, `numeric`, transactional DDL — so SQLite is not an option.

**Scope.**
- `docker-compose.yml` at repository root with a pinned PostgreSQL image, named volume,
  healthcheck, and credentials sourced from `.env`.
- Root `.env.example` documenting every variable the compose file consumes.
- First real `alembic upgrade head` against the running database.

**Acceptance criteria.**
- `docker compose up -d` brings Postgres to a healthy state.
- `uv run alembic upgrade head` completes and creates `alembic_version`.
- `GET /api/v1/health/ready` returns `{"status":"ok","database":"up"}`.
- `docker compose down -v` followed by `up -d` and `upgrade head` reproduces a clean database.

**Modules.** `docker-compose.yml`, `.env.example`, `backend/.env.example`.

**Tests.** Readiness endpoint returning `up` is the verification.

**Out of scope.** MinIO / object storage (PRD defers attachments), pgAdmin, production compose.

**Verification (2026-08-30).** Docker Engine 29.7.2 responded after the reboot, so the blocker
is cleared. `docker compose config` valid · `docker compose up -d` → healthcheck `healthy` ·
server reports `PostgreSQL 17.11 on x86_64-pc-linux-musl` · `uv run alembic upgrade head`
→ `Context impl PostgresqlImpl`, `Will assume transactional DDL`, `alembic_version` created ·
`GET /api/v1/health/ready` → `{"status":"ok","database":"up","detail":null}` ·
`docker compose down -v` removed the volume, then `up -d` + `upgrade head` reproduced the
clean database (`Did not find any relations` → `alembic_version`).

**Note.** `alembic_version` is created even though `migrations/versions/` holds no revision
yet; the first revision lands in Phase 2 with the identity models. `versions/.gitkeep` was
added so a clean checkout has the directory Alembic expects.

**Note.** `uv` is not on the PATH of shells opened before its install; it lives at
`%LOCALAPPDATA%\Programs\Python\Python314\Scripts\uv.exe`.

---

### Issue 5 — `P1: CI pipeline and developer setup documentation`

**Status:** ✅ Done (2026-08-30)

**Context.** `AGENTS.md` §12 forbids claiming completion without evidence; CI makes the
quality gates non-optional. README currently has a placeholder setup section.

**Scope.**
- GitHub Actions workflow: backend job (`uv sync`, ruff, pyright, pytest against a Postgres
  service container) and frontend job (`pnpm lint`, `vue-tsc`, `pnpm build`).
- Migration validation step: `alembic upgrade head` then `alembic check` to detect models
  that drifted from migrations.
- README: real local setup commands, prerequisites with actual versions, quality-gate commands.

**Acceptance criteria.**
- Workflow passes on the phase branch.
- Every command in the README has been executed successfully on a clean checkout.
- `alembic check` fails the build when a model has no matching migration.

**Modules.** `.github/workflows/ci.yml`, `README.md`.

**Tests.** The workflow run itself.

**Out of scope.** Deployment, container publishing, release automation.

**Verification (2026-08-30).**
- Every command in the README was executed on this checkout: `cp .env.example .env` (all
  three), `docker compose up -d` → `Up (healthy)`, `docker compose ps`, `uv sync`,
  `uv run alembic upgrade head`, `uv run ruff check .`, `uv run ruff format --check .`
  (11 files formatted), `uv run pyright` (0 errors, strict), `uv run pytest` (2 passed),
  `uv run alembic check`, `pnpm install`, `pnpm lint`, `pnpm typecheck`, `pnpm build`,
  `pnpm dev`, `docker compose down -v`.
- **`alembic check` was proven load-bearing, not assumed:** a throwaway `DriftProbe` model
  was added, `alembic check` failed with
  `FAILED: New upgrade operations detected: [('add_table', ...'drift_probe'...)]` and a
  non-zero exit; the probe was then removed and the check returned to exit 0.
- `.github/workflows/ci.yml`, `docker-compose.yml` and `pnpm-workspace.yaml` parse as valid
  YAML; the workflow declares 2 jobs (9 backend steps, 7 frontend steps).
- Action versions pinned to the current majors as of 2026-08-30: `actions/checkout@v7`,
  `actions/setup-node@v7`, `pnpm/action-setup@v6`, `astral-sh/setup-uv@v10`.

- **The workflow passes on the phase branch.** `phase-1` was pushed to `origin` and
  [run 33318800111](https://github.com/UkrAndy/shop-crm/actions/runs/33318800111) for commit
  `3c58339` is green: both jobs succeeded, all 11 backend steps and all 8 frontend steps.

**Two defects the CI run caught that local verification could not:**

| Defect | Fix |
|---|---|
| The workflow triggered only on `main` and pull requests, so a phase branch never got a run — the very thing this criterion asks for | Trigger on `phase-**` too; concurrency keyed on `head_ref` so the push and PR runs of one commit collapse instead of billing twice |
| `astral-sh/setup-uv@v10` failed to resolve: that repository stopped publishing moving major tags after `v7`, so the alias does not exist | Pin the exact release, `astral-sh/setup-uv@v10.0.1` |

**Decision taken during implementation.** A root `package.json` was added: `pnpm/action-setup`
resolves the pnpm version from `packageManager`, and the workspace root previously had no
manifest. It also pins `engines.node` and forwards `lint`/`typecheck`/`build`/`dev` to the
frontend package, so the README and CI use one set of commands.

---

## Milestone 2 — Phase 2: Identity & Organizations

Goal: authenticated user operating inside an organization scope; 401/403 contracts established.

### Issue 6 — `P2: Auth strategy decision and identity models`

**Status:** ✅ Done (2026-08-30)

**Context.** The plan defers the session-vs-JWT choice to implementation time. SSR changes the
trade-off: an HTTP-only cookie is readable by the Nuxt server during SSR, a token in
`localStorage` is not. This decision must be written down before code depends on it.

**Scope.**
- `docs/design-docs/design-auth.md` recording the chosen mechanism, rationale, session
  lifetime, CSRF posture, and the SSR implication.
- `User`, `Organization`, `Membership` models with an Alembic revision.
- Argon2 password hashing (PRD: bcrypt/argon2).

**Acceptance criteria.**
- Design document states the decision and its consequences, not just options.
- `alembic upgrade head` creates the three tables; `alembic check` is clean.
- Password hashes are never returned by any serializer.

**Modules.** `docs/design-docs/design-auth.md`, `backend/app/models/identity.py`,
`backend/migrations/versions/*`.

**Tests.** Hash round-trip; unique constraint on `users.email`.

**Out of scope.** Registration, password reset, multi-role RBAC (PRD Out of Scope).

**Decision.** Opaque server-side session token in an HTTP-only `SameSite=Lax` cookie, stored
hashed in a `sessions` table; 8h idle / 30d absolute; Argon2id via `argon2-cffi`. Full rationale
and consequences — including the CSRF posture and the 401-vs-403 contract — are in
[`../../design-docs/design-auth.md`](../../design-docs/design-auth.md), pointed to from
`AGENTS.md`.

**Conventions established here** (they bind every later model):

| Convention | Reason |
|---|---|
| UUID primary keys | A sequential id in a URL leaks row counts and invites enumeration across organizations; scope checks stop access, not inference. `uuid7` is the drop-in upgrade once the Python floor reaches 3.14. |
| `timestamptz` for every timestamp | research §385 |
| `email` lowercased, enforced by a `CHECK` constraint | Application-only normalisation is how `Bob@x.com` ends up beside `bob@x.com` |
| Session tokens hashed at rest | A database read then yields nothing an attacker can present as a cookie |
| No `role` column | RBAC is PRD Out of Scope; an unused column invites code to depend on a shape nobody designed |

**Scope note.** `app/core/security.py` (password hashing only) and `tests/conftest.py` were
added although the issue lists neither: the hashing requirement has to live somewhere, and the
"unique constraint on `users.email`" criterion cannot be verified without a database fixture.
The fixture is deliberately minimal — Issue 25 hardens it for concurrency.

**Scope note.** `migrations/script.py.mako` was rewritten so generated revisions match the
project's lint and format rules. Fixing the template rather than each generated file stops the
same manual cleanup recurring in Phases 3–5.

**Verification (2026-08-30).**
- **Test-first, RED confirmed:** before the migration existed, `uv run pytest` reported
  `10 failed, 14 passed` — every failure a missing relation, while the hashing tests already
  passed. After `alembic upgrade head`: **24 passed**.
- `uv run ruff check .` clean · `ruff format --check .` 16 files · `uv run pyright` 0 errors,
  strict · `uv run alembic check` clean.
- **Downgrade proven, not assumed:** `alembic downgrade base` dropped all three tables and
  `upgrade head` recreated them.
- `\d users` confirms `timestamp with time zone`, `ck_users_email_lowercase`, the unique
  `ix_users_email`, and `ON DELETE CASCADE` from `memberships`.
- Hash leakage is guarded by serialising the **entire** OpenAPI document and asserting
  `password_hash` is absent, so a serializer added in a later phase cannot leak it quietly.

**Dependency added.** `argon2-cffi` 25.1.0. PEP 740 attestation present for it and for
`argon2-cffi-bindings` 26.1.0, both from GitHub Trusted Publishers (`hynek/argon2-cffi`,
`hynek/argon2-cffi-bindings`) — stronger provenance than any other dependency in this
repository, including `uv` itself.

---

### Issue 7 — `P2: Login endpoint, session middleware, organization scope`

**Status:** ✅ Done (2026-08-30)

**Context.** PRD: every endpoint except `/auth/login` requires authentication, and organization
membership must be enforced.

**Scope.**
- `POST /api/v1/auth/login` with validation and a deliberately non-enumerating error.
- Authentication dependency resolving the current user; 401 contract.
- `GET /api/v1/organizations`, `POST /api/v1/organizations/active`.
- An organization-scope dependency every subsequent router depends on; 403 contract.
- Structured error response shape shared by 401/403/404/409/422.

**Acceptance criteria.**
- Unauthenticated request to a protected route → 401 with the documented body.
- Authenticated user requesting another organization's data → 403.
- Active organization is resolved server-side, never trusted from a client-supplied body alone.

**Modules.** `backend/app/api/v1/{auth,organizations}.py`, `backend/app/core/security.py`,
`backend/app/core/errors.py`.

**Tests.** Integration: login success/failure, 401 on protected route, 403 cross-organization.

**Out of scope.** Product/receipt endpoints.

**Endpoints delivered.**

| Endpoint | Notes |
|---|---|
| `POST /api/v1/auth/login` | The only unauthenticated endpoint in the API |
| `POST /api/v1/auth/logout` | 204, idempotent |
| `GET /api/v1/auth/me` | Current user + active organization |
| `GET /api/v1/organizations` | Only the caller's own |
| `GET /api/v1/organizations/active` | 403 when nothing is selected |
| `POST /api/v1/organizations/active` | Body names a candidate; membership decides |

**Scope note.** `logout` and `me` are not in the issue text. Issue 8's acceptance criteria
("logging out clears session state", "reloading a protected page does not flash the login
screen") cannot be met without them, and both are a handful of lines. Recorded rather than
slipped in.

**Design decisions taken here, folded back into `design-auth.md`:**
- `sessions.active_organization_id` holds the scope **server-side**; it is re-checked against
  `memberships` on every request, so revoking a membership takes effect on the next request
  rather than at session expiry. `ON DELETE SET NULL` — deleting an organization must not
  delete its users' sessions.
- A user with exactly one membership gets it selected at login; with two or more the server
  returns `null` and refuses to guess. A wrong guess would post documents into the wrong legal
  entity.
- Session tokens are SHA-256, **not** Argon2. The token already carries 256 bits of entropy, so
  there is no dictionary to slow down, while the hash runs on every authenticated request.
- Exception classes carry `status_code`/`code`/`message` and are translated once at the
  boundary by `register_exception_handlers`, so routers never assemble error bodies. The
  `documented(401, 403)` helper puts the envelope into the OpenAPI document, so the generated
  TypeScript client knows the error shape rather than narrowing on an untyped body.

**Verification (2026-08-30).**
- **Test-first, RED confirmed:** the 28 new tests were written before the endpoints and ran
  `27 failed, 1 passed`. After implementation the suite is **52 passed**, no warnings.
- `ruff check` clean · `ruff format --check` 27 files · `pyright` 0 errors, strict ·
  `alembic check` clean · `alembic downgrade -1` and back proven.
- **Live smoke test over real HTTP** (uvicorn + curl, not only `TestClient`):
  401/403/422 envelopes as documented; a wrong password and an unknown email return
  byte-identical bodies; `Set-Cookie: HttpOnly; SameSite=lax` with no `Secure` locally;
  login is case-insensitive on email; the stored `token_hash` is 64 hex characters and differs
  from the cookie; `user_agent`/`ip_address` captured; logout deletes the row and the next
  request is 401 with `sessions` empty.

**Two problems the linters caught, fixed at the source rather than suppressed:**
`starlette.status.HTTP_422_UNPROCESSABLE_ENTITY` is deprecated in favour of
`…_UNPROCESSABLE_CONTENT`; and the exception classes needed the PEP 8 `Error` suffix (`N818`).
Exception handlers were also moved from closures to module level — pyright counts a decorated
nested function as unused, and module-level handlers are independently testable anyway.

---

### Issue 8 — `P2: Frontend authentication and organization context`

**Status:** ✅ Done (2026-08-30)

**Context.** SSR must not flash unauthenticated content; the active organization must survive
a page reload.

**Scope.**
- `/login` page with validated form (Zod).
- Pinia session store hydrated during SSR.
- Organization selector; active organization persisted and sent with API calls.
- Route middleware redirecting unauthenticated users.

**Acceptance criteria.**
- Reloading a protected page while logged in does not flash the login screen.
- Logging out clears session state and blocks protected routes.
- Active organization survives a full page reload.

**Modules.** `frontend/app/pages/login.vue`, `frontend/app/stores/session.ts`,
`frontend/app/middleware/auth.ts`, `frontend/app/components/OrgSelector.vue`.

**Tests.** Covered by Issue 9.

**Out of scope.** Products and receipts UI.

**Deviations, recorded rather than slipped in:**

| Deviation | Reason |
|---|---|
| `middleware/auth.global.ts`, not the named `middleware/auth.ts` the issue lists | Global with an explicit public allowlist fails **closed**: a page added later without the right `definePageMeta` would otherwise be silently public. |
| The active organization is **not** "persisted and sent with API calls" | It lives on the session row server-side, so there is nothing for the client to persist or send. A client that could name its own scope in every request would be able to widen it. This is a stronger design than the issue text assumed, so the text is wrong, not the code. |
| `backend/scripts/seed_dev.py` added | Registration is out of PRD scope, so the first user has to come from somewhere. Needed to verify this issue at all, and reused by Issue 9. |
| Hand-written types in `app/types/api.ts` | The generated OpenAPI client is Issue 12. The file says so, and duplication by hand is exactly why that issue exists. |

**Two defects found by verifying instead of assuming:**

1. **`NUXT_E1001` — SSR silently rendered every visitor as anonymous.** `apiFetch` called
   `useRuntimeConfig()` and `useRequestHeaders()` on each request; after the first `await` in a
   Pinia action the Nuxt context is gone, so the second call threw and `hydrate()` swallowed it
   as "not logged in". Fixed by `createApiClient()`, which captures the base URL and the
   forwarded cookie **once during store setup** — inside a context — and returns a plain
   `$fetch` instance usable afterwards. Symptom before the fix: an authenticated `GET /`
   redirected to `/login`.
2. **The seed created accounts that could not log in.** `owner@testvasja.local` is refused by
   `email-validator` behind Pydantic's `EmailStr` — `.local` is a special-use reserved name — so
   `/auth/login` answered **422** before reaching the password check. Addresses moved to
   RFC 2606's `example.com`, and the seed now validates them through the real `LoginRequest`
   schema so this cannot regress silently.

**Verification (2026-08-30),** against a live backend, a live Nuxt dev server and seeded data:

| Check | Evidence |
|---|---|
| No login flash on reload | `GET /` **with** the session cookie returns 200 whose *initial HTML* already contains `data-testid="current-user">owner@example.com` and `render-origin=server` |
| Anonymous visitors are redirected | `GET /` → `302 → /login?redirect=/` |
| Login page is server-rendered | `GET /login` returns the form's `data-testid`s in the initial HTML |
| An authenticated visitor gets no login page | `GET /login` → `302 → /` |
| Sole membership auto-selected | Page shows `active-organization = ФОП Альфа` |
| Two memberships are not guessed | `multi@example.com` gets `active_organization_id: null`, the page shows `не обрано`, and both organizations appear in the server-rendered selector |
| No context warnings remain | `NUXT_E1001` count in a fresh dev log after three requests: **0** |

`pnpm lint`, `pnpm typecheck` and `pnpm build` clean; backend gates unchanged and green.

---

### Issue 9 — `P2: Authentication test coverage`

**Status:** ✅ Done (2026-08-30)

**Scope.**
- Playwright set up for the repository (config, CI wiring).
- E2E: login → organization selection → protected page.
- E2E: invalid credentials show an error and stay on `/login`.
- Integration tests for the scope matrix from Issue 7.

**Acceptance criteria.** Suite passes locally and in CI against a real Postgres service.

**Modules.** `frontend/tests/e2e/auth.spec.ts`, `frontend/playwright.config.ts`,
`backend/tests/test_auth.py`.

**Out of scope.** Visual regression testing.

**Delivered.** `@playwright/test` 1.62.1 (SLSA provenance, `microsoft/playwright`), Chromium
only, `frontend/playwright.config.ts`, `frontend/tests/e2e/{global-setup,auth.spec}.ts`, and a
third CI job that runs the whole stack — PostgreSQL, FastAPI, Nuxt — in one runner.

**Ten E2E cases**, covering the issue's list plus the acceptance criteria Issue 8 could only
assert at the HTTP level: login → protected page; sole membership auto-selected; invalid
credentials error and stay on `/login`; client-side email validation; anonymous redirect
carrying `?redirect=`; reload without a login flash; two memberships not guessed; organization
selection surviving a full reload; logout blocking protected routes; an authenticated visitor
bounced off `/login`.

**One test-harness defect, and it is worth remembering.** The first run failed 9 of 10 with an
apparently blank form. Cause: `fill()` writes into server-rendered markup, and Vue then
re-renders from its own empty state — a hydration race, not a broken selector. Fixed by
marking the document `data-hydrated` in `app.vue` on mount and waiting for it before typing.
Anything driving an SSR page has to wait for hydration; the alternative is a suite that fails
by machine speed.

**Only Chromium.** Three engines would treble the runtime to re-test the same server-side
behaviour. Cross-browser rendering is a different concern from these flows and is not what the
PRD's Definition of Done asks about.

**Verification (2026-08-30).** `pnpm test:e2e` → **10 passed** in 14s, locally, against a live
PostgreSQL, FastAPI and Nuxt.

**The tests were proven load-bearing, not merely green.** SSR cookie forwarding was disabled on
purpose in `createApiClient`; *"reloading a protected page does not flash the login screen"* and
*"selecting an organization survives a full page reload"* both failed, and both passed again once
it was restored. A suite that stays green when the mechanism is removed is testing nothing.

**Scope note.** `test:e2e` is wired at the workspace root, and the seed script and E2E setup are
documented in the README, since neither is discoverable from the code alone.

---

## Milestone 3 — Phase 3: Catalog (Products) Minimum

Goal: establish the mutable-aggregate pattern — optimistic concurrency with a version token.

### Issue 10 — `P3: Product model with version token`

**Status:** ✅ Done (2026-08-30)

**Context.** First aggregate carrying a `version`. The pattern chosen here is repeated by
goods receipts, so it must be right.

**Scope.**
- `Product`: `id`, `organization_id`, `name`, `barcode` (nullable), `unit`, `purchase_price`,
  `version`; Alembic revision.
- `purchase_price` as `numeric`, mapped to `Decimal` — never float (PRD constraint).
- Unique constraint on `(organization_id, barcode)` where barcode is present.

**Acceptance criteria.**
- Money round-trips through the database as `Decimal` with kopiyka precision, verified by test.
- `version` starts at 1 and increments on every update.
- `alembic check` clean.

**Modules.** `backend/app/models/catalog.py`, `backend/migrations/versions/*`.

**Tests.** Decimal precision; version increment; barcode uniqueness scoped per organization.

**Out of scope.** Categories, images, price history, stock fields on the product row.

**The pattern Issues 15 and 20 will copy.** `version` is wired through SQLAlchemy's
`__mapper_args__ = {"version_id_col": version}`, not incremented by hand. That makes every
update emit `UPDATE … WHERE id = ? AND version = ?` and raise `StaleDataError` when it matches
no row, so a lost update is *impossible* rather than merely unlikely — the guarantee lives in
the SQL, not in remembering to check first.

**Other decisions:**

| Decision | Reason |
|---|---|
| `numeric(14, 2)`, extracted to `app/models/conventions.py` alongside `UUID_PK` and `TIMESTAMPTZ` | Defined once so a later table cannot quietly pick `float` for money or a naive timestamp. `identity.py` was migrated onto the same constants. |
| **Partial** unique index on `(organization_id, barcode) WHERE barcode IS NOT NULL` | Any number of products may have no barcode; those that do stay unique within their organization. Two independent ФОПs selling the same manufactured item both hold its EAN legitimately, so the constraint is scoped, not global. |
| `CHECK (btrim(name) <> '')` | Rejects `""` and `"   "` alike. Trimming in the service layer only fixes the paths that remember to call it. |
| `CHECK (purchase_price >= 0)` | PRD says non-negative, not positive — a promotional item legitimately arrives at zero cost. |
| `created_at` added, though the issue does not list it | Every other table has it; a catalog row without a creation time is an odd exception, not a deliberate one. |

**A rounding hazard, documented rather than hidden.** `numeric(14, 2)` makes PostgreSQL *round*
a third decimal place instead of refusing it, so `10.005` silently becomes `10.01`. A test pins
that behaviour, and rejecting sub-kopiyka input is Issue 11's job at the API boundary — which
makes that guard load-bearing rather than decorative.

**Verification (2026-08-30).**
- **Test-first, RED confirmed:** `tests/test_catalog.py` failed to import before the model
  existed; **17 passed** after, and **69 passed** across the whole suite.
- `ruff check` / `ruff format --check` clean (32 files) · `pyright` 0 errors, strict ·
  `alembic check` clean · `alembic downgrade -1` and back proven.
- `\d products` confirms `numeric(14,2)`, `version` defaulting to 1, both CHECK constraints, and
  the partial index rendered as `UNIQUE, btree (organization_id, barcode) WHERE barcode IS NOT NULL`.
- **`test_product_has_no_quantity_column`** asserts the PRD's central architectural claim rather
  than trusting it: a mutable stock counter on the product row is exactly the shortcut that gets
  added quietly under deadline.
- `test_stale_version_loses` moves the row's version forward with raw SQL — bypassing the
  identity map the way another connection would — and asserts `StaleDataError`, so the mechanism
  is tested, not just the counter.

---

### Issue 11 — `P3: Products API with optimistic concurrency`

**Status:** ✅ Done (2026-08-30)

**Scope.**
- `POST /api/v1/products`, `GET /api/v1/products` (filter + pagination),
  `PATCH /api/v1/products/{id}`.
- `PATCH` requires the client's `version`; mismatch → **409**.
- Validation failures → **422**; cross-organization access → **403**.

**Acceptance criteria.**
- Stale-version update returns 409 and leaves the row untouched.
- Negative or non-numeric price returns 422.
- Listing never leaks products from another organization.

**Modules.** `backend/app/api/v1/products.py`, `backend/app/services/catalog.py`,
`backend/app/schemas/product.py`.

**Tests.** Integration including two sequential updates where the second uses a stale version.

**Out of scope.** Deletion/archiving, bulk import.

**Two races, both closed.** A stale-version `PATCH` is rejected *before anything is mutated*, so
a 409 provably leaves the row untouched. A writer who commits between our read and our flush is
caught by `version_id_col` in the `UPDATE … WHERE version = ?` itself. Checking only the first
leaves a window; relying only on the second mutates the object before discovering the client was
stale. Both paths roll back — a session left in a failed state turns one bad request into every
later request on that connection failing.

**Decisions:**

| Decision | Reason |
|---|---|
| Money crosses the wire as a **string** | JSON numbers are IEEE 754 doubles in every mainstream parser, so a price sent as a number is a price that can drift. `Decimal` on both ends, `type: string` in the OpenAPI document. |
| `decimal_places=2` in the schema | This is what turns PostgreSQL's silent rounding of `10.005 → 10.01` into an explicit 422. It makes Issue 10's documented rounding hazard unreachable in practice. |
| A duplicate barcode is **409 `barcode_taken`**, not 422 | The payload is well-formed; it is the current state of the catalog that rejects it — the distinction research §555 draws. Unmapped `IntegrityError`s are deliberately *not* swallowed into 409: surfacing an unanticipated constraint as a 500 is honest. |
| A foreign product and an unknown id both answer **403** | The query is scoped in its `WHERE` clause, so the server never learns whether the row exists elsewhere and therefore cannot leak it. This keeps the contract in `design-auth.md` §6 intact instead of introducing a second convention for products. |
| `limit` capped at 200 | An unbounded page size turns one request into a full-table dump. |
| `GET /products/{id}` added, though the issue lists only POST/GET-list/PATCH | The edit form needs the current `version` before it can `PATCH`; without it the UI would have to scrape the list. |

**A contract defect found by reading the generated document.** FastAPI documents 422 with its
own `HTTPValidationError`, while our handler actually returns the shared envelope — so the
OpenAPI document described a body the API never sends, and Issue 12's generated client would
have narrowed on it. Fixed at the application level (`FastAPI(responses=documented(422))`);
`HTTPValidationError` and `ValidationError` are now absent from the schema list entirely.

**Verification (2026-08-30).**
- **Test-first, RED confirmed:** 29 failed before the router existed; **29 passed** after, and
  **98 passed** across the suite.
- `ruff check` / `ruff format --check` clean (36 files) · `pyright` 0 errors, strict ·
  `alembic check` clean.
- The acceptance criterion is tested as written: two sequential `PATCH`es where the second still
  holds version 1 → 409 `version_conflict`, and a follow-up `GET` proves the row still holds the
  first change at version 2.
- OpenAPI inspected directly: `purchase_price` is `type: string`, 409 is documented on `PATCH`,
  and every 422 across every route points at `ErrorResponse`.

---

### Issue 12 — `P3: Products UI with conflict handling`

**Scope.**
- `/products` list using PrimeVue `DataTable` with sorting and a name/barcode filter.
- Create and edit forms with Zod validation mirroring server rules.
- Explicit 409 experience: tell the user the record changed, offer reload-and-retry — never
  silently overwrite.
- Generated OpenAPI TypeScript client wired into the build.

**Acceptance criteria.**
- Creating a product shows it in the list without a manual refresh.
- A forced 409 produces the reload-and-retry prompt, not a generic error toast.
- Client regeneration is a documented, repeatable command.

**Modules.** `frontend/app/pages/products/*`, `frontend/app/composables/useProducts.ts`,
`frontend/shared/api/*` (generated).

**Tests.** Covered by Issue 13.

**Out of scope.** Inline table editing, column customization.

**Status:** ✅ Done (2026-08-30)

**Generated types, not a generated SDK.** `openapi-typescript` (dev dependency only, zero
runtime bytes) emits `frontend/shared/api/schema.d.ts`; `app/types/api.ts` is now just named
aliases over it and adds no field of its own. `openapi-fetch` and `@hey-api/openapi-ts` were
both considered and rejected: each replaces the transport, and ours already carries the SSR
cookie forwarding that Issue 8 had to get right. Types give the contract enforcement without
re-litigating the part that works.

**Generation is reproducible without a running server.** `backend/scripts/export_openapi.py`
writes the document with sorted keys, so a regenerated file differs only when the contract truly
changed — which is what lets CI diff it. Two guards, each in the job that can afford it: the
backend job re-exports `openapi.json` and fails on any diff; the E2E job, the only one with both
toolchains, runs the full `api:check`. A contract that drifts from the code now fails the build
exactly the way a model without a migration does.

**The generator immediately earned its place.** Typecheck failed on the first run:
`active_organization_id` is *optional* in the contract — it has a server-side default — while
the hand-written type had claimed it was always present. The store had been carrying a lie that
nothing could have caught by inspection.

**The 409 experience.** A version conflict shows an explicit "somebody else changed this, your
edit was not saved" message with a **Reload and retry** button. The user's typed values stay on
screen until they choose; nothing is silently overwritten and nothing is discarded on their
behalf. `barcode_taken` is routed to the barcode field instead, because it is a field problem,
not a concurrency one.

**Verification (2026-08-30).** `pnpm lint`, `pnpm typecheck` and `pnpm build` clean;
`pnpm api:generate` reproducible. Behaviour proven by the Playwright spec committed with
Issue 13 — **5 passed**, including the conflict flow end to end.

---

### Issue 13 — `P3: Product concurrency tests`

**Scope.** Unit tests for the service layer; integration test issuing two concurrent updates to
the same product and asserting exactly one wins with the other receiving 409; Playwright
happy-path create → appears in list.

**Acceptance criteria.** Concurrency test fails if optimistic locking is removed (verified by
temporarily disabling the version check).

**Modules.** `backend/tests/test_products.py`, `frontend/tests/e2e/products.spec.ts`.

**Status:** ✅ Done (2026-08-30)

**Why a second kind of test fixture was needed.** The rest of the suite runs inside one
transaction that is rolled back — the right default, and useless here: two statements in one
transaction never contend, and threads on separate connections cannot see each other's
uncommitted work. `tests/test_products_concurrency.py` therefore **commits for real** on
independent connections, on a throwaway organization it deletes afterwards.

**A barrier is what makes it a race.** Both threads read, then wait, then write. Without the
barrier the first could finish before the second even loaded, and the test would pass while
proving nothing.

**Three cases:**
1. Two concurrent updates → exactly one `won`, one `lost`, and the row ends at version **2**,
   not 3: the loser wrote nothing at all.
2. The same race through the service layer → the loser raises `VersionConflictError`, whose
   `status_code` is asserted to be **409**, tying the concurrency behaviour to the documented
   HTTP contract rather than to an internal exception name.
3. Concurrent creates of *different* products → both succeed. The counterpart case: locking must
   not turn unrelated concurrent writes into failures.

**The acceptance criterion was carried out, not assumed.** `version_id_col` and the explicit
stale-client check were both commented out, and the suite was re-run:

```
FAILED test_two_concurrent_updates_leave_exactly_one_winner
FAILED test_the_loser_gets_the_error_that_becomes_409   (assert 2 == 1 — both writes succeeded)
1 passed
```

Two failures and one pass is exactly the right shape: the lost update appears, while the
concurrent-creates test stays green because it must not depend on locking. The source files were
then restored and confirmed byte-identical to `HEAD` with `git diff --exit-code`.

**Playwright:** `frontend/tests/e2e/products.spec.ts` — create appears in the list with no manual
refresh; the search filter narrows it; a sub-kopiyka price is refused client-side; a duplicate
barcode is reported on the barcode field; and a stale edit produces the reload-and-retry prompt,
after which the *other* writer's change is the one still standing.

**Verification (2026-08-30).** **101 backend tests passed**, three consecutive runs, no
cross-test leakage. `ruff` / `ruff format --check` clean (38 files) · `pyright` 0 errors, strict ·
Playwright **5 passed** for products, **10 passed** for auth.

---

## Milestone 4 — Phase 4: Goods Receipt Draft & Edit

Goal: the document structure — header plus lines, editable only while `draft`.

### Issue 14 — `P4: Warehouse and counterparty reference stubs`

**Status:** ✅ Done (2026-08-30)

**Context.** PRD scopes one warehouse per organization and a name-only supplier entity. These
exist to make the receipt valid, not as full modules.

**Scope.**
- `Warehouse` and `CounterpartyStub` models + migration.
- A default warehouse created for each organization.

**Acceptance criteria.** Every organization resolves to exactly one warehouse; receipts can
reference a supplier by id.

**Modules.** `backend/app/models/{inventory,counterparty}.py`.

**Tests.** Default warehouse exists for a newly created organization.

**Out of scope.** Multiple warehouses, transfers, contracts, counterparty statistics.

**The boundaries are constraints, not conventions.** `warehouses` carries a unique constraint on
`organization_id` alone — the PRD scopes exactly one warehouse per organization and puts
transfers out of scope, so the day that changes is a deliberate migration rather than a surprise
found in production. `counterparties_stub` is unique on `(organization_id, name)`: the entity is
a name and nothing else, so two rows with the same name are indistinguishable and a user picking
between them in a dropdown is picking at random.

**Two tests assert what these tables must *not* grow.** `test_the_counterparty_stub_stays_a_stub`
pins the exact column set, and `test_the_warehouse_holds_no_stock` does the same while checking
there is no `quantity` — a name-only reference table is precisely the kind that accretes columns
nobody planned, and stock on a warehouse row would be the same shortcut `products` is already
guarded against.

**Get-or-create, inside a savepoint.** `inventory.default_warehouse()` creates the warehouse on
first use rather than requiring it up front, so an organization inserted by hand still resolves.
The insert runs in `session.begin_nested()`: two concurrent first-uses would both see nothing and
both insert, the unique constraint rejects one, and the savepoint confines that failure so the
caller's transaction survives and simply re-reads the winner's row. Flushing directly would
poison the outer transaction and turn a benign race into a failed request.

**Verification (2026-08-30).** Test-first, RED confirmed (the module did not exist);
**11 passed** for this issue and **112** across the suite. `ruff` / `ruff format --check` clean
(43 files) · `pyright` 0 errors, strict · `alembic check` clean · downgrade and back proven ·
the OpenAPI contract is unchanged, as expected for an issue that adds no endpoint.

---

### Issue 15 — `P4: Goods receipt document models`

**Status:** ✅ Done (2026-08-30)

**Scope.**
- `GoodsReceipt`: `id`, `organization_id`, `warehouse_id`, `counterparty_id`,
  `status` (`draft`|`posted`), `version`, `created_by`, `created_at`.
- `GoodsReceiptLine`: `id`, `receipt_id`, `product_id`, `quantity`, `purchase_price`.
- Migration; cascade rules for lines; database-level check that quantity is positive.

**Acceptance criteria.**
- Status is a constrained enum at the database level, not free text.
- Deleting a draft receipt removes its lines; no orphan lines are reachable.
- `alembic check` clean.

**Modules.** `backend/app/models/goods_receipt.py`.

**Tests.** Constraint tests: non-positive quantity rejected by the database, not only by Pydantic.

**Out of scope.** Posting logic, batches, movements.

**`VARCHAR` + `CHECK`, not a native `ENUM`.** The criterion asks for a constraint at the
database level, and both satisfy it; the difference is what happens when the set of statuses
changes. `ALTER TYPE … ADD VALUE` cannot run inside a transaction block against a pre-existing
type, so a native enum turns every future status into an awkward migration, while the `CHECK` is
a one-line rewrite. Two tests hold it from both sides: raw SQL setting `status = 'approved'` is
rejected, and every value the Python enum declares is accepted — a constraint *narrower* than the
enum would fail a legitimate transition in production.

**Other decisions:**

| Decision | Reason |
|---|---|
| `cascade="all, delete-orphan"` on `lines`, plus `ON DELETE CASCADE` | Editing a draft replaces its lines. One that lingered after being removed would be counted at posting time and quietly inflate the stock, so both the ORM and the database delete it. |
| `created_by` is `ON DELETE RESTRICT` | Audit needs an actor. A posted document must not vanish because somebody removed the user who entered it. |
| `quantity > 0`, not `>= 0` | A zero-quantity line means nothing arrived — a line that should not exist. |
| The same product may appear on **two** lines | Price is per line, so one delivery bringing the same product at two prices is a real case, not a mistake to prevent. |
| **No stored line total** | `quantity × purchase_price` is a second source of truth that can only agree with its inputs or be wrong, and the arithmetic is cheap. Asserted by a test. |

**Considered and deferred.** Cross-tenant safety on lines — a denormalised `organization_id` plus
a composite foreign key to `products (organization_id, id)` — would make it impossible to attach
another organization's product to a receipt at the database level. It is a genuine improvement
but a design change beyond this issue's stated columns, so the guard lives in the service layer
(Issue 16) and this note records the alternative rather than smuggling it in.

**Verification (2026-08-30).** Test-first, RED confirmed; **17 passed** for this issue,
**129** across the suite. `ruff` / `ruff format --check` clean · `pyright` 0 errors, strict ·
`alembic check` clean · downgrade and back proven · `\d goods_receipt_lines` confirms both CHECK
constraints, `numeric(14,2)`, and `ON DELETE CASCADE` from the receipt with `RESTRICT` to the
product.

---

### Issue 16 — `P4: Goods receipt draft API`

**Status:** ✅ Done (2026-08-30)

**Scope.**
- `POST /api/v1/goods-receipts` (create draft), `GET /api/v1/goods-receipts/{id}`,
  `GET /api/v1/goods-receipts` (list), `PATCH /api/v1/goods-receipts/{id}` (edit lines).
- Guards: editing a non-draft → 409; version mismatch → 409; invalid lines → 422;
  cross-organization → 403.

**Acceptance criteria.**
- A posted document cannot be mutated through `PATCH` under any payload.
- Line replacement is atomic — a rejected `PATCH` leaves the previous lines intact.

**Modules.** `backend/app/api/v1/goods_receipts.py`, `backend/app/services/goods_receipt.py`.

**Tests.** Draft lifecycle, stale version, edit-after-post rejection.

**Out of scope.** The `/post` command.

**Three defects this issue's tests found in Issue 15's models.** All three were invisible to
inspection and only appeared once real requests ran:

1. **`status` came back as a bare `str`.** `Mapped[ReceiptStatus]` over a plain `String(16)`
   column does no conversion, so after a round trip `receipt.status is ReceiptStatus.DRAFT` was
   quietly `False` — and the first `PATCH` answered `receipt_not_draft` for a document that was a
   draft. The annotation had been a lie. Fixed with `sa.Enum(native_enum=False)`, whose job here
   is conversion; `values_callable` is load-bearing too, or SQLAlchemy stores the member *names*.
   `create_constraint=False` on purpose: SQLAlchemy would add the CHECK through a DDL event that
   never appears in `Table.constraints`, and Alembic's check-constraint comparison then reports it
   as an orphan on every run. The constraint is declared explicitly where autogenerate can see it.
2. **Lines had no order.** They were ordered by `created_at`, but `now()` is the *transaction*
   timestamp in PostgreSQL, so every line of one document shares it exactly — the order was
   arbitrary, always. Line order is data: a `position` column now carries it, with a
   `DEFERRABLE INITIALLY DEFERRED` unique constraint on `(receipt_id, position)`, deferred
   because replacing a document's lines inserts the new set before deleting the old one inside a
   single flush.
3. **Replacing lines did not bump `version`.** `version_id_col` increments only when the *parent
   row* is updated, and a collection change does not touch it. Two users could therefore rewrite
   the same draft's lines concurrently and both be told they won — a lost update on the
   document's actual contents, which is precisely what the version token exists to prevent. The
   service now flags the row dirty so the `UPDATE` carrying the version check is issued.

The Issue 15 revision was regenerated rather than patched by a follow-up migration: it had never
run anywhere but a development database, and a migration whose only purpose is to fix a defect
introduced twenty minutes earlier on an unmerged branch is noise for a reviewer.

**API decisions:**

| Decision | Reason |
|---|---|
| `lines` distinguishes **absent** from **empty** | Omitting it leaves the document alone; `[]` clears it. Collapsing the two would let a supplier change silently wipe a delivery. |
| The warehouse is resolved **server-side** | An organization has exactly one, so letting the client name it would only create a way to get it wrong. |
| `total` and `line_total` are computed by the server | JavaScript has no decimal type. A total computed in the browser is a total that can be off by a kopiyka, and it is displayed next to money. |
| A posted document answers **409 `receipt_not_draft`** | Not 403: the caller has every right to it and the payload is fine — the document's *state* refuses. Tested under four different payloads, including an empty one. |
| An unresolvable product is **422 `unknown_product`** | A foreign product and a nonexistent one give the same answer, because the lookup is scoped and never learns which it was. |
| A duplicate supplier name is **409 `counterparty_name_taken`** | Well-formed payload, rejected by current state. |

**Scope note.** `GET`/`POST /api/v1/counterparties` were added, which the issue does not list.
Issue 17's supplier picker cannot be populated — or the flow exercised at all — without them, and
creation is a name and nothing else, exactly as the PRD scopes it.

**Verification (2026-08-30).** Test-first, RED confirmed; **31 passed** for this issue and
**162** across the suite, stable over three consecutive runs. `ruff` / `ruff format --check`
clean (50 files) · `pyright` 0 errors, strict · `alembic check` clean · contract regenerated,
`pnpm typecheck` and `pnpm lint` clean against it.

The atomicity criterion is tested as written: a `PATCH` whose second line names an unknown
product returns 422, and a follow-up `GET` shows the original line and version untouched.

---

### Issue 17 — `P4: Goods receipt draft UI`

**Status:** ✅ Done (2026-08-30)

**Scope.**
- `/goods-receipts` list showing status, supplier, created by, created at.
- Create/edit view: supplier picker, line editor (product search, quantity, purchase price),
  running total, save as draft.
- 409 handling consistent with the products pattern.

**Acceptance criteria.**
- A draft with multiple lines round-trips through a page reload unchanged.
- Posted documents render read-only with no editing affordances.

**Modules.** `frontend/app/pages/goods-receipts/*`, `frontend/app/components/ReceiptLineEditor.vue`.

**Tests.** Playwright: create draft, add three lines, reload, verify persistence.

**The running total is computed in whole kopiykas.** The server owns every saved total, but the
browser still has to show one *while the user is typing*, before anything is saved — and
JavaScript has no decimal type, so `0.1 + 0.2 !== 0.3`. `app/utils/money.ts` parses `"12.34"`
into `1234`, multiplies by an integer quantity and sums in integers, so the figure on screen is
the one the server confirms rather than one that drifts by a kopiyka next to real money.

**A posted document has no editing affordances at all** — no inputs, no save button, no supplier
picker; the values are shown read-only rather than hidden. The server refuses the edit too
(409 `receipt_not_draft`), but offering a control that cannot work is its own kind of bug.

**Posting is faked by a script, never by an endpoint.** Issue 17's second acceptance criterion
needs a posted document a phase before the posting command exists.
`backend/scripts/mark_receipt_posted.py` flips the status for the E2E suite, and lives in
`scripts/` precisely so it cannot be reached over HTTP: a route that posts a document on request
is a backdoor around the entire posting transaction, and guarding it with a debug flag would only
mean the backdoor ships with the flag.

**A test-harness finding worth keeping.** PrimeVue leaves the markup of previously opened
`Select` overlays in the DOM, so a page-wide `getByRole('option')` matches every list at once as
soon as a second line exists — the suite failed with a strict-mode violation naming two identical
options. Option lookups are now scoped to the overlay that is actually visible.

**Scope note.** `ReceiptSupplierPicker.vue` also creates a supplier inline. Without it the flow
dead-ends the first time an organization has no counterparties, and the PRD scopes supplier
creation as a name and nothing else.

**Verification (2026-08-30).** `pnpm lint`, `pnpm typecheck` and `pnpm build` clean.
Playwright: **5 passed** for this issue, **20 passed** across the whole E2E suite.
The two acceptance criteria are tested as written — three lines with a running total of `42.60`
survive a genuine page reload with quantities intact, and a posted document renders with
`receipt-save`, `line-add` and the supplier picker all absent while the total still reads
`40.00`.

---

## Milestone 5 — Phase 5: Posting — Idempotency & Atomic Movements

Goal: the core correctness claim of the whole tracer bullet.

### Issue 18 — `P5: Batch, movement, and audit models`

**Status:** ✅ Done (2026-08-30)

**Scope.**
- `InventoryBatch`, `StockMovement`, `AuditLog` models + migration.
- `StockMovement` is append-only: no update or delete path is exposed anywhere in the codebase.

**Acceptance criteria.**
- Movements carry `quantity_delta`, `movement_type`, `batch_id`, `document_id`.
- No product row holds a mutable `quantity` column (PRD requirement).
- Indexes support `(organization_id, warehouse_id, product_id)` aggregation.

**Modules.** `backend/app/models/{inventory,audit}.py`.

**Tests.** Schema assertions; index presence.

**Append-only is a database trigger, not a convention.** Research §386 asks for immutability
"by application policy and database constraints where practical" — and a policy only binds code
that has read it, which a migration, a `psql` fix-up or a future service has not. A `BEFORE
UPDATE OR DELETE` trigger on `stock_movements` and `audit_log` raises `restrict_violation`, and
two tests prove it by attempting the `UPDATE` in raw SQL. A third scans `app/` to confirm no
code path even tries — the trigger stops the database accepting it; that test stops a developer
writing something that would fail in production.

**Consequence, stated deliberately:** because the trigger also refuses `DELETE`, removing an
organization that has posted history now fails. That is the correct answer for an audit trail,
and it means tenant deletion becomes a conscious operation rather than a side effect of one row
disappearing.

**Other decisions:**

| Decision | Reason |
|---|---|
| `quantity_delta` is **signed**, with `CHECK (<> 0)` | The sign is the mechanism: balance is `SUM(quantity_delta)` over the scope. Sales are out of scope for this slice, but the column is not — forbidding negatives now would mean rebuilding it later. A zero row only pollutes an aggregation it contributes nothing to. |
| `document_id` and `audit_log.entity_id` are **not** foreign keys | The causing document may later be a sale, a transfer or an adjustment, and history must not depend on which table it lives in. An audit trail that vanishes with its subject is not an audit trail. |
| `CHECK (remaining_quantity BETWEEN 0 AND quantity)` | More left than ever arrived is a state the database should refuse to hold, not one to detect later. |
| The batch keeps its own `purchase_price` | FIFO cost, in a later phase, depends on the price the goods *arrived* at, not on today's catalog price. |
| `audit_log.old_value` / `new_value` nullable | A creation has no "before". Requiring both would push callers into writing `{}` and losing the distinction between "nothing" and "empty". |
| `actor_id` is `ON DELETE RESTRICT` | An action whose actor has been erased is unattributable, which defeats the point of recording it. |

**Verification (2026-08-30).** Test-first, RED confirmed; **18 passed** for this issue and
**180** across the suite. `ruff` / `ruff format --check` clean (54 files) · `pyright` 0 errors,
strict · `alembic check` clean · downgrade and back proven, **including the triggers**, which
`information_schema.triggers` confirms are re-created as `DELETE,UPDATE` on both tables.
The index acceptance criterion is checked against the reflected schema rather than the model:
`('organization_id', 'warehouse_id', 'product_id')` is present on `stock_movements`.

---

### Issue 19 — `P5: Idempotency key mechanism`

**Status:** ✅ Done (2026-08-30)

**Context.** PRD makes `Idempotency-Key` mandatory for the posting command. A replayed request
must return the original result; the *same key with a different payload* is a conflict, not a
replay.

**Scope.**
- Idempotency record table: key, organization, endpoint, request fingerprint, stored response,
  created at.
- Reusable dependency/decorator so future commands inherit the behaviour.
- Unique constraint enforcing at-most-once execution per key under concurrency.

**Acceptance criteria.**
- Replay with identical payload returns the stored response, executes nothing.
- Same key with a different payload returns **409**.
- Missing key on the posting endpoint returns 422.

**Modules.** `backend/app/core/idempotency.py`, `backend/app/models/idempotency.py`.

**Tests.** Replay, conflicting-payload, and missing-key cases.

**The whole mechanism is one unique constraint plus one transaction.** The reservation row is
inserted in the *same* transaction as the command, which buys two properties without any
locking, in-flight state machine or polling of our own:

- **A failed command does not burn its key.** The rollback takes the reservation with it, and the
  request that failed is exactly the one a client will retry.
- **Concurrency is PostgreSQL's problem.** Two requests carrying the same key both attempt the
  insert; the second waits on the unique index. If the first commits, the second's insert raises
  a unique violation and it returns the stored response; if the first rolls back, the second's
  insert succeeds and it does the work.

**A defect the tests found in this issue's own code.** `except IntegrityError` was too broad: a
foreign-key violation was being treated as "this key is already taken", which would have hidden a
real bug behind a 200. Only the violation of `uq_idempotency_records_scope` now means a replay;
everything else is re-raised — the same discipline already applied to `barcode_taken`.

**Other decisions:**

| Decision | Reason |
|---|---|
| Fingerprint over a **canonical** JSON rendering (`sort_keys`) | Object order carries no meaning, so an equivalent retry that serialised its fields differently must not look like a conflict. Asserted by a test. |
| A same-key-different-payload request is **409**, not a replay | It means the client's key generation is broken; returning the first response would silently answer a question that was never asked. |
| The stored response is returned **verbatim** | The record is the source of truth for a replay, not whatever the caller would compute today. Tested by replaying with a command that would return something different. |
| The key is mandatory, with no generated fallback | A fallback would make every request unique — no idempotency at all, while looking switched on. |
| Scoped per `(organization, endpoint, key)` | Client-supplied keys are not globally unique, and one key reaching two different commands is two different pieces of work. Both scopes are tested. |

**Verification (2026-08-30).** Test-first, RED confirmed; **15 passed** for this issue and
**195** across the suite. `ruff` / `ruff format --check` clean (58 files) · `pyright` 0 errors,
strict · `alembic check` clean · downgrade and back proven. True concurrent execution of the
mechanism is exercised in Issue 22, where a real command exists to run against it.

---

### Issue 20 — `P5: Post goods receipt — atomic transaction`

**Status:** ✅ Done (2026-08-30)

**Context.** The single most correctness-sensitive endpoint in the slice. Everything happens in
one transaction or nothing does.

**Scope.**
- `POST /api/v1/goods-receipts/{id}/post`.
- Transaction: lock the receipt row (`SELECT … FOR UPDATE`), verify `status = draft` and the
  client version, reject empty lines, create the batch, create the movement, flip status,
  increment version, write the audit record, commit.
- Any failure rolls back completely — no partial batch without its movement.

**Acceptance criteria.**
- Posting twice creates exactly one batch and one movement.
- Posting an already-posted document → 409.
- Posting a document with no lines → 422.
- An injected failure after batch creation leaves zero batches and zero movements.

**Modules.** `backend/app/services/posting.py`, `backend/app/api/v1/goods_receipts.py`.

**Tests.** Covered by Issue 22, plus the injected-failure rollback test here.

**Out of scope.** Unposting/cancellation (explicitly outside the PRD).

**Deviation from the plan, and it matters.** The plan says "create batch from receipt (copy
price, sum qty)" and "movement qty_delta = sum of line quantities". That holds only for a
single-product delivery. A batch is a quantity of **one** product at **one** price; summing
across lines would merge different goods into one batch and discard the price each arrived at —
which is precisely what FIFO cost depends on later. The implementation creates **one batch and
one movement per line**, and a test with two products at two prices pins it.

Two lines naming the same product at the same price still become two batches: they arrived as
two entries on the document, and keeping them separate preserves the trace back to it.

**The order of operations is the design.**

1. `SELECT … FOR UPDATE` on the receipt. This is what makes two simultaneous posts sequential —
   the second waits, and by the time it proceeds the first has flipped the status, so it reads
   `posted` and refuses. Without the lock both would read `draft` and both would post.
   `version_id_col` would still catch it at flush, but only after the loser had done all its
   work; the lock is cheaper and the error is clearer.
2. Every refusal — not-draft, stale version, empty document — happens **before the first write**,
   so a rejected post provably has not touched a row.
3. Batches, movements, status, audit. Nothing in `posting.py` commits; the router owns the
   transaction, so the idempotency reservation and the work commit together or roll back
   together.

**Status codes:** `empty_document` is **422**, not 409 — the document's *state* is fine, its
*content* is not, which is the line research §555 draws. A second post with a different key is
**409 `receipt_not_draft`**; with the *same* key it is a replay and returns the stored body.

**Verification (2026-08-30).** Test-first; **15 passed** for this issue, **210** across the
suite. `ruff` / `ruff format --check` clean (60 files) · `pyright` 0 errors, strict ·
`alembic check` clean · contract regenerated, frontend typecheck and lint clean against it.

Every acceptance criterion is tested as written, and the hardest one directly: `_record_movement`
is monkeypatched to raise **after** the batches exist in the session, and the assertions are that
zero batches, zero movements and zero audit rows survive, and that the document is still a
`draft` at its original version. A partial post — stock recorded with no movement to explain it —
is the corruption this transaction exists to prevent.

---

### Issue 21 — `P5: Posting UI`

**Status:** ✅ Done (2026-08-30)

**Scope.**
- Post action on the receipt detail view, generating and sending an `Idempotency-Key`.
- Disabled state while in flight; no double submission.
- Distinct messages for 409 (already posted / changed) and 422 (invalid document).

**Acceptance criteria.**
- Double-clicking the post button produces one movement, verified in the database.
- After posting, the document renders read-only.

**Modules.** `frontend/app/pages/goods-receipts/[id].vue`, `frontend/app/composables/usePosting.ts`.

**The key identifies an attempt, not a request.** `postingKey(receiptId, version)` memoises a
nonce per document-and-version, so a retry after a timeout **replays** while a genuinely new
attempt on a changed document gets a new key. Generating one per request would make every retry a
new command — no idempotency at all, while looking switched on.

**Double submission is closed three times over**, and deliberately so: the handler returns early
while `isPending`, the button is disabled, and the server holds a row lock. The UI guards are not
redundant decoration — a control that fires a request it knows will fail teaches users to
distrust it.

**Distinct messages, because the user's next action differs.** `version_conflict` and
`idempotency_conflict` raise the reload-and-retry banner; anything else states what the server
said. An empty document does not produce a message at all — the button is simply disabled,
because a control that cannot work should not invite the click.

**Scope note.** `backend/scripts/count_movements.py` was added. "A double click produces one
movement" is a claim about the **database**, and the browser has no way to observe it until the
stock-balance endpoint exists in Phase 6. It is a script rather than an endpoint for the same
reason as `mark_receipt_posted.py`: test-only capabilities that ship are backdoors.

**Verification (2026-08-30).** `pnpm lint`, `pnpm typecheck`, `pnpm build` clean. Playwright:
**4 passed** for this issue, **24 passed** across the whole E2E suite. Both acceptance criteria
are tested as written — a `dblclick` on the post button leaves `batches=1 movements=1` in the
database, and a posted document renders with the post button, save button, line editor and
supplier picker all absent.

---

### Issue 22 — `P5: Posting integration tests`

**Status:** ✅ Done (2026-08-30)

**Scope.**
- Post → assert batch, movement, audit row, and status transition.
- Replay with the same idempotency key → assert no duplicate movement.
- Two concurrent posts of the same receipt → exactly one succeeds.
- Different keys on an already-posted document → 409, still one movement.

**Acceptance criteria.** Each test fails when its guard is removed — verified deliberately, so
the tests are known to be load-bearing rather than merely green.

**Modules.** `backend/tests/test_posting.py`, `backend/tests/test_posting_concurrency.py`.

**The matrix.** The sequential cases live in `test_posting.py` (15 tests); the four that need
genuinely parallel transactions live in `test_posting_concurrency.py`, committing for real on
independent connections:

| Case | Result |
|---|---|
| Two concurrent posts, **different** keys | one `posted`, one `receipt_not_draft`; **1 batch, 1 movement, 1 audit row** |
| Two concurrent posts, **same** key | one `posted`, one `replayed` with a byte-identical body; **1 batch, 1 movement** |
| A different key on an already-posted document | `receipt_not_draft`, still one movement |
| Either way | the document ends `posted` at version **2**, not 3 — the loser wrote nothing |

**The acceptance criterion was carried out, not assumed.** `.with_for_update()` was commented
out and the suite re-run: `test_two_concurrent_posts_with_different_keys_leave_one_movement`
failed, and it failed *informatively* — `StaleDataError: UPDATE ... expected to update 1 row(s);
0 were matched`. That is `version_id_col` catching the lost update at flush time, exactly as the
code comment predicts, and it is why the lock earns its place: without it the loser does all its
work before discovering it lost.

**Two defects this exercise exposed:**

1. **An escaping `StaleDataError` would have been a 500.** The lock makes it unreachable in
   practice, but "unreachable in practice" is not a contract. The endpoint now maps it to
   `version_conflict`, so a race the client loses is a 409 either way.
2. **Three tests asserted *global* row counts.** They passed only while no other suite committed
   anything — an assumption the concurrency tests immediately broke. A test that depends on the
   rest of the database being empty is testing the suite rather than the code; every count is now
   scoped to the organization under test.

**Cleanup had to say out loud what the schema enforces.** Movements and audit rows are
append-only, so teardown disables the trigger for the duration — a table-owner operation confined
to the test suite. And deleting the organization is not enough: `ON DELETE RESTRICT` fires even
when the referencing row is being removed by the same cascade, so a receipt still pointing at its
warehouse blocks the warehouse's removal. The purge walks the dependency order explicitly.

**Verification (2026-08-30).** **214 backend tests passed**, three consecutive runs, no
cross-test leakage. `ruff` / `ruff format --check` clean (62 files) · `pyright` 0 errors, strict ·
`alembic check` clean · Playwright **24 passed**.

---

## Milestone 6 — Phase 6: Stock Balance Query

Goal: prove balance is derived from movements, never stored.

### Issue 23 — `P6: Stock balance aggregation endpoint`

**Scope.**
- `GET /api/v1/stock-balance?product_id=&warehouse_id=` returning `product_id`,
  `warehouse_id`, `quantity_balance`, `last_movement_date`.
- Aggregation over `stock_movements`; organization scope enforced.
- A product with no movements returns a zero balance, not 404 — absence of movement is a
  valid state, distinct from a missing product (which is 404).

**Acceptance criteria.**
- Balance equals the sum of `quantity_delta` across all posted receipts.
- No mutable quantity column is read anywhere in the query path.
- Cross-organization query → 403.

**Modules.** `backend/app/api/v1/stock_balance.py`, `backend/app/services/stock.py`.

**Tests.** Single receipt; multiple receipts aggregating; zero-movement product.

---

### Issue 24 — `P6: Stock balance UI and end-to-end verification`

**Scope.**
- `/stock-balance` page: product/warehouse filter, table of Product | Warehouse | Quantity |
  Last movement.
- E2E covering the full tracer bullet: log in → create product → create receipt → post →
  balance reflects the posted quantity.

**Acceptance criteria.** The E2E test traverses UI → API → domain → database → UI and is the
executable proof of the PRD Definition of Done.

**Modules.** `frontend/app/pages/stock-balance.vue`, `frontend/tests/e2e/tracer-bullet.spec.ts`.

---

## Milestone 7 — Phase 7: Concurrency & Integration Test Matrix

Goal: verify behaviour under contention rather than assuming it.

### Issue 25 — `P7: Real-PostgreSQL test fixture and concurrency helper`

**Context.** Concurrency tests are meaningless against a mocked or in-memory database. Research
specifies Testcontainers; if Docker-in-CI proves unreliable, a service-container fixture with
per-test schema isolation is the fallback — the fallback must be a documented decision, not a
silent downgrade.

**Scope.**
- Session-scoped Postgres fixture running migrations once.
- Per-test isolation (transaction rollback or schema-per-test).
- Helper spawning genuinely parallel requests and collecting results/exceptions.

**Acceptance criteria.**
- Two threads truly overlap inside the posting transaction — proven with a deliberate delay,
  not assumed.
- Suite is repeatable: no cross-test state leakage across 3 consecutive runs.

**Modules.** `backend/tests/conftest.py`, `backend/tests/support/concurrency.py`.

---

### Issue 26 — `P7: Concurrency and error matrix, plus phase report`

**Scope.** Implement the matrix from the plan (§Phase 7) and research §6.7:
- concurrent posts of *different* receipts for the same product → both succeed, totals aggregate;
- concurrent draft edits with mismatched versions → one 409;
- concurrent posts, same key → one execution, one stored response;
- concurrent posts, different keys → one 409, no duplicate movement;
- stale read then post then re-query → balance correct;
- malformed payloads → 422; cross-organization → 403.

Then write `docs/exec-plans/completed/report-tracer-bullet.md`: what was verified, which
commands produced the evidence, and every known limitation.

**Acceptance criteria.**
- All matrix cases pass; none is skipped or marked xfail without a written justification.
- The report states explicitly which checks could not be run, per `AGENTS.md` §12.

**Modules.** `backend/tests/test_concurrency.py`, `docs/exec-plans/completed/report-tracer-bullet.md`.

---

## Summary

| Milestone | Phase | Issues | Status |
|-----------|-------|--------|--------|
| 1 | Repository Scaffold & Baseline | 1–5 | ✅ 5 of 5 done, CI green |
| 2 | Identity & Organizations | 6–9 | ✅ 4 of 4 done |
| 3 | Catalog (Products) | 10–13 | ✅ 4 of 4 done |
| 4 | Goods Receipt Draft & Edit | 14–17 | ✅ 4 of 4 done |
| 5 | Posting — Idempotency & Atomicity | 18–22 | ✅ 5 of 5 done |
| 6 | Stock Balance Query | 23–24 | Not started |
| 7 | Concurrency & Test Matrix | 25–26 | Not started |

**26 issues across 7 milestones.**

## Open dependencies

| Blocker | Blocks | Owner | Status |
|---------|--------|-------|--------|
| Docker Desktop requires host reboot | Issue 4, and every test needing Postgres | User | ✅ Resolved — Engine 29.7.2 responding |
| Git identity is a placeholder | Commit attribution on GitHub | User | ✅ Resolved — `Andrii Bryla <bryla.andrii@gmail.com>` |
| No CI run on the phase branch | Issue 5 acceptance criterion *"workflow passes"* | — | ✅ Resolved — run 33318800111 green on `3c58339` |
| `gh auth login` is interactive (browser) | Publishing these 26 issues as GitHub milestones/issues; opening the Phase 1 PR from the CLI | User | ❌ Open — `gh` reports no logged-in host |

## Resume here — state as of 2026-08-30, end of Phase 5

**Branches.** `origin/main` is still at `f5e732c` — documents only. Each phase branch is stacked
on the previous one, so the newest contains all the others:

| Branch | Contains | CI |
|---|---|---|
| `phase-1` | Milestone 1, issues 1–5 | green |
| `phase-2` | Milestone 2, issues 6–9 | green |
| `phase-3` | Milestone 3, issues 10–13 | green |
| `phase-4` | Milestone 4, issues 14–17 | green |
| `phase-5` | Milestone 5, issues 18–22 — **contains phases 1–4** | green (3 jobs) |

**Done: Milestones 1–5, issues 1–22.** Per-issue verification evidence is recorded under each
issue above rather than summarised here.

| Gate | Result |
|---|---|
| `uv run ruff check .` / `ruff format --check .` | clean, 62 files |
| `uv run pyright` | 0 errors, strict |
| `uv run pytest` | **214 passed**, stable over 3 consecutive runs |
| `uv run alembic upgrade head` + `alembic check` | clean; 7 revisions; downgrade proven each time |
| `pnpm api:check` | contract and generated types reproduce byte-for-byte |
| `pnpm lint` / `pnpm typecheck` / `pnpm build` | clean / 0 errors / build complete |
| `pnpm test:e2e` | **24 passed** (10 auth + 5 products + 5 receipts + 4 posting) |
| GitHub Actions | [run 33843902303](https://github.com/UkrAndy/shop-crm/actions/runs/33843902303) — all three jobs green |

**Working software today.** Log in · pick an organization · manage products with optimistic
concurrency · create a supplier · draft a goods receipt with a running total · **post it**, which
creates a batch and a movement per line plus an audit record in one transaction, is idempotent
under a replayed key, and refuses a second post. `backend/scripts/seed_dev.py` provides
`owner@example.com` and `multi@example.com`, both with password `seed-password-123`.

**What is left.** Milestone 6 (issues 23–24, stock balance query and the end-to-end tracer-bullet
proof) and Milestone 7 (issues 25–26, the full concurrency matrix and the phase report). The
balance endpoint is the last piece of the PRD's Definition of Done: every movement it needs
already exists and is indexed for exactly that aggregation.

**Environment:** `uv` 0.12.7 (at `%LOCALAPPDATA%\Programs\Python\Python314\Scripts\uv.exe`,
not on the default PATH), Python pinned to **3.14** by `backend/.python-version`,
`pnpm` 11.24.0, Node 24.19.0, `gh` 2.98.0 (unauthenticated), Docker Desktop 4.88.1 /
Engine 29.7.2, Playwright 1.62.1 with Chromium only.

**Constraints established that later work must not break:**
- **The API must be same-site with the frontend.** Hosts are part of a *site*; ports are not.
  See `design-auth.md` §"Deployment constraint".
- **Anything driving an SSR page must wait for hydration** — `app.vue` sets `data-hydrated`.
  Scope PrimeVue option lookups to the **visible** overlay.
- **New models must be registered in `app/models/__init__.py`**, or `alembic check` will not see
  them and CI will pass on a schema that does not exist.
- **`openapi.json` and `schema.d.ts` are generated and committed**, and nothing in that document
  may depend on the Python version.
- **Optimistic concurrency is `version_id_col`.** A collection change does **not** bump the
  parent's version — editing child rows must flag the parent dirty.
- **`now()` is the transaction timestamp.** Rows written together share it exactly, so it can
  never order them. Line order is a stored `position`.
- **`stock_movements` and `audit_log` are append-only at the database level.** A trigger refuses
  `UPDATE` and `DELETE`, so removing an organization with posted history fails — tenant deletion
  is a conscious operation. Test cleanup disables the trigger explicitly.
- **`ON DELETE RESTRICT` fires even inside a cascade** that is removing the referencing row, so
  teardown must walk the dependency order rather than deleting the organization and hoping.
- **Never assert a global row count in a test.** The concurrency suites commit real rows; a test
  that needs the rest of the database empty is testing the suite, not the code.
- **Test-only capabilities live in `backend/scripts/`, never as endpoints.** A route that posts a
  document, or flips its status, is a backdoor around the posting transaction.

**Supply-chain notes carried forward.** `uv` has neither an Authenticode signature nor a
PEP 740 attestation. `fastapi[standard]` pulls `sentry-sdk` transitively — inert without a
DSN, but unaudited. On the npm side, `primevue` and `@primeuix/themes` have no SLSA
attestation and no `repository` field; every other dependency added since does.
`pnpm install` reports `Lockfile passes supply-chain policies`.

**Next, in this order:**
1. Merge into `main`. `gh` is unauthenticated, so this is a browser action; merging `phase-5`
   alone is sufficient because it already contains phases 1–4:
   https://github.com/UkrAndy/shop-crm/pull/new/phase-5
2. `gh auth login` in a **new** terminal, then publish these 26 issues as milestones/issues
   if GitHub tracking is still wanted.
3. Start Milestone 6 at **Issue 23** — `GET /api/v1/stock-balance`. Note the issue's own
   instruction: a product with no movements returns a **zero balance, not 404** — absence of
   movement is a valid state, distinct from a missing product. `ix_stock_movements_scope` already
   covers the aggregation.
