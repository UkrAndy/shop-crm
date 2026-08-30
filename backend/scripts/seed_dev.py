"""Idempotent development / E2E seed.

There is no registration endpoint — the PRD puts it out of scope — so the first
user has to come from somewhere. This is that somewhere, for local development
and for the E2E suite, which needs deterministic credentials.

    uv run python scripts/seed_dev.py

Creates two organizations and two users:

| user               | memberships | proves                                  |
|--------------------|-------------|-----------------------------------------|
| owner@example.com  | ФОП Альфа   | sole membership is auto-selected        |
| multi@example.com  | Альфа, Бета | the server refuses to guess between two |

`example.com` is RFC 2606's documentation domain. A `.local` address will *not*
work: `email-validator`, behind Pydantic's `EmailStr`, rejects special-use and
reserved names, so `/auth/login` answers 422 before it ever reaches the
password check. The check below fails the seed rather than leaving accounts
nobody can log into.

Never run this against anything but a development database: the passwords are
published in this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/seed_dev.py` from the backend root without installing
# the package in editable mode first.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.identity import Membership, Organization, User  # noqa: E402
from app.schemas.auth import LoginRequest  # noqa: E402

SEED_PASSWORD = "seed-password-123"

ORGANIZATION_ALPHA = "ФОП Альфа"
ORGANIZATION_BETA = "ФОП Бета"

SOLE_MEMBER_EMAIL = "owner@example.com"
MULTI_MEMBER_EMAIL = "multi@example.com"


def _reject_unusable_addresses() -> None:
    """Fail loudly if a seeded address would be refused by `/auth/login`.

    Seeding an account that cannot log in wastes whoever debugs it next; the
    login schema is the authority, so it is what gets asked.
    """
    LoginRequest(email=SOLE_MEMBER_EMAIL, password=SEED_PASSWORD)
    LoginRequest(email=MULTI_MEMBER_EMAIL, password=SEED_PASSWORD)


def main() -> None:
    _reject_unusable_addresses()

    with SessionLocal() as session:
        organizations: dict[str, Organization] = {}
        for name in (ORGANIZATION_ALPHA, ORGANIZATION_BETA):
            organization = session.scalar(select(Organization).where(Organization.name == name))
            if organization is None:
                organization = Organization(name=name)
                session.add(organization)
                session.flush()
            organizations[name] = organization

        wanted = {
            SOLE_MEMBER_EMAIL: [ORGANIZATION_ALPHA],
            MULTI_MEMBER_EMAIL: [ORGANIZATION_ALPHA, ORGANIZATION_BETA],
        }

        for email, organization_names in wanted.items():
            user = session.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(email=email, password_hash=hash_password(SEED_PASSWORD))
                session.add(user)
                session.flush()

            for name in organization_names:
                organization = organizations[name]
                exists = session.scalar(
                    select(Membership).where(
                        Membership.user_id == user.id,
                        Membership.organization_id == organization.id,
                    )
                )
                if exists is None:
                    session.add(Membership(user_id=user.id, organization_id=organization.id))

        session.commit()
        print(f"seeded {SOLE_MEMBER_EMAIL} and {MULTI_MEMBER_EMAIL}")


if __name__ == "__main__":
    main()
