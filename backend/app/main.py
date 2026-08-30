from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, goods_receipts, health, organizations, products
from app.core.config import get_settings
from app.core.errors import documented, register_exception_handlers

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    # FastAPI documents 422 with its own `HTTPValidationError`, but our handler
    # replaces that body with the shared envelope. Declaring it here keeps the
    # contract honest for every route at once — otherwise the generated
    # TypeScript client narrows on a shape the API never sends.
    responses=documented(422),
)

app.add_middleware(
    CORSMiddleware,
    # An explicit allowlist, never "*": the session cookie is only sent
    # cross-origin for origins named here, and `allow_credentials` with a
    # wildcard is rejected by browsers anyway.
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(organizations.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(goods_receipts.router, prefix="/api/v1")
app.include_router(goods_receipts.counterparties_router, prefix="/api/v1")
