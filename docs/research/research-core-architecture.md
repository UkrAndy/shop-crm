# Research: Core Architecture and Technology Stack

**Status:** Proposed baseline for review  
**Date:** 2026-08-30  
**Scope:** Repository organization, frontend architecture, backend architecture, persistence, API contract, testing, and infrastructure baseline  
**Source requirements:** `ТЗ_система_обліку_товару_версія_1_0.docx`, `vue_stack.md`, `ПРОМПРТ_ДЛЯ_CODEX.docx`, `AGENTS .md`

## 1. Purpose

This research establishes an architectural baseline for a web system covering product, inventory, procurement, sales, cash, payments, settlements, management reporting, audit, and future fiscalization through PRRO providers.

The goal is not to design every future module in advance. The goal is to select a structure that:

- supports a small, verifiable MVP;
- preserves transactional correctness;
- keeps business areas isolated;
- remains understandable as the product grows;
- supports automated testing and safe schema evolution;
- avoids premature microservices and unnecessary framework complexity.

No production scaffold or business feature is part of this research.

## 2. Repository observations

At the time of research, the workspace contains requirement and instruction documents only. It does not yet contain:

- a Git repository;
- frontend or backend applications;
- package-manager configuration;
- tests or CI configuration;
- a `docs/` knowledge structure;
- an agreed PRD or implementation plan.

The instruction file is currently named `AGENTS .md`. It was treated as an active repository instruction, but it should be renamed to `AGENTS.md` before development so agent tooling can discover it reliably.

## 3. Product and domain conclusions

### 3.1 The system is document-driven

The central flow is:

```text
Directory data
  -> Order
  -> Operational document
  -> Stock and/or cash movement
  -> Settlement entry
  -> Reporting
```

The product must not become a collection of unrelated CRUD tables. Documents and their links are the core of traceability.

### 3.2 Posted documents are the source of movements

- Draft documents do not affect physical stock or financial balances.
- Posting creates stock, payment, or settlement movements in one database transaction.
- Posted movement records should be immutable or append-oriented.
- Corrections should use cancellation, reversal, or compensating entries rather than silent edits.
- `products.quantity` must not be the authoritative stock balance.

### 3.3 Inventory and finance require strong concurrency control

Critical commands such as posting a receipt, posting a sale, allocating a payment, or cancelling a document require:

- an explicit transaction boundary;
- idempotency protection;
- state/version validation;
- database constraints;
- a defined locking or optimistic-concurrency strategy;
- an audit record;
- deterministic retry and conflict behavior.

### 3.4 Append-only ledgers are not Event Sourcing

The system should use immutable movement and settlement records, but full Event Sourcing is not recommended for the initial architecture. The operational document model remains the primary business model, while movements are durable accounting records produced by posted documents.

## 4. Recommended system shape

Use a single repository with two independently runnable applications:

```text
/
|- backend/
|- frontend/
|- docs/
|- infrastructure/
|- package.json
|- pnpm-workspace.yaml
|- .env.example
|- AGENTS.md
`- README.md
```

Recommended initial deployment shape:

```text
Browser
  -> Nuxt frontend
  -> REST API
  -> FastAPI modular monolith
  -> PostgreSQL
