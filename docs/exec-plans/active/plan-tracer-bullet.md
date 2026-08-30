# Implementation Plan: Tracer Bullet — Organization → Product → Goods Receipt → Batch → Stock Movement → Balance

**Status:** Draft (skeleton for detailing in next phase)  
**Date:** 2026-08-30  
**Related:** `docs/product-specs/prd-tracer-bullet-goods-receipt.md`, `docs/research/research-core-architecture.md`

## Overview

Implement the first end-to-end vertical slice proving document-driven architecture: authenticated user in organization context creates product, creates and posts goods receipt, receives batch and stock movement creation, views calculated stock balance.

This plan breaks the PRD into **7 sequential phases**, each producing a working increment. Phases 1–3 establish scaffold and prerequisites; phases 4–7 build the core workflow.

## Phase 1: Repository Scaffold & Baseline

**Goal:** Initialize backend and frontend applications with minimal working structure, quality gates, local dev environment, and database connectivity.

**Deliverables:**
- Backend: FastAPI app skeleton, SQLAlchemy ORM structure, Alembic migrations, pytest setup
- Frontend: Nuxt 4 setup (SSR mode), TypeScript config, PrimeVue integration, build working
- Docker Compose: PostgreSQL, local S3-compatible storage (minio for later)
- CI/CD: GitHub Actions workflow for lint, typecheck, test, build
- `.env.example` and secret handling baseline

**Tasks:**
1. Create `backend/` structure: main.py, requirements.txt, pyproject.toml, uv venv setup
2. Create `frontend/` structure: package.json (pnpm), nuxt.config.ts, tsconfig.json
3. Add FastAPI health check endpoint
4. Add Nuxt welcome page (SSR mode verification)
5. Create docker-compose.yml with PostgreSQL and services
6. Verify build/run locally: `pnpm dev` (frontend), `fastapi dev` (backend)
7. Set up GitHub Actions: lint (ruff, eslint), typecheck (pyright, vue-tsc), test, build
8. Document local setup in README.md

**Acceptance:** Both apps run locally, quality gates pass, database connections work.

---

## Phase 2: Identity & Organizations

**Goal:** Implement authentication (email/password), session management, organization scope, and active organization selection. Establish foundation for all subsequent features.

**Deliverables:**
- User model, password hashing (argon2), session/token strategy
- Organization model and user-org association
- Login endpoint, auth middleware, scope checks
- Frontend login page, org selector, session state (Pinia)
- API error contracts (401, 403)

**Tasks:**
1. Design auth strategy (JWT refresh token or session cookie) and document
2. Backend: User & Organization models, Alembic migration
3. Backend: POST /api/v1/auth/login endpoint with validation
4. Backend: Auth middleware, scope-check decorator
5. Backend: GET /api/v1/organizations, POST /api/v1/organizations/active endpoints
6. Frontend: Login page (email, password), submit to backend
7. Frontend: Org selector component, active org persistence (Pinia + localStorage)
8. Integration test: login flow, org selection, scope validation
9. E2E test (Playwright): login and navigate to org selector

**Acceptance:** User can log in, select org, requests include org context, scope violations return 403.

---

## Phase 3: Catalog (Products) Minimum

**Goal:** Implement product CRUD with minimal fields, version concurrency, and validation. Establish patterns for mutable aggregates.

**Deliverables:**
- Product model: id, organization_id, name, barcode (optional), unit, purchase_price, version
- POST/GET/PATCH endpoints with version check (409 on conflict)
- Product list UI with filtering, creation form

**Tasks:**
1. Backend: Product model with version token, Alembic migration
2. Backend: POST /api/v1/products (create), GET /api/v1/products (list), PATCH /api/v1/products/{id} (update)
3. Backend: Version mismatch returns 409 Conflict
4. Frontend: Products list page (PrimeVue DataTable)
5. Frontend: Create product form, edit form with version handling
6. Frontend: Show 409 conflict UI (reload & retry pattern)
7. Unit test: Product creation, update with version checks
8. Integration test: Concurrent updates on same product

**Acceptance:** Create/list/update products; version conflicts detected; list page displays products with sorting/filtering.

---

## Phase 4: Goods Receipt — Draft & Edit

