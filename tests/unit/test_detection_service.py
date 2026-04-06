"""Unit tests for DetectionService — deduplication, grace period, confidence routing,
event conversion, heartbeats, and callback invocation.

Also covers: EventPoller incremental polling, bucket discovery, MockActivityWatchClient,
and BrowserEventHandler event type handling.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest

from show_tracker.detection.activitywatch import (
    EventPoller,
    MockActivityWatchClient,
    discover_media_relevant_buckets,
)
from show_tracker.detection.browser_handler import BrowserMediaEvent
from show_tracker.detection.detection_service import (
    _KNOWN_MEDIA_APPS,
    ActiveWatch,
    ConfidenceTier,
    DetectionEvent,
    DetectionService,
)
from show_tracker.detection.media_session import MediaSessionEvent, PlaybackStatus

# ===========================================================================
# DetectionService._dedup_key
# ===========================================================================


class TestDedupKey:
    """Verify the deduplication key priority chain."""

    def test_structured_show_season_episode(self):
        event = DetectionEvent(show_name="Breaking Bad", season_number=5, episode_number=14)
        assert DetectionService._dedup_key(event) == "breaking bad|s05|e14"

    def test_structured_show_name_only(self):
        event = DetectionEvent(show_name="Stranger Things")
        assert DetectionService._dedup_key(event) == "stranger things"

    def test_structured_show_with_season_no_episode(self):
        event = DetectionEvent(show_name="The Office", season_number=3)
        assert DetectionService._dedup_key(event) == "the office|s03"

    def test_media_title_fallback(self):
        event = DetectionEvent(media_title="  Some Song Title  ")
        assert DetectionService._dedup_key(event) == "some song title"

    def test_window_title_fallback(self):
        event = DetectionEvent(window_title="VLC - Breaking Bad S01E01.mkv")
        assert DetectionService._dedup_key(event) == "vlc - breaking bad s01e01.mkv"

    def test_page_title_fallback(self):
        event = DetectionEvent(page_title="Stranger Things | Netflix")
        assert DetectionService._dedup_key(event) == "stranger things | netflix"

    def test_url_fallback(self):
        event = DetectionEvent(url="https://www.netflix.com/watch/12345")
        assert DetectionService._dedup_key(event) == "https://www.netflix.com/watch/12345"

    def test_empty_event_returns_empty(self):
        event = DetectionEvent()
        assert DetectionService._dedup_key(event) == ""

    def test_show_name_takes_priority_over_media_title(self):
        event = DetectionEvent(
            show_name="Breaking Bad",
            season_number=1,
            episode_number=1,
            media_title="Different Title",
        )
        assert DetectionService._dedup_key(event) == "breaking bad|s01|e01"

    def test_media_title_takes_priority_over_window_title(self):
        event = DetectionEvent(
            media_title="Song Title",
            window_title="Window Title",
        )
        assert DetectionService._dedup_key(event) == "song title"

    def test_same_episode_same_key(self):
        """Two events for the same episode should produce the same key."""
        e1 = DetectionEvent(show_name="The Office", season_number=2, episode_number=5)
        e2 = DetectionEvent(show_name="The Office", season_number=2, episode_number=5)
        assert DetectionService._dedup_key(e1) == DetectionService._dedup_key(e2)

    def test_different_episodes_different_keys(self):
        e1 = DetectionEvent(show_name="The Office", season_number=2, episode_number=5)
        e2 = DetectionEvent(show_name="The Office", season_number=2, episode_number=6)
        assert DetectionService._dedup_key(e1) != DetectionService._dedup_key(e2)


# ===========================================================================
# DetectionService._estimate_confidence
# ===========================================================================


class TestEstimateConfidence:
    """Verify heuristic confidence scoring."""

    def setup_method(self):
        self.svc = DetectionService()

    def test_structured_episode_data(self):
        event = DetectionEvent(show_name="X", season_number=1, episode_number=1)
        assert self.svc._estimate_confidence(event) == 0.85

    def test_media_title_only(self):
        event = DetectionEvent(media_title="Song Title")
        assert self.svc._estimate_confidence(event) == 0.6

    def test_window_title_only(self):
        event = DetectionEvent(window_title="Some Window")
        assert self.svc._estimate_confidence(event) == 0.4

    def test_page_title_only(self):
        event = DetectionEvent(page_title="Netflix Page")
        assert self.svc._estimate_confidence(event) == 0.4

    def test_url_only(self):
        event = DetectionEvent(url="https://example.com")
        assert self.svc._estimate_confidence(event) == 0.3

    def test_empty_event_zero(self):
        event = DetectionEvent()
        assert self.svc._estimate_confidence(event) == 0.0

    def test_known_media_app_boost(self):
        event = DetectionEvent(window_title="Some Video", app_name="vlc")
        assert self.svc._estimate_confidence(event) == 0.5  # 0.4 + 0.1

    def test_known_media_app_boost_capped_at_1(self):
        event = DetectionEvent(show_name="X", season_number=1, episode_number=1, app_name="vlc")
        assert self.svc._estimate_confidence(event) == 0.95  # 0.85 + 0.1

    def test_unknown_app_no_boost(self):
        event = DetectionEvent(window_title="Some Video", app_name="notepad")
        assert self.svc._estimate_confidence(event) == 0.4

    def test_known_media_apps_list(self):
        """All known media apps should be lowercase."""
        for app in _KNOWN_MEDIA_APPS:
            assert app == app.lower()


# ===========================================================================
# DetectionService._confidence_tier
# ===========================================================================


class TestConfidenceTier:
    """Verify confidence-to-tier mapping with default thresholds."""

    def setup_method(self):
        self.svc = DetectionService()

    def test_auto_log_at_threshold(self):
        assert self.svc._confidence_tier(0.9) == ConfidenceTier.AUTO_LOG

    def test_auto_log_above_threshold(self):
        assert self.svc._confidence_tier(0.95) == ConfidenceTier.AUTO_LOG

    def test_log_and_flag_at_review_threshold(self):
        assert self.svc._confidence_tier(0.7) == ConfidenceTier.LOG_AND_FLAG

    def test_log_and_flag_between_thresholds(self):
        assert self.svc._confidence_tier(0.8) == ConfidenceTier.LOG_AND_FLAG

    def test_unresolved_below_review(self):
        assert self.svc._confidence_tier(0.69) == ConfidenceTier.UNRESOLVED

    def test_unresolved_zero(self):
        assert self.svc._confidence_tier(0.0) == ConfidenceTier.UNRESOLVED

    def test_auto_log_at_1(self):
        assert self.svc._confidence_tier(1.0) == ConfidenceTier.AUTO_LOG

    def test_custom_thresholds(self):
        svc = DetectionService(auto_log_threshold=0.8, review_threshold=0.5)
        assert svc._confidence_tier(0.8) == ConfidenceTier.AUTO_LOG
        assert svc._confidence_tier(0.79) == ConfidenceTier.LOG_AND_FLAG
        assert svc._confidence_tier(0.5) == ConfidenceTier.LOG_AND_FLAG
        assert svc._confidence_tier(0.49) == ConfidenceTier.UNRESOLVED


# ===========================================================================
# DetectionService._process_event — deduplication
# ===========================================================================


class TestProcessEventDeduplication:
    """Verify deduplication: same key within grace period = heartbeat, not new watch."""

    def setup_method(self):
        self.svc = DetectionService(heartbeat_interval=30)
        self.callback_calls: list[tuple[DetectionEvent, ConfidenceTier]] = []
        self.svc.register_result_callback(
            lambda event, tier: self.callback_calls.append((event, tier))
        )

    def test_new_event_creates_watch(self):
        event = DetectionEvent(media_title="Breaking Bad S01E01")
        self.svc._process_event(event)
        assert len(self.svc._active_watches) == 1
        assert len(self.callback_calls) == 1

    def test_same_key_within_grace_is_heartbeat(self):
        e1 = DetectionEvent(media_title="Breaking Bad S01E01")
        e2 = DetectionEvent(media_title="Breaking Bad S01E01")
        self.svc._process_event(e1)
        self.svc._process_event(e2)
        # Still only 1 active watch
        assert len(self.svc._active_watches) == 1
        # Second event is a heartbeat, not a new detection.
        # Callback fires once (initial). Heartbeat won't fire because
        # heartbeat_interval (30s) hasn't elapsed.
        assert len(self.callback_calls) == 1

    def test_different_key_creates_separate_watch(self):
        e1 = DetectionEvent(media_title="Show A")
        e2 = DetectionEvent(media_title="Show B")
        self.svc._process_event(e1)
        self.svc._process_event(e2)
        assert len(self.svc._active_watches) == 2
        assert len(self.callback_calls) == 2

    def test_empty_key_skipped(self):
        event = DetectionEvent()  # no title, url, etc.
        self.svc._process_event(event)
        assert len(self.svc._active_watches) == 0
        assert len(self.callback_calls) == 0

    def test_stopped_event_not_started(self):
        event = DetectionEvent(
            media_title="Some Title",
            is_playing=False,
            playback_status=PlaybackStatus.STOPPED,
        )
        self.svc._process_event(event)
        assert len(self.svc._active_watches) == 0

    def test_paused_event_starts_watch(self):
        """Paused is not stopped — should start a watch."""
        event = DetectionEvent(
            media_title="Some Title",
            is_playing=False,
            playback_status=PlaybackStatus.PAUSED,
        )
        self.svc._process_event(event)
        assert len(self.svc._active_watches) == 1

    def test_heartbeat_increments_count(self):
        e1 = DetectionEvent(media_title="Show A")
        e2 = DetectionEvent(media_title="Show A")
        self.svc._process_event(e1)
        self.svc._process_event(e2)
        key = DetectionService._dedup_key(e1)
        watch = self.svc._active_watches[key]
        assert watch.heartbeat_count == 1  # touch() was called once


# ===========================================================================
# DetectionService — heartbeat emission
# ===========================================================================


class TestHeartbeatEmission:
    """Verify heartbeat fires after heartbeat_interval elapses."""

    def test_heartbeat_emits_after_interval(self):
        svc = DetectionService(heartbeat_interval=0)  # immediate heartbeat
        calls: list[tuple[DetectionEvent, ConfidenceTier]] = []
        svc.register_result_callback(lambda e, t: calls.append((e, t)))

        e1 = DetectionEvent(media_title="Show A")
        svc._process_event(e1)
        assert len(calls) == 1  # initial

        # Manually backdate the watch's last_heartbeat so interval has elapsed
        key = DetectionService._dedup_key(e1)
        svc._active_watches[key].last_heartbeat = time.monotonic() - 1

        e2 = DetectionEvent(media_title="Show A")
        svc._process_event(e2)
        # Should have emitted a heartbeat callback
        assert len(calls) == 2


# ===========================================================================
# DetectionService._finalize_watch
# ===========================================================================


class TestFinalizeWatch:
    def test_finalize_removes_from_active(self):
        svc = DetectionService()
        event = DetectionEvent(media_title="Test Show")
        svc._process_event(event)
        key = DetectionService._dedup_key(event)
        assert key in svc._active_watches

        svc._finalize_watch(key)
        assert key not in svc._active_watches

    def test_finalize_nonexistent_key_is_noop(self):
        svc = DetectionService()
        svc._finalize_watch("nonexistent")  # should not raise


# ===========================================================================
# DetectionService — grace period sweeper
# ===========================================================================


class TestGracePeriodSweeper:
    def test_stale_watch_finalized(self):
        svc = DetectionService(grace_period=0)  # immediate expiry
        event = DetectionEvent(media_title="Show A")
        svc._process_event(event)
        key = DetectionService._dedup_key(event)

        # Backdate the heartbeat so it's past grace period
        svc._active_watches[key].last_heartbeat = time.monotonic() - 1

        # Manually run sweeper logic (without async loop)
        now = time.monotonic()
        stale = [
            k for k, w in svc._active_watches.items() if now - w.last_heartbeat > svc._grace_period
        ]
        for k in stale:
            svc._finalize_watch(k)

        assert len(svc._active_watches) == 0

    def test_fresh_watch_not_finalized(self):
        svc = DetectionService(grace_period=9999)
        event = DetectionEvent(media_title="Show A")
        svc._process_event(event)

        now = time.monotonic()
        stale = [
            k for k, w in svc._active_watches.items() if now - w.last_heartbeat > svc._grace_period
        ]
        assert len(stale) == 0
        assert len(svc._active_watches) == 1


# ===========================================================================
# DetectionService — confidence routing via callbacks
# ===========================================================================


class TestConfidenceRouting:
    """Verify events route to correct tier and fire callbacks."""

    def test_high_confidence_auto_log(self):
        svc = DetectionService()
        calls: list[ConfidenceTier] = []
        svc.register_result_callback(lambda e, t: calls.append(t))

        event = DetectionEvent(
            show_name="Breaking Bad", season_number=5, episode_number=14, app_name="vlc"
        )
        svc._process_event(event)
        # 0.85 + 0.1 (vlc) = 0.95 → AUTO_LOG
        assert calls[0] == ConfidenceTier.AUTO_LOG

    def test_medium_confidence_log_and_flag(self):
        svc = DetectionService()
        calls: list[ConfidenceTier] = []
        svc.register_result_callback(lambda e, t: calls.append(t))

        event = DetectionEvent(show_name="X", season_number=1, episode_number=1)
        svc._process_event(event)
        # 0.85 → LOG_AND_FLAG (between 0.7 and 0.9)
        assert calls[0] == ConfidenceTier.LOG_AND_FLAG

    def test_low_confidence_unresolved(self):
        svc = DetectionService()
        calls: list[ConfidenceTier] = []
        svc.register_result_callback(lambda e, t: calls.append(t))

        event = DetectionEvent(url="https://example.com/something")
        svc._process_event(event)
        # 0.3 → UNRESOLVED
        assert calls[0] == ConfidenceTier.UNRESOLVED

    def test_multiple_callbacks_invoked(self):
        svc = DetectionService()
        calls_a: list[DetectionEvent] = []
        calls_b: list[DetectionEvent] = []
        svc.register_result_callback(lambda e, t: calls_a.append(e))
        svc.register_result_callback(lambda e, t: calls_b.append(e))

        event = DetectionEvent(media_title="Test")
        svc._process_event(event)
        assert len(calls_a) == 1
        assert len(calls_b) == 1

    def test_callback_exception_does_not_break_others(self):
        svc = DetectionService()
        calls: list[DetectionEvent] = []

        def bad_callback(e, t):
            raise ValueError("boom")

        svc.register_result_callback(bad_callback)
        svc.register_result_callback(lambda e, t: calls.append(e))

        event = DetectionEvent(media_title="Test")
        svc._process_event(event)
        # Second callback should still fire
        assert len(calls) == 1


# ===========================================================================
# DetectionService — AW event conversion
# ===========================================================================


class TestAWEventConversion:
    def test_window_event_to_detection(self):
        raw = {
            "timestamp": "2026-03-25T12:00:00+00:00",
            "duration": 60.0,
            "data": {"app": "vlc.exe", "title": "Breaking Bad S01E01 - VLC"},
        }
        d = DetectionService._aw_window_event_to_detection(raw)
        assert d.source == "activitywatch_window"
        assert d.window_title == "Breaking Bad S01E01 - VLC"
        assert d.app_name == "vlc.exe"
        assert d.is_playing is True

    def test_window_event_bad_timestamp_fallback(self):
        raw = {"timestamp": "not-a-date", "data": {"app": "x", "title": "y"}}
        d = DetectionService._aw_window_event_to_detection(raw)
        assert isinstance(d.timestamp, datetime)

    def test_web_event_to_detection(self):
        raw = {
            "timestamp": "2026-03-25T12:00:00+00:00",
            "data": {
                "url": "https://www.netflix.com/watch/12345",
                "title": "Stranger Things",
                "audible": True,
            },
        }
        d = DetectionService._aw_web_event_to_detection(raw)
        assert d.source == "activitywatch_web"
        assert d.url == "https://www.netflix.com/watch/12345"
        assert d.page_title == "Stranger Things"
        assert d.is_playing is True

    def test_web_event_not_audible(self):
        raw = {"timestamp": "", "data": {"url": "x", "title": "y", "audible": False}}
        d = DetectionService._aw_web_event_to_detection(raw)
        assert d.is_playing is False

    def test_browser_event_to_detection(self):
        be = BrowserMediaEvent(
            url="https://netflix.com/watch/123",
            title="Stranger Things S01E01",
            show_name="Stranger Things",
            season_number=1,
            episode_number=1,
            is_playing=True,
            metadata_source="schema_org",
        )
        d = DetectionService._browser_event_to_detection(be)
        assert d.source == "browser"
        assert d.show_name == "Stranger Things"
        assert d.season_number == 1
        assert d.episode_number == 1
        assert d.metadata_source == "schema_org"


# ===========================================================================
# ActiveWatch dataclass
# ===========================================================================


class TestActiveWatch:
    def test_touch_updates_heartbeat_count(self):
        watch = ActiveWatch(detection_key="test")
        assert watch.heartbeat_count == 0
        event = DetectionEvent(media_title="X")
        watch.touch(event)
        assert watch.heartbeat_count == 1
        assert watch.last_event is event

    def test_touch_updates_last_heartbeat(self):
        watch = ActiveWatch(detection_key="test")
        # Manually backdate the heartbeat to ensure measurable difference
        watch.last_heartbeat = time.monotonic() - 1.0
        old_hb = watch.last_heartbeat
        watch.touch(DetectionEvent())
        assert watch.last_heartbeat > old_hb


# ===========================================================================
# EventPoller — incremental polling
# ===========================================================================


class TestEventPoller:
    def test_first_poll_returns_single_event(self):
        mock = MockActivityWatchClient()
        mock.inject_event("vlc", "Show A")
        mock.inject_event("vlc", "Show B")

        poller = EventPoller(mock)
        events = poller.poll_new_events("bucket-1")
        # First poll: limit=1, returns only latest
        assert len(events) == 1

    def test_subsequent_poll_returns_incremental(self):
        from datetime import timedelta

        mock = MockActivityWatchClient()
        # Inject event with explicit past timestamp
        old_ts = datetime.now(UTC) - timedelta(seconds=10)
        mock.mock_events.append(
            {
                "timestamp": old_ts.isoformat(),
                "duration": 10.0,
                "data": {"app": "vlc", "title": "Show A"},
            }
        )

        poller = EventPoller(mock)
        first = poller.poll_new_events("bucket-1")
        assert len(first) == 1
        assert "bucket-1" in poller.last_processed

        # Inject event with a later timestamp
        new_ts = datetime.now(UTC) + timedelta(seconds=1)
        mock.mock_events.append(
            {
                "timestamp": new_ts.isoformat(),
                "duration": 10.0,
                "data": {"app": "vlc", "title": "Show B"},
            }
        )
        second = poller.poll_new_events("bucket-1")
        assert len(second) >= 1

    def test_empty_bucket_returns_empty(self):
        mock = MockActivityWatchClient()
        poller = EventPoller(mock)
        events = poller.poll_new_events("bucket-empty")
        assert events == []

    def test_last_processed_updated(self):
        mock = MockActivityWatchClient()
        mock.inject_event("vlc", "Show A")

        poller = EventPoller(mock)
        poller.poll_new_events("bucket-1")
        assert isinstance(poller.last_processed["bucket-1"], datetime)


# ===========================================================================
# Bucket discovery
# ===========================================================================


class TestBucketDiscovery:
    def test_discovers_window_and_web_buckets(self):
        mock = MockActivityWatchClient()
        mock.inject_bucket("aw-watcher-window_host", "currentwindow")
        mock.inject_bucket("aw-watcher-web-chrome_host", "web.tab.current")
        mock.inject_bucket("aw-watcher-afk_host", "afkstatus")

        result = discover_media_relevant_buckets(mock)
        assert result["window"] == ["aw-watcher-window_host"]
        assert result["web"] == ["aw-watcher-web-chrome_host"]

    def test_empty_server_returns_empty_lists(self):
        mock = MockActivityWatchClient()
        result = discover_media_relevant_buckets(mock)
        assert result == {"window": [], "web": []}

    def test_multiple_browsers(self):
        mock = MockActivityWatchClient()
        mock.inject_bucket("aw-watcher-web-chrome_host", "web.tab.current")
        mock.inject_bucket("aw-watcher-web-firefox_host", "web.tab.current")

        result = discover_media_relevant_buckets(mock)
        assert len(result["web"]) == 2


# ===========================================================================
# MockActivityWatchClient
# ===========================================================================


class TestMockActivityWatchClient:
    def test_inject_and_get_events(self):
        mock = MockActivityWatchClient()
        mock.inject_event("vlc", "Show A")
        events = mock._get_events("any-bucket", limit=5)
        assert len(events) == 1
        assert events[0]["data"]["app"] == "vlc"
        assert events[0]["data"]["title"] == "Show A"

    def test_inject_with_url(self):
        mock = MockActivityWatchClient()
        mock.inject_event("chrome", "Netflix", url="https://netflix.com/watch/1")
        events = mock._get_events("b", limit=1)
        assert events[0]["data"]["url"] == "https://netflix.com/watch/1"

    def test_get_buckets(self):
        mock = MockActivityWatchClient()
        mock.inject_bucket("b1", "currentwindow")
        assert "b1" in mock.get_buckets()

    def test_get_events_since_filters(self):
        from datetime import timedelta

        mock = MockActivityWatchClient()
        # Old event with explicit past timestamp
        old_ts = datetime.now(UTC) - timedelta(seconds=10)
        mock.mock_events.append(
            {
                "timestamp": old_ts.isoformat(),
                "duration": 10.0,
                "data": {"app": "vlc", "title": "Old Event"},
            }
        )

        cutoff = datetime.now(UTC) - timedelta(seconds=5)

        # New event with explicit future timestamp
        new_ts = datetime.now(UTC) + timedelta(seconds=1)
        mock.mock_events.append(
            {
                "timestamp": new_ts.isoformat(),
                "duration": 10.0,
                "data": {"app": "vlc", "title": "New Event"},
            }
        )

        events = mock.get_events_since("b", cutoff)
        titles = [e["data"]["title"] for e in events]
        assert "New Event" in titles
        assert "Old Event" not in titles


# ===========================================================================
# DetectionService — browser event handling
# ===========================================================================


class TestBrowserEventHandling:
    """Verify all browser event types are processed."""

    def _make_payload(self, event_type: str, url: str = "https://netflix.com/watch/1") -> dict:
        return {
            "type": event_type,
            "tab_url": url,
            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
            "metadata": {
                "url": url,
                "title": "Stranger Things S01E01",
                "schema": [],
                "og": {},
                "video": [
                    {
                        "playing": event_type in ("play", "heartbeat"),
                        "currentTime": 10.0,
                        "duration": 3600.0,
                    }
                ],
            },
        }

    def test_play_event(self):
        svc = DetectionService()
        result = svc.handle_browser_event(self._make_payload("play"))
        assert result.event_type == "play"
        assert result.is_playing is True

    def test_pause_event(self):
        svc = DetectionService()
        result = svc.handle_browser_event(self._make_payload("pause"))
        assert result.event_type == "pause"

    def test_ended_event(self):
        svc = DetectionService()
        result = svc.handle_browser_event(self._make_payload("ended"))
        assert result.event_type == "ended"

    def test_heartbeat_event(self):
        svc = DetectionService()
        result = svc.handle_browser_event(self._make_payload("heartbeat"))
        assert result.event_type == "heartbeat"

    def test_page_load_event(self):
        svc = DetectionService()
        result = svc.handle_browser_event(self._make_payload("page_load"))
        assert result.event_type == "page_load"

    def test_browser_event_enqueues_detection(self):
        svc = DetectionService()
        svc.handle_browser_event(self._make_payload("play"))
        assert svc._event_queue.qsize() == 1


# ===========================================================================
# DetectionService — async start/stop lifecycle
# ===========================================================================


class TestDetectionServiceLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop_no_clients(self):
        """Service starts and stops cleanly with no AW or media listener."""
        svc = DetectionService()
        await svc.start()
        assert svc._running is True
        assert len(svc._tasks) == 3  # poll_loop, event_processor, sweeper

        await svc.stop()
        assert svc._running is False
        assert len(svc._tasks) == 0

    @pytest.mark.asyncio
    async def test_start_with_mock_aw(self):
        mock = MockActivityWatchClient()
        mock.inject_bucket("aw-watcher-window_host", "currentwindow")
        svc = DetectionService(aw_client=mock)
        await svc.start()
        assert svc._poller is not None
        assert len(svc._bucket_ids["window"]) == 1
        await svc.stop()

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self):
        svc = DetectionService()
        await svc.start()
        await svc.start()  # should not create duplicate tasks
        assert len(svc._tasks) == 3
        await svc.stop()

    @pytest.mark.asyncio
    async def test_stop_finalizes_active_watches(self):
        svc = DetectionService()
        await svc.start()
        svc._process_event(DetectionEvent(media_title="Test"))
        assert len(svc._active_watches) == 1
        await svc.stop()
        assert len(svc._active_watches) == 0


# ===========================================================================
# DetectionService — SMTC/MPRIS callback conversion
# ===========================================================================


class TestMediaSessionCallback:
    def test_on_media_session_event_enqueues(self):
        svc = DetectionService()
        event = MediaSessionEvent(
            player_name="Spotify",
            title="Song Title",
            artist="Artist",
            album_title="Album",
            playback_status=PlaybackStatus.PLAYING,
            source_app="spotify.exe",
        )
        svc._on_media_session_event(event)
        assert svc._event_queue.qsize() == 1

    def test_media_session_conversion_fields(self):
        svc = DetectionService()
        event = MediaSessionEvent(
            player_name="VLC",
            title="Breaking Bad S01E01",
            artist="",
            album_title="",
            playback_status=PlaybackStatus.PLAYING,
            source_app="vlc.exe",
        )
        svc._on_media_session_event(event)
        detection = svc._event_queue.get_nowait()
        assert detection.media_title == "Breaking Bad S01E01"
        assert detection.app_name == "vlc.exe"
        assert detection.is_playing is True
        assert detection.source in ("smtc", "mpris")

    def test_paused_status_is_not_playing(self):
        svc = DetectionService()
        event = MediaSessionEvent(
            playback_status=PlaybackStatus.PAUSED,
            title="Something",
            source_app="app",
        )
        svc._on_media_session_event(event)
        detection = svc._event_queue.get_nowait()
        assert detection.is_playing is False