```

Microservices are not recommended initially. Domain boundaries should be enforced inside a modular monolith so modules can be separated later only when operational evidence justifies it.

## 5. Frontend decision

### 5.1 Selected stack

```text
Nuxt 4
Vue 3
TypeScript strict mode
PrimeVue 4
PrimeVue Forms
Tailwind CSS 4 for layout and local utilities
Apache ECharts with a Vue integration
TanStack Query for server state
Pinia for global client state
Zod for selected runtime/form validation
Vitest
Vue Test Utils
Nuxt Test Utils
Playwright
```

### 5.2 Frontend structure

Use standard Nuxt 4 directories and add domain modules under `app/domains`. Do not adopt full Feature-Sliced Design and do not create domain Nuxt Layers initially.

```text
frontend/
|- app/
|  |- assets/
|  |- components/
|  |  |- ui/
|  |  `- app/
|  |- composables/
|  |- domains/
|  |  |- identity/
|  |  |- organizations/
|  |  |- catalog/
|  |  |- counterparties/
|  |  |- procurement/
|  |  |- inventory/
|  |  |- sales/
|  |  |- finance/
|  |  `- reporting/
|  |- layouts/
|  |- middleware/
|  |- pages/
|  |- plugins/
|  |- stores/
|  |- utils/
|  |- app.vue
|  |- app.config.ts
|  `- error.vue
|- public/
|- test/
|- nuxt.config.ts
|- eslint.config.ts
|- vitest.config.ts
|- playwright.config.ts
|- tsconfig.json
`- package.json
```

Each domain owns its presentation and client-side data-access code:

```text
app/domains/catalog/
|- api/
|- components/
|- composables/
|- model/
|- stores/
|- utils/
|- test/
`- index.ts
```

This is a project-specific modular architecture built on standard Nuxt 4 behavior. `app/domains` is not an official Nuxt directory and receives no framework magic; files are consumed through explicit imports. That is intentional because it keeps dependencies visible.

### 5.3 Frontend dependency rules

- `app/pages` files remain thin route adapters.
- A domain exposes a public API through `index.ts`.
- Deep imports into another domain are prohibited.
- Global UI components do not depend on business domains.
- Components do not call the REST transport directly.
- Domain API functions are used by domain query/mutation composables.
- Cross-domain dependencies must be explicit and reviewed.
- Circular domain imports are prohibited and should be checked by ESLint.

### 5.4 State ownership

Use TanStack Query for:

- products and categories;
- documents and document lists;
- stock balances and movements;
- counterparties and settlements;
- payments and reports;
- caching, refetching, mutation state, and invalidation.

Use Pinia for:

- authenticated session state exposed to the UI;
- active organization or outlet;
- user interface preferences;
- saved table presentation settings;
- persistent POS workspace state when required.

Use local Vue state for component interactions and form drafts. Do not duplicate the same server resource in Pinia and TanStack Query.

### 5.5 REST transport

Do not add Axios by default. Use a generated OpenAPI client based on `fetch`/`ofetch`, with a centralized authentication and error-handling adapter.

Required behavior:

- one coordinated refresh operation for simultaneous `401` responses;
- retry the original request no more than once;
- never refresh on `403`;
- normalized API errors;
- request/correlation ID propagation where supported;
- abort support for cancelled searches and navigation.

### 5.6 UI library

PrimeVue 4 is selected as the primary UI component library because the product is dominated by data-heavy back-office workflows. Required capabilities include:

- server-driven tables;
- filtering, sorting, pagination, and row selection;
- virtual scrolling where justified;
- editable document lines;
- TreeTable and hierarchical selectors;
- overlays, dialogs, calendars, and file uploads;
- keyboard and accessibility support.

Use PrimeVue styled mode with a project-owned preset based initially on Aura or Nora. Use design tokens instead of widespread CSS overrides.

Create local wrapper components only where the product needs a stable project contract or shared behavior, for example:

- `AppDataTable`;
- `AppMoneyInput`;
- `AppQuantityInput`;
- `AppStatusBadge`;
- `AppConfirmDialog`.

Do not mechanically wrap every PrimeVue component.

### 5.7 Dashboards and charts

Use Apache ECharts for reporting visualizations rather than making PrimeVue's Chart.js wrapper the analytics foundation.

PrimeVue remains responsible for:

- dashboard filters;
- KPI cards;
- tables;
- dialogs;
- loading, empty, and error states.

ECharts is responsible for:

- sales trends;
- profit and margin;
- sales by category, seller, outlet, or organization;
- cash-flow visualizations;
- debt structure;
- inventory turnover;
- heatmaps, treemaps, funnels, gauges, or other advanced visualizations.

