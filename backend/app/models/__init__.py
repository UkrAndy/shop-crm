"""ORM model registry.

Every model module must be imported here so that `Base.metadata` is complete
when Alembic autogenerates a migration. Models arrive in Phase 2 onward
(identity, catalog, inventory); this package is intentionally empty for now.
"""

__all__: list[str] = []
