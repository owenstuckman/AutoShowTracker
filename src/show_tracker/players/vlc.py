"""VLC web interface (HTTP) integration.

VLC exposes an HTTP API on localhost (default port 8080) when started with
``--extraintf http``.  This module polls that interface to retrieve the
currently playing media title, playback position, and state.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import requests

logger = logging.getLogger(__name__)

_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 8080
_DEFAULT_PASSWORD = ""
_REQUEST_TIMEOUT = 5  # seconds


@dataclass(frozen=True, slots=True)
class PlayerStatus:
    """Snapshot of VLC's current playback state."""

    title: str
    """Media title as reported by VLC (may be filename or metadata)."""
    duration: float
    """Total duration in seconds."""
    position: float
    """Current position as a fraction (0.0 - 1.0)."""
    state: str
    """Playback state: ``"playing"``, ``"paused"``, or ``"stopped"``."""
    filename: str
    """The raw filename/URI of the current media item."""


class VLCClient:
    """Client for VLC's HTTP web interface.

    Usage::

        client = VLCClient()
        client.connect(host="localhost", port=8080, password="vlcpass")
        if client.is_available():
            status = client.get_status()
    """

    def __init__(self) -> None:
        self._base_url: str = ""
        self._auth: tuple[str, str] = ("", "")
        self._session: requests.Session | None = None

    def connect(
        self,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        password: str = _DEFAULT_PASSWORD,
    ) -> None:
        """Configure the connection to VLC's HTTP interface.

        Parameters
        ----------
        host:
            Hostname or IP.  VLC binds to localhost by default.
        port:
            HTTP port.  Default is 8080.
        password:
            The password configured in VLC's web interface settings.
            VLC uses HTTP Basic Auth with an empty username.
        """
        self._base_url = f"http://{host}:{port}"
        self._auth = ("", password)
        self._session = requests.Session()
        self._session.auth = self._auth
        logger.info("VLC client configured: %s", self._base_url)

    def is_available(self) -> bool:
        """Check whether the VLC web interface is reachable.

        Returns
        -------
        bool
            True if VLC responds to a status request.
        """
        if not self._base_url:
            return False

        try:
            resp = self._request("/requests/status.xml")
            return resp is not None
        except Exception:
            return False

    def get_status(self) -> PlayerStatus | None:
        """Retrieve the current playback status from VLC.

        Returns
        -------
        PlayerStatus or None
            Current status, or None if VLC is unreachable or not playing.
        """
        resp = self._request("/requests/status.xml")
        if resp is None:
            return None

        try:
            return self._parse_status_xml(resp)
        except (ET.ParseError, KeyError, ValueError) as exc:
            logger.error("Failed to parse VLC status XML: %s", exc)
            return None

    def _request(self, path: str, params: dict[str, Any] | None = None) -> str | None:
        """Make an HTTP GET request to the VLC interface.

        Returns the response body as a string, or None on failure.
        """
        if not self._session or not self._base_url:
            logger.debug("VLC client not connected")
            return None

        url = f"{self._base_url}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except requests.ConnectionError:
            logger.debug("VLC web interface not reachable at %s", self._base_url)
            return None
        except requests.Timeout:
            logger.debug("VLC web interface request timed out")
            return None
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                logger.warning("VLC web interface authentication failed (wrong password?)")
            else:
                logger.warning("VLC HTTP error: %s", exc)
            return None

    @staticmethod
    def _parse_status_xml(xml_text: str) -> PlayerStatus | None:
        """Parse VLC's ``/requests/status.xml`` response."""
        root = ET.fromstring(xml_text)

        state = root.findtext("state", default="stopped").strip().lower()
        if state == "stopped":
            return None

        # Duration and position
        length_text = root.findtext("length", default="0")
        position_text = root.findtext("position", default="0")

        duration = float(length_text)
        position = float(position_text)

        # Extract title from <information> metadata or from <filename>
        title = ""
        filename = ""

        # Try metadata first
        info_el = root.find("information")
        if info_el is not None:
            for category in info_el.findall("category"):
                if category.get("name") == "meta":
                    for info in category.findall("info"):
                        if info.get("name") == "title" and info.text:
                            title = info.text.strip()
                        if info.get("name") == "filename" and info.text:
                            filename = info.text.strip()

        # Fallback: <current_plid> and construct from playlist, or use filename
        if not filename:
            filename_el = root.findtext("currentplid", default="")
            # Try to get from information/category[@name='meta']/info[@name='filename']
            if not filename:
                filename = filename_el

        # If still no title, try to decode from filename
        if not title and filename:
            title = unquote(filename)

        if not title:
            return None

        return PlayerStatus(
            title=title,
            duration=duration,
            position=position,
            state=state,
            filename=filename,
        )