Chart components must share the same design tokens as PrimeVue. Every material chart should have an accessible textual summary or tabular alternative.

### 5.8 Rejected frontend alternatives

#### Full Feature-Sliced Design

Rejected as the default because the product's large workflows would be distributed across horizontal `entities`, `features`, `widgets`, and `pages` layers. Useful FSD principles such as thin pages, public APIs, and dependency boundaries are retained.

#### Domain Nuxt Layers from day one

Rejected initially because Layers introduce configuration, priority, routing, and auto-import complexity. A domain may later become a Nuxt Layer if it is reused across applications, independently owned, or requires its own Nuxt configuration.

#### Vuetify

Not selected because its Material Design direction is more opinionated than required for a dense accounting interface.

#### Nuxt UI

Not selected as the primary library because PrimeVue currently provides a stronger fit for advanced enterprise tables and hierarchical data. Nuxt UI remains a valid alternative for dashboard-centric products.

## 6. Backend decision

### 6.1 Selected stack

```text
Python
FastAPI
Pydantic 2
SQLAlchemy 2
Alembic
PostgreSQL
psycopg 3
pytest
Testcontainers
Ruff
Pyright
```

Use synchronous SQLAlchemy for the initial transactional core unless a technical spike demonstrates a concrete advantage for asynchronous database access.

### 6.2 Architectural style

Use a modular monolith with Clean Architecture / Ports and Adapters principles applied where domain complexity justifies them.

```text
HTTP router
  -> application use case
  -> domain model
  -> repository port
  -> SQLAlchemy adapter
  -> PostgreSQL
```

Recommended module boundaries:

```text
identity_access
organizations
catalog
counterparties
procurement
inventory
sales
payments
settlements
fiscalization
audit
reporting
```

Do not generate every future module at project creation. Add modules with the implementation phase that needs them.

### 6.3 Module structure

For complex domains:

