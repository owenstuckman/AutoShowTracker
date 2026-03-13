# Implementation Decisions Log

This document records the key architectural and implementation decisions made during the development of AutoShowTracker, along with the reasoning behind each choice.

---

## D001: SQLAlchemy 2.0 over raw sqlite3

**Context**: The storage layer needs to manage two SQLite databases with related tables, foreign keys, and transactional integrity.

**Decision**: Use SQLAlchemy 2.0 with the new `Mapped` type annotation style.

**Reasoning**:
- The ORM provides typed models with IDE autocompletion and static analysis support via `Mapped` and `mapped_column`.
- Relationship management (Show -> Episodes -> WatchEvents) is handled declaratively.
- SQLAlchemy's `create_all()` handles schema creation, and Alembic can be added later for migrations.
- Two separate `DeclarativeBase` subclasses (`WatchBase`, `CacheBase`) cleanly isolate the two databases while sharing the same ORM patterns.
- Raw sqlite3 would have required writing manual SQL for all queries, hand-managing foreign keys, and building a custom migration system.

**Tradeoff**: SQLAlchemy adds a dependency and some overhead for simple queries, but the developer productivity and maintainability gains are worth it for a project of this size.

---

## D002: FastAPI over Flask

**Context**: The application needs an HTTP API to receive browser extension events, serve the web UI, and expose watch history data.

**Decision**: Use FastAPI with Uvicorn as the ASGI server.

**Reasoning**:
- Native async support is critical because the detection service processes events concurrently from multiple sources (ActivityWatch polling, SMTC/MPRIS callbacks, browser extension HTTP events).
- Automatic OpenAPI/Swagger documentation at `/docs` eliminates the need to maintain separate API docs manually.
- Pydantic-based request/response validation catches malformed data at the API boundary.
- The lifespan context manager pattern cleanly manages database initialization and teardown.
- Flask would have required extensions for async support (Quart), schema validation (Marshmallow or Flask-Pydantic), and API documentation (Flask-RESTX or Flasgger).

**Tradeoff**: FastAPI has a larger learning curve for developers unfamiliar with ASGI and type annotations, but the auto-generated docs and validation save significant development time.

---

## D003: httpx over requests in TMDb client

**Context**: The TMDb client makes HTTP calls to search for shows and fetch episode details. Multiple API calls may be needed for a single identification.

**Decision**: Use `httpx` with `AsyncClient` for all TMDb API communication.

**Reasoning**:
- `httpx` provides a `requests`-compatible API but supports async/await natively.
- Multiple TMDb API calls (search, get show, get episode) can run concurrently when needed.
- The async client integrates naturally with FastAPI's async route handlers and the asyncio-based detection service.
- `requests` is synchronous-only and would block the event loop, requiring thread pool executors for concurrent calls.

**Tradeoff**: `httpx` is a newer library with a smaller ecosystem than `requests`, but its API is nearly identical and it is well-maintained.

---

## D004: rapidfuzz over python-Levenshtein

**Context**: The resolver needs to fuzzy-match parsed show titles against TMDb search results to find the best candidate.

**Decision**: Use `rapidfuzz.fuzz.ratio` for fuzzy string matching.

**Reasoning**:
- `rapidfuzz` provides the same Levenshtein-based algorithms as `python-Levenshtein` and `fuzzywuzzy` but with a cleaner API.
- It is implemented in C++ with SIMD optimizations, making it significantly faster for batch comparisons.
- MIT license (vs. GPL for the original `python-Levenshtein`).
- The `fuzz.ratio` function returns a 0-100 score that is intuitive for threshold comparisons.

**Tradeoff**: Both `rapidfuzz` and `python-Levenshtein` are listed as dependencies. This is intentional: `rapidfuzz` is used for the actual matching, while `python-Levenshtein` is a transitive dependency of `guessit`. They coexist without conflict.

---

## D005: Vanilla JavaScript for web UI (no React/Svelte/Vue)

