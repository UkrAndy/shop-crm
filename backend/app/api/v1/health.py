from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.db import get_session

router = APIRouter(prefix="/health", tags=["health"])

SessionDep = Annotated[Session, Depends(get_session)]


class LivenessResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["up", "down"]
    detail: str | None = None


@router.get("/live", response_model=LivenessResponse)
def liveness() -> LivenessResponse:
    """Process is up. Does not touch dependencies."""
    return LivenessResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
def readiness(session: SessionDep) -> ReadinessResponse:
    """Reports dependency health. Returns 200 with `degraded` when the database
    is unreachable so the scaffold stays inspectable before Postgres exists."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        return ReadinessResponse(
            status="degraded", database="down", detail=str(exc.__cause__ or exc)
        )
    return ReadinessResponse(status="ok", database="up")
