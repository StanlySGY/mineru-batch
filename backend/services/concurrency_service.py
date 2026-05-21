"""Concurrency service — business logic for concurrency management."""
from fastapi import HTTPException


def get_concurrency_impl(max_concurrency: int) -> dict:
    """Get current concurrency setting."""
    return {"concurrency": max_concurrency}


def validate_concurrency(n: int) -> int:
    """Validate and return concurrency value."""
    if not isinstance(n, int) or n < 1 or n > 20:
        raise HTTPException(400, "concurrency must be 1-20")
    return n
