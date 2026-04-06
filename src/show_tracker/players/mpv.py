"""mpv JSON IPC integration.

mpv exposes a JSON-based IPC protocol over a Unix domain socket (Linux/macOS)
or a named pipe (Windows).  This module communicates with that socket to
query playback properties like media-title, duration, and time-pos.

See: https://mpv.io/manual/master/#json-ipc
"""

from __future__ import annotations

import json
import logging
import socket
import sys
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_SOCKET_LINUX = "/tmp/mpvsocket"
_DEFAULT_PIPE_WINDOWS = r"\\.\pipe\mpvsocket"
_RECV_BUFFER = 4096
_SOCKET_TIMEOUT = 3.0  # seconds


class MpvClient:
    """Client for mpv's JSON IPC protocol.

    Usage::

        client = MpvClient()
        client.connect("/tmp/mpvsocket")
        if client.is_available():
            title = client.get_media_title()
    """

    def __init__(self) -> None:
        self._socket_path: str = ""
        self._request_id: int = 0

    def connect(self, socket_path: str | None = None) -> None:
        """Set the IPC socket path.

        Parameters
        ----------
        socket_path:
            Path to mpv's IPC socket.  Defaults to ``/tmp/mpvsocket``
            on Linux or ``\\\\.\\pipe\\mpvsocket`` on Windows.
        """
        if socket_path:
            self._socket_path = socket_path
        elif sys.platform == "win32":
            self._socket_path = _DEFAULT_PIPE_WINDOWS
        else:
            self._socket_path = _DEFAULT_SOCKET_LINUX

        logger.info("mpv client configured: %s", self._socket_path)

    def is_available(self) -> bool:
        """Check whether the mpv IPC socket is reachable.

        Returns
        -------
        bool
            True if a connection can be established and mpv responds.
        """
        try:
            result = self.get_property("mpv-version")
            return result is not None
        except Exception:
            return False

    def get_property(self, name: str) -> Any:
        """Query an mpv property via the IPC protocol.

        Parameters
        ----------
        name:
            The mpv property name (e.g. ``"media-title"``, ``"duration"``).

        Returns
        -------
        Any
            The property value, or None if the query fails.
        """
        self._request_id += 1
        command = {
            "command": ["get_property", name],
            "request_id": self._request_id,
        }
        response = self._send_command(command)
        if response is None:
            return None

        if response.get("error") != "success":
            logger.debug(
                "mpv property '%s' query failed: %s",
                name,
                response.get("error"),
            )
            return None

        return response.get("data")

    def get_media_title(self) -> str | None:
        """Get the currently playing media title.

        Tries ``media-title`` first, then falls back to ``filename``.
        """
        title: Any = self.get_property("media-title")
        if title and isinstance(title, str) and title.strip():
            result: str = title.strip()
            return result

        filename: Any = self.get_property("filename")
        if filename and isinstance(filename, str):
            result = filename.strip()
            return result

        return None

    def get_position(self) -> float | None:
        """Get the current playback position in seconds."""
        val = self.get_property("time-pos")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        return None

    def get_duration(self) -> float | None:
        """Get the total duration of the current media in seconds."""
        val = self.get_property("duration")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        return None

    def _send_command(self, command: dict[str, Any]) -> dict[str, Any] | None:
        """Send a JSON command to mpv and return the parsed response.

        Handles both Unix domain sockets and Windows named pipes.
        """
        if not self._socket_path:
            logger.debug("mpv client not connected")
            return None

        if sys.platform == "win32":
            return self._send_windows(command)
        else:
            return self._send_unix(command)

    def _send_unix(self, command: dict[str, Any]) -> dict[str, Any] | None:
        """Send a command over a Unix domain socket."""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined]
            sock.settimeout(_SOCKET_TIMEOUT)
            try:
                sock.connect(self._socket_path)

                payload = json.dumps(command) + "\n"
                sock.sendall(payload.encode("utf-8"))

                # Read response -- mpv sends one JSON object per line
                data = b""
                while True:
                    chunk = sock.recv(_RECV_BUFFER)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break

                return self._parse_response(data, command.get("request_id"))
            finally:
                sock.close()
        except (OSError, ConnectionRefusedError, FileNotFoundError) as exc:
            logger.debug("mpv IPC connection failed (%s): %s", self._socket_path, exc)
            return None

    def _send_windows(self, command: dict[str, Any]) -> dict[str, Any] | None:
        """Send a command over a Windows named pipe."""
        try:
            # On Windows, named pipes can be opened as regular files
            payload = json.dumps(command) + "\n"
            with open(self._socket_path, "r+b", buffering=0) as pipe:
                pipe.write(payload.encode("utf-8"))
                pipe.flush()

                data = b""
                while True:
                    chunk = pipe.read(_RECV_BUFFER)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break

            return self._parse_response(data, command.get("request_id"))
        except (OSError, FileNotFoundError) as exc:
            logger.debug("mpv IPC pipe failed (%s): %s", self._socket_path, exc)
            return None

    @staticmethod
    def _parse_response(data: bytes, request_id: int | None) -> dict[str, Any] | None:
        """Parse mpv's newline-delimited JSON response.

        mpv may send multiple lines (e.g. events), so we search for the
        line matching our request_id.
        """
        if not data:
            return None

        for line in data.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Match by request_id if available
            if request_id is not None and obj.get("request_id") == request_id:
                return dict(obj)

            # If no request_id filtering, return the first valid response
            if request_id is None and "error" in obj:
                return dict(obj)

        # Return the last parsed object as a fallback
        for line in reversed(data.decode("utf-8", errors="replace").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                return dict(json.loads(line))
            except json.JSONDecodeError:
                continue

        return None
