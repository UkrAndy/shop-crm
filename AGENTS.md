# AGENTS.md — Agentic Development Workflow

## Purpose
This repository is developed with a controlled agentic workflow.

Do not treat a user request as permission to implement the whole product.
Work in small, verifiable increments.

Core workflow:

CONTEXT → PRD → PLAN → ISSUES → RESEARCH → TRACER BULLET → TDD → VERIFICATION → COMMIT/PR → REVIEW

## 1. Instruction priority
Before changing code:

1. Read this `AGENTS.md`.
2. Read any more specific `AGENTS.md` / `AGENTS.override.md` that applies to the target directory.
3. Read the relevant source-of-truth documents in `docs/`.
4. Inspect existing code patterns before introducing a new pattern.
5. Read the task/issue acceptance criteria.

Never rely on memory from a previous task when the repository contains current written instructions.

## 2. Repository knowledge map
Prefer this structure when present:

```text
AGENTS.md
ARCHITECTURE.md
docs/
  product-specs/
  design-docs/
  research/
  exec-plans/
    active/
    completed/
```

Treat `AGENTS.md` as a concise map, not an encyclopedia.
Keep detailed requirements and technical decisions in `docs/`.

### Key decision pointers (as of 2026-08-30)
- **Authentication:** `docs/design-docs/design-auth.md` — opaque server-side session token in an HTTP-only `SameSite=Lax` cookie, stored hashed in `sessions`; 8h idle / 30d absolute; Argon2id via `argon2-cffi`. Chosen over JWT because SSR needs a server-readable credential and research §8 requires revocation. Also fixes the 401/403/404/409/422 contract and the CSRF posture (SameSite + JSON-only mutations — a double-submit token becomes mandatory if either falls).
- **Persistence conventions:** UUID primary keys (not sequential integers — they leak volume across tenants), `timestamptz` everywhere, money as `numeric`/`Decimal`. New models register in `app/models/__init__.py` or `alembic check` will not see them.
- **First Tracer Bullet PRD:** `docs/product-specs/prd-tracer-bullet-goods-receipt.md` — Organization → Product → Goods Receipt → Batch → Stock Movement → Balance. Covers identity/scope, catalog minimum, receipt draft/posting, inventory batch, stock movement, and balance query. Out of scope: sales, cash, PRRO, offline mode, multi-currency, POS interface.
- **Architectural baseline:** `docs/research/research-core-architecture.md` — proposes Nuxt 4 + Vue 3 + PrimeVue frontend, FastAPI + SQLAlchemy backend, PostgreSQL, modular monolith, optimistic concurrency with version tokens, idempotency keys, append-only movements. 21 open business questions, resolved in PRD (offline deferred, SSR required, single-company multi-FOP scope, base currency UAH, idempotency for posting, decimal precision for quantities and prices).
- **Business specification:** `ТЗ_система_обліку_товару_версія_1_0.docx` — Ukrainian ERP spec: 57 sections covering product/warehouse/finance/cash accounting, PRRO integration, batch accounting, FIFO cost, negative stock allowed, document linking, user roles, audit, and future modules.

## 3. Scope discipline
For every task, determine:

- Context
- Exact task
- In Scope
- Out of Scope
- Acceptance Criteria
- Verification method

Do not:
- add unrelated features;
- refactor unrelated modules;
- add dependencies without clear justification;
- change public contracts unless the task requires it;
- silently expand the scope.

If a requirement is ambiguous and materially affects architecture or behavior, ask a concise clarification before implementation.

## 4. New project workflow
For a new/empty repository, do not start with business features.

First establish:
1. product goal and MVP boundaries;
2. architecture and repository structure;
3. minimal scaffold;
4. local development environment;
5. test/lint/typecheck/build baseline;
6. `.env.example` and secret handling;
7. `AGENTS.md` and `docs/` structure;
8. initial Git/CI workflow.

The scaffold must build/run before feature development begins.

## 5. PRD workflow
Before a non-trivial feature, create or update a PRD in:

`docs/product-specs/prd-<feature>.md`

A PRD should contain:

- Goal
- User scenarios
- In Scope
- Out of Scope
- Data/API/UI behavior as applicable
- Validation
- Authorization/security
- Error cases
- Technical constraints
- Definition of Done

Do not write production code while the task is explicitly to create the PRD.

## 6. Planning workflow
Create an implementation plan in:

`docs/exec-plans/active/plan-<feature>.md`

Rules:
- split work into independent phases;
- each phase must produce a working result;
- Phase 1 should be the smallest end-to-end Tracer Bullet;
- prefer 3–5 concrete tasks per phase;
- include tests/verification in each phase;
- cover all PRD Definition of Done items;
- do not invent features absent from the PRD.

