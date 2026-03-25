# TODO

For completed features, see [FEATURES.md](FEATURES.md).

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

84 auto-fixable with `ruff check --fix src/ tests/`. Remaining 34 need manual fixes.

- [ ] Run `ruff check --fix src/ tests/` to auto-fix 84 errors
- [ ] Manually fix remaining ~34 errors (mostly `B904` raise-from, `RUF100` stale noqa, `N815`/`N806` naming)
- [ ] Verify: `ruff check src/ tests/` exits clean

### 2. Ruff Format (`ruff format --check src/ tests/`) — 43 files

- [ ] Run `ruff format src/ tests/`
- [ ] Verify: `ruff format --check src/ tests/` exits clean

### 3. Mypy (`mypy src/show_tracker/`) — 85 errors across 28 files

| Error Category | Count | Description |
|----------------|-------|-------------|
| no-any-return | 22 | Functions returning `Any` when return type is declared |
| type-arg | 13 | Missing generic type parameters |
| unused-ignore | 8 | Stale `# type: ignore` comments |
| import-not-found | 8 | Missing stubs for `plyer`, `winsdk`, `pytesseract`, `easyocr`, etc. |
| no-untyped-def | 6 | Functions missing type annotations |
| Any (explicit) | 6 | Explicit `Any` not allowed in strict mode |
| no-untyped-call | 5 | Calling untyped functions from typed context |
| arg-type | 5 | Argument type mismatches (e.g., SQLAlchemy `Cast`) |
| import-untyped | 4 | Importing from untyped third-party packages |
| attr-defined | 4 | `MovieIdentificationResult` vs `IdentificationResult` type mismatch |
| assignment | 3 | Incompatible types in assignment |
| Other | 1 | `name-defined`, `return-value`, `valid-type`, `misc` |

- [ ] Add return type annotations and explicit casts (22 errors)
- [ ] Add generic type parameters: `dict` → `dict[str, Any]`, etc. (13 errors)
- [ ] Remove stale `# type: ignore` comments (8 errors)
- [ ] Add `# type: ignore[import-not-found]` or stubs for platform imports (8 errors)
- [ ] Add type annotations to untyped functions in `main.py` (6 errors)
- [ ] Fix `IdentificationResult` vs `MovieIdentificationResult` mismatch in `identification/__init__.py` (4 errors)
- [ ] Fix SQLAlchemy `Cast` type argument in `routes_stats.py` (2 errors)
- [ ] Clean up remaining misc errors (11 errors)
- [ ] Verify: `mypy src/show_tracker/` exits clean; remove `continue-on-error: true` from CI

### 4. Pytest — 8 failures + 9 errors

| Test | Issue |
|------|-------|
| `test_detection_sources.py` — 6 Plex tests | Plex extraction logic mismatch |
| `test_detection_sources.py::TestDetectionEvent::test_defaults` | `metadata_source` defaults to `""` but test expects `None` |
| `test_activitywatch.py::test_crunchyroll_url_matched` | Crunchyroll URL pattern not matching |
| All 9 in `test_browser_extension.py` | Missing `python-multipart` dependency |

- [ ] Add `python-multipart` to core dependencies in `pyproject.toml`
- [ ] Fix Plex tests or update to match current implementation (6 failures)
- [ ] Fix `DetectionEvent` test to expect `""` not `None` (1 failure)
- [ ] Fix Crunchyroll URL pattern in `url_patterns.py` (1 failure)
- [ ] Verify: `pytest --tb=short -q` passes all tests

---

## Missing Functionality

Features described in design docs (`docs/design/`) but not implemented or not wired up.

### Movie API Routes — No Dedicated Endpoints (High Priority)

`MovieWatch` model, `resolve_movie()`, and webhook extraction all exist. Web UI Movies page exists but hacks around missing endpoints by filtering `/api/history/recent`.

- [ ] Create `src/show_tracker/api/routes_movies.py`:
  - [ ] `GET /api/movies/recent` — recent movie watches
  - [ ] `GET /api/movies/stats` — movie watch stats
  - [ ] `GET /api/movies/{id}` — single movie detail
- [ ] Register movie router in `app.py`
- [ ] Update web UI `renderMovies()` to use dedicated endpoints

### Trakt Sync — Not Wired to API or UI (Medium Priority)

`sync/trakt.py` has full OAuth2 device flow, import, and export — but nothing exposes it.

- [ ] Create `src/show_tracker/api/routes_sync.py`:
  - [ ] `POST /api/sync/trakt/auth` — initiate device auth flow
  - [ ] `GET /api/sync/trakt/status` — check auth status
  - [ ] `POST /api/sync/trakt/sync` — trigger manual sync
  - [ ] `DELETE /api/sync/trakt/disconnect` — revoke connection
