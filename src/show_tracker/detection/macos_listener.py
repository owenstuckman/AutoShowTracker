"""macOS MediaRemote listener for media session detection.

Uses pyobjc-framework-MediaPlayer to access MPNowPlayingInfoCenter
for detecting currently playing media on macOS.

Requires: pip install pyobjc-framework-MediaPlayer

This module implements the same MediaSessionListener protocol as
the SMTC (Windows) and MPRIS (Linux) listeners.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class MediaSessionInfo:
    """Information about a currently playing media session."""

    title: str
    artist: str | None = None
    album: str | None = None
    playback_status: str = "unknown"  # "playing" | "paused" | "stopped" | "unknown"
    position: float | None = None  # seconds
    duration: float | None = None  # seconds


class MacOSMediaListener:
    """Listens for media session changes on macOS via MediaRemote framework.

    This is a stub implementation. Full implementation requires running on macOS
    with pyobjc-framework-MediaPlayer installed.

    Args:
        on_session_change: Callback invoked when media session state changes.
    """

    def __init__(
        self,
        on_session_change: Callable[[MediaSessionInfo], None] | None = None,
    ) -> None:
        self._callback = on_session_change
        self._running = False

    @staticmethod
    def is_available() -> bool:
        """Check if this listener can run on the current platform."""
        if sys.platform != "darwin":
            return False

        try:
            import MediaPlayer  # noqa: F401
            return True
        except ImportError:
            return False

    def start(self) -> None:
        """Start listening for media session changes.

        On non-macOS platforms or without pyobjc, this is a no-op.
        """
        if not self.is_available():
            logger.info(
                "macOS MediaRemote listener not available "
                "(requires macOS + pyobjc-framework-MediaPlayer)"
            )
            return

        self._running = True
        logger.info("macOS MediaRemote listener started")

        try:
            self._start_observation()
        except Exception:
            logger.exception("Failed to start macOS media observation")
            self._running = False

    def stop(self) -> None:
        """Stop listening for media session changes."""
        self._running = False
        logger.info("macOS MediaRemote listener stopped")

    def get_current_session(self) -> MediaSessionInfo | None:
        """Get the current media session info, if any.

        Returns None if nothing is playing or if not on macOS.
        """
        if not self.is_available() or not self._running:
            return None

        try:
            return self._query_now_playing()
        except Exception:
            logger.debug("Failed to query now-playing info", exc_info=True)
            return None

    def _start_observation(self) -> None:
        """Start observing MediaRemote notifications (macOS-only)."""
        # Full implementation would use:
        # from MediaPlayer import MPNowPlayingInfoCenter
        # center = MPNowPlayingInfoCenter.defaultCenter()
        # NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
        #     self, 'nowPlayingChanged:', 'kMRMediaRemoteNowPlayingInfoDidChangeNotification', None
        # )
        logger.debug("macOS media observation would start here")

    def _query_now_playing(self) -> MediaSessionInfo | None:
        """Query the current now-playing info (macOS-only)."""
        # Full implementation would use MediaRemote framework
        # to get title, artist, playback state, position, duration
        return None
