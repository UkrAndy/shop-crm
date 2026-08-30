# TestVasja — Inventory & Accounting System

Inventory, warehouse, financial, and management accounting with cash register and
PRRO integration (Ukrainian fiscal receipt registrar).

## Project Status

- **Phase 1 — Repository Scaffold & Baseline:** complete (issues 1–5).
- **Next:** Phase 2 — Identity & Organizations.
- **First Tracer Bullet:** Organization → Product → Goods Receipt → Batch → Stock Movement → Balance.

Progress is tracked issue by issue in
[`docs/exec-plans/active/backlog-tracer-bullet.md`](docs/exec-plans/active/backlog-tracer-bullet.md).

## Documentation

- **Business requirements:** `ТЗ_система_обліку_товару_версія_1_0.docx`
- **Architectural baseline:** [`docs/research/research-core-architecture.md`](docs/research/research-core-architecture.md)
- **First Tracer Bullet PRD:** [`docs/product-specs/prd-tracer-bullet-goods-receipt.md`](docs/product-specs/prd-tracer-bullet-goods-receipt.md)
- **Implementation plan:** [`docs/exec-plans/active/plan-tracer-bullet.md`](docs/exec-plans/active/plan-tracer-bullet.md)
- **Issue backlog:** [`docs/exec-plans/active/backlog-tracer-bullet.md`](docs/exec-plans/active/backlog-tracer-bullet.md)
- **Development workflow:** [`AGENTS.md`](AGENTS.md)

## Technology Stack

### Frontend (`frontend/`)
Nuxt 4 (SSR) · Vue 3 · TypeScript strict · PrimeVue 4 (Aura preset) ·
Tailwind CSS 4 · Pinia · TanStack Query · ESLint via `@nuxt/eslint` · `vue-tsc`

### Backend (`backend/`)
Python 3.12+ · FastAPI · SQLAlchemy 2 (synchronous) · Alembic ·
PostgreSQL 17 via psycopg 3 · pytest · ruff · pyright (strict)

### Tooling
pnpm workspace · uv · Docker Compose · GitHub Actions

## Prerequisites

Versions this scaffold was verified against on 2026-08-30:

| Tool | Version used | Notes |
|---|---|---|
| Node.js | 24.19.0 | Nuxt 4 requires `^22.19.0 \|\| ^24.11.0 \|\| >=26` |
| pnpm | 11.24.0 | pinned by `packageManager` in the root `package.json` |
| Python | 3.12+ | managed by `uv` |
| uv | 0.12.7 | not on the PATH of shells opened before its install |
| Docker Desktop | 4.88.1 (Engine 29.7.2) | Engine must be running, not just the client |

## Local Development Setup

```bash
# 1. Local services (PostgreSQL 17)
cp .env.example .env
docker compose up -d
docker compose ps            # postgres must report "healthy"

# 2. Backend
cd backend
cp .env.example .env         # defaults already match docker-compose.yml
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# 3. Frontend — from the repository root, in a second terminal
pnpm install                 # pnpm workspace: install at the root, not in frontend/
cd frontend
cp .env.example .env         # optional; defaults to http://localhost:8000/api/v1
pnpm dev
```

| URL | What |
|---|---|
| http://localhost:3000 | Nuxt app (SSR) |
| http://localhost:8000/api/v1/health/live | Liveness — no dependencies |
| http://localhost:8000/api/v1/health/ready | Readiness — probes PostgreSQL |
| http://localhost:8000/api/v1/docs | OpenAPI docs |

Resetting the database completely:

```bash
docker compose down -v && docker compose up -d
cd backend && uv run alembic upgrade head
```

## Quality Gates

These are exactly the commands CI runs
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)). Nothing here is aspirational —
per [`AGENTS.md`](AGENTS.md) §12, completion is claimed only with evidence.

