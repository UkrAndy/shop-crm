"""Shared test fixtures.

The suite runs against a real PostgreSQL database, never SQLite: the behaviour
under test here (check constraints, unique constraints, `timestamptz`) and the
locking semantics later phases depend on are not reproducible on a substitute.

`DATABASE_URL` is redirected to a sibling `<database>_test` **at import time**,
before any application module is imported, because `app.core.db` builds its
engine at import and `get_settings()` is `lru_cache`d. Editing the environment
later would be too late.

Issue 25 hardens this into the concurrency fixture; what is here is the minimum
that makes Phase 2 verifiable.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import pytest
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.models.identity import Organization, User

_BACKEND_ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_URL = "postgresql+psycopg://testvasja:testvasja@localhost:5432/testvasja"


def _test_database_url() -> str:
    url = make_url(os.environ.get("DATABASE_URL", _DEFAULT_URL))
    database = url.database or "testvasja"
    if database.endswith("_test"):
        return url.render_as_string(hide_password=False)
    return url.set(database=f"{database}_test").render_as_string(hide_password=False)


# Must happen before `from app...` anywhere in the suite.
os.environ["DATABASE_URL"] = _test_database_url()


def _ensure_database_exists(url_string: str) -> None:
    """Create the test database if it is absent.

    Connects to the `postgres` maintenance database, because a database cannot
    be created from inside itself, and `CREATE DATABASE` cannot run inside a
    transaction block — hence the AUTOCOMMIT isolation level.
    """
    url = make_url(url_string)
    target = url.database
    assert target is not None

    maintenance = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with maintenance.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target}
            ).scalar()
            if exists is None:
                # The name is derived from our own configuration, never from input.
                conn.execute(text(f'CREATE DATABASE "{target}"'))
    finally:
        maintenance.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Bring the test database to `head` once per session.

    Migrations are applied rather than `Base.metadata.create_all`: a schema built
    straight from the models would pass even when the migration that creates it
    is wrong, which is the exact failure this project guards against.
    """
    from alembic import command
    from alembic.config import Config

    _ensure_database_exists(os.environ["DATABASE_URL"])

    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "migrations"))
    command.upgrade(config, "head")


@pytest.fixture
def db_session(migrated_database: None) -> Iterator[Session]:
    """A session whose work is rolled back, so tests cannot leak state into each other.

    The session joins an outer transaction on a single connection; committing
    inside a test would end only the nested transaction, and the outer one is
    discarded here.
    """
    from app.core.db import engine as app_engine

    engine: Engine = app_engine
    connection = engine.connect()
    transaction = connection.begin()
    # `create_savepoint` lets the service layer call `commit()` for real without
    # ending the outer transaction, so production code is exercised unmodified
    # and the test still rolls back.
    session = sessionmaker(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )()

    try:
        yield session
    finally:
        session.close()
        # A test that provoked an IntegrityError leaves the transaction already
        # deassociated; rolling it back again would only emit a warning.
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """A TestClient whose requests run inside the test's rolled-back transaction."""
    from fastapi.testclient import TestClient

    from app.core.db import get_session
    from app.main import app

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


TEST_PASSWORD = "correct horse battery staple"


@pytest.fixture
def user_factory(db_session: Session) -> Callable[..., User]:
    """Creates an active user with `TEST_PASSWORD`, optionally in organizations."""
    from app.core.security import hash_password
    from app.models.identity import Membership
    from app.models.identity import User as UserModel

    def create(email: str, *organizations: Organization, is_active: bool = True) -> UserModel:
        user = UserModel(
            email=email.lower(),
            password_hash=hash_password(TEST_PASSWORD),
            is_active=is_active,
        )
        db_session.add(user)
        db_session.flush()
        for organization in organizations:
            db_session.add(Membership(user_id=user.id, organization_id=organization.id))
        db_session.flush()
        return user

    return create


@pytest.fixture
def organization_factory(db_session: Session) -> Callable[[str], Organization]:
    from app.models.identity import Organization as OrganizationModel

    def create(name: str) -> OrganizationModel:
        organization = OrganizationModel(name=name)
        db_session.add(organization)
        db_session.flush()
        return organization

    return create


class LoggedIn(NamedTuple):
    """A client with a live session and a resolved organization scope."""

    client: TestClient
    organization: Organization
    user: User


@pytest.fixture
def logged_in(
    client: TestClient,
    user_factory: Callable[..., User],
    organization_factory: Callable[[str], Organization],
) -> LoggedIn:
    """The common starting point for scoped-endpoint tests.

    One membership, so the active organization is resolved at login and the test
    does not have to select it before every request.
    """
    organization = organization_factory("ФОП Тестова")
    user = user_factory("scoped-user@example.com", organization)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "scoped-user@example.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert response.json()["active_organization_id"] == str(organization.id)

    return LoggedIn(client=client, organization=organization, user=user)
