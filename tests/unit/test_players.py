"""Unit tests for the player client modules (VLC and mpv)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from show_tracker.players.mpv import MpvClient
from show_tracker.players.vlc import PlayerStatus, VLCClient

# ---------------------------------------------------------------------------
# TestVLCClient
# ---------------------------------------------------------------------------

# Minimal VLC status XML with a playing state and metadata
_VLC_PLAYING_XML = """<?xml version="1.0" encoding="utf-8"?>
<root>
  <state>playing</state>
  <length>2700</length>
  <position>0.35</position>
  <information>
    <category name="meta">
      <info name="title">Breaking Bad S01E01</info>
      <info name="filename">breaking.bad.s01e01.mkv</info>
    </category>
  </information>
</root>"""

_VLC_PAUSED_XML = """<?xml version="1.0" encoding="utf-8"?>
<root>
  <state>paused</state>
  <length>1800</length>
  <position>0.50</position>
  <information>
    <category name="meta">
      <info name="title">The Wire S02E03</info>
      <info name="filename">the.wire.s02e03.mkv</info>
    </category>
  </information>
</root>"""

_VLC_STOPPED_XML = """<?xml version="1.0" encoding="utf-8"?>
<root>
  <state>stopped</state>
  <length>0</length>
  <position>0</position>
