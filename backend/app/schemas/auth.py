from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    # Bounded so a multi-megabyte body cannot turn one login attempt into an
    # Argon2 denial of service.
    password: str = Field(min_length=1, max_length=1024)


class UserPublic(BaseModel):
    """Everything about a user the API is willing to disclose.

    The stored credential is absent by construction rather than by filtering:
    there is no code path that could include it. `test_identity.py` asserts the
    field name appears nowhere in the OpenAPI document — including in prose like
    this one — so the guard cannot be defeated by a description.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str


class SessionPublic(BaseModel):
    user: UserPublic
    active_organization_id: UUID | None = None
