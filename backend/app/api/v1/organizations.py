"""Organization listing and active-organization selection."""

from fastapi import APIRouter

from app.api.deps import CurrentOrganization, CurrentSession, CurrentUser, SessionDep
from app.core.errors import documented
from app.schemas.organization import OrganizationPublic, SetActiveOrganizationRequest
from app.services import auth as auth_service

router = APIRouter(prefix="/organizations", tags=["organizations"])

_PROTECTED = documented(401, 403)


@router.get("", response_model=list[OrganizationPublic], responses=_PROTECTED)
def list_organizations(user: CurrentUser, db: SessionDep) -> list[OrganizationPublic]:
    organizations = auth_service.list_organizations(db, user)
    return [OrganizationPublic.model_validate(item) for item in organizations]


@router.get("/active", response_model=OrganizationPublic, responses=_PROTECTED)
def read_active_organization(organization: CurrentOrganization) -> OrganizationPublic:
    """403 when nothing is selected — the caller must choose, not be guessed for."""
    return OrganizationPublic.model_validate(organization)


@router.post("/active", response_model=OrganizationPublic, responses=_PROTECTED)
def set_active_organization(
    payload: SetActiveOrganizationRequest, user_session: CurrentSession, db: SessionDep
) -> OrganizationPublic:
    """Store the selection on the session row.

    The body names a candidate; membership decides. A client cannot widen its
    own scope by sending a different id.
    """
    organization = auth_service.set_active_organization(db, user_session, payload.organization_id)
    return OrganizationPublic.model_validate(organization)
