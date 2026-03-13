# Project Status and TODO

## Completed

### Phase 0: Identification Pipeline

- [x] **Parser** (`identification/parser.py`): guessit-based extraction of show name, season, episode, year, quality from raw strings
- [x] **URL Patterns** (`identification/url_patterns.py`): Pattern matching for Netflix, Hulu, Disney+, HBO Max, Amazon Prime Video, YouTube, Crunchyroll, Peacock, Paramount+, Apple TV+, and more
- [x] **TMDb Client** (`identification/tmdb_client.py`): Async httpx client for TMDb v3 API (search shows, get show details, get episode details)
- [x] **Resolver** (`identification/resolver.py`): Full resolution chain (URL match, parse, alias lookup, cache check, TMDb fuzzy search, episode fetch)
- [x] **Confidence Scoring** (`identification/confidence.py`): Composite scoring with source reliability bases, bonuses, and penalties
- [x] **Test Dataset**: 100+ test cases for identification pipeline validation (`tests/data/identification_dataset.json`)

### Phase 1A: ActivityWatch Integration

- [x] **ActivityWatch Client** (`detection/activitywatch.py`): REST client for aw-server-rust
- [x] **Event Poller**: Polling loop with bucket discovery for `aw-watcher-window` and `aw-watcher-web`
- [x] **Mock Client**: `MockActivityWatchClient` for testing without a running AW server

### Phase 1A: OS Media Session Listeners

- [x] **SMTC Listener** (`detection/smtc_listener.py`): Windows System Media Transport Controls via `winsdk`
- [x] **MPRIS Listener** (`detection/mpris_listener.py`): Linux MPRIS D-Bus integration via `dbus-next`
- [x] **Media Session Abstraction** (`detection/media_session.py`): `MediaSessionListener` protocol, `PlaybackStatus` enum, `get_media_listener()` factory

### Phase 1B: Browser Extension

- [x] **Chrome Manifest V3** extension (`browser_extension/chrome/`)
- [x] **Content Script** (`content.js`): Video element detection, URL pattern matching, JSON-LD/OG metadata extraction, heartbeat emission
- [x] **Background Service Worker** (`background.js`): Event enrichment, forwarding to local API, connection status tracking
- [x] **Popup UI** (`popup.html/js/css`): Status display, tracking enable/disable toggle

### Phase 1C: Web UI and API

- [x] **FastAPI Application** (`api/app.py`): ASGI app with CORS, lifespan management, static file serving
- [x] **Media Event Routes** (`api/routes_media.py`): `POST /api/media-event`, `GET /api/currently-watching`
- [x] **History Routes** (`api/routes_history.py`): Recent episodes, show list, show detail, episode progress, next-to-watch, statistics
- [x] **Unresolved Routes** (`api/routes_unresolved.py`): List, resolve, dismiss, TMDb search
- [x] **Settings Routes** (`api/routes_settings.py`): Get/update settings, CRUD for aliases
- [x] **API Schemas** (`api/schemas.py`): Pydantic request/response models for all endpoints
- [x] **SPA Frontend** (`web_ui/`): Dashboard, shows grid, show detail with episode grid, unresolved queue, settings page
- [x] **Hash-Based Routing**: Client-side navigation (`#/dashboard`, `#/shows`, `#/shows/{id}`, `#/unresolved`, `#/settings`)

### Phase 2A: Player IPC

- [x] **VLC Web Interface** (`players/vlc.py`): HTTP client for VLC's Lua web interface, reads currently playing file and metadata
- [x] **mpv JSON IPC** (`players/mpv.py`): Unix socket / Windows named pipe client for mpv's JSON IPC protocol

### Phase 2B: OCR Subsystem

- [x] **Screenshot Capture** (`ocr/screenshot.py`): Cross-platform screenshot capture using Pillow/PIL
- [x] **Region Cropping** (`ocr/region_crop.py`): Crop title/overlay regions from player screenshots based on OCR profiles
- [x] **Tesseract Engine** (`ocr/engine.py`): pytesseract wrapper with preprocessing
- [x] **EasyOCR Engine** (`ocr/engine.py`): EasyOCR wrapper with lazy model loading
- [x] **OCR Service** (`ocr/ocr_service.py`): Orchestrator with Tesseract-first, EasyOCR-fallback strategy