**Goal:** Implement goods receipt document creation and draft editing. Establish document structure and line item patterns.

**Deliverables:**
- GoodsReceipt model: id, organization_id, warehouse_id, counterparty_id, status (draft|posted), version, created_by, created_at
- GoodsReceiptLine model: id, receipt_id, product_id, quantity, purchase_price
- POST (create), PATCH (edit lines), GET (retrieve) endpoints with version checks
- Frontend: Create receipt form, add/edit/remove lines, save as draft

**Tasks:**
1. Backend: GoodsReceipt & GoodsReceiptLine models, warehouse stub (default warehouse per org), counterparty_stub table, Alembic migrations
2. Backend: POST /api/v1/goods-receipts (create draft), GET /api/v1/goods-receipts/{id} (retrieve), PATCH /api/v1/goods-receipts/{id} (update draft lines)
3. Backend: Validation: cannot update if status != draft; version mismatch → 409; empty lines → 422
4. Frontend: Goods receipts list page
5. Frontend: Create receipt flow: select counterparty, add lines (product picker, qty, price), save draft
6. Frontend: Edit receipt lines (inline or modal), delete lines
7. Frontend: Show document status, created_by, created_at
8. Integration test: Create receipt, edit lines, version conflicts
9. E2E test: Create draft receipt, add multiple lines, save

**Acceptance:** Draft receipt persists, lines editable, version conflicts detected, UI shows counterparty & lines clearly.

---

## Phase 5: Post Goods Receipt — Idempotency & Atomic Movements

**Goal:** Implement receipt posting (status draft → posted) with idempotency, concurrency safety, and atomic creation of batch + movements + audit in one transaction.

**Deliverables:**
- InventoryBatch model: id, organization_id, warehouse_id, product_id, receipt_id, purchase_price, quantity, remaining_quantity, received_at
- StockMovement model: id, organization_id, warehouse_id, product_id, batch_id, quantity_delta, movement_type (receipt|sale|...), document_id, created_at
- AuditLog model: id, organization_id, actor_id, action, entity_type, entity_id, old_value, new_value, created_at
- POST /api/v1/goods-receipts/{id}/post endpoint (Idempotency-Key required, transaction-scoped)
- Transaction behavior: lock receipt row, verify status=draft & version, check for duplicate idempotency key, create batch, create movement, update status, write audit, commit atomically

**Tasks:**
1. Backend: InventoryBatch, StockMovement, AuditLog models, Alembic migrations
2. Backend: Idempotency key table/mechanism (track posted receipt + key → result)
3. Backend: POST /api/v1/goods-receipts/{id}/post handler with transaction & locking
4. Backend: Verify status=draft, version match, non-empty lines; else return 422/409
5. Backend: Create batch from receipt (copy price, sum qty)
6. Backend: Create movement (qty_delta = sum of line quantities, movement_type=receipt, batch_id, document_id=receipt_id)
7. Backend: Update receipt status=posted, increment version
8. Backend: Write audit record (actor=user, action=posted_receipt, entity_id=receipt_id, old_status=draft, new_status=posted)
9. Backend: On idempotency-key replay, return 200 with stored result (no duplicate movements)
10. Frontend: POST button on receipt detail, disable after post
11. Frontend: Handle 409/422 errors, show message
12. Integration test: Post receipt, verify batch & movement created, status changed
13. Integration test: Replay post with same idempotency-key, verify no duplicate movement
14. Integration test: Concurrent posts on same receipt (one wins, one gets 409)

**Acceptance:** Posting is atomic, idempotent, concurrency-safe; batch and movement created correctly; audit recorded; replay-safety verified.

---

## Phase 6: Stock Balance Query & UI Display

**Goal:** Implement stock balance calculation (sum movements by product/warehouse) and frontend display. Prove aggregation from immutable movements, not mutable quantity column.

**Deliverables:**
- GET /api/v1/stock-balance?product_id=X&warehouse_id=Y endpoint
- Returns: product_id, warehouse_id, quantity_balance (sum of movements), last_movement_date
- Frontend: Stock balance page, optional filter by product/warehouse, display in a table or card

