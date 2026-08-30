"""Pydantic API schemas.

These are the API contract, not persistence models (research §379). The
generated TypeScript client is built from the OpenAPI document they produce, so
a field added here reaches the frontend — including one that should not.
"""
