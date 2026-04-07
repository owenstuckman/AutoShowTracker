"""macOS media session listener using MPNowPlayingInfoCenter.

Polls MPNowPlayingInfoCenter.defaultCenter() on a short interval to detect
title/playback changes, then emits MediaSessionEvent to registered callbacks.
This implements the same MediaSessionListener protocol as the Windows SMTC
and Linux MPRIS listeners.

Requires: pip install show-tracker[macos]  (pyobjc-framework-MediaPlayer)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from typing import Any

from show_tracker.detection.media_session import (
    MediaSessionCallback,
    MediaSessionEvent,
    PlaybackStatus,
)

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2.0  # seconds between MPNowPlayingInfoCenter polls

# MPNowPlayingInfo dictionary keys
_KEY_TITLE = "MPMediaItemPropertyTitle"
_KEY_ARTIST = "MPMediaItemPropertyArtist"
_KEY_ALBUM = "MPMediaItemPropertyAlbumTitle"
_KEY_PLAYBACK_RATE = "MPNowPlayingInfoPropertyPlaybackRate"

# Platform guard ------------------------------------------------------------

if sys.platform != "darwin":
    _MEDIAPLAYER_AVAILABLE = False
else:
    try:
        import MediaPlayer  # type: ignore[import-not-found,import-untyped]  # noqa: F401

        _MEDIAPLAYER_AVAILABLE = True
    except ImportError:
        _MEDIAPLAYER_AVAILABLE = False


def _map_playback_rate(rate: Any) -> PlaybackStatus:
    """Convert an MPNowPlayingInfoPropertyPlaybackRate value to PlaybackStatus."""
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return PlaybackStatus.UNKNOWN
    if r > 0:
        return PlaybackStatus.PLAYING
    if r == 0:
        return PlaybackStatus.PAUSED
    return PlaybackStatus.STOPPED


class MacOSMediaListener:
    """Polls MPNowPlayingInfoCenter to detect media playback changes on macOS.

    Emits a :class:`~show_tracker.detection.media_session.MediaSessionEvent`
    whenever the now-playing title or playback status changes.

    Usage::

        listener = MacOSMediaListener()
        listener.register_callback(my_handler)
        await listener.start()
        # ...
        await listener.stop()

    Raises
    ------
    RuntimeError
        If instantiated on a non-macOS platform.
    ImportError
        If ``pyobjc-framework-MediaPlayer`` is not installed.
    """

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError(
                f"MacOSMediaListener is only supported on macOS. Current platform: {sys.platform!r}"
            )
        if not _MEDIAPLAYER_AVAILABLE:
            raise ImportError(
                "The 'pyobjc-framework-MediaPlayer' package is required for macOS "
                "media detection. Install it with: pip install show-tracker[macos]"
            )

        self._callbacks: list[MediaSessionCallback] = []
        self._running: bool = False
        self._poll_task: asyncio.Task[None] | None = None
        self._last_title: str = ""
        self._last_status: PlaybackStatus = PlaybackStatus.UNKNOWN

    # -- Public API ---------------------------------------------------------

    def register_callback(self, callback: MediaSessionCallback) -> None:
        """Register a function to be invoked on each media state change."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Begin polling MPNowPlayingInfoCenter for media changes."""
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("macOS media listener started (poll interval: %.1fs)", _POLL_INTERVAL)

    async def stop(self) -> None:
        """Stop polling and release resources."""
        self._running = False
        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        logger.info("macOS media listener stopped")

    # -- Internals ----------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Main polling loop — runs until stop() cancels it."""
        while self._running:
            try:
                self._poll_once()
            except Exception:
                logger.debug("macOS media poll error", exc_info=True)
            await asyncio.sleep(_POLL_INTERVAL)

    def _poll_once(self) -> None:
        """Read MPNowPlayingInfoCenter and emit an event if state changed."""
        import MediaPlayer as _mp  # type: ignore[import-not-found,import-untyped]  # noqa: N813

        center = _mp.MPNowPlayingInfoCenter.defaultCenter()
        info: dict[str, Any] | None = center.nowPlayingInfo()

        if not info:
            if self._last_status not in (PlaybackStatus.STOPPED, PlaybackStatus.UNKNOWN):
                self._last_status = PlaybackStatus.STOPPED
                self._last_title = ""
                self._emit(MediaSessionEvent(playback_status=PlaybackStatus.STOPPED))
            return

        title = str(info.get(_KEY_TITLE) or "")
        artist = str(info.get(_KEY_ARTIST) or "")
        album = str(info.get(_KEY_ALBUM) or "")
        status = _map_playback_rate(info.get(_KEY_PLAYBACK_RATE))

        if title == self._last_title and status == self._last_status:
            return  # nothing changed

        self._last_title = title
        self._last_status = status

        self._emit(
            MediaSessionEvent(
                player_name="MPNowPlayingInfoCenter",
                title=title,
                artist=artist,
                album_title=album,
                playback_status=status,
                source_app="macos_media",
            )
        )

    def _emit(self, event: MediaSessionEvent) -> None:
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception:
                logger.exception("Error in macOS media callback")
