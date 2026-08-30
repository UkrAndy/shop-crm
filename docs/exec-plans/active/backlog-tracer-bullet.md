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

---

### Issue 9 — `P2: Authentication test coverage`

**Scope.**
- Playwright set up for the repository (config, CI wiring).
- E2E: login → organization selection → protected page.
- E2E: invalid credentials show an error and stay on `/login`.
- Integration tests for the scope matrix from Issue 7.

**Acceptance criteria.** Suite passes locally and in CI against a real Postgres service.

**Modules.** `frontend/tests/e2e/auth.spec.ts`, `frontend/playwright.config.ts`,
`backend/tests/test_auth.py`.

**Out of scope.** Visual regression testing.

---

## Milestone 3 — Phase 3: Catalog (Products) Minimum

Goal: establish the mutable-aggregate pattern — optimistic concurrency with a version token.

### Issue 10 — `P3: Product model with version token`

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

---

### Issue 11 — `P3: Products API with optimistic concurrency`

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

---

### Issue 13 — `P3: Product concurrency tests`

**Scope.** Unit tests for the service layer; integration test issuing two concurrent updates to
the same product and asserting exactly one wins with the other receiving 409; Playwright
happy-path create → appears in list.

**Acceptance criteria.** Concurrency test fails if optimistic locking is removed (verified by
temporarily disabling the version check).

**Modules.** `backend/tests/test_products.py`, `frontend/tests/e2e/products.spec.ts`.

---

## Milestone 4 — Phase 4: Goods Receipt Draft & Edit

Goal: the document structure — header plus lines, editable only while `draft`.

### Issue 14 — `P4: Warehouse and counterparty reference stubs`

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

---

### Issue 15 — `P4: Goods receipt document models`

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

---

### Issue 16 — `P4: Goods receipt draft API`

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

---

### Issue 17 — `P4: Goods receipt draft UI`

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

---

## Milestone 5 — Phase 5: Posting — Idempotency & Atomic Movements

Goal: the core correctness claim of the whole tracer bullet.

### Issue 18 — `P5: Batch, movement, and audit models`

**Scope.**
- `InventoryBatch`, `StockMovement`, `AuditLog` models + migration.
- `StockMovement` is append-only: no update or delete path is exposed anywhere in the codebase.

**Acceptance criteria.**
- Movements carry `quantity_delta`, `movement_type`, `batch_id`, `document_id`.
- No product row holds a mutable `quantity` column (PRD requirement).
- Indexes support `(organization_id, warehouse_id, product_id)` aggregation.

**Modules.** `backend/app/models/{inventory,audit}.py`.

**Tests.** Schema assertions; index presence.

---

### Issue 19 — `P5: Idempotency key mechanism`

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

---

### Issue 20 — `P5: Post goods receipt — atomic transaction`

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

---

### Issue 21 — `P5: Posting UI`

**Scope.**
- Post action on the receipt detail view, generating and sending an `Idempotency-Key`.
- Disabled state while in flight; no double submission.
- Distinct messages for 409 (already posted / changed) and 422 (invalid document).

**Acceptance criteria.**
- Double-clicking the post button produces one movement, verified in the database.
- After posting, the document renders read-only.

**Modules.** `frontend/app/pages/goods-receipts/[id].vue`, `frontend/app/composables/usePosting.ts`.

---

### Issue 22 — `P5: Posting integration tests`

**Scope.**
- Post → assert batch, movement, audit row, and status transition.
- Replay with the same idempotency key → assert no duplicate movement.
- Two concurrent posts of the same receipt → exactly one succeeds.
- Different keys on an already-posted document → 409, still one movement.

**Acceptance criteria.** Each test fails when its guard is removed — verified deliberately, so
the tests are known to be load-bearing rather than merely green.

**Modules.** `backend/tests/test_posting.py`.

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
| 2 | Identity & Organizations | 6–9 | 2 of 4 done |
| 3 | Catalog (Products) | 10–13 | Not started |
| 4 | Goods Receipt Draft & Edit | 14–17 | Not started |
| 5 | Posting — Idempotency & Atomicity | 18–22 | Not started |
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

## Resume here — state as of 2026-08-30, end of Phase 1

**Branch:** `phase-1`, pushed and tracking `origin/phase-1` ·
**Remote:** `https://github.com/UkrAndy/shop-crm.git` · **CI:** green on the phase branch
(`origin/main` is still at `f5e732c`, documents only — the whole scaffold lives on `phase-1`
until its PR is merged).

**Done: Milestone 1 issues 1–5 are implemented.** Verification evidence is recorded under each
issue above rather than summarised here.

| Gate | Result |
|---|---|
| `uv run ruff check .` / `ruff format --check .` | clean, 11 files |
| `uv run pyright` | 0 errors, strict |
| `uv run pytest` | 2 passed |
| `uv run alembic upgrade head` + `alembic check` | clean; drift detection proven by a throwaway model |
| `docker compose up -d` | postgres:17-alpine → `Up (healthy)`, PostgreSQL 17.11 |
| `GET /api/v1/health/ready` | `{"status":"ok","database":"up"}` |
| `pnpm lint` / `pnpm typecheck` / `pnpm build` | clean / 0 errors / build complete |
| SSR proof | `render-origin=server` in the initial HTML from both `pnpm dev` and the production preview |
| GitHub Actions | [run 33318800111](https://github.com/UkrAndy/shop-crm/actions/runs/33318800111) — both jobs green |

**Environment:** `uv` 0.12.7 (at `%LOCALAPPDATA%\Programs\Python\Python314\Scripts\uv.exe`,
not on the default PATH), `pnpm` 11.24.0, Node 24.19.0, `gh` 2.98.0 (unauthenticated),
Docker Desktop 4.88.1 / Engine 29.7.2.

**Supply-chain notes carried forward.** `uv` has neither an Authenticode signature nor a
PEP 740 attestation. `fastapi[standard]` pulls `sentry-sdk` transitively — inert without a
DSN, but unaudited. On the npm side, `primevue` and `@primeuix/themes` have no SLSA
attestation and no `repository` field. `pnpm install` reports
`Lockfile passes supply-chain policies`.

**Next, in this order:**
1. Open the Phase 1 PR `phase-1` → `main` and merge it, so `main` carries the scaffold.
   `gh` is unauthenticated, so this is a browser action:
   https://github.com/UkrAndy/shop-crm/pull/new/phase-1
2. `gh auth login` in a **new** terminal, then publish these 26 issues as milestones/issues
   if GitHub tracking is still wanted.
3. Start Milestone 2 at **Issue 6** — the auth strategy decision
   (`docs/design-docs/design-auth.md`) must be written before any code depends on it, and it
   is the first issue that introduces an Alembic revision.
