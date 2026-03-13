"""Windows SMTC (System Media Transport Controls) listener.

Subscribes to the OS-level media session API to receive real-time
notifications when media properties change (track/episode transitions,
play/pause, etc.).  This is the highest-priority detection source on
Windows because it captures background playback that window-title
watchers miss.

Requires the ``winsdk`` package (install with ``pip install show-tracker[windows]``).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from show_tracker.detection.media_session import (
    MediaSessionCallback,
    MediaSessionEvent,
    PlaybackStatus,
)

logger = logging.getLogger(__name__)

# Platform guard ---------------------------------------------------------------

if sys.platform != "win32":
    # Allow the module to be *imported* on non-Windows platforms (e.g. for
    # type-checking or test collection) but raise clearly on instantiation.
    _WINSDK_AVAILABLE = False
else:
    try:
        from winsdk.windows.media.control import (  # type: ignore[import-untyped]
            GlobalSystemMediaTransportControlsSessionManager as SessionManager,
            GlobalSystemMediaTransportControlsSession as Session,
            MediaPropertiesChangedEventArgs,
            PlaybackInfoChangedEventArgs,
        )

        _WINSDK_AVAILABLE = True
    except ImportError:
        _WINSDK_AVAILABLE = False


# Helpers ----------------------------------------------------------------------


def _map_playback_status(raw_status: Any) -> PlaybackStatus:
    """Map a WinRT playback status enum value to our :class:`PlaybackStatus`."""
    # WinRT enum values: 0=Closed, 1=Opened, 2=Changing, 3=Stopped,
    # 4=Playing, 5=Paused
    mapping: dict[int, PlaybackStatus] = {
        4: PlaybackStatus.PLAYING,
        5: PlaybackStatus.PAUSED,
        3: PlaybackStatus.STOPPED,
    }
    try:
        return mapping.get(int(raw_status), PlaybackStatus.UNKNOWN)
    except (TypeError, ValueError):
        return PlaybackStatus.UNKNOWN


# Listener ---------------------------------------------------------------------


class SMTCListener:
    """Event-driven listener for Windows System Media Transport Controls.

    Usage::

        listener = SMTCListener()
        listener.register_callback(my_handler)
        await listener.start()
        # ...
        await listener.stop()

    Raises
    ------
    RuntimeError
        If instantiated on a non-Windows platform.
    ImportError
        If the ``winsdk`` package is not installed.
    """

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError(
                "SMTCListener is only supported on Windows. "
                f"Current platform: {sys.platform!r}"
            )
        if not _WINSDK_AVAILABLE:
            raise ImportError(
                "The 'winsdk' package is required for SMTC support. "
                "Install it with: pip install show-tracker[windows]"
            )

        self._callbacks: list[MediaSessionCallback] = []
        self._manager: Any = None
        self._session: Any = None
        self._running: bool = False
        self._event_tokens: list[Any] = []

    # -- Public API ---------------------------------------------------------

    def register_callback(self, callback: MediaSessionCallback) -> None:
        """Register a function to be invoked on each media property change."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Begin listening for SMTC media session events."""
        if self._running:
            return

        self._manager = await SessionManager.request_async()  # type: ignore[union-attr]
        self._attach_current_session()

        # Also listen for session changes (e.g. user opens a new player).
        self._manager.add_current_session_changed(self._on_session_changed)
        self._running = True
        logger.info("SMTC listener started")

    async def stop(self) -> None:
        """Stop listening and detach all event handlers."""
        self._detach_session()
        self._manager = None
        self._running = False
        logger.info("SMTC listener stopped")

    # -- Internals ----------------------------------------------------------

    def _attach_current_session(self) -> None:
        """Subscribe to events on the current active media session."""
        if self._manager is None:
            return

        session = self._manager.get_current_session()
        if session is None:
            logger.debug("No active SMTC session found")
            return

        self._session = session
        token_props = session.add_media_properties_changed(
            self._on_media_properties_changed
        )
        token_playback = session.add_playback_info_changed(
            self._on_playback_info_changed
        )
        self._event_tokens = [token_props, token_playback]
        logger.debug("Attached to SMTC session: %s", session.source_app_user_model_id)

    def _detach_session(self) -> None:
        """Remove event subscriptions from the current session."""
        self._event_tokens.clear()
        self._session = None

    def _on_session_changed(self, sender: Any, args: Any) -> None:
        """Called when the current media session changes."""
        self._detach_session()
        self._attach_current_session()

    def _on_media_properties_changed(
        self,
        session: Any,
        args: Any,
    ) -> None:
        """Called when media properties (title, artist, etc.) change."""
        asyncio.get_event_loop().create_task(self._emit_current_state(session))

    def _on_playback_info_changed(
        self,
        session: Any,
        args: Any,
    ) -> None:
        """Called when playback status (play/pause/stop) changes."""
        asyncio.get_event_loop().create_task(self._emit_current_state(session))

    async def _emit_current_state(self, session: Any) -> None:
        """Read current media properties and notify all registered callbacks."""
        try:
            info = await session.try_get_media_properties_async()
            playback_info = session.get_playback_info()

            event = MediaSessionEvent(
                player_name=str(getattr(session, "source_app_user_model_id", "")),
                title=str(getattr(info, "title", "")),
                artist=str(getattr(info, "artist", "")),
                album_title=str(getattr(info, "album_title", "")),
                playback_status=_map_playback_status(
                    getattr(playback_info, "playback_status", None)
                ),
                source_app=str(getattr(session, "source_app_user_model_id", "")),
            )

            for callback in self._callbacks:
                try:
                    callback(event)
                except Exception:
                    logger.exception("Error in SMTC callback")
        except Exception:
            logger.exception("Failed to read SMTC media properties")
