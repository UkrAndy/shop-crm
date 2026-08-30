"""Password hashing and session tokens.

Design: `docs/design-docs/design-auth.md` §7.
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Library defaults on purpose. argon2-cffi tracks the RFC 9106 recommendations,
# so hard-coding our own cost parameters would freeze them at their 2026 values.
# `password_needs_rehash` below migrates stored hashes as those defaults rise.
_hasher = PasswordHasher()

# Verified on login when the email is unknown, so that a missing account costs
# roughly the same wall-clock time as a wrong password and the endpoint does not
# become a user-enumeration oracle.
_DUMMY_HASH = _hasher.hash("dummy-password-for-constant-time-login")


def hash_password(password: str) -> str:
    """Return an Argon2id hash, salt and parameters included in the string."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Check a password against its hash. False on any mismatch, never an exception.

    A malformed stored hash is a data-integrity problem, not an authentication
    success, so it is treated as a failed verification rather than propagated.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True when the hash was produced with parameters weaker than today's defaults."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        # Unparseable, so it cannot be verified against either; rewriting it on
        # the next successful login is the only way it gets repaired.
        return True


def verify_dummy_password(password: str) -> None:
    """Burn the cost of one verification for an email that has no account."""
    verify_password(_DUMMY_HASH, password)


# 32 bytes = 256 bits. Guessing is not a threat model at that width.
_SESSION_TOKEN_BYTES = 32


def generate_session_token() -> str:
    """A fresh session credential. Handed to the client once, never stored raw."""
    return secrets.token_urlsafe(_SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """Digest used as the lookup key for a session row.

    SHA-256, not Argon2, and deliberately so: the token already carries 256 bits
    of entropy, so there is no dictionary to slow down, while this runs on every
    authenticated request. A slow hash here would buy nothing and cost latency.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
