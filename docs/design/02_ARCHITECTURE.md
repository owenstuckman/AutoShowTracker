# System Architecture

## Component Overview

The system is composed of five layers, each with a single responsibility. Data flows upward from collection through identification to storage and presentation.

```
┌─────────────────────────────────────────────────────┐
│                 PRESENTATION LAYER                   │
│         Web UI / Desktop App / Mobile App            │
│    (watch history, progress, next episodes, stats)   │
└──────────────────────┬──────────────────────────────┘
                       │ reads from
┌──────────────────────▼──────────────────────────────┐
│                  STORAGE LAYER                       │
│              Local SQLite Database                    │
│   (canonical episode IDs, timestamps, durations,     │
│    source metadata, watch completion status)          │
└──────────────────────┬──────────────────────────────┘
                       │ writes to
┌──────────────────────▼──────────────────────────────┐
│             IDENTIFICATION LAYER                     │
│     TMDb/TVDb API + YouTube Data API + guessit       │
│  (fuzzy matching, season/episode resolution,         │
│   canonical ID assignment)                           │
└──────────────────────┬──────────────────────────────┘
                       │ receives parsed data from
┌──────────────────────▼──────────────────────────────┐
│                 PARSING LAYER                        │
│   guessit + regex patterns + URL pattern engine      │
│  (extracts show name, season, episode from raw       │
│   strings regardless of source format)               │
└──────────────────────┬──────────────────────────────┘
                       │ receives raw signals from
┌──────────────────────▼──────────────────────────────┐
│               COLLECTION LAYER                       │
│  ┌─────────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ActivityWatch │ │SMTC/MPRIS│ │Browser Extension │  │
│  │ (bundled)   │ │ Listener │ │ (Chrome/Firefox) │  │
│  └─────────────┘ └──────────┘ └──────────────────┘  │
│  ┌─────────────────────────────────────────────────┐ │
│  │         OCR Fallback (per-app region crop)       │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

## Process Architecture

The application runs as a set of coordinated processes managed by a single launcher.

### Launcher (Main Process)

The launcher is the entry point the user interacts with. On startup it:

1. Checks if an existing ActivityWatch instance is running on port 5600.
2. If not, starts `aw-server-rust` as a child process (configurable port if 5600 is occupied).
3. Starts `aw-watcher-window` and `aw-watcher-web` as child processes.
4. Starts the SMTC/MPRIS listener daemon as a child process.
5. Starts the media identification service (the core logic) as a child process.
6. Optionally starts the web UI server.
7. Manages lifecycle: graceful shutdown of all children on exit, restart on crash.

### ActivityWatch Processes (Bundled, Unmodified)

- `aw-server-rust`: REST API on localhost:5600, stores raw activity events.
- `aw-watcher-window`: Reports active window title + app name every 5 seconds.
- `aw-watcher-web`: Browser extension backend, reports active tab URL + title.

These are stock ActivityWatch binaries. We do not modify them.

### SMTC/MPRIS Listener Daemon

A custom daemon that subscribes to OS media session events:
- On Windows: queries `GlobalSystemMediaTransportControlsSessionManager` via WinRT.
- On Linux: connects to D-Bus and listens for MPRIS `PropertiesChanged` signals.
- On macOS: uses `MediaRemote` framework callbacks.

Emits events to an internal message queue (or writes to a local file/socket) whenever the "now playing" metadata changes. Each event contains: timestamp, player name, media title (as reported by the player), and playback state (playing/paused/stopped).

### Media Identification Service (Core Logic)

The central processing loop. It:

1. Polls ActivityWatch REST API for recent events from `aw-watcher-window` and `aw-watcher-web` buckets.
2. Reads events from the SMTC/MPRIS listener.
3. Receives events from the browser extension (via a local HTTP endpoint or WebSocket).
4. For each event, runs the parsing layer (guessit + regex) to extract structured media info.
5. Queries TMDb/TVDb/YouTube API to resolve to a canonical episode ID.
6. Checks if this episode is already being tracked (deduplication).
7. Writes confirmed episode watches to the local database with duration tracking.

### OCR Subsystem (On-Demand)

Not a continuously running process. Triggered by the media identification service when:
- A media player app is detected as active (from ActivityWatch).
- AND the window title did not resolve to a known show.
- AND SMTC/MPRIS did not provide useful metadata for that player.

When triggered:
1. Captures the player's window (background-safe screenshot via OS API).
2. Crops to the region-of-interest for that app (from a stored profile).
3. Runs OCR (Tesseract/EasyOCR/PaddleOCR).
4. Passes result to the parsing layer.

## Data Flow Example: User Watches Pirated Episode in Chrome

1. `aw-watcher-web` reports tab URL `https://some-pirate-site.tv/watch/law-and-order-svu-s03e07` and title "Law & Order SVU Season 3 Episode 7 - Watch Free".
2. Browser extension (running in Chrome) additionally scrapes: Open Graph tags (if present), video player element metadata, any structured data in the DOM.
3. Media identification service receives both signals.
4. Parsing layer: `guessit` parses the URL slug and/or page title, extracts `{show: "Law and Order SVU", season: 3, episode: 7}`.
5. Identification layer: queries TMDb search API for "Law and Order SVU", finds the show, resolves season 3 episode 7 to canonical ID.
6. Storage layer: logs the episode with timestamp, duration (tracked via heartbeat while tab remains active), and source metadata.