**Context**: The web UI needs to display a dashboard, show grid, episode detail, unresolved queue, and settings page.

**Decision**: Use plain HTML, CSS, and JavaScript with no frontend framework or build step.

**Reasoning**:
- The web UI is a local dashboard served by the same process. It does not need SEO, server-side rendering, or complex state management.
- No build step means no `node_modules`, no bundler configuration, no transpilation, and no additional toolchain dependencies.
- The entire frontend is a single `index.html`, one CSS file, and one JS file, all served as static files by FastAPI.
- All data comes from `fetch()` calls to the local API, which is straightforward in vanilla JS.
- A framework would add significant complexity (package.json, build scripts, dev server) for a UI that primarily renders lists and grids.

**Tradeoff**: No component reuse, no virtual DOM diffing, no reactive state bindings. As the UI grows, it may become harder to maintain. If the UI becomes significantly more complex, migrating to a lightweight framework like Preact (no build step required with HTM) would be a reasonable next step.

---

## D006: Hash-based SPA routing

**Context**: The web UI has multiple "pages" (dashboard, shows, show detail, unresolved, settings) but is served as a single HTML file.

**Decision**: Use `window.location.hash` for client-side routing (`#/dashboard`, `#/shows/42`, etc.).

**Reasoning**:
- Hash changes do not trigger page reloads or server requests, making navigation instant.
- No server-side route configuration is needed; FastAPI just serves `index.html` for `/` and static files for everything else.
- The `hashchange` event provides a simple routing mechanism in vanilla JS.
- History API (`pushState`) would require server-side catch-all routing to handle direct navigation and refreshes, adding unnecessary complexity.

**Tradeoff**: Hash-based URLs are less "clean" than path-based URLs, but for a local dashboard this is not a meaningful concern.

---

## D007: pydantic-settings for configuration

**Context**: The application has many configurable values (ports, thresholds, API keys, paths, timing intervals) that can come from environment variables, a config file, or code defaults.

**Decision**: Use `pydantic-settings` with the `BaseSettings` class.

**Reasoning**:
- Automatic environment variable loading with the `ST_` prefix (e.g., `ST_MEDIA_SERVICE_PORT` maps to `media_service_port`).
- The `validation_alias` feature allows API keys to use their standard names (`TMDB_API_KEY`) instead of the prefixed form.
- `.env` file support is built in.
- Type validation and range constraints (`ge=0.0`, `le=1.0`) catch configuration errors at startup.
- Model validators ensure cross-field constraints (e.g., `review_threshold <= auto_log_threshold`).

**Tradeoff**: Adds a dependency beyond core Pydantic, but `pydantic-settings` is lightweight and maintained by the Pydantic team.

---

## D008: click for CLI over argparse

**Context**: The application needs a CLI with multiple subcommands (`run`, `identify`, `test-pipeline`, `init-db`), each with their own options.

**Decision**: Use `click` for CLI construction.

**Reasoning**:
- Decorator-based command definition is more readable than `argparse`'s procedural `add_argument` calls.
- Built-in support for command groups, version options, context passing, and colored output.
- `click.Path(path_type=Path)` provides type coercion to `pathlib.Path` objects.
- `click.pass_context` enables clean settings propagation from the root group to subcommands.
- `argparse` would require more boilerplate for the same functionality and produces less polished help output.

**Tradeoff**: Additional dependency, but `click` is one of the most widely used Python CLI libraries and is already a transitive dependency of many tools.

---

## D009: Protocol classes for cross-platform abstraction

**Context**: The media session listener interface must work on Windows (SMTC via `winsdk`), Linux (MPRIS via `dbus-next`), and eventually macOS. Platform-specific packages cannot be imported on other platforms.

**Decision**: Define `MediaSessionListener` as a `typing.Protocol` class and use a factory function (`get_media_listener()`) to return the platform-appropriate implementation.

**Reasoning**:
- Protocol classes provide structural subtyping (duck typing with type checker support) without requiring inheritance.
- Each platform implementation lives in its own module with platform-gated imports at the top.
- The factory function checks `sys.platform` and returns the right implementation or `None` if the platform is not supported.
- This avoids `ImportError` at module import time and keeps the codebase testable on any platform.

