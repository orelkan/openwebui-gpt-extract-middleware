"""Liveness endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Report that the process is alive. Makes no external calls."""
    return {"status": "ok"}
