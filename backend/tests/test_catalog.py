"""Issue 10 — the Product aggregate and its version token.

This is the first aggregate carrying a `version`, and Issues 15 and 20 copy the
pattern, so the mechanism is tested here rather than assumed.

Acceptance criteria under test:
- money round-trips as `Decimal` with kopiyka precision;
- `version` starts at 1 and increments on every update;
- `barcode` is unique per organization.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.models.catalog import Product

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from app.models.identity import Organization


def make_product(organization: Organization, **overrides: object) -> Product:
    values: dict[str, object] = {
        "organization_id": organization.id,
        "name": "Кава мелена 250 г",
        "unit": "шт",
        "purchase_price": Decimal("125.50"),
    }
    values.update(overrides)
    return Product(**values)


# --------------------------------------------------------------------------- #
# Money
# --------------------------------------------------------------------------- #


def test_price_round_trips_as_decimal(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    org = organization_factory("ФОП Гроші")
    product = make_product(org, purchase_price=Decimal("125.50"))
    db_session.add(product)
    db_session.flush()
    db_session.expire(product)

    assert product.purchase_price == Decimal("125.50")


def test_price_is_a_decimal_not_a_float(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    # The whole point of `numeric`: binary floating point cannot represent 0.1,
    # and money that drifts by a kopiyka per row is an accounting defect.
    org = organization_factory("ФОП Тип")
    product = make_product(org)
    db_session.add(product)
    db_session.flush()
    db_session.expire(product)

    assert isinstance(product.purchase_price, Decimal)


@pytest.mark.parametrize(
    "price",
    [Decimal("0.01"), Decimal("0.99"), Decimal("10.05"), Decimal("99999999.99")],
)
def test_kopiyka_precision_is_exact(
    db_session: Session,
    organization_factory: Callable[[str], Organization],
    price: Decimal,
) -> None:
    org = organization_factory(f"ФОП {price}")
    product = make_product(org, purchase_price=price)
    db_session.add(product)
    db_session.flush()
    db_session.expire(product)

    assert product.purchase_price == price


def test_a_third_decimal_place_is_rounded_by_the_database(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    # Documented, not desired. The column is numeric(14, 2), so PostgreSQL
    # rounds rather than rejecting. Refusing sub-kopiyka input is the API's job
    # (Issue 11) — this test pins what the storage layer does on its own so the
    # guard above it is understood to be load-bearing.
    org = organization_factory("ФОП Округлення")
    product = make_product(org, purchase_price=Decimal("10.005"))
    db_session.add(product)
    db_session.flush()
    db_session.expire(product)

    assert product.purchase_price == Decimal("10.01")


def test_negative_price_is_rejected_by_the_database(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    org = organization_factory("ФОП Мінус")
    db_session.add(make_product(org, purchase_price=Decimal("-0.01")))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_zero_price_is_allowed(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    # PRD says non-negative, not positive: a promotional or gifted item legitimately
    # arrives at zero cost.
    org = organization_factory("ФОП Нуль")
    db_session.add(make_product(org, purchase_price=Decimal("0.00")))

    db_session.flush()


# --------------------------------------------------------------------------- #
# Version token
# --------------------------------------------------------------------------- #


def test_version_starts_at_one(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    org = organization_factory("ФОП Версія")
    product = make_product(org)
    db_session.add(product)
    db_session.flush()

    assert product.version == 1


def test_version_increments_on_update(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    org = organization_factory("ФОП Інкремент")
    product = make_product(org)
    db_session.add(product)
    db_session.flush()

    product.name = "Кава мелена 500 г"
    db_session.flush()

    assert product.version == 2


def test_stale_version_loses(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    """The mechanism, not just the counter.

    SQLAlchemy issues `UPDATE ... WHERE id = ? AND version = ?`. Simulating a
    concurrent writer by moving the row's version forward behind the session's
    back must make the next flush fail, because that `WHERE` clause matches
    nothing. Issue 13 repeats this with genuinely parallel requests.
    """
    org = organization_factory("ФОП Конфлікт")
    product = make_product(org)
    db_session.add(product)
    db_session.flush()

    # Raw SQL on purpose: it bypasses the identity map exactly as another
    # connection would, which is what makes the next flush see a moved target.
    db_session.execute(
        text("UPDATE products SET version = version + 1 WHERE id = :id"),
        {"id": product.id},
    )

    product.name = "Змінено з застарілої версії"

    with pytest.raises(StaleDataError):
        db_session.flush()


# --------------------------------------------------------------------------- #
# Barcode uniqueness
# --------------------------------------------------------------------------- #


def test_barcode_is_unique_within_an_organization(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    org = organization_factory("ФОП Штрихкод")
    db_session.add(make_product(org, barcode="4820000000001"))
    db_session.flush()

    db_session.add(make_product(org, barcode="4820000000001", name="Інший товар"))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_the_same_barcode_may_exist_in_another_organization(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    # Uniqueness is scoped, not global: two independent ФОПs selling the same
    # manufactured product both hold its EAN legitimately.
    first = organization_factory("ФОП Перша")
    second = organization_factory("ФОП Друга")
    db_session.add(make_product(first, barcode="4820000000002"))
    db_session.add(make_product(second, barcode="4820000000002"))

    db_session.flush()


def test_many_products_may_have_no_barcode(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    # A plain unique constraint would allow only one such row, since NULLs do
    # not collide in some databases but the intent must not depend on that.
    # A partial index expresses it directly.
    org = organization_factory("ФОП Без штрихкоду")
    db_session.add(make_product(org, barcode=None, name="Товар А"))
    db_session.add(make_product(org, barcode=None, name="Товар Б"))

    db_session.flush()


# --------------------------------------------------------------------------- #
# Shape
# --------------------------------------------------------------------------- #


def test_name_may_not_be_blank(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    org = organization_factory("ФОП Порожнє")
    db_session.add(make_product(org, name="   "))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_product_has_no_quantity_column() -> None:
    """The PRD's central architectural claim, asserted rather than trusted.

    Stock balance is aggregated from immutable movements. A mutable `quantity`
    on the product row is the exact shortcut this design exists to forbid, and
    it is the kind of column that gets added quietly under deadline.
    """
    columns = set(inspect(Product).columns.keys())

    assert "quantity" not in columns
    assert "stock" not in columns
    assert "remaining_quantity" not in columns