**Tradeoff**: Protocol classes do not enforce the interface at runtime (only at type-checking time). A missing method would only be caught when called, not at instantiation. This is acceptable because the interface is small (3 methods) and well-tested.

---

## D010: Conditional imports for platform-specific packages

**Context**: `winsdk` only installs on Windows, `dbus-next` only makes sense on Linux. Importing either on the wrong platform raises `ImportError` or `ModuleNotFoundError`.

**Decision**: Use `try/except ImportError` blocks around platform-specific imports throughout the codebase.

**Reasoning**:
- The application can start on any platform. Missing platform features are logged as warnings and gracefully skipped.
- Optional dependency groups in `pyproject.toml` (`[windows]`, `[linux]`, `[ocr]`) allow users to install only what they need.
- The alternative (hard dependencies) would prevent installation on unsupported platforms entirely.

**Tradeoff**: Conditional imports can make the code harder to follow and may mask genuine import errors. Comprehensive test coverage mitigates this risk.

---

## D011: OCR engines use lazy loading

**Context**: EasyOCR imports PyTorch, which takes several seconds and hundreds of megabytes of memory. Tesseract requires an external binary. Neither should be loaded unless OCR is actually triggered.

**Decision**: Wrap OCR engine initialization in lazy-loading patterns. The engine objects are created on first use, not at import time.

**Reasoning**:
- Application startup remains fast (sub-second) even with OCR enabled in the configuration.
- Users who never trigger OCR (because SMTC/MPRIS or browser extension provide sufficient data) never pay the initialization cost.
- The OCR service checks `settings.ocr_enabled` before attempting any OCR operation.

**Tradeoff**: First OCR invocation has a cold-start delay (2-5 seconds for EasyOCR model loading). This is acceptable because OCR is the last-resort fallback.

---

## D012: Detection service uses asyncio for concurrent event processing

**Context**: The detection service must simultaneously poll ActivityWatch, receive SMTC/MPRIS callbacks, accept browser extension HTTP events, run the grace period sweeper, and process events from the queue.

**Decision**: Use `asyncio.create_task` for concurrent background loops and `asyncio.Queue` for event passing.

**Reasoning**:
- All detection sources feed into a single `asyncio.Queue[DetectionEvent]`, which the event processor consumes sequentially. This serializes event processing while allowing concurrent collection.
- Background tasks (`_aw_poll_loop`, `_event_processor`, `_grace_period_sweeper`) run as cooperative coroutines within the same event loop as the FastAPI server.
- No threading or multiprocessing is needed, avoiding synchronization complexity.
- `asyncio.wait_for` with a 1-second timeout in the event processor allows clean shutdown without blocking forever on an empty queue.

**Tradeoff**: CPU-bound operations (like OCR) would block the event loop. OCR should be offloaded to a thread pool executor if it becomes a bottleneck.

---

## D013: Browser extension sends HTTP events, not WebSocket

**Context**: The Chrome extension needs to communicate media playback events to the local Show Tracker service.

**Decision**: The background service worker sends events via `fetch()` to `POST /api/media-event` on the local HTTP server.

**Reasoning**:
- HTTP is stateless and requires no connection lifecycle management. If the service is temporarily down, the fetch simply fails and the extension retries on the next event.
- No reconnection logic, buffering, or backpressure handling is needed in the extension.
- Events arrive at most every 15 seconds (heartbeat interval), so the overhead of individual HTTP requests is negligible.
- WebSockets from a Manifest V3 service worker have additional complexity: service workers are ephemeral and may be terminated between events, requiring socket reconnection.
- The `/api/health` endpoint serves double duty as a connection check without requiring a persistent connection.

**Tradeoff**: Slightly higher latency per event (HTTP round-trip vs. WebSocket frame). For media tracking where events arrive every 15 seconds, this is irrelevant.
