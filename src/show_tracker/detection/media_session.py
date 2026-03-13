"""Cross-platform media session abstraction.

Defines the shared :class:`MediaSessionEvent` dataclass and the
:class:`MediaSessionListener` protocol that both the Windows SMTC listener
and the Linux MPRIS listener implement.  The :func:`get_media_listener`
factory returns the appropriate concrete listener for the current platform.
"""

from __future__ import annotations

import enum
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass


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

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
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


def get_media_listener() -> MediaSessionListener:
    """Return the appropriate :class:`MediaSessionListener` for the current OS.

    Raises
    ------
    RuntimeError
        If the current platform is not supported (neither Windows nor Linux).
    ImportError
        If the required platform-specific package is not installed.
    """
    if sys.platform == "win32":
        from show_tracker.detection.smtc_listener import SMTCListener

        return SMTCListener()

    if sys.platform == "linux":
        from show_tracker.detection.mpris_listener import MPRISListener

        return MPRISListener()

    raise RuntimeError(
        f"No media session listener available for platform {sys.platform!r}. "
        "Supported platforms: Windows (win32), Linux."
    )
