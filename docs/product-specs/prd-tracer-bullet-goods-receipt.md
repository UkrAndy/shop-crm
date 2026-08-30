# PRD: Tracer Bullet — Organization → Product → Goods Receipt → Batch → Stock Movement → Balance

## Goal

Довести наскрізну коректність document-driven архітектури найменшим корисним вертикальним зрізом: автентифікований користувач у контексті організації (ФОП) створює товар, створює й проводить надходження від постачальника, при проведенні атомарно створюються партія та рух товару, і користувач бачить актуальний залишок, порахований із рухів (не з мутабельної колонки). Перевіряє шлях UI → API → domain → persistence → response, включно з idempotency та optimistic concurrency.

## User scenarios

1. Користувач логіниться і обирає активну організацію (ФОП), у контексті якої працює.
2. Користувач створює картку товару з мінімальним набором полів.
3. Користувач створює чернетку надходження, додає рядки (товар, кількість, закупівельна ціна), вказує постачальника (мінімальна довідкова сутність).
4. Користувач проводить (posts) надходження. В одній транзакції створюються партія (batch) і рух товару (stock movement); документ стає immutable/posted.
5. Користувач переглядає залишок товару по складу — розрахований агрегацією рухів.
6. Проведений документ не редагується напряму — лише статус/подальші операції (скасування — поза цим PRD).
7. Повторне проведення з тим самим idempotency-key не створює дублікат руху.

## In Scope

- Organization/ФОП (мінімально) + перемикання активного контексту організації
- Один склад на організацію (без переміщень між складами)
- Автентифікація (email/пароль, сесія); єдина роль достатня для цього зрізу
- Мінімальний довідник товарів: internal ID, назва, штрихкод (опц.), одиниця виміру, закупівельна ціна
- Мінімальна довідкова сутність постачальника (лише назва/id — повний модуль контрагентів поза скоупом)
- Документ «Надходження»: draft → posted, рядки (товар, кількість — ціле, закупівельна ціна — копійки)
- Створення партії при проведенні (дата, постачальник, документ, ціна, кількість, залишок партії)
- Створення руху товару при проведенні (append-only, immutable)
- Запит залишку товару по складу (агрегація рухів, не колонка `quantity`)
- Idempotency-key обов'язковий для команди проведення
- Optimistic concurrency (`version`) на чернетці документа й товарі
- Базовий запис аудиту на дію проведення (актор, час, дія, сутність, старий/новий статус)
- Контракт помилок 409/422/403/401 як у research-документі
- SSR-фронтенд (Nuxt 4): логін, товари (список/створення), надходження (створення/редагування чернетки/проведення), перегляд залишку
- Лише базова валюта (UAH), цілі одиниці кількості, гроші — numeric/Decimal (копійки)

## Out of Scope

- Продажі, повернення, резервування, замовлення покупців
- Касові операції, оплати, взаєморозрахунки, ПРРО-фіскалізація
- POS-термінал, спрощений касовий інтерфейс продавця (`/pos`)
- Мультивалютність продажу, інтеграція курсу НБУ, ручне перевизначення курсу
- Переміщення між складами, політика від'ємних залишків і автокоригування при інвентаризації
- Повний модуль контрагентів (договори, статистика, кілька договорів на контрагента)
- Серійний облік / IMEI
- Часткові надходження проти замовлення постачальнику (сутності замовлення постачальнику ще немає)
- Object storage / вкладення до первинних документів
- Offline-режим
- Друк цінників/етикеток
- Розширена звітність/аналітична панель
- Повноцінний RBAC (кілька ролей) — лише один автентифікований користувач у цьому зрізі
- Фонові черги / transactional outbox

## Data / API / UI behavior

### Data model (мінімум)

```
organizations(id, name)
users(id, email, password_hash)
warehouses(id, organization_id, name)
products(id, organization_id, name, barcode, unit, purchase_price, version)
counterparties_stub(id, organization_id, name)
goods_receipts(id, organization_id, warehouse_id, counterparty_id, status[draft|posted], version, created_by, created_at)
goods_receipt_lines(id, receipt_id, product_id, quantity, purchase_price)
inventory_batches(id, organization_id, warehouse_id, product_id, receipt_id, purchase_price, quantity, remaining_quantity, received_at)
stock_movements(id, organization_id, warehouse_id, product_id, batch_id, quantity_delta, movement_type, document_id, created_at)
audit_log(id, organization_id, actor_id, action, entity_type, entity_id, old_value, new_value, created_at)
```

### API (представницький перелік)

```
POST /api/v1/auth/login
GET  /api/v1/organizations
POST /api/v1/organizations/active
POST /api/v1/products
GET  /api/v1/products
POST /api/v1/goods-receipts
PATCH /api/v1/goods-receipts/{id}          (version check)
POST /api/v1/goods-receipts/{id}/post      (Idempotency-Key required)
GET  /api/v1/stock-balance?product_id=&warehouse_id=
```

### UI (Nuxt 4, SSR)

```
/login
/products
/goods-receipts
/stock-balance
```

## Validation

- Кількість — додатне ціле число
- Закупівельна ціна — невід'ємна, numeric, точність копійки
- Не можна провести документ без рядків
- Не можна повторно провести вже проведений/скасований документ
- Розбіжність `version` при редагуванні/проведенні → 409

## Authorization / Security

- Усі ендпоінти вимагають автентифікації
- Перевірка приналежності користувача до організації (мінімальна; повна матриця прав — поза скоупом)
- Паролі — хешовані (bcrypt/argon2)
- Жодних публічних ендпоінтів, окрім `/auth/login`

## Error cases

- 401 — не автентифіковано
- 403 — порушення organization scope
- 404 — сутність не знайдена
- 409 — застаріла версія; документ уже проведений; конфлікт ідемпотентності з іншим payload
- 422 — помилка валідації (нульова кількість, порожні рядки)

## Technical constraints

- Backend: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, psycopg 3, pytest, Testcontainers (за research-документом)
- Frontend: Nuxt 4 (SSR), Vue 3, TypeScript strict, PrimeVue 4, TanStack Query, Pinia, Zod, згенерований OpenAPI TS-клієнт
- Гроші — PostgreSQL numeric / Python Decimal, ніколи float
- Проведення — одна транзакція (лок, перевірка версії, batch+movement+audit+status в одному commit)
- Без Redis/Celery/черг на цьому етапі

## Definition of Done

- Користувач логіниться, обирає організацію, створює товар, створює й проводить надходження, бачить коректний залишок — перевірено наскрізно (UI → API → DB → UI)
- Проведення ідемпотентне: повторний виклик з тим самим key не створює дубль руху — інтеграційний тест
- Тест конкурентного/повторного проведення (однаковий і різний idempotency-key) — за скороченою матрицею з research §6.7
- Редагування чернетки із застарілою версією повертає 409 — тест
- Проходять quality gates з research §10.1: lint, typecheck, тести, валідація міграцій, build
- Жодна фіча зі списку Out of Scope не реалізована