```text
module/
|- domain/
|  |- entities/
|  |- value_objects/
|  |- services/
|  |- events/
|  `- exceptions/
|- application/
|  |- commands/
|  |- queries/
|  |- use_cases/
|  |- dto/
|  `- ports/
|- infrastructure/
|  |- persistence/
|  |- repositories/
|  `- integrations/
|- presentation/
|  `- http/
`- tests/
```

Simple reference-data modules may use a lighter structure. Architecture must follow complexity rather than forcing identical boilerplate everywhere.

### 6.4 Persistence rules

- SQLAlchemy models are persistence models, not automatically domain entities.
- Pydantic API schemas are not persistence models.
- Repositories operate on aggregate boundaries, not generic CRUD abstractions.
- Repositories must not commit independently.
- The application use case owns the transaction boundary through a Unit of Work.
- Production migrations use Alembic; automatic schema synchronization is prohibited.
- Monetary values use PostgreSQL `numeric` and Python `Decimal`, never binary floating point.
- Timestamps use timezone-aware values.
- Posted movements and audit events are immutable by application policy and database constraints where practical.

### 6.5 CQRS position

Use command/query separation conceptually, and introduce explicit command/query handlers for business-significant operations such as:

- posting receipts;
- posting sales;
- reserving stock;
- allocating payments;
- cancelling or reversing documents;
- closing a cash shift.

Do not create a handler hierarchy for trivial read-only reference-data endpoints unless it improves clarity or testability.

### 6.6 Background work and integrations

Do not add Redis, Celery, or another queue to the initial scaffold without a concrete background workflow.

When durable asynchronous processing is introduced, first implement a transactional outbox so database state and published work cannot diverge. PRRO, notifications, document generation, and external synchronization are likely future queue candidates.

### 6.7 CQRS and concurrent operations

CQRS is part of the proposed backend design, but CQRS alone does not solve concurrency. It separates state-changing commands from read queries; correctness under simultaneous actions must be enforced by PostgreSQL transactions, locking, version checks, idempotency, and database constraints.

Representative commands include:

```text
CreateSale
UpdateSaleDraft
ReserveStock
ReleaseReservation
PostSale
CancelSale
ChangeProductPrice
PostGoodsReceipt
```

Representative queries include:

```text
GetProduct
SearchProducts
GetAvailableStock
GetSaleDetails
GetStockMovements
GetProductHistory
```

The command side is authoritative. A value previously displayed by a query can be stale by the time a user submits a command, so every command must re-read and validate the required state inside its transaction.

#### Concurrent stock operations

If two sellers attempt to sell or reserve the same inventory position concurrently, the command must serialize access to the relevant inventory key rather than trusting the quantity shown in either browser.

The intended lock scope is narrow:

```text
organization_id + warehouse_id + product_id
```

Operations concerning different products or warehouses should not block one another. The final mechanism may use one or more of:

- `SELECT ... FOR UPDATE` on an inventory-position row;
- an atomic conditional `UPDATE`;
- PostgreSQL transaction-level advisory locks;
- optimistic version checks;
- unique and check constraints;
- `SERIALIZABLE` isolation for a small number of justified workflows.

Global `SERIALIZABLE` isolation is not recommended. Isolation and locking must be chosen per workflow and validated with concurrency tests.

#### Negative stock policy

The source specification allows negative stock. Therefore, the second concurrent sale does not always have to fail. The policy must explicitly determine whether negative stock is allowed by organization, warehouse, product, role, or operation type.

Even when negative stock is allowed, operations must remain sequential and auditable:

```text
initial stock 1
sale A movement -1 -> balance 0
sale B movement -1 -> balance -1
```

Both sales must not independently behave as though they were the first operation. A separate product decision is required for provisional cost and later FIFO correction when a sale occurs before a corresponding receipt batch exists.

#### Optimistic concurrency for mutable records

Mutable aggregates such as product cards and document drafts should carry an explicit `version` concurrency token.

Conceptual update:

```sql
UPDATE products
SET name = :name,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
```

An update affecting zero rows means the record changed after the client loaded it. The API should return `409 Conflict`; it must never silently apply last-write-wins behavior to business-critical records.

#### Concurrent document posting

Posting must be protected by all of the following:

- a transaction;
- a row lock or equivalent protection on the document;
- an expected status/version check;
- an idempotency key;
- a uniqueness constraint preventing duplicate posting operations;
- movement creation, audit, status change, and outbox writes in the same transaction.

Conceptual flow:

```text
BEGIN
  lock document
  verify expected version and postable status
  if already posted, return the existing result where idempotency permits
  create batches/movements/settlement entries
  write audit record
  change status to posted
  write outbox records
COMMIT
```

Two concurrent requests must never create duplicate movements.

#### Reservations

Available stock is conceptually:

```text
available = physical stock - active reservations
```

Reservation creation must atomically lock or conditionally update the relevant inventory position, recalculate availability, validate policy, and insert the reservation. A stale read-side projection must not authorize the reservation.

#### Serial numbers and IMEI

A serial number or IMEI must not be reserved or sold twice. Enforcement requires:

- uniqueness in the agreed organizational scope;
- explicit lifecycle transitions such as `available -> reserved -> sold`;
- locking or optimistic versioning during a command;
- database uniqueness constraints for active ownership/reservation links;
- a complete audit trail.

#### Price concurrency

A sale must persist the actual commercial facts used at posting time, including the final unit price, discount, price source/version, and actor. If a catalog price changes while a seller edits a sale, the product policy must choose between repricing, warning, explicit reconfirmation, or honoring the quoted price when the actor has permission.

#### Idempotency and retries

Commands with externally repeatable side effects must accept an idempotency key. This protects against double clicks, network retries, timeouts, and repeated job delivery.

A repeated request with the same key and command identity must return the stored outcome rather than creating a second movement or payment.

Deadlocks and serialization failures may be retried a small bounded number of times with backoff only when the command is demonstrably idempotent. Exhausted retries must produce a normalized technical error and correlation ID.

#### Read-side consistency

Read models may eventually be projections or materialized views and can be briefly stale. They are suitable for search, dashboards, and user display, but not as the final authority for posting, reservation, serial-number allocation, or payment allocation.

The command transaction must validate authoritative records immediately before mutation.

#### Required API conflict behavior

The API contract should distinguish:

```text
409 Conflict
  stale aggregate version
  document already posted or changed
  serial number already reserved/sold
  duplicate idempotency conflict