## Data Flow Example: VLC Auto-Advances in Background

1. User starts watching `law.and.order.svu.s03e07.mkv` in VLC. VLC is focused.
2. `aw-watcher-window` reports VLC with that filename as window title.
3. SMTC/MPRIS also reports the filename as now-playing metadata.
4. Both signals are parsed and identified. Episode logged.
5. User switches to a browser tab. VLC continues playing in background.
6. Episode ends, VLC auto-advances to `law.and.order.svu.s03e08.mkv`.
7. `aw-watcher-window` does NOT detect this (VLC is not focused).
8. SMTC/MPRIS DOES detect this — the now-playing metadata changes. Event emitted.
9. Media identification service picks up the SMTC/MPRIS event, parses and identifies the new episode.
10. New episode logged. The background auto-advance was captured.

## Inter-Process Communication

| Source | Destination | Mechanism |
|--------|-------------|-----------|
| ActivityWatch server | Media ID service | HTTP REST (poll `localhost:5600/api/0/buckets/*/events`) |
| SMTC/MPRIS daemon | Media ID service | Local socket or named pipe (event push) |
| Browser extension | Media ID service | HTTP POST to `localhost:<port>/api/media-event` |
| Media ID service | OCR subsystem | Direct function call (same process) or subprocess invocation |
| Media ID service | SQLite database | Direct file access |
| Web UI | SQLite database | Read via a local HTTP API served by the media ID service |

## Technology Stack Recommendation

| Component | Language | Rationale |
|-----------|----------|-----------|
| Launcher + Media ID service | Python | guessit is Python-native, rapid prototyping, cross-platform |
| SMTC listener (Windows) | Python (winsdk) or Rust | winsdk package provides WinRT bindings; Rust if performance matters |
| MPRIS listener (Linux) | Python (dbus-next) | dbus-next is async-native and well-maintained |
| MediaRemote listener (macOS) | Python (pyobjc) or Swift | pyobjc for consistency; Swift if deeper integration needed |
| Browser extension | JavaScript | Required by browser extension APIs |
| OCR | Python (easyocr or tesserocr) | EasyOCR for accuracy on screen text; Tesseract for speed |
| Database | SQLite | Local-first, zero config, sufficient for single-user workload |
| Web UI | React or Svelte | Standard frontend; communicates with media ID service HTTP API |

Python is the recommended primary language because it maximizes code sharing across components (parsing, identification, OCR all have mature Python libraries) and keeps the project accessible to contributors. Performance-critical paths (SMTC/MPRIS polling, screenshot capture) can be isolated into small native modules if needed.
