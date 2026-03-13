"""Player IPC orchestrator.

Coordinates multiple strategies for determining what media a player is
currently playing:

1. **Native IPC** -- VLC HTTP interface or mpv JSON socket (richest data).
2. **File handle inspection** -- examine open file descriptors (works on
   any player, but gives only the filename).

The service is designed to be called only when ActivityWatch reports that
a known media player is the active (or recently active) application.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from show_tracker.players.file_inspector import find_media_player_pids, get_open_media_files
from show_tracker.players.mpv import MpvClient
from show_tracker.players.vlc import VLCClient

logger = logging.getLogger(__name__)

# Known media player process names (lowercase) mapped to their type
_KNOWN_PLAYERS: dict[str, str] = {
    "vlc": "vlc",
    "vlc.exe": "vlc",
    "mpv": "mpv",
    "mpv.exe": "mpv",
    "mpc-hc": "mpc-hc",
    "mpc-hc.exe": "mpc-hc",
    "mpc-hc64.exe": "mpc-hc",
    "mpc-be": "mpc-be",
    "mpc-be.exe": "mpc-be",
    "mpc-be64.exe": "mpc-be",
    "plex": "plex",
    "plex.exe": "plex",
    "plex htpc": "plex",
    "plex htpc.exe": "plex",
    "kodi": "kodi",
    "kodi.exe": "kodi",
}


@dataclass(frozen=True, slots=True)
class MediaInfo:
    """Information about the currently playing media."""

    title: str
    """The media title or filename."""
    source: str
    """How the info was obtained: ``"vlc_http"``, ``"mpv_ipc"``, ``"file_handle"``."""
    player: str
    """The player application name."""
    duration: float | None = None
    """Total duration in seconds, if available."""
    position: float | None = None
    """Current playback position in seconds, if available."""
    state: str | None = None
    """Playback state (``"playing"``, ``"paused"``), if available."""
    file_path: str | None = None
    """Full path to the media file, if available."""


@dataclass
class PlayerService:
    """Orchestrates media-player IPC to determine what is currently playing.

    Usage::

        service = PlayerService()
        info = service.get_now_playing("vlc.exe")
        if info:
            print(info.title)
    """

    vlc_host: str = "localhost"
    vlc_port: int = 8080
    vlc_password: str = ""
    mpv_socket_path: str | None = None

    _vlc_client: VLCClient = field(default_factory=VLCClient, init=False, repr=False)
    _mpv_client: MpvClient = field(default_factory=MpvClient, init=False, repr=False)
    _initialised: bool = field(default=False, init=False, repr=False)

    def _ensure_init(self) -> None:
        """Lazy-initialise IPC clients."""
        if self._initialised:
            return

        self._vlc_client.connect(
            host=self.vlc_host, port=self.vlc_port, password=self.vlc_password,
        )
        self._mpv_client.connect(socket_path=self.mpv_socket_path)
        self._initialised = True

    def get_now_playing(self, app_name: str) -> MediaInfo | None:
        """Determine what the given media player is currently playing.

        Tries native IPC first, then falls back to file handle inspection.

        Parameters
        ----------
        app_name:
            The application name as reported by ActivityWatch (e.g.
            ``"vlc.exe"``, ``"mpv"``).

        Returns
        -------
        MediaInfo or None
            Currently playing media, or None if nothing could be determined.
        """
        self._ensure_init()

        player_type = self._identify_player(app_name)
        if not player_type:
            logger.debug("'%s' is not a recognised media player", app_name)
            return None

        logger.debug("Identified '%s' as player type '%s'", app_name, player_type)

        # Strategy 1: Try native IPC
        info = self._try_native_ipc(app_name, player_type)
        if info:
            return info

        # Strategy 2: File handle inspection
        info = self._try_file_inspection(app_name, player_type)
        if info:
            return info

        logger.debug("Could not determine now-playing for '%s'", app_name)
        return None

    def is_media_player(self, app_name: str) -> bool:
        """Check whether an application name belongs to a known media player.

        Parameters
        ----------
        app_name:
            The application name to check.

        Returns
        -------
        bool
            True if the name matches a known media player.
        """
        return self._identify_player(app_name) is not None

    @staticmethod
    def _identify_player(app_name: str) -> str | None:
        """Map an app name to a canonical player type."""
        name_lower = app_name.lower().strip()

        # Direct match
        if name_lower in _KNOWN_PLAYERS:
            return _KNOWN_PLAYERS[name_lower]

        # Substring match for flexibility
        for known_name, player_type in _KNOWN_PLAYERS.items():
            if known_name in name_lower or name_lower in known_name:
                return player_type

        return None

    def _try_native_ipc(self, app_name: str, player_type: str) -> MediaInfo | None:
        """Attempt to get now-playing info via native IPC."""
        if player_type == "vlc":
            return self._query_vlc(app_name)
        elif player_type == "mpv":
            return self._query_mpv(app_name)

        # No native IPC for other players (MPC-HC, Kodi, etc.)
        return None

    def _query_vlc(self, app_name: str) -> MediaInfo | None:
        """Query VLC's HTTP interface."""
        if not self._vlc_client.is_available():
            logger.debug("VLC web interface not available")
            return None

        status = self._vlc_client.get_status()
        if status is None:
            return None

        position_secs: float | None = None
        if status.duration > 0 and status.position >= 0:
            position_secs = status.duration * status.position

        return MediaInfo(
            title=status.title,
            source="vlc_http",
            player=app_name,
            duration=status.duration if status.duration > 0 else None,
            position=position_secs,
            state=status.state,
            file_path=status.filename if status.filename else None,
        )

    def _query_mpv(self, app_name: str) -> MediaInfo | None:
        """Query mpv's JSON IPC socket."""
        if not self._mpv_client.is_available():
            logger.debug("mpv IPC socket not available")
            return None

        title = self._mpv_client.get_media_title()
        if not title:
            return None

        duration = self._mpv_client.get_duration()
        position = self._mpv_client.get_position()

        # Try to get the file path
        file_path = self._mpv_client.get_property("path")
        if isinstance(file_path, str) and file_path.startswith("/"):
            pass  # It's an absolute path
        elif isinstance(file_path, str) and not file_path.startswith("http"):
            # Relative path or protocol -- keep as-is
            pass
        else:
            file_path = None

        return MediaInfo(
            title=title,
            source="mpv_ipc",
            player=app_name,
            duration=duration,
            position=position,
            state="playing",  # mpv socket is only available while playing
            file_path=file_path if isinstance(file_path, str) else None,
        )

    def _try_file_inspection(self, app_name: str, player_type: str) -> MediaInfo | None:
        """Inspect open file handles to find video files."""
        pids = find_media_player_pids(app_name)
        if not pids:
            logger.debug("No running processes found for '%s'", app_name)
            return None

        for pid in pids:
            media_files = get_open_media_files(pid)
            if media_files:
                # Use the first video file found (usually there's only one)
                file_path = media_files[0]
                title = Path(file_path).name
                logger.debug(
                    "File inspection found '%s' for PID %d (%s)",
                    title, pid, app_name,
                )
                return MediaInfo(
                    title=title,
                    source="file_handle",
                    player=app_name,
                    file_path=file_path,
                )

        return None
