"""Main detection loop / media identification service.

:class:`DetectionService` is the central orchestrator of the collection
layer.  It merges signals from three sources — ActivityWatch polling,
OS media session events (SMTC/MPRIS), and browser extension HTTP events
— performs deduplication, and feeds results to downstream processing
(parsing, identification, confidence routing).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from show_tracker.detection.activitywatch import (
    ActivityWatchClient,
    EventPoller,
    MockActivityWatchClient,
    discover_media_relevant_buckets,
)
from show_tracker.detection.browser_handler import BrowserEventHandler, BrowserMediaEvent
from show_tracker.detection.media_session import (
    MediaSessionEvent,
    MediaSessionListener,
    PlaybackStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Confidence routing
# ---------------------------------------------------------------------------


class ConfidenceTier(Enum):
    """How a detection result should be routed based on its confidence."""

    AUTO_LOG = "auto_log"  # >= auto_log_threshold
    LOG_AND_FLAG = "log_and_flag"  # >= review_threshold, < auto_log_threshold
    UNRESOLVED = "unresolved"  # < review_threshold


# ---------------------------------------------------------------------------
# Internal detection event (unified across all sources)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DetectionEvent:
    """A unified detection event produced by any source.

    Downstream consumers (parsing, identification) operate on this
    type regardless of whether the original signal came from
    ActivityWatch, SMTC/MPRIS, or the browser extension.
    """

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = ""  # "activitywatch_window", "activitywatch_web", "smtc", "mpris", "browser"

    # Raw text signals (at least one will be populated).
    window_title: str = ""
    app_name: str = ""
    url: str = ""
    page_title: str = ""

    # Structured metadata (may be empty if not available).
    media_title: str = ""
    artist: str = ""
    album_title: str = ""
    show_name: str = ""
    season_number: int | None = None
    episode_number: int | None = None

    # Playback state.
    is_playing: bool = True
    playback_status: PlaybackStatus = PlaybackStatus.UNKNOWN

    # Browser metadata provenance.
    metadata_source: str = ""

    # Raw data for debugging.
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Currently-watching state (for deduplication / heartbeat)
# ---------------------------------------------------------------------------


@dataclass
class ActiveWatch:
    """Tracks the "currently watching" state for a single episode."""

    detection_key: str  # deduplication key (e.g. "<source>:<title>")
    first_seen: float = field(default_factory=time.monotonic)
    last_heartbeat: float = field(default_factory=time.monotonic)
    heartbeat_count: int = 0
    last_event: DetectionEvent | None = None

    def touch(self, event: DetectionEvent) -> None:
        """Record a new heartbeat for this watch."""
        self.last_heartbeat = time.monotonic()
        self.heartbeat_count += 1
        self.last_event = event


# Type alias for the callback that receives fully processed detection events.
DetectionResultCallback = Callable[[DetectionEvent, ConfidenceTier], None]


# ---------------------------------------------------------------------------
# Detection service
# ---------------------------------------------------------------------------

# Default timing constants (seconds).
_AW_POLL_INTERVAL = 10
_HEARTBEAT_INTERVAL = 30
_GRACE_PERIOD = 120  # 2 minutes of silence before marking stopped


class DetectionService:
    """Central orchestrator for the collection layer.

    Responsibilities:

    * Polls ActivityWatch every ``polling_interval`` seconds.
    * Receives SMTC/MPRIS events in real time (event-driven).
    * Receives browser extension events pushed via :meth:`handle_browser_event`.
    * Deduplicates overlapping signals for the same episode.
    * Maintains a grace period before finalising a watch session.
    * Emits heartbeats to extend active watch events.
    * Routes results by confidence tier.

    Parameters
    ----------
    aw_client:
        ActivityWatch REST client (real or mock).
    media_listener:
        Platform-specific media session listener, or *None* to skip.
    polling_interval:
        Seconds between AW poll cycles (default 10).
    heartbeat_interval:
        Seconds between heartbeat emissions (default 30).
    grace_period:
        Seconds of no signal before a watch is finalised (default 120).
    auto_log_threshold:
        Confidence >= this value is auto-logged.
    review_threshold:
        Confidence >= this value (but below auto_log) is logged and flagged.
    """

    def __init__(
        self,
        aw_client: ActivityWatchClient | MockActivityWatchClient | None = None,
        media_listener: MediaSessionListener | None = None,
        *,
        polling_interval: int = _AW_POLL_INTERVAL,
        heartbeat_interval: int = _HEARTBEAT_INTERVAL,
        grace_period: int = _GRACE_PERIOD,
        auto_log_threshold: float = 0.9,
        review_threshold: float = 0.7,
    ) -> None:
        self._aw_client = aw_client
        self._media_listener = media_listener
        self._browser_handler = BrowserEventHandler()

        self._polling_interval = polling_interval
        self._heartbeat_interval = heartbeat_interval
        self._grace_period = grace_period
        self._auto_log_threshold = auto_log_threshold
        self._review_threshold = review_threshold

        # Internal state.
        self._poller: EventPoller | None = None
        self._bucket_ids: dict[str, list[str]] = {"window": [], "web": []}
        self._active_watches: dict[str, ActiveWatch] = {}
        self._event_queue: asyncio.Queue[DetectionEvent] = asyncio.Queue()
        self._result_callbacks: list[DetectionResultCallback] = []
        self._tasks: list[asyncio.Task[None]] = []
        self._running: bool = False

    # -- Public API ---------------------------------------------------------

    def register_result_callback(self, callback: DetectionResultCallback) -> None:
        """Register a callback invoked for every processed detection result."""
        self._result_callbacks.append(callback)

    async def start(self) -> None:
        """Start all detection loops and listeners."""
        if self._running:
            return

        self._running = True

        # Initialise AW poller and discover buckets.
        if self._aw_client is not None:
            self._poller = EventPoller(self._aw_client)
            try:
                self._bucket_ids = discover_media_relevant_buckets(self._aw_client)
                logger.info("Discovered AW buckets: %s", self._bucket_ids)
            except Exception:
                logger.warning("Could not discover AW buckets — will retry on poll")

        # Start media session listener with callback into our queue.
        if self._media_listener is not None:
            self._media_listener.register_callback(self._on_media_session_event)
            try:
                await self._media_listener.start()
            except Exception:
                logger.exception("Failed to start media session listener")

        # Launch background tasks.
        self._tasks.append(asyncio.create_task(self._aw_poll_loop()))
        self._tasks.append(asyncio.create_task(self._event_processor()))
        self._tasks.append(asyncio.create_task(self._grace_period_sweeper()))

        logger.info("DetectionService started")

    async def stop(self) -> None:
        """Stop all background tasks and listeners."""
        self._running = False

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        if self._media_listener is not None:
            try:
                await self._media_listener.stop()
            except Exception:
                logger.exception("Error stopping media session listener")

        # Finalize all active watches.
        for key in list(self._active_watches):
            self._finalize_watch(key)

        logger.info("DetectionService stopped")

    def handle_browser_event(self, payload: dict[str, Any]) -> BrowserMediaEvent:
        """Process an incoming browser extension event (HTTP endpoint handler).

        Converts the raw payload into a :class:`BrowserMediaEvent`,
        enqueues a :class:`DetectionEvent`, and returns the browser event
        for the HTTP response.
        """
        browser_event = self._browser_handler.handle_event(payload)
        detection = self._browser_event_to_detection(browser_event)
        self._event_queue.put_nowait(detection)
        return browser_event

    # -- ActivityWatch polling -----------------------------------------------

    async def _aw_poll_loop(self) -> None:
        """Periodically poll ActivityWatch for new events."""
        while self._running:
            try:
                await asyncio.sleep(self._polling_interval)
                if self._poller is None:
                    continue
                await self._poll_aw_buckets()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Error in AW poll loop")

    async def _poll_aw_buckets(self) -> None:
        """Fetch new events from all known AW buckets."""
        if self._poller is None:
            return

        for bucket_id in self._bucket_ids.get("window", []):
            try:
                events = self._poller.poll_new_events(bucket_id)
                for ev in events:
                    detection = self._aw_window_event_to_detection(ev)
                    self._event_queue.put_nowait(detection)
            except Exception:
                logger.debug("Failed to poll bucket %s", bucket_id, exc_info=True)

        for bucket_id in self._bucket_ids.get("web", []):
            try:
                events = self._poller.poll_new_events(bucket_id)
                for ev in events:
                    detection = self._aw_web_event_to_detection(ev)
                    self._event_queue.put_nowait(detection)
            except Exception:
                logger.debug("Failed to poll bucket %s", bucket_id, exc_info=True)

    # -- Media session callback -----------------------------------------------

    def _on_media_session_event(self, event: MediaSessionEvent) -> None:
        """Callback invoked by SMTC/MPRIS listeners."""
        import sys as _sys

        source = "smtc" if _sys.platform == "win32" else "mpris"
        detection = DetectionEvent(
            timestamp=event.timestamp,
            source=source,
            media_title=event.title,
            artist=event.artist,
            album_title=event.album_title,
            app_name=event.source_app,
            is_playing=event.playback_status == PlaybackStatus.PLAYING,
            playback_status=event.playback_status,
            raw={
                "player_name": event.player_name,
                "source_app": event.source_app,
            },
        )
        self._event_queue.put_nowait(detection)

    # -- Event processing loop -----------------------------------------------

    async def _event_processor(self) -> None:
        """Consume events from the queue and process them."""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0,
                )
            except (TimeoutError, asyncio.CancelledError):
                if not self._running:
                    return
                continue

            try:
                self._process_event(event)
            except Exception:
                logger.exception("Error processing detection event")

    def _process_event(self, event: DetectionEvent) -> None:
        """Run a single detection event through deduplication and routing."""
        key = self._dedup_key(event)
        if not key:
            return

        now = time.monotonic()

        if key in self._active_watches:
            # Heartbeat: extend the existing watch.
            watch = self._active_watches[key]
            old_heartbeat = watch.last_heartbeat
            watch.touch(event)

            if now - old_heartbeat >= self._heartbeat_interval:
                self._emit_heartbeat(event, watch)
        else:
            # New watch session.
            if not event.is_playing and event.playback_status == PlaybackStatus.STOPPED:
                # Don't start a watch for a stopped event.
                return

            watch = ActiveWatch(detection_key=key, last_event=event)
            self._active_watches[key] = watch
            logger.info("New watch detected: %s", key)

            # Emit initial detection to callbacks.
            self._route_event(event)

    def _emit_heartbeat(self, event: DetectionEvent, watch: ActiveWatch) -> None:
        """Emit a heartbeat for an ongoing watch."""
        self._route_event(event)

    # -- Grace period sweeper ------------------------------------------------

    async def _grace_period_sweeper(self) -> None:
        """Periodically check for stale watches that should be finalized."""
        while self._running:
            try:
                await asyncio.sleep(self._polling_interval)
                now = time.monotonic()
                stale_keys = [
                    key
                    for key, watch in self._active_watches.items()
                    if now - watch.last_heartbeat > self._grace_period
                ]
                for key in stale_keys:
                    self._finalize_watch(key)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Error in grace period sweeper")

    def _finalize_watch(self, key: str) -> None:
        """Mark a watch session as stopped and remove it from active tracking."""
        watch = self._active_watches.pop(key, None)
        if watch is None:
            return
        logger.info(
            "Finalized watch: %s (heartbeats=%d, duration=%.0fs)",
            key,
            watch.heartbeat_count,
            time.monotonic() - watch.first_seen,
        )

    # -- Confidence routing --------------------------------------------------

    def _route_event(self, event: DetectionEvent) -> None:
        """Assign a preliminary confidence tier and invoke result callbacks.

        Note: The real confidence score comes from the identification layer.
        Here we assign a *preliminary* tier based on how much structured
        metadata we have — downstream layers will refine it.
        """
        confidence = self._estimate_confidence(event)
        tier = self._confidence_tier(confidence)

        for callback in self._result_callbacks:
            try:
                callback(event, tier)
            except Exception:
                logger.exception("Error in result callback")

    def _estimate_confidence(self, event: DetectionEvent) -> float:
        """Heuristic pre-identification confidence based on available metadata.

        This is intentionally coarse; the identification layer will produce
        the real score.
        """
        score = 0.0

        # Structured show/episode metadata is the strongest signal.
        if event.show_name and event.season_number is not None and event.episode_number is not None:
            score = 0.85

        # A media title from SMTC/MPRIS is moderately strong.
        elif event.media_title:
            score = 0.6

        # Window title or page title is weaker.
        elif event.window_title or event.page_title:
            score = 0.4

        # URL alone is minimal.
        elif event.url:
            score = 0.3

        # Boost if we know the app is a known media player.
        if event.app_name and event.app_name.lower() in _KNOWN_MEDIA_APPS:
            score = min(score + 0.1, 1.0)

        return score

    def _confidence_tier(self, confidence: float) -> ConfidenceTier:
        if confidence >= self._auto_log_threshold:
            return ConfidenceTier.AUTO_LOG
        if confidence >= self._review_threshold:
            return ConfidenceTier.LOG_AND_FLAG
        return ConfidenceTier.UNRESOLVED

    # -- Deduplication -------------------------------------------------------

    @staticmethod
    def _dedup_key(event: DetectionEvent) -> str:
        """Produce a deduplication key for an event.

        Events that would represent the same episode/content should
        produce the same key.
        """
        parts: list[str] = []

        # Prefer structured metadata.
        if event.show_name:
            parts.append(event.show_name.lower())
            if event.season_number is not None:
                parts.append(f"s{event.season_number:02d}")
            if event.episode_number is not None:
                parts.append(f"e{event.episode_number:02d}")
        elif event.media_title:
            parts.append(event.media_title.lower().strip())
        elif event.window_title:
            parts.append(event.window_title.lower().strip())
        elif event.page_title:
            parts.append(event.page_title.lower().strip())
        elif event.url:
            parts.append(event.url)

        if not parts:
            return ""

        return "|".join(parts)

    # -- Conversion helpers --------------------------------------------------

    @staticmethod
    def _aw_window_event_to_detection(raw: dict[str, Any]) -> DetectionEvent:
        data = raw.get("data", {})
        ts_str = raw.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            ts = datetime.now(UTC)

        return DetectionEvent(
            timestamp=ts,
            source="activitywatch_window",
            window_title=data.get("title", ""),
            app_name=data.get("app", ""),
            is_playing=True,
            raw=raw,
        )

    @staticmethod
    def _aw_web_event_to_detection(raw: dict[str, Any]) -> DetectionEvent:
        data = raw.get("data", {})
        ts_str = raw.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            ts = datetime.now(UTC)

        return DetectionEvent(
            timestamp=ts,
            source="activitywatch_web",
            url=data.get("url", ""),
            page_title=data.get("title", ""),
            is_playing=data.get("audible", False),
            raw=raw,
        )

    @staticmethod
    def _browser_event_to_detection(browser_event: BrowserMediaEvent) -> DetectionEvent:
        return DetectionEvent(
            timestamp=browser_event.timestamp,
            source="browser",
            url=browser_event.url,
            page_title=browser_event.title,
            media_title=browser_event.title,
            show_name=browser_event.show_name,
            season_number=browser_event.season_number,
            episode_number=browser_event.episode_number,
            is_playing=browser_event.is_playing,
            metadata_source=browser_event.metadata_source,
            raw=browser_event.raw_payload,
        )


# Known media player app names (lowercase) for confidence boosting.
_KNOWN_MEDIA_APPS: frozenset[str] = frozenset(
    {
        "vlc",
        "vlc media player",
        "mpv",
        "mpc-hc",
        "mpc-be",
        "plex",
        "plex htpc",
        "kodi",
        "jellyfin",
        "emby",
        "infuse",
        "iina",
        "celluloid",
        "totem",
        "smplayer",
        "potplayer",
        "kmplayer",
    }
)
