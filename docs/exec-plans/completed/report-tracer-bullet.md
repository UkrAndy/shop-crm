# Tracer Bullet — Completion Report

**Date:** 2026-08-30 · **Scope:** Milestones 1–7, issues 1–26
**Related:** [`../active/plan-tracer-bullet.md`](../active/plan-tracer-bullet.md),
[`../active/backlog-tracer-bullet.md`](../active/backlog-tracer-bullet.md),
[`../../product-specs/prd-tracer-bullet-goods-receipt.md`](../../product-specs/prd-tracer-bullet-goods-receipt.md)

The first vertical slice is complete: **Organization → Product → Goods Receipt → Batch → Stock
Movement → Balance**, end to end through a browser.

Per-issue evidence lives under each issue in the backlog. This report says what was verified,
which commands produced the evidence, and — per `AGENTS.md` §12 — what could **not** be checked.

---

## 1. Definition of Done, item by item

| PRD requirement | Status | Evidence |
|---|---|---|
| User logs in, selects an organization, session persists | ✅ | `tests/test_auth.py`, `e2e/auth.spec.ts` (10 cases) |
| Creates a product with version safety | ✅ | `tests/test_products.py`, `test_products_concurrency.py` |
| Creates and edits a goods receipt draft | ✅ | `tests/test_goods_receipts_api.py`, `e2e/goods-receipts.spec.ts` |
| Posts it: batch + movement + audit, atomic and idempotent | ✅ | `tests/test_posting.py`, `test_posting_concurrency.py` |
| Sees a balance aggregated from movements | ✅ | `tests/test_stock_balance.py`, `e2e/tracer-bullet.spec.ts` |
| Idempotent posting: a replay creates no duplicate movement | ✅ | `test_posting.py::test_a_replay_returns_the_same_body_and_creates_nothing_more` |
| Concurrency matrix from research §6.7 | ✅ (reduced, as scoped) | §3 below |
| Stale-version draft edit → 409 | ✅ | `test_goods_receipts_api.py`, `test_concurrency_matrix.py` |
| Quality gates: lint, typecheck, tests, migration validation, build | ✅ | §2 below |
| No Out-of-Scope feature implemented | ✅ | §5 below |

**The executable proof** is `frontend/tests/e2e/tracer-bullet.spec.ts`. It logs in, creates a
product, drafts a receipt for 6 units, posts it, reads a balance of **6**, then drafts and posts a
second delivery of 4 and reads **10** — demonstrating that the number *aggregates* rather than
being overwritten, which is the whole difference between summing movements and storing a counter.

---

## 2. Verification commands and results

Run on 2026-08-30 against PostgreSQL 17.11 in Docker, Python 3.14, Node 24.19.

| Command | Result |
|---|---|
| `uv run ruff check .` | All checks passed (71 files) |
| `uv run ruff format --check .` | 71 files already formatted |
| `uv run pyright` | 0 errors, 0 warnings — **strict** mode |
| `uv run pytest` | **232 passed**, stable across 3 consecutive runs |
| `uv run alembic upgrade head` + `alembic check` | clean; 7 revisions; each downgraded and reapplied |
| `pnpm api:check` | contract and generated types reproduce byte-for-byte |
| `pnpm lint` / `pnpm typecheck` / `pnpm build` | clean / 0 errors / build complete |
| `pnpm test:e2e` | **26 passed** (Chromium, live stack) |
| GitHub Actions | three jobs — backend, frontend, e2e — green on every phase branch |

---

## 3. Concurrency matrix

Research §6.7 lists ten cases. Six are in scope for this slice; four concern sales, reservations
and serial numbers, which the PRD puts out of scope and which have no code to test.

