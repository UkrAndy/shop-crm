"""Product API contract.

Money crosses the wire as a **string**, never a JSON number: JSON numbers are
IEEE 754 doubles in every mainstream parser, so a price sent as a number is a
price that can drift. Pydantic parses the string into `Decimal` on the way in
and serialises it back on the way out.
"""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# `decimal_places=2` is what turns PostgreSQL's silent rounding of a third
# decimal into an explicit 422. Without it `10.005` would be stored as `10.01`
# and nobody would be told.
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]

Name = Annotated[str, Field(min_length=1, max_length=255)]
Unit = Annotated[str, Field(min_length=1, max_length=32)]
Barcode = Annotated[str, Field(min_length=1, max_length=64)]


def _strip(value: str) -> str:
    return value.strip()


class ProductCreate(BaseModel):
    name: Name
    unit: Unit
    purchase_price: Money
    barcode: Barcode | None = None

    @field_validator("name", "unit", "barcode", mode="before")
    @classmethod
    def strip_whitespace(cls, value: object) -> object:
        # Runs *before* the length checks, so "   " is rejected as empty rather
        # than accepted as three characters.
        return _strip(value) if isinstance(value, str) else value


class ProductUpdate(BaseModel):
    """A partial update guarded by the version the client last saw.

    `version` is required: omitting it must not mean "overwrite whatever is
    there now". Every other field is optional, and `None` for `barcode` clears
    it — which is why the model distinguishes "absent" from "null".
    """

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)

    name: Name | None = None
    unit: Unit | None = None
    purchase_price: Money | None = None
    barcode: Barcode | None = None

    @field_validator("name", "unit", "barcode", mode="before")
    @classmethod
    def strip_whitespace(cls, value: object) -> object:
        return _strip(value) if isinstance(value, str) else value


class ProductPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    unit: str
    purchase_price: Decimal
    barcode: str | None
    version: int


class ProductPage(BaseModel):
    """A page plus the size of the whole result set.

    `total` counts everything matching the filter, not the page: a pager that
    only knows its own slice cannot tell the user how many pages there are.
    """

    items: list[ProductPublic]
    total: int
    limit: int
    offset: int