## 7. Issues and milestones
When GitHub task tracking is requested/available:

- map each phase to a milestone;
- map each concrete task to an issue;
- each issue should include:
  - Context
  - Scope
  - Acceptance Criteria
  - Relevant modules/files
  - Tests / verification
  - Out of Scope when useful

Do not start implementation if the user asked only for backlog creation.

## 8. Research phase
For architecture-sensitive or unfamiliar work, research before coding.

Create:

`docs/research/research-<feature>.md`

Research should answer:
- which existing repository patterns should be reused;
- which files/modules will change;
- which new files are necessary;
- library/framework choices already present in the repo;
- data model / API implications;
- authorization/security implications;
- risks and edge cases;
- testing and verification approach.

Research is not production code.

After research, add only a short pointer from `AGENTS.md` if the decision is important for future tasks.

## 9. Tracer Bullet
The first implementation phase should prove the end-to-end path with the smallest useful slice.

Example:

UI → API → service/domain → persistence → response in UI

Do not add polish or adjacent features until the vertical path works and is verified.

## 10. TDD / test-first behavior
When the repository supports tests and the task is testable:

1. Write or identify a failing test that captures the requested behavior.
2. Run it and confirm RED.
3. Implement the minimum change.
4. Run the test and reach GREEN.
5. Refactor without changing behavior.
6. Re-run relevant tests.

For bug fixes, add a regression test whenever practical.

If test-first is not practical, state why and use the strongest available verification.

## 11. Error-fix protocol
When fixing a bug, reason from:

- full error message;
- reproduction context;
- Expected behavior;
- Actual behavior.

Fix the root cause, not merely the symptom.
Avoid blanket try/catch, ignored errors, weakened validation, or disabled tests unless explicitly justified.

## 12. Verification gate
Never claim completion without evidence.

Before finishing a code task:

1. Inspect repository scripts/config to determine real commands.
2. Run relevant tests.
3. Run lint if configured.
4. Run typecheck if configured.
5. Run build if relevant/configured.
6. Run integration/E2E/browser checks for user-facing flows when available.
7. Inspect `git diff` / changed files for scope creep.
8. Report any check you could not run.

Do not invent commands that are not configured in the repository.

## 13. Browser/UI feedback
For UI work, verify the actual user flow when browser automation is available.

Typical checks:
- happy path;
- invalid input;
- loading state;
- error state;
- persistence after reload;
- authorization behavior;
- responsive layout where relevant.

If given a screenshot:
- treat it as concrete visual feedback;
- fix only the described defect unless broader changes are required;
- re-check the page after the fix.

## 14. Dependencies
Before adding a dependency:
- check whether the repository already has a suitable library;
- explain why the new dependency is needed;
- prefer mature, maintained packages;
- avoid adding a package for trivial functionality.

Do not upgrade unrelated dependencies as part of a feature task.

## 15. Git discipline
Prefer:
- one feature/phase branch;
- small logical commits;
- no secrets;
- no generated junk unless expected by the repo;
- commit message that matches actual scope.

Before a commit/PR, inspect:
- `git status`;
- `git diff`;
- verification results.

## 16. Pull Request standard
A PR should include:

- Summary
- Linked issue/milestone when available
- What changed
- Verification performed
- Tests added/updated
- Screenshots for UI changes
- Known limitations / Out of Scope

Do not include work from the next phase in the current PR.

## 17. Code review mode
When asked to review code:

Do not automatically rewrite the code first.

Report findings by severity:
- Critical
- Major
- Minor

Check:
- correctness;
- security/auth;
- architecture boundaries;
- data integrity;
- missing tests;
- edge cases;
- unnecessary dependencies;
- maintainability;
- scope creep.

Only apply fixes when explicitly asked or when the active task includes fixing review findings.

## 18. Completion response
At the end of a task, report concisely:

- what was changed;
- key files;
- verification commands/results;
- unresolved risks or checks not run;
- next logical phase only if useful.

Do not say “done” if required acceptance criteria or checks are failing.

## 19. Default prompt interpretation
If the user gives a broad feature request without a plan:

- for a small, local change: inspect → plan briefly → implement → verify;
- for a multi-layer or multi-day feature: propose PRD/plan/research first;
- for architecture-sensitive work: research before implementation;
- for a new project: establish scaffold and quality baseline first.

## 20. Golden rule
Do not optimize for the amount of code written.

Optimize for:
- correct scope;
- explicit requirements;
- reuse of repository conventions;
- fast feedback;
- verifiable behavior;
- small reviewable changes;
- durable documentation.
