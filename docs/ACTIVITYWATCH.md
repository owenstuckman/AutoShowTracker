# ActivityWatch Integration

How AutoShowTracker uses ActivityWatch to detect media playback via window titles and browser tab metadata.

## Overview

ActivityWatch (AW) is an open-source time-tracking tool that records the active window title and browser tab at all times. AutoShowTracker bundles AW as unmodified binaries and polls its REST API for events, converting them into detection signals that feed the identification pipeline.

AW is the **second priority** detection source — it kicks in when SMTC/MPRIS (OS-level Now Playing APIs) are unavailable or don't report metadata for the current player.

## Components

Four classes in `src/show_tracker/detection/activitywatch.py`:

| Class | Role |
|-------|------|
| `ActivityWatchManager` | Starts/stops bundled AW binaries as child processes |
| `ActivityWatchClient` | Thin REST API wrapper around AW's HTTP endpoints |
| `EventPoller` | Tracks last-processed timestamp per bucket; returns only new events |
| `MockActivityWatchClient` | Drop-in test double that accepts injected synthetic events |

Plus one helper function:

- `discover_media_relevant_buckets(client)` — queries AW for all buckets, returns those matching `currentwindow` and `web.tab.current` types.

## Data Flow

```
ActivityWatch Server (localhost:5600)
    │
    ├── aw-watcher-window bucket (window title + app name)
    │       │
    │       ▼
    │   EventPoller.poll_new_events()
    │       │
    │       ▼
    │   DetectionService._aw_window_event_to_detection()
    │       │
    │       ▼
    │   DetectionEvent(source="activitywatch_window",
    │                  window_title=..., app_name=...)
    │
    └── aw-watcher-web bucket (URL + page title)
            │
            ▼
        EventPoller.poll_new_events()
            │
            ▼
        DetectionService._aw_web_event_to_detection()
            │
            ▼
        DetectionEvent(source="activitywatch_web",
                       url=..., page_title=...)
            │
            ▼
    DetectionService._event_queue
            │
            ▼
    Deduplication → Confidence routing → Identification pipeline
```

## Subprocess Management (ActivityWatchManager)

`ActivityWatchManager` handles the lifecycle of bundled AW binaries:

1. **Startup**: Checks if an AW server is already running on the preferred port (default 5600). If yes, reuses it (`using_external = True`). Otherwise, finds a free port in range 5600-5609, launches `aw-server-rust`, waits up to 15s for it to become ready, then launches `aw-watcher-window`.
2. **Health checks**: `health_check()` inspects each child process. If one has exited, it attempts a restart with exponential backoff (2s, 4s, 8s), giving up after 3 consecutive failures.
3. **Shutdown**: Sends SIGTERM to all children (in reverse order), waits 5s for graceful exit, then SIGKILL if needed.

**Not bundled** (intentionally):
- `aw-qt` — AW's system tray GUI; AutoShowTracker has its own UI
- `aw-watcher-afk` — AFK detection adds noise without helping media tracking

## REST API Client (ActivityWatchClient)

Wraps AW's HTTP API at `http://localhost:{port}/api/0`:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `get_buckets()` | `GET /buckets` | List all available buckets |
| `get_recent_window_events()` | `GET /buckets/aw-watcher-window_{host}/events?limit=N` | Recent window events |
| `get_recent_web_events()` | `GET /buckets/aw-watcher-web-{browser}_{host}/events?limit=N` | Recent browser events |
| `get_events_since()` | `GET /buckets/{id}/events?start=...&end=...` | Events after a timestamp |

**AW event structure:**
```json
{
  "timestamp": "2025-01-15T20:30:00.000Z",
  "duration": 45.0,
  "data": {
    "app": "vlc.exe",
    "title": "Breaking Bad S01E01 - Pilot - VLC media player"
  }
}
```

## Incremental Polling (EventPoller)

`EventPoller` avoids reprocessing events by tracking the newest timestamp per bucket:

- **First poll**: Returns only the single most recent event (avoids replaying history).
- **Subsequent polls**: Returns all events newer than the stored timestamp via `get_events_since()`.
- **State**: `last_processed: dict[str, datetime]` — one entry per bucket ID.

The `DetectionService` runs `_aw_poll_loop()` which calls `EventPoller.poll_new_events()` for each discovered bucket every `polling_interval` seconds (default: 10s).

## Integration with DetectionService

`DetectionService` (`src/show_tracker/detection/detection_service.py`) is the central orchestrator. It accepts an `ActivityWatchClient` (or mock) and manages three async tasks:

1. **`_aw_poll_loop`** — polls AW buckets every N seconds
2. **`_event_processor`** — consumes from `_event_queue`, deduplicates, routes by confidence
3. **`_grace_period_sweeper`** — finalizes watches after 120s of silence

**Deduplication**: The `_dedup_key()` method produces a canonical key from each `DetectionEvent`. Events with the same key within the grace period are treated as heartbeats rather than new detections.

**Confidence estimation**: AW events start at low confidence (0.3-0.4) since they only provide window titles and URLs. The identification layer (TMDb fuzzy matching) produces the real confidence score downstream.

## Configuration

| Setting | Default | Env var | Description |
|---------|---------|---------|-------------|
| `activitywatch_port` | 5600 | `ST_ACTIVITYWATCH_PORT` | AW server port |
| `polling_interval` | 10 | — | Seconds between AW polls |
| `heartbeat_interval` | 30 | — | Seconds between heartbeat emissions |
| `grace_period` | 120 | — | Seconds of silence before finalizing a watch |

Settings load from: env vars (`ST_` prefix) > `.env` file > `config/default_settings.json`.

## Testing

Integration tests in `tests/integration/test_activitywatch.py` use `MockActivityWatchClient` to inject synthetic events without a running AW server:

```python
mock = MockActivityWatchClient()
mock.inject_bucket("aw-watcher-window_testhost", "currentwindow")
mock.inject_event(app="vlc.exe", title="Breaking Bad S01E01 - Pilot - VLC media player")
```

Test classes:
- `TestActivityWatchEventParsing` — event structure validation
- `TestParsingIntegration` — AW events through the parser
- `TestUrlPatternMatching` — URL extraction from browser events
- `TestDeduplication` — same-title event merging
- `TestHeartbeatMerging` — consecutive event duration accumulation

## Detection Priority

AW sits at priority level 2 in the detection chain:

| Priority | Source | Trigger | Confidence |
|----------|--------|---------|------------|
| 1 | Plex/Jellyfin/Emby webhooks | Webhook push | 0.90 base |
| 1 | SMTC / MPRIS | Event-driven | 0.60 base |
| **2** | **ActivityWatch window/web** | **Polled every 10s** | **0.30-0.40 base** |
| 3 | VLC/mpv IPC | Polled | varies |
| 4 | File handle scanning | Polled | varies |
| 5 | OCR (region crop) | Triggered | varies |
| 6 | OCR (full window) | Last resort | varies |

AW's lower base confidence reflects that window titles are noisy (may include player UI text, resolution tags, etc.). The identification layer compensates by running fuzzy matching against TMDb.
