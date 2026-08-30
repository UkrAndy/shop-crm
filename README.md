# TestVasja — Inventory & Accounting System

A comprehensive inventory, warehouse, financial, and management accounting system with cash register and PRRO integration (Ukrainian fiscal receipt registrar).

## Project Status

- **Phase:** Pre-implementation (planning & research complete)
- **First Tracer Bullet:** Organization → Product → Goods Receipt → Batch → Stock Movement → Balance

## Documentation

- **Business Requirements:** `ТЗ_система_обліку_товару_версія_1_0.docx`
- **Architectural Baseline:** `docs/research/research-core-architecture.md`
- **First Tracer Bullet PRD:** `docs/product-specs/prd-tracer-bullet-goods-receipt.md`
- **Development Workflow:** `AGENTS.md`

## Technology Stack

### Frontend
- Nuxt 4, Vue 3 (TypeScript strict)
- PrimeVue 4 (UI components)
- TanStack Query (server state)
- Pinia (client state)
- Tailwind CSS 4
- Apache ECharts (reporting)

### Backend
- Python, FastAPI
- SQLAlchemy 2, Alembic (ORM & migrations)
- PostgreSQL, psycopg 3
- pytest, Testcontainers (testing)

### Infrastructure
- pnpm (JavaScript workspace)
- uv (Python environment)
- Docker Compose (local development)
- GitHub Actions (CI)

## Getting Started

### Prerequisites
- Node.js (with pnpm)
- Python 3.11+
- PostgreSQL 13+
- Docker & Docker Compose (for local services)

### Local Development Setup

*To be completed during implementation phase*

```bash
# Clone and setup
git clone <repo>
cd TestVasja

# Frontend
cd frontend
pnpm install
pnpm dev

# Backend
cd ../backend
uv venv
uv pip install -e .
fastapi dev

# Services (PostgreSQL, S3-compatible storage)
docker-compose up -d
```

## Project Structure

```
/
├── backend/              (FastAPI modular monolith)
├── frontend/             (Nuxt 4 SPA+SSR)
├── docs/
│   ├── product-specs/    (PRDs)
│   ├── design-docs/      (Technical designs)
│   ├── research/         (Architecture & spike results)
│   └── exec-plans/       (Implementation phases & issues)
├── infrastructure/       (Docker, CI/CD configuration)
├── AGENTS.md             (Development workflow rules)
├── .gitignore
└── README.md
```

## Key Principles

1. **Document-driven architecture:** Orders → Operations → Movements → Settlements
2. **Posted documents create immutable movements:** Once posted, movements are append-only
3. **Aggregate balance from movements:** Not a mutable `quantity` column
4. **Idempotency & concurrency:** Version tokens, idempotency keys, optimistic locking
5. **Test-first & small increments:** Tracer Bullet, then vertical slices

## Roadmap (Phases)

1. **Tracer Bullet:** Organization/User → Product → Goods Receipt → Batch → Stock Movement → Balance
2. **Inventory & Procurement:** Full goods receipt flow, partial receipts, supplier orders, returns
3. **Sales & Cash:** Sales documents, cash operations, payments, PRRO integration
4. **Finance & Reporting:** Analytics dashboard, cost accounting (FIFO), settlements
5. **Advanced Features:** Offline mode, multi-currency, advanced PRRO, label printing

## Development Workflow

See `AGENTS.md` for full workflow discipline, including:
- CONTEXT → PRD → PLAN → ISSUES → RESEARCH → TRACER BULLET → TDD → VERIFICATION → COMMIT/PR → REVIEW

## License

*To be determined*

## Contact

*To be determined*
