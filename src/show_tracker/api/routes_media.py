"""Media event API routes.

Receives real-time playback events from the browser extension and
exposes the current detection state.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request

from show_tracker.api.schemas import (
    CurrentlyWatchingResponse,
    MediaEventIn,
    MediaEventResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["media"])

# In-memory state for the current detection — lightweight, no persistence needed.
_current_state: dict = {}


@router.post("/media-event", response_model=MediaEventResponse)
async def receive_media_event(
    event: MediaEventIn,
    request: Request,
) -> MediaEventResponse:
    """Receive a media event from the browser extension.

    The extension sends play/pause/ended/heartbeat/page_load events with
    rich metadata scraped from the page.  This endpoint updates the
    currently-watching state and feeds the event into the detection
    service for identification and persistence.
    """
    global _current_state

    _current_state = {
        "event_type": event.type,
        "tab_url": event.tab_url,
        "title": event.metadata.title,
        "position": event.position,
        "duration": event.duration,
        "last_update": event.timestamp or int(time.time() * 1000),
        "metadata": event.metadata.model_dump(by_alias=True),
    }

    # Mark as not watching on pause/ended
    if event.type in ("pause", "ended"):
        _current_state["is_watching"] = False
    else:
        _current_state["is_watching"] = True

    # Feed event into the detection service for dedup, routing, and
    # downstream identification/persistence.
    detection = getattr(request.app.state, "detection", None)
    if detection is not None:
        try:
            payload = event.model_dump(by_alias=True)
            detection.handle_browser_event(payload)
        except Exception:
            logger.exception("Error feeding browser event to DetectionService")

    return MediaEventResponse(status="ok", message=f"Received {event.type} event")


@router.get("/currently-watching", response_model=CurrentlyWatchingResponse)
async def get_currently_watching() -> CurrentlyWatchingResponse:
    """Return the current detection state.

    Returns whether the user is actively watching something and, if so,
    basic metadata about the current playback.
    """
    if not _current_state:
        return CurrentlyWatchingResponse(is_watching=False)

    # Consider stale after 2 minutes without a heartbeat
    last_update = _current_state.get("last_update", 0)
    now_ms = int(time.time() * 1000)
    stale = (now_ms - last_update) > 120_000

    if stale:
        return CurrentlyWatchingResponse(is_watching=False)

    return CurrentlyWatchingResponse(
        is_watching=_current_state.get("is_watching", False),
        event_type=_current_state.get("event_type"),
        tab_url=_current_state.get("tab_url"),
        title=_current_state.get("title"),
        position=_current_state.get("position"),
        duration=_current_state.get("duration"),
        last_update=_current_state.get("last_update"),
    )
