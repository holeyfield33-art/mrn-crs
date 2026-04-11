"""Shared FastAPI dependencies – client singletons and auth available via Depends()."""

from __future__ import annotations

import hmac
from functools import lru_cache

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.clients.aletheia_client import AletheiaClient
from src.clients.geometric_client import GeometricClient
from src.clients.mneme_client import MnemeClient
from src.config import settings

# --------------------------------------------------------------------------- #
# Client singletons
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=1)
def get_aletheia() -> AletheiaClient:
    return AletheiaClient()


@lru_cache(maxsize=1)
def get_geometric() -> GeometricClient:
    return GeometricClient()


@lru_cache(maxsize=1)
def get_mneme() -> MnemeClient:
    return MnemeClient()


# --------------------------------------------------------------------------- #
# API key auth
# --------------------------------------------------------------------------- #

_bearer = HTTPBearer(auto_error=False)


def _valid_keys() -> set[str]:
    raw = settings.crs_api_keys.strip()
    if not raw:
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}


async def verify_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = None,
) -> str | None:
    """Validate the Bearer token against CRS_API_KEYS.

    Can be called directly from middleware (no Depends) by passing the request.
    Returns the key prefix (first 8 chars) as client_id for logging.
    If CRS_API_KEYS is empty, auth is disabled and None is returned.
    """
    keys = _valid_keys()
    if not keys:
        return None  # auth disabled

    # Extract credentials from the request header
    if credentials is None:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer ") and len(auth) > 7:
            token = auth[7:]
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        token = credentials.credentials

    if not any(hmac.compare_digest(token, k) for k in keys):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token[:8]