422 Unprocessable Entity
  current state violates a domain rule
  insufficient available stock under the active policy

403 Forbidden
  actor lacks permission for negative stock, price override, or cancellation
```

#### Required concurrency test matrix

Before sales and reservation workflows are considered complete, integration tests against real PostgreSQL must cover:

- two sellers posting sales for the final available unit;
- the same scenario with negative stock allowed and prohibited;
- simultaneous reservations for the final available unit;
- posting the same document twice with different and identical idempotency keys;
- simultaneous edits using the same expected document version;
- simultaneous sale/reservation of the same IMEI;
- receipt posting concurrent with a sale for the same inventory position;
- rollback after movement creation fails partway through posting;
- bounded retry after deadlock or serialization failure;
- read projection lag followed by authoritative command validation.

Detailed mechanics must be specified before implementing reservations or sales in:

```text
docs/design-docs/inventory-concurrency.md
```

## 7. API contract

FastAPI's OpenAPI document is the contract source for the frontend.

```text
Pydantic request/response schemas
  -> OpenAPI
  -> generated TypeScript client
  -> frontend domain API modules
  -> TanStack Query
```

Rules:

- Do not manually duplicate DTO definitions across Python and TypeScript.
- Generated client files are not edited manually.
- Contract generation must be reproducible in CI.
- Breaking API changes require deliberate versioning or coordinated migration.
- Error envelopes, pagination, filtering, sorting, and validation errors must be standardized before feature proliferation.

## 8. Authentication and authorization

The architecture should support:

- short-lived access credentials;
- secure refresh-token handling;
- role-based and permission-based authorization;
- organization/outlet scope checks;
- session/device audit data;
- explicit `401` versus `403` behavior.

The exact token transport and session-revocation design remain open and must be resolved in the identity/access PRD. Frontend route middleware improves user experience but never replaces API authorization.

## 9. Testing strategy

### 9.1 Frontend

- Unit tests for formatters, validation, query mapping, and composables.
- Component tests for forms, document lines, tables, and permission-aware controls.
- Integration tests for domain workflows with mocked REST boundaries.
- Playwright E2E tests for critical user journeys.

### 9.2 Backend

- Unit tests for domain rules and use cases.
- Repository integration tests against real PostgreSQL.
- Object-storage integration tests against a disposable S3-compatible service.
- API integration tests for validation, authorization, errors, and idempotency.
- Transaction/concurrency tests for posting and cancellation.
- Contract tests for the generated OpenAPI schema.

SQLite must not substitute for PostgreSQL in tests covering transactions, constraints, locking, numeric behavior, or PostgreSQL-specific queries.

Automated tests must never receive production AWS credentials or production bucket names. Unit tests use an in-memory/fake storage adapter; integration tests create disposable buckets in an isolated local S3-compatible container. Manual and acceptance testing may use a dedicated AWS S3 staging bucket with separate credentials and lifecycle rules.

### 9.3 Initial end-to-end business path

The first meaningful system test should eventually prove:

```text
Create organization/user context
  -> create product
  -> create and post goods receipt
  -> create batch and stock movement
  -> query resulting stock balance