| Case | Where | Result |
|---|---|---|
| Concurrent posts of the same receipt, **different** keys | `test_posting_concurrency.py` | one `posted`, one `receipt_not_draft`; 1 batch, 1 movement, 1 audit row |
| Concurrent posts of the same receipt, **same** key | same | one `posted`, one `replayed` with a byte-identical body; 1 movement |
| Concurrent posts of **different** receipts, same product | `test_concurrency_matrix.py` | both succeed; balance aggregates to 35 |
| Concurrent draft edits at the same expected version | same | one saves, one 409; document at version 2 |
| Concurrent product updates | `test_products_concurrency.py` | one wins, one `version_conflict`; version 2, not 3 |
| Stale read → post → re-query | `test_concurrency_matrix.py` | balance correct afterwards; a refused post moves nothing |
| Rollback after a failure partway through posting | `test_posting.py` | zero batches, zero movements, zero audit rows; document still a draft |
| Malformed payloads → 422 | products, receipts, posting suites | validated |
| Cross-organization → 403 | every scoped suite | validated |

**Not covered, because the feature does not exist:** two sellers competing for the final unit,
negative-stock policy, simultaneous reservations, IMEI allocation, and bounded retry after a
deadlock. All are sales-side; the PRD places them out of scope. Research's requirement is that
they be covered *before sales workflows are considered complete*, which remains true and unmet by
design.

**The tests are load-bearing, and that was demonstrated rather than asserted.** Three guards were
removed on purpose and the suites re-run:

| Guard removed | Consequence |
|---|---|
| `version_id_col` + the stale-client check on `Product` | both contention tests failed with `assert 2 == 1` — the lost update itself — while the concurrent-*creates* test stayed green, which is the right shape |
| `SELECT … FOR UPDATE` in `post_receipt` | the race test failed with `StaleDataError: UPDATE … expected to update 1 row(s); 0 were matched` |
| SSR cookie forwarding in `createApiClient` | two E2E tests failed; the "no login flash" guarantee is real |

Each was restored and confirmed byte-identical to `HEAD`.

**The workers genuinely overlap**, which is the claim every one of these tests rests on.
`test_concurrency_harness.py` makes the winner sleep 0.75 s while holding the row lock and asserts
that *both* workers took at least that long — the loser because it was blocked. A suite that
cannot demonstrate this is a set of sequential tests with threads in them.

---

## 4. Decisions that departed from the plan

Recorded here because a plan followed literally where it was wrong is worse than a plan amended
in the open.

| Decision | Why |
|---|---|
| **One batch and one movement per receipt line**, not "copy price, sum qty" per document | A batch is a quantity of one product at one price. Summing across lines would merge different goods and discard the price each arrived at — precisely what FIFO cost depends on later. The plan's wording only holds for a single-product delivery. |
| **Testcontainers was not used.** Postgres comes from `docker-compose.yml` locally and a GitHub Actions service container in CI | Research names Testcontainers and permits a service-container fallback *provided the choice is documented rather than silently downgraded* — this is that documentation. One `postgres:17-alpine`, pinned identically in both places, is simpler than a second container runtime inside the test process, starts once instead of per session, and needs no Docker socket access from pytest. Isolation is per test: a rolled-back transaction by default, and a throwaway organization for the suites that must commit. |
| **PrimeVue held at major 4**; **TypeScript pinned to 5.9** | The backlog and research specify PrimeVue 4; moving to 5 is a scope change. TypeScript 7 is the native rewrite and the typecheck gate should not ride a brand-new major. |
| **Generated types, not a generated SDK** | `openapi-fetch` and `@hey-api/openapi-ts` both replace the transport, and ours already carries SSR cookie forwarding. Types give contract enforcement without re-litigating the part that works. |
| **`VARCHAR` + `CHECK` instead of native `ENUM`** for statuses | `ALTER TYPE … ADD VALUE` cannot run inside a transaction block, which would make every future status an awkward migration. |
| **Test-only capabilities live in `backend/scripts/`, never as endpoints** | A route that posts a document, flips its status, or counts movements is a backdoor around the posting transaction. A debug flag guarding it only ships the backdoor with the flag. |

---

## 5. Out of scope — confirmed absent

