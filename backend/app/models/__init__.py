"""ORM model registry.

Every model module must be imported here so that `Base.metadata` is complete
when Alembic autogenerates or checks a migration. A model missing from this list
is a model CI believes does not exist.
"""

from app.models.catalog import Product
from app.models.counterparty import CounterpartyStub
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLine, ReceiptStatus
from app.models.identity import Membership, Organization, User, UserSession
from app.models.inventory import Warehouse

__all__ = [
    "CounterpartyStub",
    "GoodsReceipt",
    "GoodsReceiptLine",
    "Membership",
    "Organization",
    "Product",
    "ReceiptStatus",
    "User",
    "UserSession",
    "Warehouse",
]
