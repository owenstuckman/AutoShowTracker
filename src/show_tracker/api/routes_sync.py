"""Trakt sync API routes.

Exposes endpoints for Trakt.tv OAuth device authentication, connection
status, manual history import, and disconnection.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from show_tracker.sync.trakt import TraktClient, TraktError, import_from_trakt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync/trakt", tags=["sync"])


def _get_trakt_client(request: Request) -> TraktClient:
    """Build a TraktClient from app settings."""
    settings = request.app.state.settings
    if not settings.trakt_client_id or not settings.trakt_client_secret:
        raise HTTPException(
            status_code=503,
            detail="Trakt client_id / client_secret not configured.",
        )
    return TraktClient(
        client_id=settings.trakt_client_id,
        client_secret=settings.trakt_client_secret,
    )


# ---------------------------------------------------------------------------
# POST /api/sync/trakt/auth — Start device auth flow
# ---------------------------------------------------------------------------

@router.post("/auth")
async def start_auth(request: Request) -> dict[str, str]:
    """Start the Trakt OAuth2 device flow.

    Returns the user_code and verification_url the user must visit,
    plus the device_code the frontend needs to poll with.
    """
    client = _get_trakt_client(request)
    try:
        result = client.start_device_auth()
        return {
            "user_code": result["user_code"],
            "verification_url": result["verification_url"],
            "device_code": result["device_code"],
        }
    except TraktError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        client.close()


# ---------------------------------------------------------------------------
# GET /api/sync/trakt/status — Check connection status
# ---------------------------------------------------------------------------

@router.get("/status")
async def connection_status(request: Request) -> dict[str, bool]:
    """Check whether Trakt is currently authenticated."""
    client = _get_trakt_client(request)
    try:
        return {"connected": client.is_authenticated}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# POST /api/sync/trakt/sync — Trigger manual import from Trakt
# ---------------------------------------------------------------------------

@router.post("/sync")
async def manual_sync(request: Request) -> dict[str, Any]:
    """Import watch history from Trakt into the local database."""
    client = _get_trakt_client(request)
    try:
        if not client.is_authenticated:
            raise HTTPException(
                status_code=401,
                detail="Trakt is not authenticated. Complete device auth first.",
            )
        db = request.app.state.db
        stats = import_from_trakt(client, db)
        return {"imported": stats["imported"]}
    except TraktError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        client.close()


# ---------------------------------------------------------------------------
# DELETE /api/sync/trakt/disconnect — Remove stored token
# ---------------------------------------------------------------------------

@router.delete("/disconnect")
async def disconnect(request: Request) -> dict[str, str]:
    """Delete the stored Trakt OAuth token, disconnecting the account."""
    client = _get_trakt_client(request)
    try:
        if client.token_path.exists():
            client.token_path.unlink()
            logger.info("Trakt token deleted: %s", client.token_path)
        return {"status": "disconnected"}
    finally:
        client.close()
