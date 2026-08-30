"""Login, logout and the current-session probe.

`/auth/login` is the only endpoint in the API that does not require
authentication (PRD §Authorization).
"""

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentSession, SessionDep
from app.core.config import get_settings
from app.core.errors import documented
from app.schemas.auth import LoginRequest, SessionPublic, UserPublic
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, raw_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_absolute_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


@router.post(
    "/login",
    response_model=SessionPublic,
    responses=documented(401, 422),
)
def login(
    payload: LoginRequest, request: Request, response: Response, db: SessionDep
) -> SessionPublic:
    user = auth_service.authenticate(db, payload.email, payload.password)
    raw_token, user_session = auth_service.start_session(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    _set_session_cookie(response, raw_token)
    return SessionPublic(
        user=UserPublic.model_validate(user),
        active_organization_id=user_session.active_organization_id,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: SessionDep) -> Response:
    """Revoke the session. Succeeds even without one, so a retry is harmless."""
    settings = get_settings()
    auth_service.end_session(db, request.cookies.get(settings.session_cookie_name))
    response.delete_cookie(key=settings.session_cookie_name, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=dict(response.headers))


@router.get(
    "/me",
    response_model=SessionPublic,
    responses=documented(401),
)
def read_current_session(user_session: CurrentSession, db: SessionDep) -> SessionPublic:
    """Who the caller is, for SSR hydration without a login-screen flash.

    The active organization is re-resolved rather than read off the session row,
    so a revoked membership disappears here immediately.
    """
    organization = auth_service.get_active_organization(db, user_session)
    return SessionPublic(
        user=UserPublic.model_validate(user_session.user),
        active_organization_id=organization.id if organization else None,
    )
