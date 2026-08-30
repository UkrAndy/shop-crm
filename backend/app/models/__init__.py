"""ORM model registry.

Every model module must be imported here so that `Base.metadata` is complete
when Alembic autogenerates or checks a migration. A model missing from this list
is a model CI believes does not exist.
"""

from app.models.audit import AuditLog
from app.models.catalog import Product
from app.models.counterparty import CounterpartyStub
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLine, ReceiptStatus
from app.models.identity import Membership, Organization, User, UserSession
from app.models.inventory import InventoryBatch, MovementType, StockMovement, Warehouse

__all__ = [
    "AuditLog",
    "CounterpartyStub",
    "GoodsReceipt",
    "GoodsReceiptLine",
    "InventoryBatch",
    "Membership",
    "MovementType",
    "Organization",
    "Product",
    "ReceiptStatus",
    "StockMovement",
    "User",
    "UserSession",
    "Warehouse",
]