Sales, returns, reservations, customer orders · cash operations, payments, settlements, PRRO ·
POS terminal · multi-currency · inter-warehouse transfers and negative-stock policy · full
counterparty module · serial/IMEI accounting · partial receipts against purchase orders · object
storage and attachments · offline mode · label printing · extended reporting · full RBAC ·
background queues and outbox.

Three of these are actively guarded by tests rather than merely unimplemented:
`test_the_counterparty_stub_stays_a_stub` pins the stub's exact column set,
`test_the_warehouse_holds_no_stock` and `test_no_product_row_holds_a_quantity` assert the absence
of any stored quantity, and `test_the_query_path_reads_no_stored_quantity` reads the balance
service's source to confirm the query never grew one either.

---

## 6. Known limitations and checks not run

Stated plainly, per `AGENTS.md` §12.

1. **Nothing is merged to `main`.** `origin/main` is still at `f5e732c` — documents only. All work
   lives on stacked branches `phase-1` … `phase-7`, each green in CI. `gh` is not authenticated on
   the development host, so the pull request must be opened in a browser.
2. **The 26 issues were never published to GitHub.** Same cause. The backlog file has been the
   source of truth throughout.
3. **No load or performance testing.** `ix_stock_movements_scope` exists and covers the balance
   aggregation, but no measurement was taken at any data volume. The balance is computed on
   demand; if that ever becomes slow, a materialised view is the intended next step, and the
   API contract was written so it can change without the client noticing.
4. **Cross-browser testing was not done.** Playwright runs Chromium only. Three engines would
   treble the runtime to re-test the same server-side behaviour; cross-browser rendering is a
   separate concern from these flows.
5. **No accessibility audit.** Labels and roles are present because Playwright selects by role,
   but no screen-reader or contrast testing was performed.
6. **Rate limiting on `/auth/login` is absent** and deliberately so — it belongs to a hardening
   pass with a shared throttling mechanism rather than a hand-rolled counter on one endpoint.
   `design-auth.md` §8 records it as a real gap.
7. **Supply chain.** `uv` has neither an Authenticode signature nor a PEP 740 attestation.
   `fastapi[standard]` pulls `sentry-sdk` transitively — inert without a DSN, but unaudited. On
   the npm side, `primevue` and `@primeuix/themes` have no SLSA attestation and no `repository`
   field; every other dependency added since does. `pnpm install` reports
   `Lockfile passes supply-chain policies`.
8. **Deletion, cancellation and unposting do not exist.** Deliberate — the PRD excludes them. One
   consequence is worth flagging: because `stock_movements` and `audit_log` are append-only at the
   database level, deleting an organization that has posted history now **fails**. That is correct
   for an audit trail and makes tenant removal a conscious operation, but it means there is no
   supported way to remove a tenant today.
9. **The `sessions` table is never pruned.** Expired rows accumulate. A periodic cleanup is
   trivial but has no scheduler to live in yet.

---

## 7. Constraints the next phase must not break

Carried forward from the backlog's resume section, because each was discovered the hard way:

- **The API must be same-site with the frontend.** Hosts are part of a *site*; ports are not.
  Pointing the frontend at `127.0.0.1` while the browser is on `localhost` silently breaks every
  login.
- **Nothing in the OpenAPI document may depend on the Python version.** `http.HTTPStatus` phrases
  are not stable across releases; a committed artifact that varies with the interpreter makes the
  drift check meaningless.
- **A collection change does not bump the parent's version.** Editing child rows must flag the
  parent dirty, or two users rewriting one document both win.
- **`now()` is the transaction timestamp.** Rows written together share it exactly, so it can
  never order them.
- **`ON DELETE RESTRICT` fires even inside a cascade** removing the referencing row.
- **Never assert a global row count in a test.** The concurrency suites commit real rows.
- **Anything driving an SSR page must wait for hydration** before typing.

---

## 8. Next

Phase 7 closes the Tracer Bullet. The natural successors, in the PRD's own terms, are sales and
the movement of stock *out* — at which point research §6.7's remaining four concurrency cases stop
being out of scope and become the first thing to write.