- [ ] Register sync router in `app.py`
- [ ] Add Trakt section to web UI Settings page
- [ ] Wire automatic scrobble on watch completion (optional per setting)

### Notifications — Not Wired to Scheduled Checks (Medium Priority)

`notifications.py` has `check_new_episodes()` and `notify_new_episodes()` via plyer — but never called.

- [ ] Add periodic new-episode check to FastAPI lifespan (background task, e.g. hourly)
- [ ] Add notification preference endpoints or use existing settings API
- [ ] Add notification toggle to web UI Settings page
- [ ] Consider: "continue watching" prompt on app open (design doc 4C)

### Alembic Migrations — No Migration Files (Medium Priority)

`alembic/` directory exists with `env.py` and `script.py.mako`, but `alembic/versions/` is empty. Schema changes require manual DB recreation.

- [ ] Generate initial migration: `alembic revision --autogenerate -m "initial schema"`
- [ ] Test on fresh DB: `alembic upgrade head`
- [ ] Test on existing DB with data (ensure no data loss)
- [ ] Document migration workflow in SETUP.md

### macOS Support — Stub Only (Low Priority)

`macos_listener.py` exists as skeleton. `get_media_listener()` returns `None` on macOS.

- [ ] Implement `MacOSMediaListener` using pyobjc or Swift helper binary
- [ ] Add `pyobjc-framework-MediaPlayer` to `[macos]` optional dependency group
- [ ] Add macOS screenshot capture for OCR (`CGWindowListCreateImage`)
- [ ] Test on macOS: Safari, Music.app, VLC, IINA

### Cloud Sync / Backup — Not Implemented (Low Priority)

Design doc Phase 4B mentions optional cloud sync (Syncthing/Dropbox compatible).

- [ ] Document recommended backup strategy (copy `watch_history.db` to cloud folder)
- [ ] Consider: Syncthing/Dropbox-compatible data directory setting (`ST_DATA_DIR`)
- [ ] Consider: import/merge from another instance's export

### Windows Installer — No Inno Setup Script (Low Priority)

DISTRIBUTION.md references `scripts/inno_setup.iss` but the file does not exist.

- [ ] Create `scripts/inno_setup.iss` template for Inno Setup
- [ ] Or document alternative: NSIS script, MSIX, or ZIP-only distribution

### Simkl Import — Not Implemented (Low Priority)

Design doc Phase 4B mentions import from Simkl alongside Trakt.

- [ ] Consider adding Simkl import support (low priority)

### Android Support — Not Implemented (Future/Exploratory)

Design doc Phase 4D describes Android support. No code exists.

- [ ] Future scope — not a current gap

---

## Missing Test Coverage

### Detection (`src/show_tracker/detection/`)

- [ ] SMTC listener unit tests — mock `winsdk`, verify callback extracts title/artist/album/playback_status/source_app
- [ ] MPRIS listener unit tests — mock `dbus-next`, verify PropertiesChanged signal handling
- [ ] DetectionService deduplication tests — same show within 120s grace = heartbeat not new detection
- [ ] DetectionService grace period sweeper — watches finalized after 120s silence
- [ ] DetectionService confidence routing — >=0.9 auto-log, 0.7-0.9 flag, <0.7 unresolved
- [ ] ActivityWatch subprocess management — port conflict detection, crash recovery with backoff
- [ ] ActivityWatch incremental polling — `last_processed` tracking, first-poll vs subsequent-poll behavior
- [ ] Browser extension event handling — all event types: play, pause, ended, heartbeat, page_load

### Parsing (`src/show_tracker/identification/parser.py`)

- [ ] Date-based episode parsing (e.g., `show.2024.03.15`)
- [ ] Absolute episode numbering (e.g., `naruto.150.720p`)
- [ ] URL pattern completeness for all platforms
- [ ] Platform suffix stripping, noise word removal, whitespace normalization

### Identification (`src/show_tracker/identification/`)

- [ ] TMDb fuzzy matching threshold (0.80 accept, 0.95+ bonus)
- [ ] Alias table lookup (~50 pre-seeded aliases)
- [ ] Cache TTL (show search 30d, episode indefinite, failed lookup 24h)
- [ ] TVDb fallback for anime/absolute numbering
- [ ] YouTube Data API (playlist detection, metadata extraction)
- [ ] Movie identification pipeline

### Storage (`src/show_tracker/storage/`)

- [ ] Dual database isolation (separate files, cache rebuildable)
- [ ] WatchRepository CRUD for all models
- [ ] Unresolved event lifecycle (create → search → resolve/dismiss)
- [ ] Watch event completion (completed flag at >= 90%)
- [ ] Alembic migration tests

### API Endpoints (`src/show_tracker/api/`)

