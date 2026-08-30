"""Issue 7 — login, session authentication and organization scope.

Acceptance criteria under test:
- an unauthenticated request to a protected route returns 401 with the documented body;
- an authenticated user reaching another organization's data returns 403;
- the active organization is resolved server-side, never trusted from the request body.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

from tests.conftest import TEST_PASSWORD

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.identity import Organization, User

SESSION_COOKIE = "testvasja_session"


def login(client: TestClient, email: str, password: str = TEST_PASSWORD):  # noqa: ANN201
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #


def test_login_succeeds_and_sets_a_session_cookie(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    user = user_factory("owner@example.com")

    response = login(client, "owner@example.com")

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "owner@example.com"
    assert response.json()["user"]["id"] == str(user.id)
    assert SESSION_COOKIE in response.cookies


def test_session_cookie_is_http_only_and_same_site_lax(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    # The whole design rests on the cookie being unreadable from JavaScript and
    # not riding cross-site requests. Asserting it stops a later refactor from
    # quietly dropping either flag.
    user_factory("flags@example.com")

    response = login(client, "flags@example.com")

    # Compared lowercased: RFC 6265bis treats attribute names and the SameSite
    # value case-insensitively, so asserting exact casing would test Starlette's
    # formatting rather than our behaviour.
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "path=/" in set_cookie
    # No TLS in local development, so `Secure` would make the cookie unusable.
    assert "secure" not in set_cookie


def test_login_is_case_insensitive_on_email(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    user_factory("mixed@example.com")

    assert login(client, "Mixed@Example.COM").status_code == 200


def test_wrong_password_is_rejected(client: TestClient, user_factory: Callable[..., User]) -> None:
    user_factory("real@example.com")

    response = login(client, "real@example.com", password="wrong")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    assert SESSION_COOKIE not in response.cookies


def test_unknown_email_gives_the_same_answer_as_a_wrong_password(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    # Distinguishing the two would turn the login form into a user-enumeration
    # oracle, which the design document explicitly forbids.
    user_factory("known@example.com")

    wrong_password = login(client, "known@example.com", password="wrong")
    unknown_email = login(client, "nobody@example.com", password="wrong")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_deactivated_user_cannot_log_in(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    user_factory("disabled@example.com", is_active=False)

    assert login(client, "disabled@example.com").status_code == 401


def test_malformed_login_body_returns_422_in_the_shared_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"email": "not-an-email"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["fields"]


def test_login_never_echoes_the_password(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    user_factory("echo@example.com")

    response = login(client, "echo@example.com")

    assert TEST_PASSWORD not in response.text
    assert "password" not in response.text


# --------------------------------------------------------------------------- #
# 401 contract on protected routes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/organizations"),
        ("GET", "/api/v1/organizations/active"),
        ("POST", "/api/v1/organizations/active"),
    ],
)
def test_protected_route_requires_authentication(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(method, path, json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_unknown_session_cookie_is_401_not_500(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, "a-token-that-was-never-issued")

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_logout_invalidates_the_session(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    user_factory("bye@example.com")
    login(client, "bye@example.com")
    assert client.get("/api/v1/auth/me").status_code == 200

    assert client.post("/api/v1/auth/logout").status_code == 204

    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_is_idempotent(client: TestClient, user_factory: Callable[..., User]) -> None:
    user_factory("bye2@example.com")
    login(client, "bye2@example.com")

    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/logout").status_code == 204


# --------------------------------------------------------------------------- #
# Organization scope
# --------------------------------------------------------------------------- #


def test_organizations_lists_only_the_users_own(
    client: TestClient,
    user_factory: Callable[..., User],
    organization_factory: Callable[[str], Organization],
) -> None:
    mine = organization_factory("ФОП Мій")
    organization_factory("ФОП Чужий")
    user_factory("scoped@example.com", mine)
    login(client, "scoped@example.com")

    response = client.get("/api/v1/organizations")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(mine.id)]


def test_setting_an_organization_the_user_belongs_to_succeeds(
    client: TestClient,
    user_factory: Callable[..., User],
    organization_factory: Callable[[str], Organization],
) -> None:
    org = organization_factory("ФОП Активний")
    user_factory("active@example.com", org)
    login(client, "active@example.com")

    response = client.post("/api/v1/organizations/active", json={"organization_id": str(org.id)})

    assert response.status_code == 200
    assert client.get("/api/v1/organizations/active").json()["id"] == str(org.id)


def test_setting_a_foreign_organization_is_403(
    client: TestClient,
    user_factory: Callable[..., User],
    organization_factory: Callable[[str], Organization],
) -> None:
    mine = organization_factory("ФОП A")
    theirs = organization_factory("ФОП B")
    user_factory("a@example.com", mine)
    login(client, "a@example.com")

    response = client.post("/api/v1/organizations/active", json={"organization_id": str(theirs.id)})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "organization_forbidden"


def test_a_nonexistent_organization_is_403_not_404(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    # Membership is what is being checked; whether the row exists is not the
    # caller's business, and answering 404 would leak existence.
    user_factory("ghost@example.com")
    login(client, "ghost@example.com")

    response = client.post(
        "/api/v1/organizations/active", json={"organization_id": str(uuid.uuid4())}
    )

    assert response.status_code == 403


def test_active_organization_survives_a_new_request(
    client: TestClient,
    user_factory: Callable[..., User],
    organization_factory: Callable[[str], Organization],
) -> None:
    # It lives on the session row, not in the client's hands, so it must be
    # there on the next request without the client resending anything.
    org = organization_factory("ФОП Стійкий")
    user_factory("persist@example.com", org)
    login(client, "persist@example.com")
    client.post("/api/v1/organizations/active", json={"organization_id": str(org.id)})

    assert client.get("/api/v1/auth/me").json()["active_organization_id"] == str(org.id)


def test_no_active_organization_is_reported_not_guessed(
    client: TestClient,
    user_factory: Callable[..., User],
    organization_factory: Callable[[str], Organization],
) -> None:
    # With several memberships the server must not silently pick one; a wrong
    # guess would post documents into the wrong legal entity.
    first = organization_factory("ФОП Один")
    second = organization_factory("ФОП Два")
    user_factory("many@example.com", first, second)
    login(client, "many@example.com")

    assert client.get("/api/v1/auth/me").json()["active_organization_id"] is None
    assert client.get("/api/v1/organizations/active").status_code == 403


def test_sole_membership_is_selected_on_login(
    client: TestClient,
    user_factory: Callable[..., User],
    organization_factory: Callable[[str], Organization],
) -> None:
    # Exactly one membership leaves nothing to guess, so the round-trip is spared.
    org = organization_factory("ФОП Єдиний")
    user_factory("sole@example.com", org)

    response = login(client, "sole@example.com")

    assert response.json()["active_organization_id"] == str(org.id)


def test_losing_membership_drops_the_active_organization(
    client: TestClient,
    db_session: Session,
    user_factory: Callable[..., User],
    organization_factory: Callable[[str], Organization],
) -> None:
    # Revoking access must take effect on the next request, not at session
    # expiry -- the session row caches the id, not the permission.
    from app.models.identity import Membership

    org = organization_factory("ФОП Відкликаний")
    user = user_factory("revoked@example.com", org)
    login(client, "revoked@example.com")
    assert client.get("/api/v1/organizations/active").status_code == 200

    db_session.query(Membership).filter_by(user_id=user.id).delete()
    db_session.flush()

    assert client.get("/api/v1/organizations/active").status_code == 403


# --------------------------------------------------------------------------- #
# Session storage
# --------------------------------------------------------------------------- #


def test_raw_session_token_is_not_stored(
    client: TestClient, db_session: Session, user_factory: Callable[..., User]
) -> None:
    # A database read must not yield anything an attacker can present as a cookie.
    from app.models.identity import UserSession as SessionModel

    user_factory("hashed@example.com")
    response = login(client, "hashed@example.com")
    raw_token = response.cookies[SESSION_COOKIE]

    stored = db_session.query(SessionModel).one()
    assert stored.token_hash != raw_token
    assert raw_token not in stored.token_hash


def test_each_login_creates_a_distinct_session(
    client: TestClient, db_session: Session, user_factory: Callable[..., User]
) -> None:
    from app.models.identity import UserSession as SessionModel

    user_factory("twice@example.com")
    first = login(client, "twice@example.com").cookies[SESSION_COOKIE]
    client.cookies.clear()
    second = login(client, "twice@example.com").cookies[SESSION_COOKIE]

    assert first != second
    assert db_session.query(SessionModel).count() == 2


def test_expired_session_is_rejected(
    client: TestClient, db_session: Session, user_factory: Callable[..., User]
) -> None:
    import datetime as dt

    from app.models.identity import UserSession as SessionModel

    user_factory("expired@example.com")
    login(client, "expired@example.com")

    stored = db_session.query(SessionModel).one()
    stored.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    db_session.flush()

    assert client.get("/api/v1/auth/me").status_code == 401


def test_idle_session_is_rejected(
    client: TestClient, db_session: Session, user_factory: Callable[..., User]
) -> None:
    import datetime as dt

    from app.core.config import get_settings
    from app.models.identity import UserSession as SessionModel

    user_factory("idle@example.com")
    login(client, "idle@example.com")

    stored = db_session.query(SessionModel).one()
    idle_limit = get_settings().session_idle_seconds
    stored.last_used_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=idle_limit + 60)
    db_session.flush()

    assert client.get("/api/v1/auth/me").status_code == 401


def test_absolute_expiry_does_not_slide_with_use(
    client: TestClient, db_session: Session, user_factory: Callable[..., User]
) -> None:
    from app.models.identity import UserSession as SessionModel

    user_factory("absolute@example.com")
    login(client, "absolute@example.com")
    original = db_session.query(SessionModel).one().expires_at

    client.get("/api/v1/auth/me")
    db_session.expire_all()

    assert db_session.query(SessionModel).one().expires_at == original