**Backend** (from `backend/`, requires PostgreSQL running for the last two):

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright                # strict mode
uv run pytest
uv run alembic upgrade head
uv run alembic check          # fails if a model has no matching migration
```

**Frontend** (from the repository root):

```bash
pnpm lint
pnpm typecheck                # vue-tsc, strict
pnpm build
```

**API contract** (from `frontend/`; needs `uv` on PATH):

```bash
pnpm api:generate            # export openapi.json, then regenerate shared/api/schema.d.ts
pnpm api:check               # regenerate and fail if either file differs from git
```

`backend/openapi.json` and `frontend/shared/api/schema.d.ts` are **generated and committed**.
Never edit either by hand: change the Pydantic schema and regenerate. CI runs `api:check`, so a
contract that drifts from the code fails the build the same way a model without a migration does.

**End-to-end** (from the repository root; needs PostgreSQL running and `uv` on PATH):

```bash
pnpm test:e2e                 # Playwright, Chromium
```

The first run needs the browser once:

```bash
pnpm --filter @testvasja/frontend exec playwright install chromium
```

Nothing else has to be started by hand. `playwright.config.ts` launches the API and the Nuxt
dev server (reusing them if they are already running), and its `globalSetup` applies migrations
and seeds deterministic accounts.

## Seed Data

Registration is out of scope for the Tracer Bullet, so the first accounts come from a script:

```bash
cd backend && uv run python scripts/seed_dev.py
```

| Account | Password | Organizations |
|---|---|---|
| `owner@example.com` | `seed-password-123` | ФОП Альфа |
| `multi@example.com` | `seed-password-123` | ФОП Альфа, ФОП Бета |

`owner` has a single membership, which the server selects automatically at login; `multi` has
two, which the server deliberately refuses to choose between. The script is idempotent and is
for development databases only — the passwords are in version control.

Addresses use `example.com` on purpose: Pydantic's `EmailStr` rejects special-use names such as
`.local`, so a `user@company.local` account would be created but could never log in.

## Project Structure

```
/
├── backend/                (FastAPI modular monolith)
│   ├── app/
│   │   ├── api/v1/         (routers)
│   │   ├── core/           (config, db, security)
│   │   └── models/         (SQLAlchemy models — registry for Alembic)
│   ├── migrations/         (Alembic; revisions land from Phase 2)
│   └── tests/
├── frontend/               (Nuxt 4, SSR)
│   └── app/                (pages, components, plugins, stores)
├── docs/
│   ├── product-specs/      (PRDs)
│   ├── design-docs/        (technical designs)
│   ├── research/           (architecture & spike results)
│   └── exec-plans/         (plan, backlog, phase reports)
├── .github/workflows/      (CI)
├── docker-compose.yml      (local PostgreSQL)
├── AGENTS.md               (development workflow rules)
└── README.md
```

## Secrets

No credentials live in version control. Each `.env.example` documents the variables
its consumer reads, and every `.env` is gitignored:

| File | Consumed by |
|---|---|
| `.env.example` → `.env` | `docker-compose.yml` only |
| `backend/.env.example` → `backend/.env` | FastAPI settings and Alembic (`DATABASE_URL`) |
| `frontend/.env.example` → `frontend/.env` | Nuxt `runtimeConfig` (`NUXT_PUBLIC_API_BASE`) |

The committed defaults are development credentials on purpose. Never reuse them
anywhere reachable from outside the developer machine. Alembic reads its URL from
application settings, never from `alembic.ini`.

## Key Principles

1. **Document-driven architecture:** Orders → Operations → Movements → Settlements.
2. **Posted documents create immutable movements:** once posted, movements are append-only.
3. **Balance is aggregated from movements,** never a mutable `quantity` column.
4. **Idempotency & concurrency:** version tokens, idempotency keys, optimistic locking.
5. **Test-first, small increments:** Tracer Bullet, then vertical slices.
6. **Real PostgreSQL everywhere:** SQLite would not reproduce the locking semantics the
   posting transaction depends on.

## Roadmap (Phases)

1. **Repository scaffold & baseline** — done
2. **Identity & organizations** — auth, org scope, active org selection
3. **Catalog (products)** — CRUD with optimistic concurrency
4. **Goods receipt draft & edit** — document header and lines
5. **Posting** — idempotency, atomic batch + movement + audit
6. **Stock balance query** — aggregation from movements
7. **Concurrency & integration test matrix**

Later modules (sales, cash, PRRO, offline, multi-currency, POS) are explicitly out of
scope for the Tracer Bullet.

## Development Workflow

See [`AGENTS.md`](AGENTS.md):
CONTEXT → PRD → PLAN → ISSUES → RESEARCH → TRACER BULLET → TDD → VERIFICATION → COMMIT/PR → REVIEW

## License

*To be determined*
