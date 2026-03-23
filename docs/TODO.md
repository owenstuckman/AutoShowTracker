# Project Status and TODO

## What Is Done

All five architectural layers are implemented. All planned phases (0–4) are code-complete.

| Phase | Scope | Status |
|-------|-------|--------|
| **0** | Identification pipeline (guessit + TMDb + fuzzy matching + confidence scoring) | Complete |
| **1** | Windows MVP (ActivityWatch, SMTC/MPRIS, browser extension, FastAPI API, web UI, storage, CLI) | Complete |
| **1D** | Packaging (PyInstaller, system tray, first-run wizard) | Complete |
| **2** | Robust detection (VLC/mpv IPC, file handles, OCR, movie support, TVDb fallback, YouTube enrichment) | Complete |
| **3** | Cross-platform (macOS MediaRemote stub, macOS screenshot, Linux AppImage) | Complete |
| **4** | Advanced features (analytics, webhooks, notifications, Trakt sync, Alembic migrations) | Complete |

**Infrastructure:** GitHub Actions CI (Ubuntu + Windows, Python 3.11/3.12), systemd service, export API, Firefox extension port, privacy policy, third-party licenses, full documentation.

**Testing:** 249 unit + integration tests, Playwright browser extension E2E, OCR accuracy benchmark, API load test.

**Distribution tooling:** Release workflow (`.github/workflows/release.yml`), extension packager, version bump script, PyPI metadata.

---

## CI Failures — Must Fix to Pass CI

CI runs four checks: `ruff check`, `ruff format`, `mypy`, and `pytest`. All four currently fail.

### 1. Ruff Lint (`ruff check src/ tests/`) — 118 errors

| Rule | Count | Description |
|------|-------|-------------|
| I001 | 30 | Import blocks un-sorted or un-formatted |
| F401 | 21 | Unused imports |
| UP017 | 16 | Use `datetime.UTC` alias (Python 3.11+) |
| UP035 | 8 | Import from `collections.abc` instead of `typing` |
| B904 | 8 | Use `raise ... from err` in `except` blocks |
| RUF100 | 7 | Unused `noqa` directives |
| SIM105 | 5 | Use `contextlib.suppress(...)` instead of try/except/pass |
| TC002/TC005 | 7 | Move imports into `TYPE_CHECKING` block |
| N815/N806 | 3 | Variable naming convention violations |
| Other | 13 | RUF001 (ambiguous char), RUF006, RUF012, RUF022, SIM103, SIM109, UP037, UP041, TC001 |

84 of these are auto-fixable with `ruff check --fix src/ tests/`. The remaining 34 need manual fixes.

**How to fix:**
- [ ] Run `ruff check --fix src/ tests/` to auto-fix 84 errors
- [ ] Manually fix remaining ~34 errors (mostly `B904` raise-from, `RUF100` stale noqa, `N815`/`N806` naming)
- [ ] Verify: `ruff check src/ tests/` exits clean

### 2. Ruff Format (`ruff format --check src/ tests/`) — 43 files need reformatting

43 of 62 source files have formatting issues (whitespace, line breaks, trailing commas, etc.).

**How to fix:**
- [ ] Run `ruff format src/ tests/`
- [ ] Verify: `ruff format --check src/ tests/` exits clean

### 3. Mypy (`mypy src/show_tracker/`) — 85 errors across 28 files

| Error Category | Count | Description |
|----------------|-------|-------------|
| no-any-return | 22 | Functions returning `Any` when return type is declared |
| type-arg | 13 | Missing generic type parameters (e.g., `dict` instead of `dict[str, Any]`) |
| unused-ignore | 8 | Stale `# type: ignore` comments |
| import-not-found | 8 | Missing stubs for `plyer`, `winsdk`, `pytesseract`, `easyocr`, etc. |
| no-untyped-def | 6 | Functions missing type annotations |
| Any (explicit) | 6 | Explicit `Any` not allowed in strict mode |
| no-untyped-call | 5 | Calling untyped functions from typed context |
| arg-type | 5 | Argument type mismatches (e.g., SQLAlchemy `Cast`) |
| import-untyped | 4 | Importing from untyped third-party packages |
| attr-defined | 4 | Attribute access on wrong type (e.g., `MovieIdentificationResult` vs `IdentificationResult`) |
| assignment | 3 | Incompatible types in assignment |
| Other | 1 | `name-defined`, `return-value`, `valid-type`, `misc` |