```

This is the recommended Tracer Bullet because it validates identity scope, catalog, documents, transactions, batches, movements, API contracts, and frontend rendering without yet requiring sales, cash, or fiscalization.

## 10. Tooling and infrastructure baseline

Recommended workspace tooling:

```text
pnpm workspace for JavaScript/TypeScript
uv for Python environments and dependencies
Docker and Docker Compose for local services
GitHub Actions for CI when the repository host is confirmed
```

Initial local services should be limited to:

```text
frontend
backend
postgres
s3-compatible object storage (only when file workflows are exercised)
```

### 10.1 File and object storage

AWS S3 is the selected managed object store for production documents and images. PostgreSQL stores file metadata, ownership, authorization scope, status, checksum, and the S3 object reference; binary payloads must not be stored in ordinary database columns or on the backend instance filesystem.

The backend must depend on an application-level `ObjectStorage` port rather than AWS-specific calls inside domain services. The production adapter uses the S3 API. This preserves testability and allows local development to use a disposable S3-compatible service without changing business logic.

Environment isolation is mandatory:

```text
development -> local S3-compatible storage and synthetic files
test        -> disposable local bucket/container per test run
staging     -> dedicated AWS account or dedicated staging bucket and credentials
production  -> dedicated private AWS S3 buckets and least-privilege credentials
```

No environment may share writable buckets or credentials with production. Bucket names, AWS region, endpoint, and credentials are deployment configuration and must not be hard-coded.

Recommended separation by sensitivity and delivery model:

```text
private documents     -> invoices, contracts, source documents, generated private PDFs
private originals     -> original product and organization images
derived public media  -> approved thumbnails/optimized product images, if public access is required
temporary quarantine  -> uploads awaiting verification or malware scanning
```

These may be separate buckets or rigorously isolated prefixes initially, but production and non-production must always use separate buckets. All buckets are private by default. Public product media should be exposed only through an explicitly approved delivery path such as CloudFront; business documents must never receive permanent public URLs.

The database attachment record should include at least:

- `id`, `organization_id`, owner/entity reference, and purpose/category;
- bucket and immutable generated object key (never the raw user filename);
- original filename, detected media type, byte size, and SHA-256 checksum;
- upload status such as `pending`, `quarantined`, `available`, `rejected`, or `deleted`;
- S3 version identifier when versioning is enabled;
- uploader, timestamps, retention class, and optional image-variant metadata.

Recommended upload flow:

1. The frontend requests an upload intent from the backend.
2. The backend authorizes the organization/entity, validates declared type and size, generates a unique object key, and returns a short-lived presigned `PUT` URL.
3. The browser uploads directly to S3 without receiving AWS credentials.
4. The frontend calls finalize; the backend verifies object existence, actual size/type/checksum, and scanning status before marking the attachment available.
5. Only an `available` attachment may be linked to a finalized business document.

Small files may initially be streamed through the backend if that simplifies the first vertical slice, but the storage boundary and metadata model must remain the same. Presigned URLs are bearer capabilities and therefore must be short-lived, limited to one operation and one generated object key, and never written to logs.

Private downloads require backend authorization followed by a short-lived presigned `GET` URL. Highly sensitive downloads may instead be streamed through the backend when stronger audit or one-time access is required. Access to protected business documents must respect organization scope and be auditable.

Upload security requirements:

- allowlisted file types and explicit size/count limits by use case;
- server-side content detection rather than trusting extension or browser MIME type;
- checksum verification and collision-safe generated keys;
- quarantine and malware-scanning path for documents;
- reject or sanitize active formats such as SVG where appropriate;
- remove sensitive EXIF metadata and create bounded image variants asynchronously;
- TLS in transit, S3 server-side encryption, private bucket policies, and least-privilege IAM;
- no overwrite of posted-document attachments: corrections create a new attachment/version.

Enable S3 Versioning for production private-document buckets to improve recovery from accidental overwrite or deletion. Lifecycle policies should clean temporary uploads, expire abandoned multipart uploads, and transition or remove old noncurrent versions only according to an approved retention policy. S3 Object Lock/WORM should be enabled only after legal/fiscal retention requirements are confirmed because it intentionally prevents deletion or overwrite for the configured period.

S3 durability and versioning do not replace backup governance. The deployment design must define recovery objectives, an independent backup or replication boundary where required, database-to-object reconciliation, and periodic restore testing. Database soft deletion and asynchronous object cleanup should prevent dangling references and premature permanent deletion.

For images, retain the original privately and generate controlled thumbnails/optimized WebP or AVIF variants. Store each variant as a separate S3 object linked through metadata. CDN use is a delivery optimization and can be introduced when real traffic requires it; it must not alter authorization rules for private originals.

Recommended quality gates:

Frontend:

- ESLint;
- Prettier;
- `vue-tsc` / Nuxt typecheck;
- Vitest;
- Playwright where relevant;
- production build.

Backend:

- Ruff format and lint;
- Pyright;
- pytest;
- Alembic migration validation;
- application startup/health check.

## 11. Observability and audit baseline

The initial architecture should reserve standard integration points for:

- structured JSON logs;
- request/correlation IDs;
- health and readiness checks;
- error tracking;
- database query diagnostics;
- OpenTelemetry when operational requirements justify it.

Business audit is not the same as technical logging. Audit records must be durable domain data that identifies actor, time, action, entity/document, old/new values when appropriate, organization scope, and session/device context.

## 12. Security baseline

Before feature development, the implementation plan must cover:

- secret handling and `.env.example`;
- password hashing and account recovery;
- token/session revocation;
- rate limiting for sensitive endpoints;
- tenant/organization scoping;
- least-privilege permissions;
- upload type/size validation and malware strategy;
- private S3 buckets, least-privilege IAM, short-lived presigned URLs, encryption, and environment isolation;
- CORS and cookie policy;
- secure headers;
- prevention of mass assignment;
- audit access and retention;
- backup and restore testing.

Legal and fiscalization requirements are time-sensitive and must be verified separately before implementing PRRO behavior.

## 13. Major risks

### 13.1 Scope expansion

The source specification describes a long-term platform rather than a single MVP. Building all modules concurrently would prevent fast validation and increase integration risk.

### 13.2 Incorrect accounting semantics

FIFO, simultaneous receipts with average cost, negative stock, cancellation, reversal, payment allocation, multi-currency settlements, and cross-organization transfers require explicit business definitions before implementation.

### 13.3 Frontend over-abstraction

Creating all domain folders, wrappers, stores, and UI abstractions before the first workflow would produce speculative architecture. The target structure should be expanded only as working slices are added.

### 13.4 Reporting load

Operational screens and analytical reporting have different query needs. Reporting may eventually require read models, materialized views, or asynchronous projections, but these should be introduced only after real query and volume evidence.

### 13.5 Offline scope

Offline sales and synchronization introduce identity, conflict, inventory, fiscalization, and idempotency complexity. Offline behavior must remain outside the initial MVP until a separate design is approved.

## 14. Open questions requiring product decisions

1. Is the product single-company software with several organizations/FOPs, or future multi-tenant SaaS?
2. Can one user belong to multiple organizations, and can permissions differ per organization/outlet?
3. Is the scope management accounting only, or does it include statutory accounting requirements?
4. Can a posted document ever be edited, or only cancelled/reversed?
5. What precision is required for quantity, price, money, exchange rates, and cost?
6. What exactly constitutes a simultaneous receipt for average-cost treatment within FIFO?
7. Can users manually select a batch for sale, or is FIFO always mandatory?
8. How is cost assigned when negative stock is allowed and a sale occurs before a receipt?
9. Are exchange rates and exchange differences part of the MVP?
10. Which PRRO operations are required in the first fiscalized release?
11. What volumes are expected for products, documents per day, outlets, warehouses, and concurrent cashiers?
12. Is SSR required for this authenticated business application, or should the frontend operate primarily as a client-rendered application?
13. Must the POS continue working when the internet is unavailable, and for which exact operations?
14. What are the required retention periods for audit logs, documents, attachments, and fiscal data?
15. Which printing workflows are required in the first release?
16. At what scope can negative stock be enabled, and which roles may override the default policy?
17. What should happen to pricing and FIFO cost when another operation changes stock or price while a sale draft is open?
18. Which commands require idempotency keys in the first release?
19. Which AWS region and data-residency constraints apply to production files?
20. Which attachment categories may be publicly delivered, and which require audited private download?
21. Do any legal or fiscal documents require immutable WORM/Object Lock retention?

## 15. Recommended next artifacts

After approval of this research:

1. Create a narrowly scoped PRD for the first Tracer Bullet.
2. Resolve the open business rules required by that PRD.
3. Create `docs/design-docs/inventory-concurrency.md` before implementing stock reservations or sales.
4. Create `docs/design-docs/object-storage.md` before implementing production file uploads.
5. Create an implementation plan with independently verifiable phases.
6. Create the minimal repository scaffold and quality baseline.
7. Implement the first vertical slice test-first.

Recommended first PRD scope:

```text
Organization context
  + authenticated user
  + product catalog minimum
  + goods receipt draft/posting
  + inventory batch
  + stock movement
  + stock balance query and frontend screen
