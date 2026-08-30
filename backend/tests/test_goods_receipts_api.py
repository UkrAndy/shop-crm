"""Issue 16 — the goods receipt draft API.

Acceptance criteria under test:
- a posted document cannot be mutated through `PATCH` under any payload;
- line replacement is atomic — a rejected `PATCH` leaves the previous lines intact.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.identity import Organization
    from tests.conftest import LoggedIn

RECEIPTS = "/api/v1/goods-receipts"
PRODUCTS = "/api/v1/products"
COUNTERPARTIES = "/api/v1/counterparties"


def make_product(client: TestClient, name: str = "Кава мелена") -> dict[str, Any]:
    response = client.post(PRODUCTS, json={"name": name, "unit": "шт", "purchase_price": "100.00"})
    assert response.status_code == 201, response.text
    return response.json()


def make_supplier(client: TestClient, name: str = "ТОВ Постачальник") -> dict[str, Any]:
    response = client.post(COUNTERPARTIES, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def some_supplier(client: TestClient) -> dict[str, Any]:
    """Reuse the organization's supplier, creating one only if there is none.

    Supplier names are unique per organization, so a helper that always creates
    would collide the second time it is called in a test.
    """
    existing = client.get(COUNTERPARTIES).json()
    return existing[0] if existing else make_supplier(client)


def make_draft(client: TestClient, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"counterparty_id": some_supplier(client)["id"], "lines": []}
    body.update(overrides)
    response = client.post(RECEIPTS, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def line(product_id: str, quantity: int = 10, price: str = "100.00") -> dict[str, Any]:
    return {"product_id": product_id, "quantity": quantity, "purchase_price": price}


# --------------------------------------------------------------------------- #
# Creating a draft
# --------------------------------------------------------------------------- #


def test_a_new_receipt_is_a_draft_at_version_one(logged_in: LoggedIn) -> None:
    receipt = make_draft(logged_in.client)

    assert receipt["status"] == "draft"
    assert receipt["version"] == 1
    assert receipt["lines"] == []


def test_the_warehouse_is_resolved_server_side(logged_in: LoggedIn) -> None:
    # The client never names a warehouse. One organization has exactly one, so
    # letting the client choose would only create a way to get it wrong.
    receipt = make_draft(logged_in.client)

    assert receipt["warehouse_id"]


def test_a_draft_can_be_created_with_lines(logged_in: LoggedIn) -> None:
    product = make_product(logged_in.client)

    receipt = make_draft(logged_in.client, lines=[line(product["id"], 3, "50.00")])

    assert len(receipt["lines"]) == 1
    assert receipt["lines"][0]["quantity"] == 3
    assert receipt["lines"][0]["product_name"] == "Кава мелена"


def test_the_total_is_computed_by_the_server(logged_in: LoggedIn) -> None:
    # Money arithmetic in JavaScript is where kopiykas go missing. The server
    # holds Decimals, so it does the sum and the client only renders it.
    product = make_product(logged_in.client)

    receipt = make_draft(
        logged_in.client,
        lines=[line(product["id"], 3, "10.10"), line(product["id"], 2, "0.05")],
    )

    assert receipt["total"] == "30.40"
    assert receipt["lines"][0]["line_total"] == "30.30"


def test_an_unknown_counterparty_is_rejected(logged_in: LoggedIn) -> None:
    response = logged_in.client.post(
        RECEIPTS, json={"counterparty_id": str(uuid.uuid4()), "lines": []}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_counterparty"


def test_a_product_from_another_organization_cannot_be_put_on_a_line(
    logged_in: LoggedIn,
    db_session: Session,
    organization_factory: Callable[[str], Organization],
) -> None:
    """The cross-tenant guard, which lives in the service layer.

    A foreign product and a nonexistent one give the same answer, because the
    lookup is scoped and never learns which it was.
    """
    from decimal import Decimal

    from app.models.catalog import Product

    other = organization_factory("ФОП Чужа")
    foreign = Product(
        organization_id=other.id, name="Чужий", unit="шт", purchase_price=Decimal("1.00")
    )
    db_session.add(foreign)
    db_session.flush()

    supplier = make_supplier(logged_in.client)
    response = logged_in.client.post(
        RECEIPTS, json={"counterparty_id": supplier["id"], "lines": [line(str(foreign.id))]}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_product"


@pytest.mark.parametrize(
    ("field", "value"),
    [("quantity", 0), ("quantity", -1), ("purchase_price", "-0.01"), ("purchase_price", "1.005")],
)
def test_invalid_line_values_are_422(logged_in: LoggedIn, field: str, value: object) -> None:
    product = make_product(logged_in.client)
    bad = line(product["id"])
    bad[field] = value
    supplier = make_supplier(logged_in.client)

    response = logged_in.client.post(
        RECEIPTS, json={"counterparty_id": supplier["id"], "lines": [bad]}
    )

    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


def test_listing_is_newest_first(logged_in: LoggedIn, db_session: Session) -> None:
    """Ordering, with timestamps that genuinely differ.

    `now()` is the *transaction* timestamp in PostgreSQL, and this whole test
    runs in one transaction, so two receipts created here would share it exactly
    and the assertion would be testing the tie-break rather than the ordering.
    Backdating one makes the question real. In production each request is its own
    transaction, so the timestamps differ on their own.
    """
    import datetime as dt

    from app.models.goods_receipt import GoodsReceipt

    older = make_draft(logged_in.client)
    newer = make_draft(logged_in.client)

    row = db_session.get(GoodsReceipt, uuid.UUID(older["id"]))
    assert row is not None
    row.created_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    db_session.flush()

    body = logged_in.client.get(RECEIPTS).json()

    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [newer["id"], older["id"]]


def test_the_list_carries_what_the_table_shows(logged_in: LoggedIn) -> None:
    # Status, supplier, author and date, so the list page needs no extra call
    # per row to render.
    make_draft(logged_in.client)

    item = logged_in.client.get(RECEIPTS).json()["items"][0]

    assert item["status"] == "draft"
    assert item["counterparty_name"] == "ТОВ Постачальник"
    assert item["created_by_email"] == "scoped-user@example.com"
    assert item["created_at"]


def test_an_unknown_receipt_is_403(logged_in: LoggedIn) -> None:
    response = logged_in.client.get(f"{RECEIPTS}/{uuid.uuid4()}")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "organization_forbidden"


# --------------------------------------------------------------------------- #
# Editing a draft
# --------------------------------------------------------------------------- #


def test_lines_are_replaced_wholesale(logged_in: LoggedIn) -> None:
    product = make_product(logged_in.client)
    receipt = make_draft(logged_in.client, lines=[line(product["id"], 1)])

    response = logged_in.client.patch(
        f"{RECEIPTS}/{receipt['id']}",
        json={"version": 1, "lines": [line(product["id"], 7), line(product["id"], 8)]},
    )

    assert response.status_code == 200
    # In payload order. Every line of one document shares `created_at`, so the
    # order has to be stored explicitly rather than inferred from a timestamp.
    assert [item["quantity"] for item in response.json()["lines"]] == [7, 8]
    assert response.json()["version"] == 2


def test_omitting_lines_leaves_them_alone(logged_in: LoggedIn) -> None:
    # Absent is not the same as empty: a PATCH that only changes the supplier
    # must not silently wipe the document.
    product = make_product(logged_in.client)
    receipt = make_draft(logged_in.client, lines=[line(product["id"], 4)])
    other_supplier = make_supplier(logged_in.client, "ТОВ Інший")

    response = logged_in.client.patch(
        f"{RECEIPTS}/{receipt['id']}",
        json={"version": 1, "counterparty_id": other_supplier["id"]},
    )

    assert response.status_code == 200
    assert [item["quantity"] for item in response.json()["lines"]] == [4]
    assert response.json()["counterparty_name"] == "ТОВ Інший"


def test_an_empty_line_list_clears_the_document(logged_in: LoggedIn) -> None:
    product = make_product(logged_in.client)
    receipt = make_draft(logged_in.client, lines=[line(product["id"])])

    response = logged_in.client.patch(
        f"{RECEIPTS}/{receipt['id']}", json={"version": 1, "lines": []}
    )

    assert response.status_code == 200
    assert response.json()["lines"] == []


def test_a_stale_version_is_409(logged_in: LoggedIn) -> None:
    receipt = make_draft(logged_in.client)
    logged_in.client.patch(f"{RECEIPTS}/{receipt['id']}", json={"version": 1, "lines": []})

    response = logged_in.client.patch(
        f"{RECEIPTS}/{receipt['id']}", json={"version": 1, "lines": []}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_conflict"


def test_a_rejected_patch_leaves_the_previous_lines_intact(logged_in: LoggedIn) -> None:
    """The acceptance criterion: line replacement is atomic.

    The new lines are validated *before* anything is removed, so a payload that
    fails halfway cannot leave the document holding a partial delivery — which
    would post as real stock.
    """
    product = make_product(logged_in.client)
    receipt = make_draft(logged_in.client, lines=[line(product["id"], 5)])

    response = logged_in.client.patch(
        f"{RECEIPTS}/{receipt['id']}",
        json={
            "version": 1,
            "lines": [line(product["id"], 9), line(str(uuid.uuid4()), 3)],
        },
    )

    assert response.status_code == 422
    current = logged_in.client.get(f"{RECEIPTS}/{receipt['id']}").json()
    assert [item["quantity"] for item in current["lines"]] == [5]
    assert current["version"] == 1


def test_a_patch_without_a_version_is_422(logged_in: LoggedIn) -> None:
    receipt = make_draft(logged_in.client)

    response = logged_in.client.patch(f"{RECEIPTS}/{receipt['id']}", json={"lines": []})

    assert response.status_code == 422


def test_patching_a_receipt_from_another_organization_is_403(logged_in: LoggedIn) -> None:
    response = logged_in.client.patch(
        f"{RECEIPTS}/{uuid.uuid4()}", json={"version": 1, "lines": []}
    )

    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# A posted document is immutable
# --------------------------------------------------------------------------- #


@pytest.fixture
def posted_receipt(logged_in: LoggedIn, db_session: Session) -> dict[str, Any]:
    """A receipt already in `posted`.

    Flipped directly in the database because the posting command is Issue 20;
    what is under test here is that `PATCH` refuses to touch it, whoever posted.
    """
    from app.models.goods_receipt import GoodsReceipt, ReceiptStatus

    product = make_product(logged_in.client)
    receipt = make_draft(logged_in.client, lines=[line(product["id"], 6)])

    row = db_session.get(GoodsReceipt, uuid.UUID(receipt["id"]))
    assert row is not None
    row.status = ReceiptStatus.POSTED
    db_session.flush()

    return logged_in.client.get(f"{RECEIPTS}/{receipt['id']}").json()


@pytest.mark.parametrize(
    "payload",
    [
        {"lines": []},
        {
            "lines": [
                {
                    "product_id": "00000000-0000-0000-0000-000000000000",
                    "quantity": 1,
                    "purchase_price": "1.00",
                }
            ]
        },
        {"counterparty_id": "00000000-0000-0000-0000-000000000000"},
        {},
    ],
    ids=["clear-lines", "replace-lines", "change-supplier", "empty-payload"],
)
def test_a_posted_document_cannot_be_mutated_under_any_payload(
    logged_in: LoggedIn, posted_receipt: dict[str, Any], payload: dict[str, Any]
) -> None:
    body = {"version": posted_receipt["version"], **payload}

    response = logged_in.client.patch(f"{RECEIPTS}/{posted_receipt['id']}", json=body)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "receipt_not_draft"


def test_refusing_to_edit_a_posted_document_changes_nothing(
    logged_in: LoggedIn, posted_receipt: dict[str, Any]
) -> None:
    logged_in.client.patch(
        f"{RECEIPTS}/{posted_receipt['id']}",
        json={"version": posted_receipt["version"], "lines": []},
    )

    current = logged_in.client.get(f"{RECEIPTS}/{posted_receipt['id']}").json()
    assert [item["quantity"] for item in current["lines"]] == [6]
    assert current["version"] == posted_receipt["version"]


# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", RECEIPTS), ("POST", RECEIPTS), ("GET", COUNTERPARTIES), ("POST", COUNTERPARTIES)],
)
def test_receipt_endpoints_require_authentication(
    client: TestClient, method: str, path: str
) -> None:
    assert client.request(method, path, json={}).status_code == 401


def test_counterparties_are_scoped_to_the_organization(logged_in: LoggedIn) -> None:
    make_supplier(logged_in.client, "ТОВ Мій")

    body = logged_in.client.get(COUNTERPARTIES).json()

    assert [item["name"] for item in body] == ["ТОВ Мій"]


def test_a_duplicate_supplier_name_is_409(logged_in: LoggedIn) -> None:
    make_supplier(logged_in.client, "ТОВ Дубль")

    response = logged_in.client.post(COUNTERPARTIES, json={"name": "ТОВ Дубль"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "counterparty_name_taken"
