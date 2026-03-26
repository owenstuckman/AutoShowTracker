"""Linux MPRIS (Media Player Remote Interfacing Specification) listener.

Connects to the session D-Bus and subscribes to ``PropertiesChanged``
signals emitted by any MPRIS-capable media player.  This is the
highest-priority detection source on Linux.

Requires the ``dbus-next`` package (install with ``pip install show-tracker[linux]``).
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

Variant: Any = None  # placeholder for type-checking on non-Linux
MessageBus: Any = None  # placeholder for type-checking on non-Linux

if sys.platform != "linux":
    _DBUS_AVAILABLE = False
else:
    try:
        from dbus_next import Variant  # type: ignore[import-not-found,no-redef]
        from dbus_next.aio import MessageBus  # type: ignore[import-not-found,no-redef]

        _DBUS_AVAILABLE = True
    except ImportError:
        _DBUS_AVAILABLE = False

_MPRIS_PREFIX = "org.mpris.MediaPlayer2."
_MPRIS_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
_MPRIS_PATH = "/org/mpris/MediaPlayer2"
_PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"
_DBUS_IFACE = "org.freedesktop.DBus"


def _variant_value(v: Any) -> Any:
    """Unwrap a ``dbus_next.Variant`` to its Python value, or return as-is."""
    if _DBUS_AVAILABLE and isinstance(v, Variant):
        return v.value
    return v


def _map_playback_status(raw: str) -> PlaybackStatus:
    """Map an MPRIS PlaybackStatus string to our enum."""
    mapping: dict[str, PlaybackStatus] = {
        "Playing": PlaybackStatus.PLAYING,
        "Paused": PlaybackStatus.PAUSED,
        "Stopped": PlaybackStatus.STOPPED,
    }
    return mapping.get(raw, PlaybackStatus.UNKNOWN)


class MPRISListener:
    """Event-driven listener for Linux MPRIS media sessions via D-Bus.

    Discovers all running MPRIS-capable players and subscribes to their
    ``PropertiesChanged`` signals so we are notified in real time when
    metadata or playback status changes.

    Usage::

        listener = MPRISListener()
        listener.register_callback(my_handler)
        await listener.start()
        # ...
        await listener.stop()

    Raises
    ------
    RuntimeError
        If instantiated on a non-Linux platform.
    ImportError
        If the ``dbus-next`` package is not installed.
    """

    def __init__(self) -> None:
        if sys.platform != "linux":
            raise RuntimeError(
                "MPRISListener is only supported on Linux. "
                f"Current platform: {sys.platform!r}"
            )
        if not _DBUS_AVAILABLE:
            raise ImportError(
                "The 'dbus-next' package is required for MPRIS support. "
                "Install it with: pip install show-tracker[linux]"
            )

        self._callbacks: list[MediaSessionCallback] = []
        self._bus: Any = None
        self._running: bool = False
        self._tracked_players: dict[str, Any] = {}  # bus_name -> proxy obj
        self._name_watch_task: asyncio.Task[None] | None = None

    # -- Public API ---------------------------------------------------------

    def register_callback(self, callback: MediaSessionCallback) -> None:
        """Register a function to be invoked on each media property change."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Connect to D-Bus and subscribe to all MPRIS player signals."""
        if self._running:
            return

        self._bus = await MessageBus().connect()
        logger.info("Connected to session D-Bus")

        # Discover existing MPRIS players.
        players = await self._discover_players()
        for bus_name in players:
            await self._track_player(bus_name)

        # Watch for new MPRIS players appearing on the bus.
        self._name_watch_task = asyncio.create_task(self._watch_for_new_players())
        self._running = True
        logger.info("MPRIS listener started, tracking %d player(s)", len(players))

    async def stop(self) -> None:
        """Disconnect from D-Bus and release all subscriptions."""
        if self._name_watch_task is not None:
            self._name_watch_task.cancel()
            try:
                await self._name_watch_task
            except asyncio.CancelledError:
                pass
            self._name_watch_task = None

        self._tracked_players.clear()

        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None

        self._running = False
        logger.info("MPRIS listener stopped")

    # -- Player discovery ---------------------------------------------------

    async def _discover_players(self) -> list[str]:
        """List all bus names matching the MPRIS prefix."""
        introspection = await self._bus.introspect("org.freedesktop.DBus", "/org/freedesktop/DBus")
        proxy = self._bus.get_proxy_object(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            introspection,
        )
        dbus_iface = proxy.get_interface(_DBUS_IFACE)
        names: list[str] = await dbus_iface.call_list_names()
        return [n for n in names if n.startswith(_MPRIS_PREFIX)]

    async def _track_player(self, bus_name: str) -> None:
        """Subscribe to PropertiesChanged for a single MPRIS player."""
        if bus_name in self._tracked_players:
            return

        try:
            introspection = await self._bus.introspect(bus_name, _MPRIS_PATH)
            proxy = self._bus.get_proxy_object(bus_name, _MPRIS_PATH, introspection)
            props_iface = proxy.get_interface(_PROPERTIES_IFACE)

            player_short_name = bus_name.removeprefix(_MPRIS_PREFIX)

            def _on_properties_changed(
                interface_name: str,
                changed: dict[str, Any],
                invalidated: list[str],
                _bus_name: str = bus_name,
                _player: str = player_short_name,
            ) -> None:
                self._handle_properties_changed(_bus_name, _player, interface_name, changed)

            props_iface.on_properties_changed(_on_properties_changed)
            self._tracked_players[bus_name] = proxy
            logger.debug("Tracking MPRIS player: %s", bus_name)
        except Exception:
            logger.exception("Failed to track MPRIS player %s", bus_name)

    async def _watch_for_new_players(self) -> None:
        """Monitor D-Bus for new MPRIS-capable players appearing."""
        introspection = await self._bus.introspect("org.freedesktop.DBus", "/org/freedesktop/DBus")
        proxy = self._bus.get_proxy_object(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            introspection,
        )
        dbus_iface = proxy.get_interface(_DBUS_IFACE)

        def _on_name_owner_changed(name: str, old_owner: str, new_owner: str) -> None:
            if not name.startswith(_MPRIS_PREFIX):
                return
            if new_owner and not old_owner:
                # New player appeared.
                asyncio.ensure_future(self._track_player(name))
            elif old_owner and not new_owner:
                # Player disappeared.
                self._tracked_players.pop(name, None)
                logger.debug("MPRIS player removed: %s", name)

        dbus_iface.on_name_owner_changed(_on_name_owner_changed)

        # Keep the task alive until cancelled.
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return

    # -- Signal handling ----------------------------------------------------

    def _handle_properties_changed(
        self,
        bus_name: str,
        player_name: str,
        interface_name: str,
        changed: dict[str, Any],
    ) -> None:
        """Process a PropertiesChanged signal from an MPRIS player."""
        if interface_name != _MPRIS_PLAYER_IFACE:
            return

        metadata_variant = changed.get("Metadata")
        status_variant = changed.get("PlaybackStatus")

        title = ""
        artist = ""
        album = ""
        playback_status = PlaybackStatus.UNKNOWN

        if metadata_variant is not None:
            metadata = _variant_value(metadata_variant)
            if isinstance(metadata, dict):
                title = str(_variant_value(metadata.get("xesam:title", "")))
                artists = _variant_value(metadata.get("xesam:artist", []))
                if isinstance(artists, list) and artists:
                    artist = str(artists[0])
                album = str(_variant_value(metadata.get("xesam:album", "")))

        if status_variant is not None:
            playback_status = _map_playback_status(str(_variant_value(status_variant)))

        event = MediaSessionEvent(
            player_name=player_name,
            title=title,
            artist=artist,
            album_title=album,
            playback_status=playback_status,
            source_app=bus_name,
        )

        for callback in self._callbacks:
            try:
                callback(event)
            except Exception:
                logger.exception("Error in MPRIS callback")