```

Out of scope for the first Tracer Bullet:

- sales and returns;
- cash and payments;
- settlements;
- PRRO;
- POS terminal integration;
- offline mode;
- label printing;
- advanced reporting;
- microservices;
- background queues.

## 16. Research sources

- Nuxt 4 directory structure: <https://nuxt.com/docs/4.x/directory-structure>
- Nuxt Layers: <https://nuxt.com/docs/4.x/directory-structure/layers>
- Nuxt data fetching: <https://nuxt.com/docs/4.x/getting-started/data-fetching>
- Nuxt custom API fetcher: <https://nuxt.com/docs/4.x/guide/recipes/custom-usefetch>
- PrimeVue Nuxt integration: <https://primevue.org/nuxt>
- PrimeVue theming: <https://primevue.org/theming/styled>
- Apache ECharts: <https://echarts.apache.org/en/>
- TanStack Query for Vue: <https://tanstack.com/query/latest/docs/framework/vue/overview>
- FastAPI larger applications: <https://fastapi.tiangolo.com/tutorial/bigger-applications/>
- FastAPI dependencies: <https://fastapi.tiangolo.com/tutorial/dependencies/>
- SQLAlchemy session and Unit of Work: <https://docs.sqlalchemy.org/en/20/orm/session_basics.html>
- SQLAlchemy transaction management: <https://docs.sqlalchemy.org/en/20/orm/session_transaction.html>
- Amazon S3 pricing and Free Tier: <https://aws.amazon.com/s3/pricing/>
- Amazon S3 presigned uploads: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html>
- Amazon S3 Versioning: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html>
- Amazon S3 lifecycle management: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html>
- Amazon S3 Object Lock: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html>

## 17. Decision summary

| Area | Decision |
| --- | --- |
| Repository | Single repository, separate `frontend` and `backend` applications |
| Frontend framework | Nuxt 4, Vue 3, strict TypeScript |
| Frontend architecture | Standard Nuxt directories plus explicit `app/domains` modules |
| UI | PrimeVue 4 styled mode with a project preset |
| Charts | Apache ECharts |
| Server state | TanStack Query |
| Client state | Pinia |
| Backend framework | FastAPI modular monolith |
| Persistence | SQLAlchemy 2, Alembic, PostgreSQL, psycopg 3 |
| Documents and images | Private AWS S3 object storage; metadata and relations in PostgreSQL |
| File access | Authorized short-lived presigned URLs; no permanent public document URLs |
| File testing | Fake adapter for unit tests; disposable S3-compatible storage for integration tests; isolated AWS S3 staging bucket for acceptance tests |
| Commands and reads | Pragmatic CQRS with authoritative transactional command validation |
| Concurrency | Narrow inventory locks, optimistic versions, idempotency, constraints, PostgreSQL concurrency tests |
| API contract | OpenAPI-generated TypeScript client |
| Initial distributed architecture | None; no microservices or queue without evidence |
| First vertical slice | Organization/user -> product -> posted receipt -> batch/movement -> balance |
