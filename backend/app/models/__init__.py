"""ORM model registry.

Every model module must be imported here so that `Base.metadata` is complete
when Alembic autogenerates or checks a migration.
"""

from app.models.identity import Membership, Organization, User

__all__ = ["Membership", "Organization", "User"]
