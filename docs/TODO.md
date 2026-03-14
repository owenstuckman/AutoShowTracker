# Project Status and TODO

## What Is Done

All five architectural layers are implemented with working code, tests, and documentation.

### Phase 0: Identification Pipeline (Complete)
- Parser with guessit integration and preprocessing for browser titles, filenames, SMTC metadata
- URL pattern matching for Netflix, YouTube, Crunchyroll, Plex, Disney+, Hulu, Amazon Prime, HBO Max, and generic pirate sites
- TMDb API client (httpx-based) with search, show detail, episode detail, find-by-external-id
- Episode resolver with alias lookup, cache, fuzzy matching (rapidfuzz, 0.80 threshold), confidence scoring
- 249 passing tests (52 unit + 197 integration across 100+ real-world inputs)
- CLI: `show-tracker identify "filename.mkv"`

### Phase 1: Windows Desktop MVP (Complete)
- **ActivityWatch integration**: REST client, event poller, bucket discovery, process manager with crash recovery, mock client for testing
- **SMTC listener**: Windows media session detection via winsdk WinRT bindings (event-driven)
- **MPRIS listener**: Linux D-Bus media session detection via dbus-next (event-driven)
- **Detection service**: Central orchestrator merging AW + SMTC/MPRIS + browser signals, deduplication, grace period, confidence routing
- **Browser extension**: Chrome Manifest V3 with content script (schema.org, Open Graph, video element monitoring, heartbeats), background service worker, popup UI
- **FastAPI API**: All endpoints for media events, watch history, show detail, episode grid, stats, unresolved queue, settings, aliases
- **Web UI**: Vanilla JS SPA with dashboard, shows grid, show detail with season tabs, unresolved resolution workflow, settings page
- **Storage**: Dual SQLite databases (watch_history.db + media_cache.db), SQLAlchemy ORM, repository pattern with heartbeat merging
- **CLI**: `show-tracker run`, `show-tracker init-db`, `show-tracker identify`, `show-tracker test-pipeline`

### Phase 2: Robust Detection (Complete)
- **VLC IPC**: HTTP interface client for VLC's web API (status, title, duration, position)
- **mpv IPC**: JSON IPC socket/pipe client (media-title, duration, position, path)
- **File handle inspection**: Cross-platform open file detection via psutil
- **Player service**: Orchestrator that tries native IPC then falls back to file handles
- **OCR subsystem**: Screenshot capture, per-app region cropping from JSON profiles, Tesseract + EasyOCR engines, preprocessing pipeline, orchestrator service
- **Browser event handler**: Priority chain (schema.org > Open Graph > URL pattern > page title)

### Configuration & Utilities (Complete)
- Pydantic-settings config with env vars, .env file, JSON defaults
- 50+ initial show alias seed data
- Default OCR region profiles for VLC, mpv, Plex, MPC-HC, Kodi
- Structured logging with file rotation

---

## What Is Left To Do

### Immediate (Before First Real Use)

- [ ] **Get a TMDb API key and validate end-to-end**: The full resolver → TMDb → episode fetch pipeline has not been tested against the live TMDb API. Get a key, set `TMDB_API_KEY` in `.env`, and run `show-tracker identify` on real inputs
- [ ] **Test SMTC listener on Windows**: The SMTC listener code is written but needs to be tested on a real Windows machine with media players running
- [ ] **Test MPRIS listener on Linux**: Same — needs testing with a real D-Bus session and media player
- [ ] **Test browser extension in Chrome**: Load the unpacked extension from `browser_extension/chrome/` and verify it detects playback on Netflix, YouTube, and a pirate site
- [ ] **Confidence threshold tuning**: Run the system for a few days and analyze whether 0.9/0.7 thresholds produce the right auto-log vs review split

### Phase 1D: Packaging (Not Started)

- [ ] PyInstaller or cx_Freeze bundling into a single executable
- [ ] Windows installer (Inno Setup or NSIS) with Start Menu shortcuts
- [ ] System tray icon via `pystray` (start/stop, open UI, status indicator)
- [ ] Auto-start on Windows login (optional, registry or Startup folder)
- [ ] Bundle ActivityWatch binaries alongside the installer
- [ ] First-run wizard for TMDb API key setup

### Phase 2 Gaps

- [ ] **Full-window OCR spatial filtering**: When no app profile exists, run full-window OCR and filter by position (top/bottom 15%) and font size
- [ ] **OCR profile tuning**: Test crop regions in `profiles/default_profiles.json` against real screenshots at various resolutions and themes
- [ ] **TVDb fallback**: Integrate TVDb API for anime with absolute episode numbering
- [ ] **YouTube Data API**: Use video ID to fetch playlist/series info and detect YouTube original series
- [ ] **Movie support**: Extend pipeline to identify movies (currently TV-episode only)

### Phase 3: Cross-Platform (Partially Done)

- [ ] **macOS MediaRemote listener**: Implement via pyobjc or Swift helper binary
- [ ] **macOS screenshot capture**: CGWindowListCreateImage for OCR
- [ ] **macOS packaging**: DMG installer, code signing, notarization
- [ ] **Linux packaging**: AppImage, possibly Flatpak
- [ ] **Linux systemd service file**: For running as a background daemon

### Phase 4: Polish & Advanced Features (Not Started)

- [ ] **Watch time analytics**: Daily/weekly/monthly charts, binge detection, viewing patterns
- [ ] **Export**: JSON and CSV export of watch history
- [ ] **Import**: Trakt.tv and Simkl import
- [ ] **Sync**: Optional Trakt.tv two-way sync
- [ ] **New episode notifications**: Check TMDb air dates, desktop notifications via plyer
- [ ] **Plex/Jellyfin/Emby webhooks**: Direct webhook integration (highest accuracy, lowest effort)
- [ ] **Android**: ActivityWatch Android integration, REST API sync
- [ ] **Database migrations**: Alembic setup for schema evolution

### Testing Gaps

- [ ] End-to-end tests with a real or emulated ActivityWatch server
- [ ] Browser extension automated testing
- [ ] OCR accuracy benchmarks on real player screenshots
- [ ] Cross-platform CI (GitHub Actions: Windows + Linux + macOS)
- [ ] API load testing

### Distribution

- [ ] Chrome Web Store submission (requires privacy policy for `<all_urls>`)
- [ ] Firefox extension port and Add-ons submission
- [ ] PyPI publication (`pip install show-tracker`)
- [ ] `THIRD_PARTY_LICENSES.txt` generation
- [ ] Privacy policy document