**How to fix:**
- [ ] Add return type annotations and explicit casts to fix `no-any-return` (22 errors)
- [ ] Add generic type parameters: `dict` → `dict[str, Any]`, etc. (13 errors)
- [ ] Remove stale `# type: ignore` comments (8 errors)
- [ ] Add `# type: ignore[import-not-found]` or stub packages for platform-specific imports (`plyer`, `winsdk`, `pytesseract`, `easyocr`, `pystray`, etc.) (8 errors)
- [ ] Add type annotations to untyped functions in `main.py` (6 errors)
- [ ] Fix `IdentificationResult` vs `MovieIdentificationResult` type mismatch in `identification/__init__.py` (4 errors)
- [ ] Fix SQLAlchemy `Cast` type argument in `routes_stats.py` (2 errors)
- [ ] Clean up remaining misc errors (11 errors)
- [ ] Verify: `mypy src/show_tracker/` exits clean (currently `continue-on-error: true` in CI — remove that flag once clean)

### 4. Pytest (`pytest --tb=short -q`) — 8 failures + 9 errors

**8 test failures:**

| Test | Issue |
|------|-------|
| `test_detection_sources.py::TestPlexExtraction::test_episode_metadata` | Plex extraction logic mismatch |
| `test_detection_sources.py::TestPlexExtraction::test_movie_metadata` | Plex extraction logic mismatch |
| `test_detection_sources.py::TestPlexExtraction::test_unsupported_type` | Plex extraction logic mismatch |
| `test_detection_sources.py::TestPlexExtraction::test_guid_extraction` | Plex extraction logic mismatch |
| `test_detection_sources.py::TestPlexExtraction::test_guid_empty_list` | Plex extraction logic mismatch |
| `test_detection_sources.py::TestPlexExtraction::test_guid_malformed` | Plex extraction logic mismatch |
| `test_detection_sources.py::TestDetectionEvent::test_defaults` | `metadata_source` defaults to `""` but test expects `None` |
| `test_activitywatch.py::TestUrlPatternMatching::test_crunchyroll_url_matched` | Crunchyroll URL pattern not matching |

