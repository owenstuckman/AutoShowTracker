"""Detection/collection layer for Show Tracker.

This package implements the collection layer — the bottom of the architecture
stack.  It gathers raw media signals from multiple sources:

- **ActivityWatch** integration (window titles, browser tab URLs)
- **SMTC** (Windows) and **MPRIS** (Linux) OS-level media session APIs
- **Browser extension** events (rich metadata from streaming sites)

All sources emit events that are consumed by :class:`DetectionService`, the
central orchestrator that feeds parsed signals into the identification layer.
"""

from show_tracker.detection.media_session import (
    MediaSessionEvent,
    MediaSessionListener,
    PlaybackStatus,
    get_media_listener,
)

__all__ = [
    "MediaSessionEvent",
    "MediaSessionListener",
    "PlaybackStatus",
    "get_media_listener",
]
