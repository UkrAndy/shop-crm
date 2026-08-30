from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OrganizationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class SetActiveOrganizationRequest(BaseModel):
    organization_id: UUID