**9 test errors (not failures — tests can't even run):**

| Test | Issue |
|------|-------|
| All 9 in `test_browser_extension.py` | `RuntimeError: Form data requires "python-multipart"` — missing dependency |

**How to fix:**
- [ ] Add `python-multipart` to core dependencies in `pyproject.toml` (fixes all 9 E2E errors)
- [ ] Fix Plex webhook extraction logic or update tests to match current implementation (6 failures)
- [ ] Fix `DetectionEvent.metadata_source` default value — should be `None` not `""` (or update test) (1 failure)
- [ ] Fix Crunchyroll URL pattern in `url_patterns.py` to match current Crunchyroll URL format (1 failure)
- [ ] Verify: `pytest --tb=short -q` passes all 338 tests

---

## Missing Test Coverage — Features Described in Documentation

The following features are described in project documentation but have no dedicated tests. Tests should be added to ensure all documented behavior is verified.

### Layer 1: Collection/Detection (`src/show_tracker/detection/`)

- [ ] **SMTC listener unit tests** — Mock `winsdk` WinRT bindings, verify `media_properties_changed` callback extracts title/artist/album/playback_status/source_app correctly
- [ ] **MPRIS listener unit tests** — Mock `dbus-next` D-Bus interface, verify `PropertiesChanged` signal handling extracts `xesam:title`, `xesam:artist`, `xesam:album`, `mpris:length`
- [ ] **DetectionService deduplication tests** — Verify same show+season+episode within 120s grace period treated as heartbeat (not new detection), heartbeat_count incremented, last_heartbeat updated
- [ ] **DetectionService grace period sweeper tests** — Verify watches finalized after 120s of heartbeat silence
- [ ] **DetectionService event processor routing tests** — Verify events routed by confidence tier: >=0.9 auto-log, 0.7-0.9 log+flag, <0.7 unresolved queue
- [ ] **ActivityWatch subprocess management tests** — Verify port conflict detection (5600-5609), crash recovery with exponential backoff (2s, 4s, 8s, max 3 attempts), reuse of existing aw-server
- [ ] **ActivityWatch incremental polling tests** — Verify `last_processed` timestamp tracking per bucket, first-poll behavior (only most recent event), subsequent-poll behavior (all since last timestamp)
- [ ] **Browser extension event handling tests** — Verify all event types processed: `play`, `pause`, `ended`, `heartbeat`, `page_load`

### Layer 2: Parsing (`src/show_tracker/identification/parser.py`)

- [ ] **Date-based episode parsing tests** — Verify parsing of date-formatted episodes (e.g., `show.2024.03.15`)
- [ ] **Absolute episode numbering tests** — Verify anime-style absolute numbering (e.g., `naruto.150.720p`)
- [ ] **URL pattern tests for all platforms** — Verify URL extraction for: Netflix, YouTube, HBO Max, Amazon Prime, Disney+, Hulu, and generic pirate site patterns (some exist, ensure completeness)
- [ ] **Custom preprocessing tests** — Verify stripping of platform suffixes (`" | Netflix"`, `" - YouTube"`), noise word removal, whitespace normalization

### Layer 3: Identification/Resolution (`src/show_tracker/identification/`)

- [ ] **TMDb fuzzy matching threshold tests** — Verify 0.80 threshold for acceptance, 0.95+ bonus scoring
- [ ] **Alias table lookup tests** — Verify ~50 pre-seeded aliases resolve correctly (SVU → Law & Order: SVU, HIMYM → How I Met Your Mother, etc.)
- [ ] **Cache TTL tests** — Verify show search cache (30-day TTL), episode cache (indefinite for aired), failed lookup cache (24-hour TTL)
- [ ] **TVDb fallback tests** — Verify fallback to TVDb when TMDb lacks data, especially for anime with absolute episode numbering
- [ ] **YouTube Data API tests** — Verify playlist detection, video metadata extraction, YouTube-specific identification flow
- [ ] **Movie identification tests** — Verify movie identification pipeline (separate from TV show flow)

### Layer 4: Storage (`src/show_tracker/storage/`)

- [ ] **Dual database isolation tests** — Verify `watch_history.db` and `media_cache.db` are separate files, media_cache.db is rebuildable (delete + rebuild without data loss)
- [ ] **WatchRepository CRUD tests** — Verify create/read/update for `shows`, `episodes`, `watch_events`, `show_aliases`, `unresolved_events`, `youtube_watches`, `user_settings`
- [ ] **Unresolved event lifecycle tests** — Verify: create unresolved → search TMDb → resolve to episode (or dismiss) → mark resolved
- [ ] **Watch event completion logic tests** — Verify `completed` flag set when >= 90% of episode watched
- [ ] **Alembic migration tests** — Verify database migrations run cleanly on fresh and existing databases

### Layer 5: Presentation — API (`src/show_tracker/api/`)

- [ ] **`GET /api/health`** — Verify returns status and version
- [ ] **`POST /api/media-event`** — Verify accepts all event types (play/pause/ended/heartbeat/page_load) and processes them
- [ ] **`GET /api/currently-watching`** — Verify returns current detection state
- [ ] **`GET /api/history/recent`** — Verify returns recent episodes with `limit` parameter
- [ ] **`GET /api/history/shows`** — Verify returns all tracked shows with progress summaries
- [ ] **`GET /api/history/shows/{show_id}`** — Verify returns show detail with season/episode grid
- [ ] **`GET /api/history/shows/{show_id}/progress`** — Verify episode-level progress tracking
- [ ] **`GET /api/history/next-to-watch`** — Verify returns next unwatched episode per show
- [ ] **`GET /api/history/stats`** — Verify total watch time, episodes, breakdown by show/week
- [ ] **`GET /api/unresolved`** — Verify lists low-confidence events
- [ ] **`POST /api/unresolved/{event_id}/resolve`** — Verify manual assignment to show/episode
- [ ] **`POST /api/unresolved/{event_id}/dismiss`** — Verify discard without resolution
- [ ] **`POST /api/unresolved/{event_id}/search`** — Verify TMDb search for assignment candidates
- [ ] **`GET /api/settings`** / `PUT /api/settings/{key}`** — Verify settings CRUD
- [ ] **`POST /api/aliases`** / `GET /api/aliases/{show_id}` / `DELETE /api/aliases/{alias_id}`** — Verify alias CRUD
- [ ] **`GET /api/export/history.json`** — Verify JSON export of all watch events
- [ ] **`GET /api/export/history.csv`** — Verify CSV export with correct headers
- [ ] **`GET /api/export/shows.json`** / `GET /api/export/shows.csv`** — Verify show export
- [ ] **`POST /api/webhooks/plex`** — Verify Plex events: media.play, media.pause, media.resume, media.stop, media.scrobble
- [ ] **`POST /api/webhooks/jellyfin`** — Verify Jellyfin events: PlaybackStart, PlaybackStop, PlaybackProgress
- [ ] **`POST /api/webhooks/emby`** — Verify Emby events: playback.start, playback.stop, playback.progress
- [ ] **`GET /api/stats/daily`** — Verify per-day stats with `days` parameter
- [ ] **`GET /api/stats/weekly`** — Verify per-week stats with `weeks` parameter
- [ ] **`GET /api/stats/monthly`** — Verify per-month stats with `months` parameter
- [ ] **`GET /api/stats/binge-sessions`** — Verify binge detection (3+ episodes same show, same day)
- [ ] **`GET /api/stats/patterns`** — Verify viewing patterns (hour distribution, weekday distribution, avg session, most active hour/day)

### Layer 5: Presentation — Web UI (`web_ui/`)

- [ ] **SPA routing tests** — Verify hash-based navigation to `#/dashboard`, `#/shows`, `#/shows/{id}`, `#/unresolved`, `#/settings`
- [ ] **Dashboard render tests** — Verify recently watched, shows in progress, quick stats displayed
- [ ] **Unresolved queue UI tests** — Verify manual resolution flow (search → assign), dismiss flow
- [ ] **Settings page tests** — Verify theme toggle, threshold editing, API key configuration, alias management

### Confidence Scoring (`src/show_tracker/detection/detection_service.py`)

- [ ] **Base confidence by source** — Verify each source gets correct base: webhook=0.90, browser=0.85, SMTC/MPRIS=0.70, player_ipc=0.65, activitywatch=0.55, OCR=0.40
- [ ] **Bonus scoring tests** — Verify: URL platform match +0.15, season+episode present +0.10, fuzzy>=0.95 +0.08
- [ ] **Penalty scoring tests** — Verify: OCR source -0.10, no season -0.10, abbreviated title -0.05
- [ ] **Confidence routing thresholds** — Verify: >=0.9 AUTO_LOG, >=0.7 LOG_AND_FLAG, <0.7 UNRESOLVED

### OCR Pipeline (`src/show_tracker/ocr/`)

- [ ] **Region cropping tests** — Verify per-app bounding box profiles load from JSON and crop correctly (percentage-based coordinates)
- [ ] **Preprocessing tests** — Verify grayscale conversion, adaptive thresholding, upscaling to 300+ DPI, optional invert for light-on-dark
- [ ] **Full-window fallback tests** — Verify spatial filtering (top/bottom 15%), font size filtering, media-title pattern scoring
- [ ] **Engine selection tests** — Verify Tesseract primary, EasyOCR fallback, graceful degradation when neither installed

### Player IPC (`src/show_tracker/players/`)

- [ ] **VLC web interface tests** — Mock HTTP responses from `localhost:8080/requests/status.json`, verify metadata extraction
- [ ] **mpv JSON IPC tests** — Mock socket/pipe responses, verify `get_property` commands and response parsing

### CLI (`src/show_tracker/main.py`)

- [ ] **`show-tracker identify` tests** — Verify single string identification with `--source` flag
- [ ] **`show-tracker test-pipeline` tests** — Verify test dataset processing with `-v` verbose output
- [ ] **`show-tracker init-db` tests** — Verify database initialization with `--force` flag
- [ ] **`show-tracker setup` tests** — Verify interactive setup wizard flow

### Configuration (`src/show_tracker/config.py`)

- [ ] **Config priority tests** — Verify: env vars (ST_ prefix) > .env file > CLI flags > default_settings.json > Pydantic defaults
- [ ] **All ST_ env vars tests** — Verify each: `ST_DATA_DIR`, `ST_MEDIA_SERVICE_PORT`, `ST_ACTIVITYWATCH_PORT`, `ST_AUTO_LOG_THRESHOLD`, `ST_REVIEW_THRESHOLD`, `ST_OCR_ENABLED`, `ST_HEARTBEAT_INTERVAL`, `ST_GRACE_PERIOD`, `ST_POLLING_INTERVAL`

### Sync (`src/show_tracker/sync/`)

- [ ] **Trakt.tv sync tests** — Verify export watch history to Trakt, import from Trakt, conflict resolution

### Notifications (`src/show_tracker/notifications.py`)

- [ ] **Notification dispatch tests** — Verify notification sent for new episodes, recommendations (mock `plyer`)

---

## What Is Left To Do (Non-CI)

#### Code — DetectionService Wiring
- [x] **Wire `DetectionService` into FastAPI lifespan** (`src/show_tracker/api/app.py`) — SMTC, MPRIS, and ActivityWatch polling now start automatically with `show-tracker run`

#### Distribution Submissions
- [ ] **PyPI publication** — `git tag v0.1.0 && git push --tags` (triggers CI), or manually `python -m build && twine upload dist/*`
- [ ] **Chrome Web Store** — Create developer account ($5), upload `dist/show-tracker-chrome-*.zip` — see [docs/DISTRIBUTION.md](DISTRIBUTION.md)
- [ ] **Firefox Add-ons** — Upload `dist/show-tracker-firefox-*.zip` at https://addons.mozilla.org/developers/

#### Detection Source Testing
- [ ] Test SMTC listener (Windows) — see HUMAN_TODO 2a
- [ ] Test MPRIS listener (Linux) — see HUMAN_TODO 2b
- [ ] Test browser extension (Chrome + Firefox)
- [ ] Test VLC web interface
- [ ] Test mpv IPC socket
- [ ] Test Plex/Jellyfin/Emby webhooks

See [docs/HUMAN_TODO.md](HUMAN_TODO.md) for detailed steps on each.

#### Post-Setup Tuning
- [ ] Tune confidence thresholds after 3-5 days of use
- [ ] Seed show aliases for your library
- [ ] Set up Trakt.tv sync
