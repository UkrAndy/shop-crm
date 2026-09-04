"""Issue 23 — the stock balance query.

Acceptance criteria under test:
- balance equals the sum of `quantity_delta` across all posted receipts;
- no mutable quantity column is read anywhere in the query path;
- a cross-organization query returns 403.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from tests.conftest import LoggedIn

BALANCE = "/api/v1/stock-balance"
RECEIPTS = "/api/v1/goods-receipts"
PRODUCTS = "/api/v1/products"
COUNTERPARTIES = "/api/v1/counterparties"


def make_product(client: TestClient, name: str) -> dict[str, Any]:
    response = client.post(PRODUCTS, json={"name": name, "unit": "шт", "purchase_price": "100.00"})
    assert response.status_code == 201, response.text
    return response.json()


def some_supplier(client: TestClient) -> dict[str, Any]:
    existing = client.get(COUNTERPARTIES).json()
    if existing:
        return existing[0]
    response = client.post(COUNTERPARTIES, json={"name": "ТОВ Постачальник"})
    assert response.status_code == 201, response.text
    return response.json()


def post_receipt(client: TestClient, product_id: str, quantity: int, key: str) -> None:
    """Create a draft with one line and post it — the only way stock exists."""
    draft = client.post(
        RECEIPTS,
        json={
            "counterparty_id": some_supplier(client)["id"],
            "lines": [{"product_id": product_id, "quantity": quantity, "purchase_price": "100.00"}],
        },
    )
    assert draft.status_code == 201, draft.text
    body = draft.json()

    posted = client.post(
        f"{RECEIPTS}/{body['id']}/post",
        json={"version": body["version"]},
        headers={"Idempotency-Key": key},
    )
    assert posted.status_code == 200, posted.text


def balance_of(client: TestClient, product_id: str) -> dict[str, Any]:
    response = client.get(BALANCE, params={"product_id": product_id})
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    return items[0]


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #


def test_one_posted_receipt_becomes_the_balance(logged_in: LoggedIn) -> None:
    product = make_product(logged_in.client, "Кава")

    post_receipt(logged_in.client, product["id"], 10, key="k1")

    row = balance_of(logged_in.client, product["id"])
    assert row["quantity_balance"] == 10
    assert row["product_id"] == product["id"]
    assert row["last_movement_at"] is not None


def test_several_receipts_aggregate(logged_in: LoggedIn) -> None:
    """The claim the whole architecture rests on.

    Stock is the sum of movements. Three deliveries of the same product are
    three movements and one number, computed on demand — there is no counter
    anywhere that could have drifted from them.
    """
    product = make_product(logged_in.client, "Кава")

    post_receipt(logged_in.client, product["id"], 10, key="k1")
    post_receipt(logged_in.client, product["id"], 5, key="k2")
    post_receipt(logged_in.client, product["id"], 7, key="k3")

    assert balance_of(logged_in.client, product["id"])["quantity_balance"] == 22


def test_a_product_with_no_movements_has_a_zero_balance(logged_in: LoggedIn) -> None:
    """Zero, not 404.

    "Nothing has ever moved" is a valid, informative state — quite unlike "this
    product does not exist". Collapsing the two would make an empty shelf
    indistinguishable from a typo.
    """
    product = make_product(logged_in.client, "Ніколи не надходив")

    row = balance_of(logged_in.client, product["id"])

    assert row["quantity_balance"] == 0
    assert row["last_movement_at"] is None


def test_balances_are_per_product(logged_in: LoggedIn) -> None:
    coffee = make_product(logged_in.client, "Кава")
    tea = make_product(logged_in.client, "Чай")

    post_receipt(logged_in.client, coffee["id"], 10, key="k1")
    post_receipt(logged_in.client, tea["id"], 3, key="k2")

    assert balance_of(logged_in.client, coffee["id"])["quantity_balance"] == 10
    assert balance_of(logged_in.client, tea["id"])["quantity_balance"] == 3


def test_listing_without_a_filter_shows_only_what_has_moved(logged_in: LoggedIn) -> None:
    # A catalog-wide list of zeros is noise. The unfiltered view answers "what is
    # in the warehouse", and a product that never arrived is not.
    stocked = make_product(logged_in.client, "Кава")
    make_product(logged_in.client, "Ніколи не надходив")
    post_receipt(logged_in.client, stocked["id"], 4, key="k1")

    body = logged_in.client.get(BALANCE).json()

    assert [item["product_id"] for item in body["items"]] == [stocked["id"]]
    assert body["total"] == 1


def test_the_row_carries_the_product_name(logged_in: LoggedIn) -> None:
    # The page renders a table; resolving the name here saves a call per row.
    product = make_product(logged_in.client, "Кава мелена")
    post_receipt(logged_in.client, product["id"], 1, key="k1")

    assert balance_of(logged_in.client, product["id"])["product_name"] == "Кава мелена"


# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #


def test_a_foreign_product_is_403(logged_in: LoggedIn) -> None:
    response = logged_in.client.get(BALANCE, params={"product_id": str(uuid.uuid4())})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "organization_forbidden"


def test_another_organizations_movements_are_invisible(
    logged_in: LoggedIn, db_session: Session
) -> None:
    """Scoped in the `WHERE` clause, not filtered afterwards.

    A balance that leaked another tenant's stock would be wrong *and* a
    disclosure; the query never looks outside the organization.
    """
    from decimal import Decimal

    from app.models.catalog import Product
    from app.models.counterparty import CounterpartyStub
    from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLine
    from app.models.identity import Organization
    from app.models.inventory import InventoryBatch, MovementType, StockMovement
    from app.services import inventory

    mine = make_product(logged_in.client, "Кава")
    post_receipt(logged_in.client, mine["id"], 10, key="k1")

    other = Organization(name="ФОП Чужа")
    db_session.add(other)
    db_session.flush()
    other_warehouse = inventory.default_warehouse(db_session, other)
    other_product = Product(
        organization_id=other.id, name="Чужа кава", unit="шт", purchase_price=Decimal("1.00")
    )
    supplier = CounterpartyStub(organization_id=other.id, name="ТОВ Чужий")
    db_session.add_all([other_product, supplier])
    db_session.flush()
    receipt = GoodsReceipt(
        organization_id=other.id,
        warehouse_id=other_warehouse.id,
        counterparty_id=supplier.id,
        created_by=logged_in.user.id,
        lines=[
            GoodsReceiptLine(
                product_id=other_product.id,
                position=0,
                quantity=999,
                purchase_price=Decimal("1.00"),
            )
        ],
    )
    db_session.add(receipt)
    db_session.flush()
    batch = InventoryBatch(
        organization_id=other.id,
        warehouse_id=other_warehouse.id,
        product_id=other_product.id,
        receipt_id=receipt.id,
        purchase_price=Decimal("1.00"),
        quantity=999,
        remaining_quantity=999,
    )
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        StockMovement(
            organization_id=other.id,
            warehouse_id=other_warehouse.id,
            product_id=other_product.id,
            batch_id=batch.id,
            quantity_delta=999,
            movement_type=MovementType.RECEIPT,
            document_id=receipt.id,
        )
    )
    db_session.flush()

    body = logged_in.client.get(BALANCE).json()

    assert [item["quantity_balance"] for item in body["items"]] == [10]


def test_the_balance_endpoint_requires_authentication(client: TestClient) -> None:
    assert client.get(BALANCE).status_code == 401


# --------------------------------------------------------------------------- #
# The architectural claim, asserted against the code
# --------------------------------------------------------------------------- #


def test_the_query_path_reads_no_stored_quantity() -> None:
    """`SUM(quantity_delta)`, and nothing else.

    The PRD forbids a mutable stock column; this asserts the *query* never grew
    one either — reading `InventoryBatch.remaining_quantity` here would be the
    same shortcut wearing a different hat.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "app" / "services" / "stock.py").read_text(
        encoding="utf-8"
    )

    assert "quantity_delta" in source
    assert "remaining_quantity" not in source
    assert "Product.quantity" not in source