### Storage Layer

- [x] **SQLAlchemy Models** (`storage/models.py`): Show, Episode, WatchEvent, YouTubeWatch, ShowAlias, UnresolvedEvent, UserSetting, TMDbShowCache, TMDbSearchCache, TMDbEpisodeCache, FailedLookup
- [x] **Database Manager** (`storage/database.py`): Dual-database management with WAL mode, foreign keys, transactional session scopes
- [x] **Repository** (`storage/repository.py`): Higher-level data operations with heartbeat merging pattern

### Configuration and CLI

- [x] **Pydantic Settings** (`config.py`): Typed configuration with env var loading, `.env` support, validation
- [x] **CLI Entry Points** (`main.py`): `show-tracker run`, `show-tracker identify`, `show-tracker test-pipeline`, `show-tracker init-db`
- [x] **Default OCR Profiles** (`profiles/default_profiles.json`): Pre-configured crop regions for common player layouts
- [x] **Default Alias Seed Data** (`utils/aliases.py`): Common show abbreviations and alternate names

### Testing

- [x] **Unit Tests**: `test_parser.py` (parser edge cases), `test_url_patterns.py` (URL matching for all supported platforms)
- [x] **Integration Tests**: `test_identification_pipeline.py` (end-to-end identification with 100+ test cases)

---

## Remaining / TODO

### Phase 0 Remaining: Identification Tuning

- [ ] **Real TMDb API validation**: Get a TMDb API key and validate the full pipeline against the live API (currently tested with mock responses)
- [ ] **Confidence threshold tuning**: Analyze real-world identification results to fine-tune `auto_log_threshold` (0.9) and `review_threshold` (0.7)
- [ ] **Alias table expansion**: Add more common abbreviations, international titles, and alternate names based on real usage patterns
- [ ] **Failed lookup analysis**: Review `failed_lookups` table after real usage to identify patterns that need new parsing rules

### Phase 1D: Windows Installer and Packaging

- [ ] **PyInstaller bundling**: Create a single-file or single-directory Windows executable
- [ ] **NSIS or Inno Setup installer**: Windows installer with Start Menu shortcuts and uninstall support
- [ ] **System tray icon**: Background operation via tray icon (start/stop tracking, open web UI, view status)
- [ ] **Auto-start on login**: Optional Windows registry entry or Startup folder shortcut
- [ ] **First-run wizard**: Guide users through TMDb API key setup and ActivityWatch installation

### Phase 2C: Full-Window OCR with Spatial Filtering

- [ ] **Real-world OCR testing**: Test screenshot capture and OCR on actual player windows (VLC, mpv, browser fullscreen)
- [ ] **Spatial filtering**: Filter OCR results by position to ignore subtitles and UI chrome, focusing on title overlays
- [ ] **OCR profile tuning**: Refine crop regions in `default_profiles.json` based on real screenshots from different players and resolutions
- [ ] **Confidence calibration**: Tune OCR confidence penalties with real OCR output data
- [ ] **Performance optimization**: Profile OCR pipeline latency and optimize preprocessing steps

### Phase 2D: Improved Identification

- [ ] **TVDb fallback for anime**: Integrate TVDb API as a secondary lookup for anime titles that TMDb handles poorly
- [ ] **YouTube Data API integration**: Use the YouTube Data API v3 to detect series/playlists and map them to shows
- [ ] **Expanded alias table**: Automated alias generation from TMDb alternative titles API endpoint
- [ ] **Multi-language title support**: Handle shows known by different names in different regions
- [ ] **Movie support**: Extend the pipeline to identify movies (currently TV-only)

### Phase 3A: Linux Packaging

- [ ] **AppImage**: Create a self-contained AppImage for easy Linux distribution
- [ ] **MPRIS end-to-end testing**: Test the MPRIS listener with real D-Bus sessions across multiple desktop environments (GNOME, KDE, Sway)
- [ ] **systemd user service**: Provide a `.service` file for running Show Tracker as a background service
- [ ] **Flatpak / Snap**: Evaluate containerized Linux packaging options

