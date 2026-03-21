# Architecture

## Overview

AutoShowTracker is a layered system that automatically detects what TV show episode a user is watching, identifies it against TMDb, and logs it to a local watch history database. The architecture is organized into five primary layers, each with a clear responsibility boundary.

```
  ┌──────────────────────────────────────────────────────┐
  │                     Web UI / CLI                      │  Presentation
  ├──────────────────────────────────────────────────────┤
  │                    FastAPI HTTP API                   │  API Layer
  ├──────────────────────────────────────────────────────┤
  │              Identification Pipeline                  │  Intelligence
  │   (parser, URL patterns, TMDb client, resolver,      │
  │    confidence scoring, alias lookup)                  │
  ├──────────────────────────────────────────────────────┤
  │              Detection / Collection                   │  Collection
  │   (ActivityWatch, SMTC/MPRIS, Browser Extension,     │
  │    VLC/mpv IPC, OCR)                                 │
  ├──────────────────────────────────────────────────────┤
  │                  Storage Layer                        │  Persistence
  │   (SQLAlchemy ORM, SQLite, DatabaseManager)          │
  └──────────────────────────────────────────────────────┘
```

---

## Technology Choices

### Python 3.11+ with asyncio

Python was chosen for rapid prototyping, broad library availability (guessit, rapidfuzz, SQLAlchemy, FastAPI), and because the primary workload is I/O-bound (polling APIs, waiting for events). Python 3.11+ was required for `StrEnum`, `ExceptionGroup`, and performance improvements.

### FastAPI over Flask

FastAPI provides native async support (critical for concurrent event processing), automatic OpenAPI/Swagger documentation, and Pydantic-based request validation out of the box. Flask would have required additional extensions for async, schema validation, and API docs.

### SQLAlchemy 2.0 over raw sqlite3

SQLAlchemy's ORM gives us typed models, relationship management, and a migration path via Alembic. The 2.0 API with `Mapped` type annotations provides excellent IDE support. Raw sqlite3 would have been faster to start but harder to maintain as the schema grows.

### SQLite (two databases)

SQLite requires zero configuration and stores everything in local files that users can back up. Two separate databases are used:

- **watch_history.db**: Contains the user's irreplaceable watch log, show metadata, aliases, and settings.
- **media_cache.db**: Contains cached TMDb API responses. This is entirely rebuildable and can be deleted without data loss.

Both databases use WAL (Write-Ahead Logging) journal mode for better concurrent read performance and have foreign key enforcement enabled.

### httpx over requests

The TMDb client uses `httpx` for its async HTTP support, allowing multiple API calls to run concurrently. The `requests` library is synchronous-only and would block the event loop.

### rapidfuzz over python-Levenshtein

`rapidfuzz` offers the same fuzzy string matching algorithms with a cleaner API, better performance (C++ backend with SIMD), and a permissive MIT license. It is used in the resolver to match parsed show titles against TMDb search results.

### guessit for filename parsing

`guessit` is the industry-standard library for extracting show name, season, episode, quality, and codec information from media filenames. It handles an enormous variety of naming conventions.

### click for CLI

`click` provides a decorator-based CLI framework with automatic help generation, type coercion, and nested command groups. It produces a better user experience than `argparse` with less boilerplate.

### pydantic-settings for configuration

`pydantic-settings` gives us typed configuration with automatic environment variable loading, `.env` file support, and validation, eliminating the need for custom config parsing code.

### Vanilla JavaScript for the web UI

The web UI uses plain HTML, CSS, and JavaScript with no build step. This avoids the complexity of a bundler, framework dependencies, and node_modules. For a locally-served dashboard that primarily displays data, the simplicity tradeoff is worthwhile.

---

## How the Five Layers Interact

### 1. Collection Layer (Detection)

The `DetectionService` is the central orchestrator. It runs three concurrent input streams:

- **ActivityWatch Poller**: Polls the AW REST API every 10 seconds for window-title and web-browser events from `aw-watcher-window` and `aw-watcher-web` buckets.
- **SMTC/MPRIS Listener**: Receives real-time media session events from the operating system. On Windows, it listens to System Media Transport Controls via `winsdk`. On Linux, it listens to MPRIS D-Bus signals via `dbus-next`.
- **Browser Extension**: A Chrome Manifest V3 extension injects a content script into every page. The content script detects `<video>` elements, extracts metadata (URL patterns, Open Graph tags, JSON-LD schema, page title), and sends events (`play`, `pause`, `ended`, `heartbeat`, `page_load`) to the background service worker. The service worker forwards them to the local HTTP API at `POST /api/media-event`.

All three streams produce a unified `DetectionEvent` dataclass that flows into the identification pipeline.

### 2. Identification Pipeline

The `EpisodeResolver` processes each `DetectionEvent` through a resolution chain:

