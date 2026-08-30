"""ORM model registry.

Every model module must be imported here so that `Base.metadata` is complete
when Alembic autogenerates or checks a migration. A model missing from this list
is a model CI believes does not exist.
"""

from app.models.catalog import Product
from app.models.identity import Membership, Organization, User, UserSession

__all__ = ["Membership", "Organization", "Product", "User", "UserSession"]
