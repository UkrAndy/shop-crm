"""Shared error contract.

One response shape for 401/403/404/409/422 so the generated TypeScript client
has a single thing to narrow on. See `docs/design-docs/design-auth.md` §6.

The distinction that matters is 401 versus 403: 401 means *authenticate and
retry*, 403 means *retrying will not help*. Research §218 requires the frontend
to attempt exactly one coordinated refresh on 401 and never to refresh on 403,
so collapsing the two would break the client's retry logic.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class FieldError(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    fields: list[FieldError] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# Our own wording, deliberately, rather than whatever `http.HTTPStatus` calls
# these. The stdlib phrases are not stable across Python versions — 3.13 renamed
# 422 from "Unprocessable Entity" to "Unprocessable Content" per RFC 9110 — and
# the OpenAPI document is a committed artifact that CI diffs. A description that
# changes with the interpreter would make that check meaningless.
_DESCRIPTIONS = {
    401: "Not authenticated",
    403: "Outside the caller's organization scope",
    404: "Not found within the caller's scope",
    409: "Conflicts with the current state",
    422: "Validation failed",
}


def documented(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries, so the generated client knows the error shape.

    Without this the document advertises only the success body, and the client
    ends up narrowing on a type it was never told about.
    """
    return {
        code: {"model": ErrorResponse, "description": _DESCRIPTIONS.get(code, "Error")}
        for code in status_codes
    }


class AppError(Exception):
    """Base class for errors that map onto the contract above.

    Raised by the service layer, which knows the domain rule that was broken,
    and translated once at the boundary rather than at every call site.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    message: str = "Unexpected error."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message is not None:
            self.message = message


class UnauthenticatedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"
    message = "Authentication required."


class InvalidCredentialsError(AppError):
    """Deliberately identical for an unknown email and a wrong password.

    Telling them apart would make the login form a user-enumeration oracle.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "invalid_credentials"
    message = "Invalid email or password."


class OrganizationForbiddenError(AppError):
    """The caller is authenticated but is not a member of that organization.

    403 rather than 404: the organizations a user may reach are enumerable
    through `GET /organizations` anyway, so 404 would hide the failure from the
    developer without hiding anything from an attacker.
    """

    status_code = status.HTTP_403_FORBIDDEN
    code = "organization_forbidden"
    message = "You do not have access to this organization."


class NoActiveOrganizationError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "no_active_organization"
    message = "Select an active organization first."


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Not found."


class VersionConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "version_conflict"
    message = "The record changed since you loaded it."


class DomainValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"
    message = "Request validation failed."


def _envelope(
    status_code: int, code: str, message: str, fields: list[FieldError] | None = None
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, fields=fields))
    return JSONResponse(status_code=status_code, content=body.model_dump())


# Starlette hands every handler a bare `Exception`, so each one narrows the type
# it was registered for and re-raises anything else rather than guessing.


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc
    return _envelope(exc.status_code, exc.code, exc.message)


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    fields = [
        FieldError(
            field=".".join(str(part) for part in error["loc"]),
            message=error["msg"],
        )
        for error in exc.errors()
    ]
    return _envelope(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        DomainValidationError.code,
        DomainValidationError.message,
        fields,
    )


# What the framework raises before our code runs — unmatched routes, wrong
# methods — so the client never sees a second error shape.
_FRAMEWORK_CODES = {
    status.HTTP_401_UNAUTHORIZED: "unauthenticated",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
}


async def http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    return _envelope(
        exc.status_code,
        _FRAMEWORK_CODES.get(exc.status_code, "error"),
        str(exc.detail),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Route every error the API can emit through the single envelope."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