1. **URL Pattern Matching** (`url_patterns.py`): Checks if the URL matches a known streaming platform (Netflix, Hulu, Disney+, HBO Max, Amazon Prime, YouTube, Crunchyroll, etc.) and extracts platform-specific content IDs.
2. **YouTube Enrichment** (`youtube_client.py`): For YouTube URLs, queries the YouTube Data API v3 to fetch video/playlist metadata and detect series info from playlist structure or title patterns.
3. **String Parsing** (`parser.py`): Uses `guessit` to extract show name, season, episode, year, and quality from the raw string. Auto-detects movies vs. episodes.
4. **Alias Lookup**: Checks the `show_aliases` table for known mappings (e.g., "SVU" maps to "Law & Order: Special Victims Unit").
5. **Cache Check**: Looks up prior TMDb search results in `media_cache.db` to avoid redundant API calls.
6. **TMDb Search + Fuzzy Match**: Searches the TMDb API and uses `rapidfuzz.fuzz.ratio` to find the best match above an 80% threshold. A small popularity boost breaks ties. Supports both TV shows and movies.
7. **TVDb Fallback** (`tvdb_client.py`): If TMDb confidence is low, no season number is present, and episode number exceeds 50, tries TVDb for anime with absolute episode numbering and maps to season/episode format.
8. **Episode/Movie Fetch**: Retrieves episode or movie details from TMDb and caches the result.
9. **Confidence Scoring** (`confidence.py`): Computes a 0.0-1.0 confidence score.

### 3. Confidence Routing

The confidence score determines how the result is handled:

| Score Range | Tier | Action |
|-------------|------|--------|
| >= 0.9 (auto_log_threshold) | AUTO_LOG | Automatically create a watch event in the database |
| >= 0.7 (review_threshold) | LOG_AND_FLAG | Log the event but flag it for user review |
| < 0.7 | UNRESOLVED | Send to the unresolved queue for manual resolution |

### 4. Storage Layer

The `DatabaseManager` manages two SQLAlchemy engines with transactional session scopes. The `Repository` class provides higher-level operations like creating watch events with heartbeat merging.

### 5. API and Presentation

FastAPI serves both the REST API and the single-page web UI. The SPA uses hash-based routing (`#/dashboard`, `#/shows`, `#/unresolved`, `#/settings`) and communicates with the API via `fetch()`.

---

## Data Flow: Detection to Storage

```
Browser Extension ─── POST /api/media-event ──┐
                                               │
ActivityWatch ─── REST polling ───────────────┤
                                               ├──► DetectionService
SMTC/MPRIS ─── OS event callback ────────────┤     (deduplication,
                                               │      heartbeat mgmt)
VLC/mpv IPC ─── socket/HTTP polling ──────────┤
                                               │
Plex/Jellyfin/Emby ─── webhooks ──────────────┘          │
                                                          ▼
                                               EpisodeResolver.resolve()
                                                    │
                                                    ├─ URL pattern match
                                                    ├─ guessit parse
                                                    ├─ Alias lookup
                                                    ├─ Cache check
                                                    ├─ TMDb search + fuzzy match
                                                    ├─ Episode detail fetch
                                                    └─ Confidence scoring
                                                          │
                                                          ▼
                                               Confidence Routing
                                                    │
                                    ┌───────────────┼───────────────┐
                                    ▼               ▼               ▼
                              AUTO_LOG        LOG_AND_FLAG      UNRESOLVED
                                    │               │               │
                                    ▼               ▼               ▼
                            WatchEvent        WatchEvent       UnresolvedEvent
                            (auto)          (flagged)         (pending review)
                                    │               │               │
                                    └───────┬───────┘               │
                                            ▼                       ▼
                                    watch_history.db         unresolved_events
                                                                 table
```

---

## Detection Priority Chain

When multiple detection sources report information about the same playback session, the system prioritizes them in this order:

1. **Plex/Jellyfin/Emby Webhooks**: Highest priority. Media servers send structured events with show name, season, episode, and playback state directly. Receives a 0.90 base confidence score.

2. **Browser Extension (structured metadata)**: Extracts structured data directly from the page: URL patterns for platform identification, JSON-LD schema markup, Open Graph tags, and video element state. Very complete and accurate signal.

3. **SMTC / MPRIS (OS media session)**: The operating system's media transport layer provides the media title, artist, and playback state as reported by the application itself. Reliable but often lacks season/episode information.

4. **Player IPC (VLC web interface, mpv JSON IPC)**: Direct communication with the media player provides the file path, which can be parsed for episode information. Very reliable for local media files.

5. **ActivityWatch (window titles / web watcher)**: Passive observation of window titles. Useful as a fallback but window titles vary widely in format and may be truncated.

6. **OCR (screenshot analysis)**: Last resort. Takes a screenshot of the player window, crops the title/overlay region, and runs Tesseract or EasyOCR. Inherently noisy and receives a confidence penalty.

This ordering reflects the signal-to-noise ratio of each source. Browser metadata gives explicit structured data, while OCR produces noisy text that may contain artifacts.

---

## Deduplication and Heartbeats

### Deduplication

The `DetectionService` generates a **deduplication key** for each event based on the most specific available metadata:

- Structured metadata: `"{show_name}|s{NN}|e{NN}"` (most specific)
- Media title: `"{media_title}"` (from SMTC/MPRIS)
- Window/page title: `"{window_title}"`
- URL: `"{url}"` (least specific)

