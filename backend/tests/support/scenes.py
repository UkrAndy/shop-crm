"""Committed fixtures for tests that need real transactions.

The default `db_session` fixture wraps everything in a transaction that is
rolled back — the right choice almost everywhere, and useless for concurrency:
threads on separate connections cannot see each other's uncommitted work.

Everything here therefore **commits**, on a throwaway organization it deletes
afterwards.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import delete, text

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.catalog import Product
from app.models.counterparty import CounterpartyStub
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLine
from app.models.idempotency import IdempotencyRecord
from app.models.identity import Membership, Organization, User
from app.models.inventory import InventoryBatch, StockMovement, Warehouse
from app.services import inventory

APPEND_ONLY_TABLES = ("stock_movements", "audit_log")


class Scene(NamedTuple):
    organization_id: uuid.UUID
    user_id: uuid.UUID
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    receipt_id: uuid.UUID


def committed_draft(*, quantity: int = 10, price: str = "100.00") -> Scene:
    """A real, committed draft receipt with one line, on its own organization."""
    with SessionLocal() as session:
        organization = Organization(name=f"ФОП Гонка {uuid.uuid4()}")
        session.add(organization)
        session.flush()

        user = User(email=f"racer-{uuid.uuid4()}@example.com", password_hash=hash_password("x"))
        session.add(user)
        session.flush()
        session.add(Membership(user_id=user.id, organization_id=organization.id))

        warehouse = inventory.default_warehouse(session, organization)
        supplier = CounterpartyStub(organization_id=organization.id, name="ТОВ Гонка")
        product = Product(
            organization_id=organization.id,
            name="Кава",
            unit="шт",
            purchase_price=Decimal(price),
        )
        session.add_all([supplier, product])
        session.flush()

        receipt = GoodsReceipt(
            organization_id=organization.id,
            warehouse_id=warehouse.id,
            counterparty_id=supplier.id,
            created_by=user.id,
            lines=[
                GoodsReceiptLine(
                    product_id=product.id,
                    position=0,
                    quantity=quantity,
                    purchase_price=Decimal(price),
                )
            ],
        )
        session.add(receipt)
        session.commit()

        return Scene(
            organization_id=organization.id,
            user_id=user.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            receipt_id=receipt.id,
        )


def add_draft(scene: Scene, *, quantity: int, price: str = "100.00") -> uuid.UUID:
    """Another committed draft for the same product, so posts can be raced."""
    with SessionLocal() as session:
        supplier_id = session.scalar(
            text("SELECT id FROM counterparties_stub WHERE organization_id = :org LIMIT 1"),
            {"org": scene.organization_id},
        )
        receipt = GoodsReceipt(
            organization_id=scene.organization_id,
            warehouse_id=scene.warehouse_id,
            counterparty_id=supplier_id,
            created_by=scene.user_id,
            lines=[
                GoodsReceiptLine(
                    product_id=scene.product_id,
                    position=0,
                    quantity=quantity,
                    purchase_price=Decimal(price),
                )
            ],
        )
        session.add(receipt)
        session.commit()
        return receipt.id


def purge_organization(organization_id: uuid.UUID) -> None:
    """Remove everything a scene wrote, child rows first.

    Two things make this less trivial than a cascade:

    - Movements and audit rows are **append-only**: the trigger refuses
      `DELETE`, which is the point of it. Disabling it for the duration is a
      deliberate, table-owner operation confined to the test suite; production
      has no code path that reaches it.
    - Deleting the organization alone is not enough. `ON DELETE RESTRICT` fires
      even when the referencing row is itself being removed by the same cascade,
      so a receipt still pointing at its warehouse blocks the warehouse's
      removal. The order below is the dependency order, made explicit.
    """
    with SessionLocal() as session:
        for table in APPEND_ONLY_TABLES:
            session.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {table}_append_only"))
        session.commit()

    try:
        with SessionLocal() as session:
            actors = set(
                session.scalars(
                    text("SELECT created_by FROM goods_receipts WHERE organization_id = :org"),
                    {"org": organization_id},
                )
            )
            session.execute(
                text(
                    "DELETE FROM goods_receipt_lines WHERE receipt_id IN "
                    "(SELECT id FROM goods_receipts WHERE organization_id = :org)"
                ),
                {"org": organization_id},
            )
            for model in (
                StockMovement,
                AuditLog,
                InventoryBatch,
                IdempotencyRecord,
                GoodsReceipt,
                Product,
                CounterpartyStub,
                Warehouse,
            ):
                session.execute(delete(model).where(model.organization_id == organization_id))
            session.execute(delete(Organization).where(Organization.id == organization_id))
            # Users outlive the organization only because nothing references
            # them any more once the documents are gone.
            for actor in actors:
                session.execute(delete(User).where(User.id == actor))
            session.commit()
    finally:
        with SessionLocal() as session:
            for table in APPEND_ONLY_TABLES:
                session.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {table}_append_only"))
            session.commit()