### Phase 3B: macOS Support

- [ ] **MediaRemote listener**: Implement media session detection via `pyobjc` (NSMediaRemote framework) or a Swift helper binary
- [ ] **CGWindowListCreateImage**: Screenshot capture for OCR on macOS
- [ ] **DMG packaging**: Create a macOS disk image for distribution
- [ ] **Launchd agent**: Background service management via launchd
- [ ] **Code signing**: Sign the application for Gatekeeper compatibility

### Phase 4A: Statistics and Insights

- [ ] **Watch time analytics**: Daily, weekly, monthly watch time charts
- [ ] **Binge detection**: Identify binge-watching sessions (3+ consecutive episodes)
- [ ] **Viewing patterns**: Time-of-day and day-of-week analysis
- [ ] **Completion tracking**: Percentage completion per show with progress bars
- [ ] **Year-in-review**: Annual summary of watching habits

### Phase 4B: Sync and Backup

- [ ] **JSON export**: Export full watch history as structured JSON
- [ ] **CSV export**: Export watch history as CSV for spreadsheet analysis
- [ ] **Trakt.tv import**: Import existing watch history from Trakt
- [ ] **Trakt.tv sync**: Two-way sync with Trakt.tv for cloud backup and social features
- [ ] **Simkl import/sync**: Integration with Simkl tracking service
- [ ] **Database backup**: Scheduled automatic backup of `watch_history.db`

### Phase 4C: Notifications

- [ ] **New episode alerts**: Check TMDb air dates and notify when tracked shows have new episodes
- [ ] **Desktop notifications**: System notifications via `plyer` or native APIs
- [ ] **Unwatched episode reminders**: Periodic reminders for shows with unwatched episodes

### Phase 4D: Android Support

- [ ] **ActivityWatch Android**: Integrate with the ActivityWatch Android app for mobile tracking
- [ ] **REST API sync**: Mobile clients could sync with the desktop database via the HTTP API

### Phase 4E: Media Server Webhooks

- [ ] **Plex webhooks**: Receive playback events from Plex Media Server
- [ ] **Jellyfin webhooks**: Receive playback events from Jellyfin
- [ ] **Emby webhooks**: Receive playback events from Emby

### Testing

- [ ] **End-to-end tests with ActivityWatch**: Integration tests against a real or emulated AW server
- [ ] **Browser extension testing**: Automated tests for content script metadata extraction
- [ ] **OCR accuracy benchmarks**: Test OCR pipeline on a corpus of real player screenshots
- [ ] **Cross-platform CI**: GitHub Actions matrix for Windows, Linux, and macOS
- [ ] **Load testing**: Verify API performance under sustained event throughput
- [ ] **Database migration tests**: Ensure schema changes work with Alembic migrations

### Polish

- [ ] **Error handling audit**: Review all `except Exception` blocks for proper error recovery and logging
- [ ] **Logging completeness**: Ensure all significant operations produce structured log output
- [ ] **Performance profiling**: Profile the identification pipeline and API response times under load
- [ ] **Privacy policy document**: Document what data is collected, stored, and transmitted
- [ ] **Rate limiting**: Add rate limiting to the TMDb client to respect API quotas
- [ ] **Graceful degradation**: Ensure the app functions (with reduced features) when TMDb is unreachable

### Distribution

- [ ] **Chrome Web Store submission**: Package and submit the Chrome extension
- [ ] **Firefox Add-ons submission**: Port the extension to Firefox WebExtensions API and submit
- [ ] **Firefox browser extension**: Port from Chrome Manifest V3 to Firefox-compatible format
- [ ] **PyPI publication**: Publish the Python package to PyPI for `pip install show-tracker`
- [ ] **THIRD_PARTY_LICENSES.txt**: Generate a comprehensive third-party license file for all dependencies
- [ ] **System tray integration**: Implement tray icon using `pystray` or platform-native APIs