**Tasks:**
1. Backend: Query endpoint: SELECT SUM(quantity_delta) FROM stock_movements WHERE product_id=? AND warehouse_id=? (calculate on-demand or materialized view; start with on-demand)
2. Backend: Include organization scope check
3. Backend: Return 404 if no product or no movements
4. Frontend: Stock balance page, optional product selector
5. Frontend: Display table: Product | Warehouse | Quantity | Last Movement Date
6. Integration test: Post receipt, query balance, verify correct sum
7. Integration test: Post multiple receipts for same product, verify sum aggregates
8. E2E test: Post receipt, navigate to balance page, verify displayed quantity matches

**Acceptance:** Balance reflects sum of all movements; no mutable quantity column was used; UI displays clearly.

---

## Phase 7: Concurrency & Integration Tests (Test Matrix)

**Goal:** Verify concurrency behavior under contention: simultaneous posts, stale reads, version conflicts, idempotency correctness. Implement test matrix from research §6.7.

**Tests (representative, not exhaustive):**
- Two sellers post receipts for same product concurrently → both succeed (different documents), totals aggregate correctly
- Concurrent edits of draft receipt with mismatched versions → one succeeds (409 other)
- Concurrent posts of same receipt with identical idempotency-key → one succeeds, other returns stored result (no duplicate movement)
- Concurrent posts of same receipt with different idempotency-keys → both succeed independently (idempotency-key is per-command, not per-receipt)
- Read stale product balance, then post receipt, re-query → balance updates correctly
- Malformed requests (missing lines, negative qty, invalid product) → return 422 with clear error
- Unauthorized org access (user from org A tries to post receipt in org B) → return 403

**Tasks:**
1. Backend: Set up Testcontainers for real PostgreSQL in pytest
2. Backend: Write concurrent test helper (spawn threads, collect results)
3. Backend: Implement 5–7 concurrency test cases from matrix
4. Backend: Implement 3–4 error case tests (malformed, unauthorized)
5. Frontend: Playwright concurrent login & action tests (if relevant)
6. Document test results, known limitations

**Acceptance:** All concurrency tests pass; error cases handled correctly; no race conditions observed.

---

## Definition of Done (Full PRD Coverage)

- ✅ User authenticates, selects organization, persists session
- ✅ User creates product (CRUD with version safety)
- ✅ User creates & edits goods receipt (draft lines)
- ✅ User posts receipt (atomic: batch + movement + audit, idempotent, concurrency-safe)
- ✅ User queries stock balance (aggregation from movements, not mutable column)
- ✅ Concurrency test matrix passes (simultaneous posts, version conflicts, idempotency)
- ✅ Quality gates pass: lint, typecheck, all tests, build
- ✅ No out-of-scope features implemented (sales, cash, PRRO, offline, multi-currency, POS)
- ✅ Documentation: phase-by-phase verification, test coverage report, known issues

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| SSR complexity (Nuxt 4) | Hydration issues, auth context | Early E2E test; consider CSR fallback if blocking |
| PostgreSQL concurrency unfamiliar | Deadlocks, serialization failures | Thorough locking tests; start with `SELECT ... FOR UPDATE` |
| Idempotency-key correctness | Duplicate movements on retry | Write test that replays exact request multiple times |
| OpenAPI client generation lag | Frontend blocked on API changes | Generate early; update on breaking changes |

---

## Timeline Estimate

Assuming ~1–2 person-weeks per phase:
- Phase 1: 1 week (setup, baseline)
- Phase 2: 3–4 days (auth, straightforward)
- Phase 3: 3–4 days (products, familiar CRUD)
- Phase 4: 3–4 days (receipt draft, document structure)
- Phase 5: 1 week (posting, concurrency, idempotency — most complex)
- Phase 6: 2–3 days (balance query, aggregate)
- Phase 7: 3–4 days (concurrency tests, edge cases)

**Total: ~4–5 weeks** (can be compressed with parallel work on frontend/backend).

---

## Next Steps (After This Plan Approval)

1. Create GitHub issues/milestones for each phase
2. Assign initial work to Phase 1 (scaffold)
3. First commit: empty backend/ and frontend/ folders with minimal configs
4. Track progress in `docs/exec-plans/completed/` as phases finish
5. Escalate blockers or scope changes immediately
