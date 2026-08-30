"""Request-scoped dependencies shared by every v1 router.

`CurrentOrganization` is the one every later feature router depends on: it is
where organization scope stops being advisory. Frontend route middleware is UX
only and never a substitute (research §624).
"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import NoActiveOrganizationError
from app.models.identity import Organization, User, UserSession
from app.services import auth as auth_service

SessionDep = Annotated[Session, Depends(get_session)]


def session_token(request: Request) -> str | None:
    return request.cookies.get(get_settings().session_cookie_name)


def current_session(request: Request, db: SessionDep) -> UserSession:
    return auth_service.resolve_session(db, session_token(request))


CurrentSession = Annotated[UserSession, Depends(current_session)]


def current_user(user_session: CurrentSession) -> User:
    return user_session.user


CurrentUser = Annotated[User, Depends(current_user)]


def current_organization(user_session: CurrentSession, db: SessionDep) -> Organization:
    """The organization every scoped query must filter on.

    Raises 403 when none is selected or the membership behind it is gone, rather
    than falling back to a default — a wrong guess would write documents into
    the wrong legal entity.
    """
    organization = auth_service.get_active_organization(db, user_session)
    if organization is None:
        raise NoActiveOrganizationError
    return organization


CurrentOrganization = Annotated[Organization, Depends(current_organization)]
