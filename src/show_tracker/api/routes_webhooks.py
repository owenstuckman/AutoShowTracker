"""Webhook endpoints for Plex, Jellyfin, and Emby media servers.

These are the highest-accuracy detection sources — the media server
knows exactly what is playing. Plex webhooks require Plex Pass;
Jellyfin/Emby webhooks are free.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Form, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class WebhookResponse(BaseModel):
    status: str = "ok"
    event: str = ""
    title: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _extract_plex_media(metadata: dict[str, Any]) -> dict[str, Any] | None:
    """Extract show/episode info from a Plex webhook metadata block."""
    media_type = metadata.get("type")
    if media_type == "episode":
        return {
            "media_type": "episode",
            "show_name": metadata.get("grandparentTitle", ""),
            "season": metadata.get("parentIndex"),
            "episode": metadata.get("index"),
            "episode_title": metadata.get("title", ""),
            "year": metadata.get("year"),
            "tmdb_id": _extract_guid_id(metadata.get("Guid", []), "tmdb"),
            "tvdb_id": _extract_guid_id(metadata.get("Guid", []), "tvdb"),
        }
    elif media_type == "movie":
        return {
            "media_type": "movie",
            "title": metadata.get("title", ""),
            "year": metadata.get("year"),
            "tmdb_id": _extract_guid_id(metadata.get("Guid", []), "tmdb"),
        }
    return None


def _extract_guid_id(guids: list[dict], provider: str) -> int | None:
    """Extract an ID from Plex's Guid array (e.g. tmdb://12345)."""
    for g in guids:
        guid_str = g.get("id", "")
        if guid_str.startswith(f"{provider}://"):
            try:
                return int(guid_str.split("://")[1])
            except (ValueError, IndexError):
                pass
    return None


# ---------------------------------------------------------------------------
# POST /api/webhooks/plex
# ---------------------------------------------------------------------------

@router.post("/plex", response_model=WebhookResponse)
async def plex_webhook(request: Request, payload: str = Form("")) -> WebhookResponse:
    """Receive a Plex webhook event.

    Plex sends webhooks as multipart form data with a JSON ``payload`` field.
    Events: media.play, media.pause, media.resume, media.stop, media.scrobble.
    """
    try:
        data = json.loads(payload) if payload else await request.json()
    except (json.JSONDecodeError, Exception):
        logger.warning("Plex webhook: invalid payload")
        return WebhookResponse(status="error", event="unknown")

    event = data.get("event", "")
    metadata = data.get("Metadata", {})
    media_info = _extract_plex_media(metadata)

    if media_info is None:
        logger.debug("Plex webhook: unsupported media type in event %s", event)
        return WebhookResponse(status="ignored", event=event)

    title = media_info.get("show_name") or media_info.get("title", "")
    logger.info(
        "Plex webhook: %s — %s S%sE%s",
        event,
        title,
        media_info.get("season"),
        media_info.get("episode"),
    )

    # Store as a detection event for the identification pipeline
    _store_webhook_event(request, "plex", event, media_info)

    return WebhookResponse(status="ok", event=event, title=title)


# ---------------------------------------------------------------------------
# POST /api/webhooks/jellyfin
# ---------------------------------------------------------------------------

@router.post("/jellyfin", response_model=WebhookResponse)
async def jellyfin_webhook(request: Request) -> WebhookResponse:
    """Receive a Jellyfin webhook event.

    Jellyfin sends JSON payloads. Uses the Jellyfin Webhook plugin.
    Events: PlaybackStart, PlaybackStop, PlaybackProgress.
    """
    try:
        data = await request.json()
    except Exception:
        logger.warning("Jellyfin webhook: invalid JSON")
        return WebhookResponse(status="error", event="unknown")

    event = data.get("NotificationType", data.get("Event", ""))

    # Extract media info
    media_type = data.get("ItemType", "").lower()
    media_info: dict[str, Any] = {"media_type": media_type}

    if media_type == "episode":
        media_info.update({
            "show_name": data.get("SeriesName", ""),
            "season": data.get("SeasonNumber"),
            "episode": data.get("EpisodeNumber"),
            "episode_title": data.get("Name", ""),
            "year": data.get("Year"),
        })
    elif media_type == "movie":
        media_info.update({
            "title": data.get("Name", ""),
            "year": data.get("Year"),
        })
    else:
        return WebhookResponse(status="ignored", event=event)

    title = media_info.get("show_name") or media_info.get("title", "")
    logger.info("Jellyfin webhook: %s — %s", event, title)

    _store_webhook_event(request, "jellyfin", event, media_info)

    return WebhookResponse(status="ok", event=event, title=title)


# ---------------------------------------------------------------------------
# POST /api/webhooks/emby
# ---------------------------------------------------------------------------

@router.post("/emby", response_model=WebhookResponse)
async def emby_webhook(request: Request) -> WebhookResponse:
    """Receive an Emby webhook event.

    Emby's webhook format is similar to Jellyfin's.
    Events: playback.start, playback.stop, playback.progress.
    """
    try:
        data = await request.json()
    except Exception:
        logger.warning("Emby webhook: invalid JSON")
        return WebhookResponse(status="error", event="unknown")

    event = data.get("Event", "")
    item = data.get("Item", {})
    media_type = item.get("Type", "").lower()

    media_info: dict[str, Any] = {"media_type": media_type}

    if media_type == "episode":
        media_info.update({
            "show_name": item.get("SeriesName", ""),
            "season": item.get("ParentIndexNumber"),
            "episode": item.get("IndexNumber"),
            "episode_title": item.get("Name", ""),
            "year": item.get("ProductionYear"),
        })
    elif media_type == "movie":
        media_info.update({
            "title": item.get("Name", ""),
            "year": item.get("ProductionYear"),
        })
    else:
        return WebhookResponse(status="ignored", event=event)

    title = media_info.get("show_name") or media_info.get("title", "")
    logger.info("Emby webhook: %s — %s", event, title)

    _store_webhook_event(request, "emby", event, media_info)

    return WebhookResponse(status="ok", event=event, title=title)


# ---------------------------------------------------------------------------
# Internal: store webhook events
# ---------------------------------------------------------------------------

def _store_webhook_event(
    request: Request,
    source: str,
    event: str,
    media_info: dict[str, Any],
) -> None:
    """Store a webhook-sourced detection for the identification pipeline.

    Webhook events have the highest confidence since the media server
    knows exactly what is playing.
    """
    db = request.app.state.db

    # Build a raw input string for the identification pipeline
    show_name = media_info.get("show_name") or media_info.get("title", "")
    season = media_info.get("season")
    episode = media_info.get("episode")

    if media_info.get("media_type") == "episode" and season and episode:
        raw_input = f"{show_name} S{season:02d}E{episode:02d}"
    else:
        raw_input = show_name

    # Store as unresolved event with high confidence (webhook = 0.95)
    from show_tracker.storage.models import UnresolvedEvent

    with db.get_watch_session() as session:
        unresolved = UnresolvedEvent(
            raw_input=raw_input,
            source=f"webhook_{source}",
            source_detail=f"{source}:{event}",
            detected_at=_now_iso(),
            best_guess_show=show_name,
            best_guess_season=season,
            best_guess_episode=episode,
            confidence=0.95,
            resolved=False,
        )
        session.add(unresolved)
        session.commit()

    logger.debug("Stored webhook event: %s from %s", raw_input, source)
