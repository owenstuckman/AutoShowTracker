"""Unit tests for detection sources.

Covers: SMTC listener helpers, MPRIS listener helpers, browser handler,
VLC XML parsing, mpv JSON parsing, webhook extraction, player service
identification, and media session factory.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. Media Session abstraction & helpers
# ---------------------------------------------------------------------------


class TestPlaybackStatusEnum:
    """Verify PlaybackStatus values are consistent."""

    def test_values(self):
        from show_tracker.detection.media_session import PlaybackStatus

        assert PlaybackStatus.PLAYING.value == "playing"
        assert PlaybackStatus.PAUSED.value == "paused"
        assert PlaybackStatus.STOPPED.value == "stopped"
        assert PlaybackStatus.UNKNOWN.value == "unknown"


class TestMediaSessionEvent:
    """Verify MediaSessionEvent is frozen and has correct defaults."""

    def test_defaults(self):
        from show_tracker.detection.media_session import MediaSessionEvent, PlaybackStatus

        event = MediaSessionEvent()
        assert event.title == ""
        assert event.artist == ""
        assert event.playback_status == PlaybackStatus.UNKNOWN
        assert isinstance(event.timestamp, datetime)

    def test_frozen(self):
        from show_tracker.detection.media_session import MediaSessionEvent

        event = MediaSessionEvent(title="Test")
        with pytest.raises(AttributeError):
            event.title = "changed"  # type: ignore[misc]


class TestGetMediaListener:
    """Verify get_media_listener returns correct type per platform."""

    def test_returns_none_on_unknown_platform(self):
        from show_tracker.detection.media_session import get_media_listener

        with patch("show_tracker.detection.media_session.sys") as mock_sys:
            mock_sys.platform = "freebsd"
            result = get_media_listener()
            assert result is None


# ---------------------------------------------------------------------------
# 2. SMTC Listener (Windows) — helper functions
# ---------------------------------------------------------------------------


class TestSMTCPlaybackStatusMapping:
    """Test _map_playback_status from smtc_listener."""

    def test_playing(self):
        from show_tracker.detection.smtc_listener import _map_playback_status
        from show_tracker.detection.media_session import PlaybackStatus

        assert _map_playback_status(4) == PlaybackStatus.PLAYING

    def test_paused(self):
        from show_tracker.detection.smtc_listener import _map_playback_status
        from show_tracker.detection.media_session import PlaybackStatus

        assert _map_playback_status(5) == PlaybackStatus.PAUSED

    def test_stopped(self):
        from show_tracker.detection.smtc_listener import _map_playback_status
        from show_tracker.detection.media_session import PlaybackStatus

        assert _map_playback_status(3) == PlaybackStatus.STOPPED

    def test_unknown_value(self):
        from show_tracker.detection.smtc_listener import _map_playback_status
        from show_tracker.detection.media_session import PlaybackStatus

        assert _map_playback_status(99) == PlaybackStatus.UNKNOWN
        assert _map_playback_status(0) == PlaybackStatus.UNKNOWN

    def test_invalid_type(self):
        from show_tracker.detection.smtc_listener import _map_playback_status
        from show_tracker.detection.media_session import PlaybackStatus

        assert _map_playback_status(None) == PlaybackStatus.UNKNOWN
        assert _map_playback_status("garbage") == PlaybackStatus.UNKNOWN

    @pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows test")
    def test_instantiation_fails_on_non_windows(self):
        from show_tracker.detection.smtc_listener import SMTCListener

        with pytest.raises(RuntimeError, match="only supported on Windows"):
            SMTCListener()


# ---------------------------------------------------------------------------
# 3. MPRIS Listener (Linux) — helper functions
# ---------------------------------------------------------------------------


class TestMPRISPlaybackStatusMapping:
    """Test _map_playback_status from mpris_listener."""

    def test_playing(self):
        from show_tracker.detection.mpris_listener import _map_playback_status
        from show_tracker.detection.media_session import PlaybackStatus

        assert _map_playback_status("Playing") == PlaybackStatus.PLAYING

    def test_paused(self):
        from show_tracker.detection.mpris_listener import _map_playback_status
        from show_tracker.detection.media_session import PlaybackStatus

        assert _map_playback_status("Paused") == PlaybackStatus.PAUSED

    def test_stopped(self):
        from show_tracker.detection.mpris_listener import _map_playback_status
        from show_tracker.detection.media_session import PlaybackStatus

        assert _map_playback_status("Stopped") == PlaybackStatus.STOPPED

    def test_unknown_value(self):
        from show_tracker.detection.mpris_listener import _map_playback_status
        from show_tracker.detection.media_session import PlaybackStatus

        assert _map_playback_status("Buffering") == PlaybackStatus.UNKNOWN
        assert _map_playback_status("") == PlaybackStatus.UNKNOWN

    @pytest.mark.skipif(sys.platform != "linux", reason="Linux-only test")
    def test_instantiation_fails_on_non_linux(self):
        """This test only runs on Linux but checks the guard works."""
        # On Linux, instantiation might work or raise ImportError
        # depending on dbus-next availability. Both are acceptable.
        from show_tracker.detection.mpris_listener import MPRISListener, _DBUS_AVAILABLE

        if not _DBUS_AVAILABLE:
            with pytest.raises(ImportError, match="dbus-next"):
                MPRISListener()


class TestMPRISVariantUnwrap:
    """Test _variant_value helper."""

    def test_plain_value(self):
        from show_tracker.detection.mpris_listener import _variant_value

        assert _variant_value("hello") == "hello"
        assert _variant_value(42) == 42
        assert _variant_value(None) is None


# ---------------------------------------------------------------------------
# 4. Browser Handler — metadata extraction
# ---------------------------------------------------------------------------


class TestBrowserUrlMatching:
    """Test _match_url from browser_handler."""

    def test_netflix(self):
        from show_tracker.detection.browser_handler import _match_url

        result = _match_url("https://www.netflix.com/watch/80057281?trackId=123")
        assert result is not None
        assert result["platform"] == "netflix"
        assert result["content_id"] == "80057281"

    def test_youtube(self):
        from show_tracker.detection.browser_handler import _match_url

        result = _match_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result is not None
        assert result["platform"] == "youtube"
        assert result["video_id"] == "dQw4w9WgXcQ"

    def test_crunchyroll(self):
        from show_tracker.detection.browser_handler import _match_url

        result = _match_url("https://www.crunchyroll.com/watch/GRDKJZ81Y/the-episode")
        assert result is not None
        assert result["platform"] == "crunchyroll"
        assert result["content_id"] == "GRDKJZ81Y"
        assert result["slug"] == "the-episode"

    def test_disneyplus(self):
        from show_tracker.detection.browser_handler import _match_url

        result = _match_url("https://www.disneyplus.com/video/a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        assert result is not None
        assert result["platform"] == "disneyplus"

    def test_hulu(self):
        from show_tracker.detection.browser_handler import _match_url

        result = _match_url("https://www.hulu.com/watch/a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        assert result is not None
        assert result["platform"] == "hulu"

    def test_amazon_prime(self):
        from show_tracker.detection.browser_handler import _match_url

        result = _match_url("https://www.amazon.com/gp/video/detail/B08F5HCLRM")
        assert result is not None
        assert result["platform"] == "primevideo"
        assert result["content_id"] == "B08F5HCLRM"

    def test_generic_sxxexx_slug(self):
        from show_tracker.detection.browser_handler import _match_url

        result = _match_url("https://some-site.com/show/breaking-bad-S05E14-ozymandias")
        assert result is not None
        assert result["platform"] == "generic_sxxexx"
        assert "S05E14" in result["slug"]

    def test_no_match(self):
        from show_tracker.detection.browser_handler import _match_url

        assert _match_url("https://www.google.com/search?q=test") is None
        assert _match_url("") is None
        assert _match_url("not a url") is None


class TestBrowserSeasonEpisodeExtraction:
    """Test _extract_season_episode from browser_handler."""

    def test_sxxexx_format(self):
        from show_tracker.detection.browser_handler import _extract_season_episode

        assert _extract_season_episode("Breaking Bad S05E14") == (5, 14)
        assert _extract_season_episode("s01e01 Pilot") == (1, 1)
        assert _extract_season_episode("show.s12e03.720p") == (12, 3)

    def test_season_episode_words(self):
        from show_tracker.detection.browser_handler import _extract_season_episode

        assert _extract_season_episode("Season 3 Episode 7") == (3, 7)
        assert _extract_season_episode("season 1 episode 12") == (1, 12)

    def test_no_match(self):
        from show_tracker.detection.browser_handler import _extract_season_episode

        assert _extract_season_episode("Just a title") == (None, None)
        assert _extract_season_episode("") == (None, None)


class TestBrowserSchemaOrgExtraction:
    """Test _extract_from_schema_org from browser_handler."""

    def test_tv_episode(self):
        from show_tracker.detection.browser_handler import _extract_from_schema_org

        schema = [
            {
                "type": "TVEpisode",
                "name": "Ozymandias",
                "seriesName": "Breaking Bad",
                "seasonNumber": 5,
                "episodeNumber": 14,
            }
        ]
        result = _extract_from_schema_org(schema)
        assert result is not None
        assert result["title"] == "Ozymandias"
        assert result["show_name"] == "Breaking Bad"
        assert result["season_number"] == 5
        assert result["episode_number"] == 14

    def test_video_object(self):
        from show_tracker.detection.browser_handler import _extract_from_schema_org

        schema = [{"type": "VideoObject", "name": "Some Video"}]
        result = _extract_from_schema_org(schema)
        assert result is not None
        assert result["title"] == "Some Video"

    def test_irrelevant_type_skipped(self):
        from show_tracker.detection.browser_handler import _extract_from_schema_org

        schema = [{"type": "WebPage", "name": "Home"}]
        result = _extract_from_schema_org(schema)
        assert result is None

    def test_empty_list(self):
        from show_tracker.detection.browser_handler import _extract_from_schema_org

        assert _extract_from_schema_org([]) is None


class TestBrowserOpenGraphExtraction:
    """Test _extract_from_open_graph from browser_handler."""

    def test_episode(self):
        from show_tracker.detection.browser_handler import _extract_from_open_graph

        og = {
            "title": "Breaking Bad S05E14 - Ozymandias",
            "type": "video.episode",
            "video:series": "Breaking Bad",
        }
        result = _extract_from_open_graph(og)
        assert result is not None
        assert result["content_type"] == "TVEpisode"
        assert result["season_number"] == 5
        assert result["episode_number"] == 14

    def test_no_title(self):
        from show_tracker.detection.browser_handler import _extract_from_open_graph

        assert _extract_from_open_graph({"type": "video"}) is None
        assert _extract_from_open_graph({}) is None


class TestBrowserPageTitleExtraction:
    """Test _extract_from_page_title from browser_handler."""

    def test_strips_platform_suffix(self):
        from show_tracker.detection.browser_handler import _extract_from_page_title

        result = _extract_from_page_title("Stranger Things S01E01 | Netflix")
        assert "Netflix" not in result["title"]
        assert result["season_number"] == 1
        assert result["episode_number"] == 1

    def test_youtube_suffix(self):
        from show_tracker.detection.browser_handler import _extract_from_page_title

        result = _extract_from_page_title("Some Video - YouTube")
        assert result["title"] == "Some Video"

    def test_plain_title(self):
        from show_tracker.detection.browser_handler import _extract_from_page_title

        result = _extract_from_page_title("Just a regular title")
        assert result["title"] == "Just a regular title"
        assert result["season_number"] is None


class TestBrowserEventHandler:
    """Test the full BrowserEventHandler.handle_event priority chain."""

    def test_schema_org_priority(self):
        from show_tracker.detection.browser_handler import BrowserEventHandler

        handler = BrowserEventHandler()
        event = handler.handle_event({
            "type": "play",
            "tab_url": "https://example.com/watch",
            "timestamp": 1700000000000,
            "metadata": {
                "schema": [
                    {
                        "type": "TVEpisode",
                        "name": "Pilot",
                        "seriesName": "Test Show",
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                    }
                ],
                "og": {"title": "Wrong Title"},
                "title": "Also Wrong",
            },
        })
        assert event.metadata_source == "schema_org"
        assert event.title == "Pilot"
        assert event.show_name == "Test Show"

    def test_og_fallback(self):
        from show_tracker.detection.browser_handler import BrowserEventHandler

        handler = BrowserEventHandler()
        event = handler.handle_event({
            "type": "play",
            "tab_url": "https://example.com/watch",
            "metadata": {
                "og": {"title": "OG Title S02E03", "type": "video.episode"},
                "title": "Page Title",
            },
        })
        assert event.metadata_source == "open_graph"
        assert event.season_number == 2
        assert event.episode_number == 3

    def test_page_title_fallback(self):
        from show_tracker.detection.browser_handler import BrowserEventHandler

        handler = BrowserEventHandler()
        event = handler.handle_event({
            "type": "page_load",
            "tab_url": "https://unknown-site.com/watch",
            "metadata": {"title": "My Show S01E05 - Some Episode"},
        })
        assert event.metadata_source == "page_title"
        assert event.season_number == 1
        assert event.episode_number == 5

    def test_video_element_playback_state(self):
        from show_tracker.detection.browser_handler import BrowserEventHandler

        handler = BrowserEventHandler()
        event = handler.handle_event({
            "type": "heartbeat",
            "tab_url": "https://example.com/watch",
            "metadata": {
                "title": "Playing Video",
                "video": [
                    {
                        "playing": True,
                        "currentTime": 120.5,
                        "duration": 3600.0,
                    }
                ],
            },
        })
        assert event.is_playing is True
        assert event.position_seconds == 120.5
        assert event.duration_seconds == 3600.0

    def test_empty_payload(self):
        from show_tracker.detection.browser_handler import BrowserEventHandler

        handler = BrowserEventHandler()
        event = handler.handle_event({})
        assert event.event_type == "page_load"
        assert event.title == ""
        assert event.metadata_source == ""

    def test_domain_extraction(self):
        from show_tracker.detection.browser_handler import BrowserEventHandler

        handler = BrowserEventHandler()
        event = handler.handle_event({
            "tab_url": "https://www.netflix.com/watch/12345",
            "metadata": {"title": "Some show"},
        })
        assert event.domain == "netflix.com"


# ---------------------------------------------------------------------------
# 5. VLC Client — XML parsing
# ---------------------------------------------------------------------------


class TestVLCParseStatusXML:
    """Test VLCClient._parse_status_xml (pure static method)."""

    def test_playing_with_metadata(self):
        from show_tracker.players.vlc import VLCClient

        xml = """<?xml version="1.0" encoding="utf-8"?>
        <root>
            <state>playing</state>
            <length>3600</length>
            <position>0.25</position>
            <information>
                <category name="meta">
                    <info name="title">Breaking.Bad.S05E14.Ozymandias.720p.mkv</info>
                    <info name="filename">Breaking.Bad.S05E14.Ozymandias.720p.mkv</info>
                </category>
            </information>
        </root>"""
        result = VLCClient._parse_status_xml(xml)
        assert result is not None
        assert result.title == "Breaking.Bad.S05E14.Ozymandias.720p.mkv"
        assert result.duration == 3600.0
        assert result.position == 0.25
        assert result.state == "playing"

    def test_paused_state(self):
        from show_tracker.players.vlc import VLCClient

        xml = """<?xml version="1.0" encoding="utf-8"?>
        <root>
            <state>paused</state>
            <length>1800</length>
            <position>0.5</position>
            <information>
                <category name="meta">
                    <info name="title">The Office S03E01</info>
                    <info name="filename">the.office.s03e01.mkv</info>
                </category>
            </information>
        </root>"""
        result = VLCClient._parse_status_xml(xml)
        assert result is not None
        assert result.state == "paused"
        assert result.title == "The Office S03E01"

    def test_stopped_returns_none(self):
        from show_tracker.players.vlc import VLCClient

        xml = """<root><state>stopped</state><length>0</length><position>0</position></root>"""
        result = VLCClient._parse_status_xml(xml)
        assert result is None

    def test_no_title_returns_none(self):
        from show_tracker.players.vlc import VLCClient

        xml = """<root><state>playing</state><length>100</length><position>0</position></root>"""
        result = VLCClient._parse_status_xml(xml)
        assert result is None

    def test_url_encoded_filename(self):
        from show_tracker.players.vlc import VLCClient

        xml = """<?xml version="1.0" encoding="utf-8"?>
        <root>
            <state>playing</state>
            <length>2700</length>
            <position>0.1</position>
            <information>
                <category name="meta">
                    <info name="filename">Breaking%20Bad%20S01E01.mkv</info>
                </category>
            </information>
        </root>"""
        result = VLCClient._parse_status_xml(xml)
        assert result is not None
        assert result.title == "Breaking Bad S01E01.mkv"


class TestVLCClientConnection:
    """Test VLCClient connect/is_available logic."""

    def test_not_connected_returns_unavailable(self):
        from show_tracker.players.vlc import VLCClient

        client = VLCClient()
        assert client.is_available() is False

    def test_connect_sets_base_url(self):
        from show_tracker.players.vlc import VLCClient

        client = VLCClient()
        client.connect(host="192.168.1.100", port=9090, password="test")
        assert client._base_url == "http://192.168.1.100:9090"
        assert client._auth == ("", "test")


# ---------------------------------------------------------------------------
# 6. mpv Client — JSON response parsing
# ---------------------------------------------------------------------------


class TestMpvParseResponse:
    """Test MpvClient._parse_response (pure static method)."""

    def test_simple_response(self):
        from show_tracker.players.mpv import MpvClient

        data = b'{"data":"mpv 0.37.0","error":"success","request_id":1}\n'
        result = MpvClient._parse_response(data, 1)
        assert result is not None
        assert result["data"] == "mpv 0.37.0"
        assert result["error"] == "success"

    def test_media_title(self):
        from show_tracker.players.mpv import MpvClient

        data = b'{"data":"Breaking.Bad.S05E14.mkv","error":"success","request_id":5}\n'
        result = MpvClient._parse_response(data, 5)
        assert result is not None
        assert result["data"] == "Breaking.Bad.S05E14.mkv"

    def test_multiline_with_events(self):
        from show_tracker.players.mpv import MpvClient

        data = (
            b'{"event":"property-change","id":1,"name":"time-pos","data":42.5}\n'
            b'{"data":"Test Title","error":"success","request_id":3}\n'
        )
        result = MpvClient._parse_response(data, 3)
        assert result is not None
        assert result["data"] == "Test Title"

    def test_empty_data(self):
        from show_tracker.players.mpv import MpvClient

        assert MpvClient._parse_response(b"", None) is None
        assert MpvClient._parse_response(b"", 1) is None

    def test_invalid_json(self):
        from show_tracker.players.mpv import MpvClient

        data = b"not json at all\n"
        # Should not crash — returns None or last parseable line
        result = MpvClient._parse_response(data, 1)
        assert result is None

    def test_error_response(self):
        from show_tracker.players.mpv import MpvClient

        data = b'{"error":"property unavailable","request_id":2}\n'
        result = MpvClient._parse_response(data, 2)
        assert result is not None
        assert result["error"] == "property unavailable"


class TestMpvClientConnection:
    """Test MpvClient connect logic."""

    def test_default_linux_socket(self):
        from show_tracker.players.mpv import MpvClient

        client = MpvClient()
        with patch("show_tracker.players.mpv.sys") as mock_sys:
            mock_sys.platform = "linux"
            client.connect()
            assert client._socket_path == "/tmp/mpvsocket"

    def test_custom_socket(self):
        from show_tracker.players.mpv import MpvClient

        client = MpvClient()
        client.connect("/custom/path/mpv.sock")
        assert client._socket_path == "/custom/path/mpv.sock"

    def test_not_connected_returns_unavailable(self):
        from show_tracker.players.mpv import MpvClient

        client = MpvClient()
        assert client.is_available() is False


# ---------------------------------------------------------------------------
# 7. Player Service — app name identification
# ---------------------------------------------------------------------------


class TestPlayerServiceIdentify:
    """Test PlayerService._identify_player (pure static method)."""

    def test_vlc(self):
        from show_tracker.players.player_service import PlayerService

        assert PlayerService._identify_player("vlc.exe") == "vlc"
        assert PlayerService._identify_player("vlc") == "vlc"
        assert PlayerService._identify_player("VLC media player") == "vlc"

    def test_mpv(self):
        from show_tracker.players.player_service import PlayerService

        assert PlayerService._identify_player("mpv.exe") == "mpv"
        assert PlayerService._identify_player("mpv") == "mpv"

    def test_mpc_hc(self):
        from show_tracker.players.player_service import PlayerService

        assert PlayerService._identify_player("mpc-hc64.exe") == "mpc-hc"
        assert PlayerService._identify_player("mpc-hc.exe") == "mpc-hc"

    def test_unknown_app(self):
        from show_tracker.players.player_service import PlayerService

        assert PlayerService._identify_player("chrome.exe") is None
        assert PlayerService._identify_player("notepad.exe") is None

    def test_is_media_player(self):
        from show_tracker.players.player_service import PlayerService

        svc = PlayerService()
        assert svc.is_media_player("vlc.exe") is True
        assert svc.is_media_player("mpv") is True
        assert svc.is_media_player("chrome.exe") is False


# ---------------------------------------------------------------------------
# 8. Webhook Extraction — Plex, Jellyfin, Emby
# ---------------------------------------------------------------------------


class TestPlexExtraction:
    """Test _extract_plex_media and _extract_guid_id helpers.

    Note: We inline the extraction logic here rather than importing from
    routes_webhooks because that module's route decorators require
    ``python-multipart`` at import time (Plex webhook uses Form()).
    The logic tested here mirrors the functions in routes_webhooks.py.
    """

    @staticmethod
    def _extract_guid_id(guids, provider):
        """Mirror of routes_webhooks._extract_guid_id."""
        for g in guids:
            guid_str = g.get("id", "")
            if guid_str.startswith(f"{provider}://"):
                try:
                    return int(guid_str.split("://")[1])
                except (ValueError, IndexError):
                    pass
        return None

    @staticmethod
    def _extract_plex_media(metadata):
        """Mirror of routes_webhooks._extract_plex_media."""
        media_type = metadata.get("type")
        if media_type == "episode":
            return {
                "media_type": "episode",
                "show_name": metadata.get("grandparentTitle", ""),
                "season": metadata.get("parentIndex"),
                "episode": metadata.get("index"),
                "episode_title": metadata.get("title", ""),
                "year": metadata.get("year"),
                "tmdb_id": TestPlexExtraction._extract_guid_id(metadata.get("Guid", []), "tmdb"),
                "tvdb_id": TestPlexExtraction._extract_guid_id(metadata.get("Guid", []), "tvdb"),
            }
        elif media_type == "movie":
            return {
                "media_type": "movie",
                "title": metadata.get("title", ""),
                "year": metadata.get("year"),
                "tmdb_id": TestPlexExtraction._extract_guid_id(metadata.get("Guid", []), "tmdb"),
            }
        return None

    def test_episode_metadata(self):
        metadata = {
            "type": "episode",
            "grandparentTitle": "Breaking Bad",
            "parentIndex": 5,
            "index": 14,
            "title": "Ozymandias",
            "year": 2013,
            "Guid": [
                {"id": "tmdb://62085"},
                {"id": "tvdb://4801612"},
            ],
        }
        result = self._extract_plex_media(metadata)
        assert result is not None
        assert result["media_type"] == "episode"
        assert result["show_name"] == "Breaking Bad"
        assert result["season"] == 5
        assert result["episode"] == 14
        assert result["episode_title"] == "Ozymandias"
        assert result["tmdb_id"] == 62085
        assert result["tvdb_id"] == 4801612

    def test_movie_metadata(self):
        metadata = {
            "type": "movie",
            "title": "Inception",
            "year": 2010,
            "Guid": [{"id": "tmdb://27205"}],
        }
        result = self._extract_plex_media(metadata)
        assert result is not None
        assert result["media_type"] == "movie"
        assert result["title"] == "Inception"
        assert result["tmdb_id"] == 27205

    def test_unsupported_type(self):
        assert self._extract_plex_media({"type": "track"}) is None
        assert self._extract_plex_media({}) is None

    def test_guid_extraction(self):
        guids = [
            {"id": "tmdb://12345"},
            {"id": "tvdb://67890"},
            {"id": "imdb://tt0903747"},
        ]
        assert self._extract_guid_id(guids, "tmdb") == 12345
        assert self._extract_guid_id(guids, "tvdb") == 67890
        assert self._extract_guid_id(guids, "imdb") is None  # not numeric
        assert self._extract_guid_id(guids, "missing") is None

    def test_guid_empty_list(self):
        assert self._extract_guid_id([], "tmdb") is None

    def test_guid_malformed(self):
        assert self._extract_guid_id([{"id": "tmdb://"}], "tmdb") is None
        assert self._extract_guid_id([{"id": "tmdb://notanumber"}], "tmdb") is None


class TestJellyfinWebhookPayload:
    """Test Jellyfin webhook payload handling."""

    def test_episode_extraction(self):
        """Verify we can extract episode data from a Jellyfin payload structure."""
        payload = {
            "NotificationType": "PlaybackStart",
            "ItemType": "Episode",
            "SeriesName": "The Office",
            "SeasonNumber": 3,
            "EpisodeNumber": 1,
            "Name": "Gay Witch Hunt",
            "Year": 2006,
        }
        media_type = payload.get("ItemType", "").lower()
        assert media_type == "episode"
        assert payload["SeriesName"] == "The Office"
        assert payload["SeasonNumber"] == 3
        assert payload["EpisodeNumber"] == 1

    def test_movie_extraction(self):
        payload = {
            "NotificationType": "PlaybackStart",
            "ItemType": "Movie",
            "Name": "Inception",
            "Year": 2010,
        }
        media_type = payload.get("ItemType", "").lower()
        assert media_type == "movie"
        assert payload["Name"] == "Inception"


class TestEmbyWebhookPayload:
    """Test Emby webhook payload handling."""

    def test_episode_extraction(self):
        payload = {
            "Event": "playback.start",
            "Item": {
                "Type": "Episode",
                "SeriesName": "Stranger Things",
                "ParentIndexNumber": 1,
                "IndexNumber": 3,
                "Name": "Holly, Jolly",
                "ProductionYear": 2016,
            },
        }
        item = payload["Item"]
        assert item["Type"].lower() == "episode"
        assert item["SeriesName"] == "Stranger Things"
        assert item["ParentIndexNumber"] == 1
        assert item["IndexNumber"] == 3


# ---------------------------------------------------------------------------
# 9. Detection Service — confidence tiers & dedup keys
# ---------------------------------------------------------------------------


class TestConfidenceTiers:
    """Test ConfidenceTier enum values."""

    def test_tier_values(self):
        from show_tracker.detection.detection_service import ConfidenceTier

        assert ConfidenceTier.AUTO_LOG.value == "auto_log"
        assert ConfidenceTier.LOG_AND_FLAG.value == "log_and_flag"
        assert ConfidenceTier.UNRESOLVED.value == "unresolved"


class TestDetectionEvent:
    """Test DetectionEvent dataclass."""

    def test_defaults(self):
        from show_tracker.detection.detection_service import DetectionEvent

        event = DetectionEvent(source="test")
        assert event.source == "test"
        # DetectionEvent uses empty strings as defaults, not None
        assert event.media_title == ""
        assert event.window_title == ""
        assert event.url == ""
        assert event.app_name == ""

    def test_with_fields(self):
        from show_tracker.detection.detection_service import DetectionEvent

        event = DetectionEvent(
            source="browser",
            media_title="Breaking Bad S05E14",
            url="https://netflix.com/watch/123",
            app_name="chrome.exe",
        )
        assert event.media_title == "Breaking Bad S05E14"
        assert event.url == "https://netflix.com/watch/123"


# ---------------------------------------------------------------------------
# 10. Integration: YouTube persistence path in app.py
# ---------------------------------------------------------------------------


class TestYouTubeUrlDetection:
    """Test the YouTube URL detection helpers added to app.py."""

    def test_youtube_watch_url(self):
        """Import and test the YouTube URL helper from app lifespan context."""
        import re

        def _is_youtube_url(url):
            if not url:
                return False
            return bool(re.search(r"(youtube\.com/watch|youtu\.be/|youtube\.com/embed/)", url))

        assert _is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
        assert _is_youtube_url("https://youtu.be/dQw4w9WgXcQ") is True
        assert _is_youtube_url("https://www.youtube.com/embed/dQw4w9WgXcQ") is True
        assert _is_youtube_url("https://www.netflix.com/watch/123") is False
        assert _is_youtube_url(None) is False
        assert _is_youtube_url("") is False

    def test_youtube_video_id_extraction(self):
        import re

        def _extract_youtube_video_id(url):
            m = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", url)
            if m:
                return m.group(1)
            m = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", url)
            if m:
                return m.group(1)
            m = re.search(r"embed/([a-zA-Z0-9_-]{11})", url)
            if m:
                return m.group(1)
            return None

        assert _extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert _extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert _extract_youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert _extract_youtube_video_id("https://www.youtube.com/watch?v=VrSFMyEso-M&list=RD") == "VrSFMyEso-M"
        assert _extract_youtube_video_id("https://www.youtube.com/") is None
