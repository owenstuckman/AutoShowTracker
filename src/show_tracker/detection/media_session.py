"""Cross-platform media session abstraction.

Defines the shared :class:`MediaSessionEvent` dataclass and the
:class:`MediaSessionListener` protocol that both the Windows SMTC listener
and the Linux MPRIS listener implement.  The :func:`get_media_listener`
factory returns the appropriate concrete listener for the current platform.
"""

from __future__ import annotations

import enum
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


class PlaybackStatus(enum.Enum):
    """Playback states reported by OS media session APIs."""

    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MediaSessionEvent:
    """A single media session state change from SMTC or MPRIS.

    Instances are immutable so they can safely be passed across async
    boundaries.
    """

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    player_name: str = ""
    title: str = ""
    artist: str = ""
    album_title: str = ""
    playback_status: PlaybackStatus = PlaybackStatus.UNKNOWN
    source_app: str = ""


# Type alias for consumer callbacks.
MediaSessionCallback = Callable[[MediaSessionEvent], None]


@runtime_checkable
class MediaSessionListener(Protocol):
    """Interface that platform-specific listeners must satisfy."""

    async def start(self) -> None:
        """Begin listening for media session changes."""
        ...

    async def stop(self) -> None:
        """Stop listening and release resources."""
        ...

    def register_callback(self, callback: MediaSessionCallback) -> None:
        """Register a function to be called on each media session event."""
        ...


def _is_wsl() -> bool:
    """Detect if running inside Windows Subsystem for Linux."""
    if sys.platform != "linux":
        return False
    try:
        with open("/proc/version", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def get_media_listener() -> MediaSessionListener | None:
    """Return the appropriate :class:`MediaSessionListener` for the current OS.

    Returns *None* on platforms where no listener is available (e.g. WSL,
    unsupported OS) so callers can degrade gracefully.

    Raises
    ------
    ImportError
        If the required platform-specific package is not installed.
    """
    if sys.platform == "win32":
        from show_tracker.detection.smtc_listener import SMTCListener

        return SMTCListener()

    if sys.platform == "linux":
        if _is_wsl():
            # WSL cannot access D-Bus or Windows SMTC — no media listener.
            import logging

            logging.getLogger(__name__).info(
                "WSL detected — SMTC and MPRIS media listeners are unavailable. "
                "Detection will rely on browser extension, ActivityWatch, and player IPC."
            )
            return None

        from show_tracker.detection.mpris_listener import MPRISListener

        return MPRISListener()

    if sys.platform == "darwin":
        from show_tracker.detection.macos_listener import MacOSMediaListener

        return MacOSMediaListener()

    return None
