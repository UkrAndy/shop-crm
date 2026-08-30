"""Issue 11 — the products API and its optimistic concurrency.

Acceptance criteria under test:
- a stale-version update returns 409 and leaves the row untouched;
- a negative or non-numeric price returns 422;
- listing never leaks products from another organization.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.identity import Organization, User
    from tests.conftest import LoggedIn

PRODUCTS = "/api/v1/products"


def payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Кава мелена 250 г",
        "unit": "шт",
        "purchase_price": "125.50",
    }
    body.update(overrides)
    return body


def create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post(PRODUCTS, json=payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Creation
# --------------------------------------------------------------------------- #


def test_create_returns_the_product_at_version_one(logged_in: LoggedIn) -> None:
    response = logged_in.client.post(PRODUCTS, json=payload())

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Кава мелена 250 г"
    assert body["purchase_price"] == "125.50"
    assert body["version"] == 1


def test_price_is_serialised_as_a_string_not_a_float(logged_in: LoggedIn) -> None:
    # JSON numbers are IEEE 754 doubles in every mainstream parser, so a price
    # sent as a number is a price that can drift. It crosses the wire as a
    # string and is parsed back into Decimal on both sides.
    body = create(logged_in.client)

    assert isinstance(body["purchase_price"], str)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("purchase_price", "-0.01"),
        ("purchase_price", "10.005"),
        ("purchase_price", "not-a-number"),
        ("name", "   "),
        ("name", ""),
        ("unit", ""),
    ],
)
def test_invalid_input_is_422(logged_in: LoggedIn, field: str, value: str) -> None:
    response = logged_in.client.post(PRODUCTS, json=payload(**{field: value}))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_sub_kopiyka_price_is_refused_rather_than_rounded(logged_in: LoggedIn) -> None:
    # numeric(14, 2) would silently round 10.005 to 10.01. This guard is the
    # reason that rounding never happens in practice, so it is asserted on its
    # own rather than left inside the parametrised case above.
    response = logged_in.client.post(PRODUCTS, json=payload(purchase_price="10.005"))

    assert response.status_code == 422
    fields = response.json()["error"]["fields"]
    assert any("purchase_price" in item["field"] for item in fields)


def test_name_is_trimmed(logged_in: LoggedIn) -> None:
    body = create(logged_in.client, name="  Хліб  ")

    assert body["name"] == "Хліб"


def test_duplicate_barcode_in_the_same_organization_is_409(logged_in: LoggedIn) -> None:
    create(logged_in.client, barcode="4820000000001")

    response = logged_in.client.post(PRODUCTS, json=payload(barcode="4820000000001", name="Інший"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "barcode_taken"


def test_several_products_may_have_no_barcode(logged_in: LoggedIn) -> None:
    create(logged_in.client, name="Товар А")
    create(logged_in.client, name="Товар Б")

    assert logged_in.client.get(PRODUCTS).json()["total"] == 2


# --------------------------------------------------------------------------- #
# Listing
# --------------------------------------------------------------------------- #


def test_listing_is_scoped_to_the_active_organization(
    logged_in: LoggedIn,
    db_session: Session,
    organization_factory: Callable[[str], Organization],
) -> None:
    from decimal import Decimal

    from app.models.catalog import Product

    create(logged_in.client, name="Мій товар")

    other = organization_factory("ФОП Чужа")
    db_session.add(
        Product(
            organization_id=other.id,
            name="Чужий товар",
            unit="шт",
            purchase_price=Decimal("1.00"),
        )
    )
    db_session.flush()

    body = logged_in.client.get(PRODUCTS).json()

    assert body["total"] == 1
    assert [item["name"] for item in body["items"]] == ["Мій товар"]


def test_listing_filters_by_name_and_barcode(logged_in: LoggedIn) -> None:
    create(logged_in.client, name="Кава арабіка", barcode="4820000000010")
    create(logged_in.client, name="Чай зелений", barcode="4820000000011")

    by_name = logged_in.client.get(PRODUCTS, params={"q": "кава"}).json()
    by_barcode = logged_in.client.get(PRODUCTS, params={"q": "0000011"}).json()

    assert [item["name"] for item in by_name["items"]] == ["Кава арабіка"]
    assert [item["name"] for item in by_barcode["items"]] == ["Чай зелений"]


def test_listing_paginates_and_reports_the_full_total(logged_in: LoggedIn) -> None:
    for index in range(5):
        create(logged_in.client, name=f"Товар {index}")

    page = logged_in.client.get(PRODUCTS, params={"limit": 2, "offset": 2}).json()

    # `total` counts everything matching the filter, not the page — otherwise a
    # pager cannot know how many pages exist.
    assert page["total"] == 5
    assert len(page["items"]) == 2


def test_an_absurd_limit_is_refused(logged_in: LoggedIn) -> None:
    # An unbounded limit turns one request into a full-table dump.
    assert logged_in.client.get(PRODUCTS, params={"limit": 10_000}).status_code == 422


# --------------------------------------------------------------------------- #
# Reading one
# --------------------------------------------------------------------------- #


def test_get_returns_the_product(logged_in: LoggedIn) -> None:
    created = create(logged_in.client)

    response = logged_in.client.get(f"{PRODUCTS}/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_a_product_from_another_organization_is_403(
    logged_in: LoggedIn,
    db_session: Session,
    organization_factory: Callable[[str], Organization],
) -> None:
    from decimal import Decimal

    from app.models.catalog import Product

    other = organization_factory("ФОП Стороння")
    foreign = Product(
        organization_id=other.id, name="Чужий", unit="шт", purchase_price=Decimal("1.00")
    )
    db_session.add(foreign)
    db_session.flush()

    response = logged_in.client.get(f"{PRODUCTS}/{foreign.id}")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "organization_forbidden"


def test_an_unknown_id_answers_exactly_like_a_foreign_one(logged_in: LoggedIn) -> None:
    # Both are "not in your organization". The query is scoped, so the server
    # never learns whether the row exists elsewhere — and therefore cannot leak
    # it, even accidentally.
    response = logged_in.client.get(f"{PRODUCTS}/{uuid.uuid4()}")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "organization_forbidden"


# --------------------------------------------------------------------------- #
# Updating — optimistic concurrency
# --------------------------------------------------------------------------- #


def test_update_bumps_the_version(logged_in: LoggedIn) -> None:
    created = create(logged_in.client)

    response = logged_in.client.patch(
        f"{PRODUCTS}/{created['id']}",
        json={"version": created["version"], "name": "Кава мелена 500 г"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Кава мелена 500 г"
    assert response.json()["version"] == 2


def test_a_stale_version_is_409_and_changes_nothing(logged_in: LoggedIn) -> None:
    """The acceptance criterion of this issue.

    Two sequential updates where the second still holds version 1: it must lose,
    and it must not have half-applied anything on its way out.
    """
    created = create(logged_in.client)
    first = logged_in.client.patch(
        f"{PRODUCTS}/{created['id']}", json={"version": 1, "name": "Перша зміна"}
    )
    assert first.status_code == 200

    second = logged_in.client.patch(
        f"{PRODUCTS}/{created['id']}", json={"version": 1, "name": "Друга зміна"}
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "version_conflict"

    current = logged_in.client.get(f"{PRODUCTS}/{created['id']}").json()
    assert current["name"] == "Перша зміна"
    assert current["version"] == 2


def test_update_without_a_version_is_422(logged_in: LoggedIn) -> None:
    # Omitting the version must not mean "overwrite whatever is there".
    created = create(logged_in.client)

    response = logged_in.client.patch(f"{PRODUCTS}/{created['id']}", json={"name": "Без версії"})

    assert response.status_code == 422


def test_update_rejects_a_sub_kopiyka_price(logged_in: LoggedIn) -> None:
    created = create(logged_in.client)

    response = logged_in.client.patch(
        f"{PRODUCTS}/{created['id']}", json={"version": 1, "purchase_price": "1.005"}
    )

    assert response.status_code == 422


def test_update_can_clear_a_barcode(logged_in: LoggedIn) -> None:
    created = create(logged_in.client, barcode="4820000000020")

    response = logged_in.client.patch(
        f"{PRODUCTS}/{created['id']}", json={"version": 1, "barcode": None}
    )

    assert response.status_code == 200
    assert response.json()["barcode"] is None


def test_update_to_a_taken_barcode_is_409(logged_in: LoggedIn) -> None:
    create(logged_in.client, name="Перший", barcode="4820000000030")
    second = create(logged_in.client, name="Другий", barcode="4820000000031")

    response = logged_in.client.patch(
        f"{PRODUCTS}/{second['id']}", json={"version": 1, "barcode": "4820000000030"}
    )

    assert response.status_code == 409


def test_updating_a_foreign_product_is_403(
    logged_in: LoggedIn,
    db_session: Session,
    organization_factory: Callable[[str], Organization],
) -> None:
    from decimal import Decimal

    from app.models.catalog import Product

    other = organization_factory("ФОП Недосяжна")
    foreign = Product(
        organization_id=other.id, name="Чужий", unit="шт", purchase_price=Decimal("1.00")
    )
    db_session.add(foreign)
    db_session.flush()

    response = logged_in.client.patch(
        f"{PRODUCTS}/{foreign.id}", json={"version": 1, "name": "Захоплено"}
    )

    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Scope and authentication
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("method", "path"), [("GET", PRODUCTS), ("POST", PRODUCTS)])
def test_products_require_authentication(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, path, json=payload())

    assert response.status_code == 401


def test_products_require_a_selected_organization(
    client: TestClient,
    user_factory: Callable[..., User],
    organization_factory: Callable[[str], Organization],
) -> None:
    # Two memberships, so login resolves no active organization and the server
    # refuses to guess which legal entity the product belongs to.
    from tests.conftest import TEST_PASSWORD

    first = organization_factory("ФОП Один")
    second = organization_factory("ФОП Два")
    user_factory("undecided@example.com", first, second)
    client.post(
        "/api/v1/auth/login",
        json={"email": "undecided@example.com", "password": TEST_PASSWORD},
    )

    response = client.post(PRODUCTS, json=payload())

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "no_active_organization"