Events with the same dedup key within an active watch session are treated as heartbeats rather than new detections.

### Heartbeat Pattern

When an event matches an existing `ActiveWatch`:
1. The `last_heartbeat` timestamp is updated.
2. The `heartbeat_count` is incremented.
3. If enough time has elapsed since the last emitted heartbeat (default: 30 seconds), a new heartbeat event is routed downstream.

### Grace Period

When heartbeats stop arriving (e.g., the user paused or closed the player), the `_grace_period_sweeper` runs every polling interval and checks for stale watches. A watch is finalized after 120 seconds (configurable) of silence. This handles:

- Brief pauses (bathroom break, phone call)
- Network buffering interruptions
- Tab switches that temporarily stop content script events

---

## Confidence Scoring

The confidence score is a composite of four factors:

### Source Base Score

Each detection source has an inherent reliability rating:

| Source | Base Score |
|--------|-----------|
| Plex webhook | 0.90 |
| Browser URL match | 0.85 |
| SMTC / MPRIS | 0.70 |
| Filename | 0.65 |
| Browser page title | 0.60 |
| YouTube | 0.55 |
| Window title | 0.55 |
| Unknown | 0.50 |
| OCR | 0.40 |

### TMDb Fuzzy Match Score

The `rapidfuzz.fuzz.ratio` between the parsed title and the TMDb result name. Ranges from 0.0 to 1.0. Combined with the source base as an average.

### Bonuses

- **URL platform match** (+0.15): URL was matched to a known streaming platform.
- **Both season and episode present** (+0.10): The parser found explicit S__E__ patterns.
- **High fuzzy match** (+0.08): TMDb match score >= 0.95.

### Penalties

- **OCR source** (-0.10): Additional penalty for inherent OCR noise.
- **No season number** (-0.10): Ambiguity when only an episode number is found.
- **Abbreviated title** (-0.05): Titles of 5 characters or fewer are likely abbreviations.

The final score is clamped to [0.0, 1.0].

---

## Cross-Platform Strategy

The application uses **Protocol classes** and **conditional imports** to support multiple operating systems without requiring platform-specific packages to be installed everywhere.

### MediaSessionListener Protocol

```python
class MediaSessionListener(Protocol):
    def register_callback(self, callback: Callable) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
```

The `get_media_listener()` factory function returns the appropriate implementation:
- **Windows**: `SmtcListener` (uses `winsdk` to listen to System Media Transport Controls)
- **Linux**: `MprisListener` (uses `dbus-next` to listen to MPRIS D-Bus signals)
- **macOS**: Returns `None` (not yet implemented; planned via `pyobjc` or Swift helper)

### Conditional Imports

Platform-specific packages (`winsdk`, `dbus-next`) are imported inside `try/except` blocks. The application starts on any platform; unavailable listeners are simply skipped with a log warning.

### OCR Engine Lazy Loading

Both Tesseract and EasyOCR engines are lazily initialized to avoid importing heavy ML models (EasyOCR loads PyTorch) at application startup. The OCR service falls back from Tesseract to EasyOCR if the primary engine fails.

---

## Key Design Tradeoffs

### Two Separate Databases vs. One

**Chose**: Two SQLite databases (`watch_history.db` and `media_cache.db`).

**Rationale**: The cache database can be safely deleted and rebuilt from TMDb. Keeping it separate means the user's watch history is never at risk from cache corruption, and the cache can be nuked without affecting user data. It also keeps the watch history database smaller for faster backups.

### Local HTTP Endpoint vs. WebSocket for Browser Extension

**Chose**: The browser extension sends events via `POST /api/media-event` to the local FastAPI server.

**Rationale**: HTTP is simpler to implement, debug, and test. WebSockets would require connection lifecycle management, reconnection logic, and buffering in the extension. Since events arrive at most every few seconds, the overhead of individual HTTP requests is negligible.

### Hash-Based SPA Routing vs. Server-Side Rendering

**Chose**: Client-side hash routing (`#/dashboard`, `#/shows/{id}`, etc.) in vanilla JavaScript.

**Rationale**: The web UI is a local dashboard, not a public website. Hash routing requires no server-side route configuration and works with FastAPI's static file serving. No framework was needed because the UI primarily renders data from API calls.

### In-Memory Detection State vs. Persistent Queue

**Chose**: The `DetectionService` keeps active watches in memory (`dict[str, ActiveWatch]`).

**Rationale**: Detection state is ephemeral by nature. If the application restarts, any in-progress watch is simply re-detected on the next poll cycle. Persisting the queue would add complexity without meaningful benefit, since the grace period is only 2 minutes.

### Polling ActivityWatch vs. Subscribing to Events

**Chose**: Poll the ActivityWatch REST API every 10 seconds.

**Rationale**: ActivityWatch does not expose a push/subscription API. Polling at 10-second intervals is efficient enough (AW itself typically produces events every 5-15 seconds) and avoids depending on undocumented or unstable AW internals.
