"""Password hashing.

Design: `docs/design-docs/design-auth.md` §7. Session handling joins this module
in Issue 7; only the password primitives live here for now.
"""

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