- [ ] `GET /api/health`
- [ ] `POST /api/media-event` — all event types
- [ ] `GET /api/currently-watching`
- [ ] `GET /api/history/recent`, `/shows`, `/shows/{id}`, `/shows/{id}/progress`, `/next-to-watch`, `/stats`
- [ ] `GET /api/unresolved`, `POST .../resolve`, `POST .../dismiss`, `POST .../search`
- [ ] `GET /api/settings`, `PUT /api/settings/{key}`
- [ ] `POST /api/aliases`, `GET /api/aliases/{show_id}`, `DELETE /api/aliases/{alias_id}`
- [ ] `GET /api/export/history.json`, `.csv`, `shows.json`, `.csv`
- [ ] `POST /api/webhooks/plex`, `/jellyfin`, `/emby`
- [ ] `GET /api/stats/daily`, `/weekly`, `/monthly`, `/binge-sessions`, `/patterns`
- [ ] `GET /api/youtube/recent`, `/stats`

### Web UI (`web_ui/`)

- [ ] SPA routing to all pages
- [ ] Dashboard render (recent episodes, stats, YouTube)
- [ ] Unresolved queue UI (search/assign/dismiss)
- [ ] Settings page (theme, thresholds, API keys, aliases)
- [ ] Movies page
- [ ] YouTube page
- [ ] Stats page charts

### Confidence Scoring (`src/show_tracker/identification/confidence.py`)

- [ ] Base confidence by source (webhook=0.90, browser=0.85, SMTC/MPRIS=0.70, player_ipc=0.65, activitywatch=0.55, OCR=0.40)
- [ ] Bonus scoring (URL match +0.15, season+episode +0.10, fuzzy>=0.95 +0.08)
- [ ] Penalty scoring (OCR -0.10, no season -0.10, abbreviated title -0.05)
- [ ] Confidence routing thresholds

### OCR Pipeline (`src/show_tracker/ocr/`)

- [ ] Region cropping from JSON profiles
- [ ] Preprocessing (grayscale, threshold, upscale, invert)
- [ ] Full-window fallback (spatial filtering, font size filtering)
- [ ] Engine selection (Tesseract primary, EasyOCR fallback, graceful degradation)

### Player IPC (`src/show_tracker/players/`)

- [ ] VLC web interface — mock HTTP, verify metadata extraction
- [ ] mpv JSON IPC — mock socket/pipe, verify response parsing

### CLI (`src/show_tracker/main.py`)

- [ ] `show-tracker identify` with `--source` flag
- [ ] `show-tracker test-pipeline` with `-v` verbose
- [ ] `show-tracker init-db` with `--force`
- [ ] `show-tracker setup` wizard flow

### Configuration (`src/show_tracker/config.py`)

- [ ] Config priority (env vars > .env > defaults > Pydantic)
- [ ] All ST_ env vars

### Sync & Notifications

- [ ] Trakt.tv sync (export, import, conflict resolution)
- [ ] Notification dispatch (mock plyer)

---

## Manual Testing

- [ ] Test SMTC listener (Windows) — see [HUMAN_TODO.md](HUMAN_TODO.md) 2a
- [ ] Test MPRIS listener (Linux) — see [HUMAN_TODO.md](HUMAN_TODO.md) 2b
- [ ] Test browser extension (Chrome + Firefox)
- [ ] Test VLC web interface
- [ ] Test mpv IPC socket
- [ ] Test Plex/Jellyfin/Emby webhooks

---

## Distribution

- [ ] **PyPI publication** — `git tag v0.1.0 && git push --tags` or `python -m build && twine upload dist/*`
- [ ] **Chrome Web Store** — developer account ($5), upload ZIP — see [DISTRIBUTION.md](DISTRIBUTION.md)
- [ ] **Firefox Add-ons** — upload ZIP at https://addons.mozilla.org/developers/
- [ ] **Windows Installer** — create `scripts/inno_setup.iss` (referenced in DISTRIBUTION.md but missing)

---

## Documentation Gaps

- [ ] **TMDb API attribution** — design doc 09 requires disclaimer in about/credits. Verify it appears in web UI.
- [ ] **YouTube API attribution** — design doc 09 requires YouTube branding when using Data API.
- [ ] **TMDb cache max 6 months** — design doc 09 notes ToS requirement. Verify cache TTL enforces this.
- [ ] **YouTube API quota tracking** — 10,000 units/day free tier. No quota tracking or warning exists.
- [ ] **SETUP.md migration section** — document `alembic upgrade head` workflow once migrations exist.

---

## Post-Setup Tuning

- [ ] Tune confidence thresholds after 3-5 days of use
- [ ] Seed show aliases for your library
- [ ] Set up Trakt.tv sync
