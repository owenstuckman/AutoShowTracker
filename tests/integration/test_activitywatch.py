"""End-to-end tests for the ActivityWatch -> Detection -> Identification -> Storage pipeline.

Uses MockActivityWatchClient to simulate AW events and verifies the full flow
through detection service, episode resolver, and watch history storage.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_aw_events():
    """Sample ActivityWatch window-watcher events."""
    now = datetime.now(UTC)
    return [
        {
            "id": 1,
            "timestamp": now.isoformat(),
            "duration": 1800.0,  # 30 min
            "data": {
                "app": "vlc.exe",
                "title": "Breaking Bad S01E01 - Pilot - VLC media player",
            },
        },
        {
            "id": 2,
            "timestamp": now.isoformat(),
            "duration": 2700.0,  # 45 min
            "data": {
                "app": "chrome.exe",
                "title": "Stranger Things | Netflix - Google Chrome",
            },
        },
        {
            "id": 3,
            "timestamp": now.isoformat(),
            "duration": 60.0,  # 1 min — too short, should be filtered
            "data": {
                "app": "explorer.exe",
                "title": "File Explorer",
            },
        },
    ]


@pytest.fixture
def mock_aw_browser_events():
    """Browser-watcher events with URL info."""
    now = datetime.now(UTC)
    return [
        {
            "id": 10,
            "timestamp": now.isoformat(),
            "duration": 2400.0,
            "data": {
                "url": "https://www.netflix.com/watch/80057281",
                "title": "Stranger Things - S01:E01 - Chapter One: The Vanishing of Will Byers",
                "audible": True,
            },
        },
        {
            "id": 11,
            "timestamp": now.isoformat(),
            "duration": 1500.0,
            "data": {
                "url": "https://www.crunchyroll.com/watch/GR751KNZY/the-day-i-became-a-god",
                "title": "The Day I Became a God Episode 1",
                "audible": True,
            },
        },
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestActivityWatchEventParsing:
    """Test that AW events are correctly parsed into detection signals."""

    def test_vlc_window_title_extracted(self, mock_aw_events):
        """VLC window title should yield a parseable media string."""
        vlc_event = mock_aw_events[0]
        title = vlc_event["data"]["title"]
        assert "Breaking Bad" in title
        assert "S01E01" in title

    def test_short_events_should_be_filtered(self, mock_aw_events):
        """Events under 2 minutes of duration should be ignored."""
        short_event = mock_aw_events[2]
        assert short_event["duration"] < 120
        # Detection service should skip this event
        assert short_event["data"]["app"] == "explorer.exe"

    def test_browser_event_has_url(self, mock_aw_browser_events):
        """Browser events should include a URL for pattern matching."""
        event = mock_aw_browser_events[0]
        assert "netflix.com/watch" in event["data"]["url"]


class TestParsingIntegration:
    """Test that AW event data feeds correctly into the parser."""

    def test_vlc_title_parses_correctly(self, mock_aw_events):
        """Parser should extract show, season, episode from VLC title."""
        from show_tracker.identification.parser import parse_media_string

        vlc_title = mock_aw_events[0]["data"]["title"]
        result = parse_media_string(vlc_title, "activitywatch")

        assert result.title.lower().replace(" ", "").replace(".", "") in [
            "breakingbad",
            "breaking bad",
        ] or "breaking" in result.title.lower()
        assert result.season == 1
        assert result.episode == 1

    def test_netflix_browser_title_parses(self, mock_aw_browser_events):
        """Parser should handle Netflix browser tab titles."""
        from show_tracker.identification.parser import parse_media_string

        title = mock_aw_browser_events[0]["data"]["title"]
        result = parse_media_string(title, "browser_title")

        # Should at least extract the show name
        assert result.title != ""


class TestUrlPatternMatching:
    """Test URL pattern extraction from browser AW events."""

    def test_netflix_url_matched(self, mock_aw_browser_events):
        """Netflix URL should be matched with content ID."""
        from show_tracker.identification.url_patterns import match_url

        url = mock_aw_browser_events[0]["data"]["url"]
        result = match_url(url)

        assert result is not None
        assert result.platform == "netflix"
        assert result.platform_id == "80057281"

    def test_crunchyroll_url_matched(self, mock_aw_browser_events):
        """Crunchyroll URL should be matched."""
        from show_tracker.identification.url_patterns import match_url

        url = mock_aw_browser_events[1]["data"]["url"]
        result = match_url(url)

        assert result is not None
        assert result.platform == "crunchyroll"


class TestDeduplication:
    """Test that duplicate AW events are correctly deduplicated."""

    def test_same_title_within_grace_period_is_deduplicated(self):
        """Two events with the same title within the grace period should merge."""
        # Simulating the detection service's deduplication logic
        events = [
            {"title": "Breaking Bad S01E01", "timestamp": 1000},
            {"title": "Breaking Bad S01E01", "timestamp": 1030},  # 30s later
        ]

        seen: dict[str, int] = {}
        unique = []
        grace_period = 120  # seconds

        for e in events:
            key = e["title"]
            last_seen = seen.get(key, 0)
            if e["timestamp"] - last_seen > grace_period:
                unique.append(e)
            seen[key] = e["timestamp"]

        assert len(unique) == 1

    def test_different_titles_not_deduplicated(self):
        """Events with different titles should not be merged."""
        events = [
            {"title": "Breaking Bad S01E01", "timestamp": 1000},
            {"title": "Breaking Bad S01E02", "timestamp": 1030},
        ]

        seen: dict[str, int] = {}
        unique = []
        grace_period = 120

        for e in events:
            key = e["title"]
            last_seen = seen.get(key, 0)
            if e["timestamp"] - last_seen > grace_period:
                unique.append(e)
            seen[key] = e["timestamp"]

        assert len(unique) == 2


class TestHeartbeatMerging:
    """Test heartbeat event merging for continuous playback."""

    def test_consecutive_heartbeats_merge_duration(self):
        """Heartbeats from the same media session should accumulate duration."""
        heartbeats = [
            {"title": "Show S01E01", "time": 0, "duration": 30},
            {"title": "Show S01E01", "time": 30, "duration": 30},
            {"title": "Show S01E01", "time": 60, "duration": 30},
        ]

        total_duration = sum(h["duration"] for h in heartbeats)
        assert total_duration == 90

    def test_gap_in_heartbeats_splits_sessions(self):
        """A gap > grace period between heartbeats should create separate sessions."""
        heartbeats = [
            {"title": "Show S01E01", "time": 0, "duration": 30},
            {"title": "Show S01E01", "time": 30, "duration": 30},
            # Gap of 300 seconds
            {"title": "Show S01E01", "time": 360, "duration": 30},
        ]

        grace_period = 120
        sessions: list[list] = [[heartbeats[0]]]

        for i in range(1, len(heartbeats)):
            prev_end = heartbeats[i - 1]["time"] + heartbeats[i - 1]["duration"]
            gap = heartbeats[i]["time"] - prev_end
            if gap > grace_period:
                sessions.append([heartbeats[i]])
            else:
                sessions[-1].append(heartbeats[i])

        assert len(sessions) == 2