</root>"""


class TestVLCClient:
    """Tests for VLCClient using mocked HTTP responses."""

    def test_vlc_client_instantiates(self) -> None:
        """VLCClient can be instantiated without error."""
        client = VLCClient()
        assert client is not None

    def test_connect_sets_base_url(self) -> None:
        """connect() configures the base URL correctly."""
        client = VLCClient()
        client.connect(host="localhost", port=8080, password="testpass")
        assert client._base_url == "http://localhost:8080"

    def test_is_available_false_before_connect(self) -> None:
        """is_available() returns False when not connected."""
        client = VLCClient()
        assert not client.is_available()

    def test_parse_status_xml_playing(self) -> None:
        """_parse_status_xml returns PlayerStatus for a playing state."""
        result = VLCClient._parse_status_xml(_VLC_PLAYING_XML)
        assert result is not None
        assert isinstance(result, PlayerStatus)
        assert result.state == "playing"
        assert result.title == "Breaking Bad S01E01"
        assert result.duration == 2700.0
        assert abs(result.position - 0.35) < 1e-9

    def test_parse_status_xml_paused(self) -> None:
        """_parse_status_xml handles paused state correctly."""
        result = VLCClient._parse_status_xml(_VLC_PAUSED_XML)
        assert result is not None
        assert result.state == "paused"
        assert result.title == "The Wire S02E03"

    def test_parse_status_xml_stopped_returns_none(self) -> None:
        """_parse_status_xml returns None when VLC is stopped."""
        result = VLCClient._parse_status_xml(_VLC_STOPPED_XML)
        assert result is None

    def test_parse_status_xml_invalid_returns_none(self) -> None:
        """_parse_status_xml raises on invalid XML."""
        import xml.etree.ElementTree as ET

        with pytest.raises(ET.ParseError):
            VLCClient._parse_status_xml("not xml at all <<<")

    def test_get_status_returns_none_when_request_fails(self) -> None:
        """get_status() returns None when the HTTP request fails."""
        client = VLCClient()
        client.connect(host="localhost", port=8080)
        with patch.object(client, "_request", return_value=None):
            result = client.get_status()
        assert result is None

    def test_get_status_with_mock_response(self) -> None:
        """get_status() parses XML from a successful HTTP response."""
        client = VLCClient()
        client.connect(host="localhost", port=8080)
        with patch.object(client, "_request", return_value=_VLC_PLAYING_XML):
            result = client.get_status()
        assert result is not None
        assert result.title == "Breaking Bad S01E01"
        assert result.state == "playing"

    def test_player_status_dataclass_fields(self) -> None:
        """PlayerStatus dataclass has expected fields."""
        status = PlayerStatus(
            title="Test Show S01E01",
            duration=3600.0,
            position=0.25,
            state="playing",
            filename="test_show_s01e01.mkv",
        )
        assert status.title == "Test Show S01E01"
        assert status.duration == 3600.0
        assert status.position == 0.25
        assert status.state == "playing"
        assert status.filename == "test_show_s01e01.mkv"

    def test_is_available_with_working_request(self) -> None:
        """is_available() returns True when request returns content."""
        client = VLCClient()
        client.connect(host="localhost", port=8080)
        with patch.object(client, "_request", return_value=_VLC_PLAYING_XML):
            assert client.is_available()

    def test_is_available_with_failing_request(self) -> None:
        """is_available() returns False when request returns None."""
        client = VLCClient()
        client.connect(host="localhost", port=8080)
        with patch.object(client, "_request", return_value=None):
            assert not client.is_available()


# ---------------------------------------------------------------------------
# TestMpvClient
# ---------------------------------------------------------------------------


def _mpv_response(data: object, request_id: int = 1, error: str = "success") -> bytes:
    """Build a fake mpv JSON IPC response line."""
    return (json.dumps({"data": data, "error": error, "request_id": request_id}) + "\n").encode()


class TestMpvClient:
    """Tests for MpvClient using mocked socket I/O."""

    def test_mpv_client_instantiates(self) -> None:
        """MpvClient can be instantiated without error."""
        client = MpvClient()
        assert client is not None

    def test_connect_sets_socket_path(self) -> None:
        """connect() stores the provided socket path."""
        client = MpvClient()
        client.connect("/tmp/testsocket")
        assert client._socket_path == "/tmp/testsocket"

    def test_connect_default_linux_path(self) -> None:
        """connect() uses /tmp/mpvsocket when no path given on Linux."""
        import sys

        client = MpvClient()
        with patch.object(sys, "platform", "linux"):
            client.connect()
        assert client._socket_path == "/tmp/mpvsocket"

    def test_is_available_returns_false_when_send_fails(self) -> None:
        """is_available() returns False when IPC connection fails."""
        client = MpvClient()
        client.connect("/tmp/nonexistent")
        with patch.object(client, "_send_command", return_value=None):
            assert not client.is_available()

    def test_is_available_returns_true_when_responds(self) -> None:
        """is_available() returns True when mpv responds to version query."""
        client = MpvClient()
        client.connect("/tmp/mpvsocket")
        with patch.object(
            client, "_send_command", return_value={"data": "mpv 0.35.0", "error": "success"}
        ):
            assert client.is_available()

    def test_get_property_returns_data_on_success(self) -> None:
        """get_property() returns the data field on a successful response."""
        client = MpvClient()
        client.connect("/tmp/mpvsocket")
        with patch.object(
            client,
            "_send_command",
            return_value={"data": "Breaking Bad S01E01", "error": "success"},
        ):
            result = client.get_property("media-title")
        assert result == "Breaking Bad S01E01"

    def test_get_property_returns_none_on_error(self) -> None:
        """get_property() returns None when error != 'success'."""
        client = MpvClient()
        client.connect("/tmp/mpvsocket")
        with patch.object(
            client,
            "_send_command",
            return_value={"data": None, "error": "property unavailable"},
        ):
            result = client.get_property("missing-property")
        assert result is None

    def test_get_property_returns_none_on_no_response(self) -> None:
        """get_property() returns None when _send_command returns None."""
        client = MpvClient()
        client.connect("/tmp/mpvsocket")
        with patch.object(client, "_send_command", return_value=None):
            result = client.get_property("media-title")
        assert result is None

    def test_get_media_title_uses_media_title_property(self) -> None:
        """get_media_title() returns the media-title property when set."""
        client = MpvClient()
        client.connect("/tmp/mpvsocket")

        responses = [
            {"data": "The Wire S03E09", "error": "success"},
        ]
        call_count = 0

        def fake_send(cmd):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            return responses[0]

        with patch.object(client, "_send_command", side_effect=fake_send):
            title = client.get_media_title()
        assert title == "The Wire S03E09"

    def test_get_media_title_falls_back_to_filename(self) -> None:
        """get_media_title() falls back to filename when media-title is empty."""
        client = MpvClient()
        client.connect("/tmp/mpvsocket")

        call_count = 0

        def fake_send(cmd):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            prop = cmd["command"][1]
            if prop == "media-title":
                return {"data": "", "error": "success"}
            if prop == "filename":
                return {"data": "sopranos.s04e07.mkv", "error": "success"}
            return None

        with patch.object(client, "_send_command", side_effect=fake_send):
            title = client.get_media_title()
        assert title == "sopranos.s04e07.mkv"

    def test_get_media_title_returns_none_when_both_fail(self) -> None:
        """get_media_title() returns None when both properties are empty."""
        client = MpvClient()
        client.connect("/tmp/mpvsocket")
        with patch.object(client, "_send_command", return_value={"data": None, "error": "success"}):
            title = client.get_media_title()
        assert title is None

    def test_get_position(self) -> None:
        """get_position() returns float seconds from time-pos property."""
        client = MpvClient()
        client.connect("/tmp/mpvsocket")
        with patch.object(
            client, "_send_command", return_value={"data": 123.45, "error": "success"}
        ):
            pos = client.get_position()
        assert pos == pytest.approx(123.45)

    def test_get_duration(self) -> None:
        """get_duration() returns float seconds from duration property."""
        client = MpvClient()
        client.connect("/tmp/mpvsocket")
        with patch.object(
            client, "_send_command", return_value={"data": 2700.0, "error": "success"}
        ):
            dur = client.get_duration()
        assert dur == pytest.approx(2700.0)

    def test_parse_response_matches_request_id(self) -> None:
        """_parse_response() returns the line matching the given request_id."""
        line1 = json.dumps({"event": "property-change", "id": 1})
        line2 = json.dumps({"data": "mpv 0.35.0", "error": "success", "request_id": 42})
        data = (line1 + "\n" + line2 + "\n").encode()
        result = MpvClient._parse_response(data, request_id=42)
        assert result is not None
        assert result["data"] == "mpv 0.35.0"

    def test_parse_response_empty_data_returns_none(self) -> None:
        """_parse_response() returns None for empty bytes."""
        result = MpvClient._parse_response(b"", request_id=1)
        assert result is None
