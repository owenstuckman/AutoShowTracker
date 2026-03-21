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

## What Is Left To Do

### Human-Required Tasks (see `docs/HUMAN_TODO.md` for step-by-step instructions)

#### Critical Path (COMPLETE)
- [x] **Set up Python environment** — venv created, dependencies installed, CLI verified
- [x] **Get a TMDb API key** — account created, key configured in `.env`
- [x] **Initialize databases and validate pipeline** — databases created, `show-tracker identify` tested end-to-end with TMDb resolution
- [x] **Start full service and verify web UI** — service starts, dashboard loads, API health check passes

#### Detection Source Testing (IN PROGRESS — test the ones you use)
- [ ] **Test SMTC listener on Windows** — start service, play media in VLC/browser, check logs for SMTC events, verify title/artist/playback status captured, test pause/resume
- [ ] **Test MPRIS listener on Linux** — verify D-Bus running, start service, play media, check logs for MPRIS events, test with VLC/mpv/browser
- [ ] **Test browser extension in Chrome** — load unpacked from `browser_extension/chrome/`, verify popup shows "Connected", test on Netflix/YouTube/Crunchyroll/Disney+/Hulu/Prime/HBO Max, verify heartbeats every 15s, verify pause/ended events
- [ ] **Test browser extension in Firefox** — load from `browser_extension/firefox/` via about:debugging, verify same functionality as Chrome
- [ ] **Test VLC web interface** — enable web interface in VLC preferences, set Lua HTTP password, restart VLC, verify http://localhost:8080 works, play a file, check detection
- [ ] **Test mpv IPC socket** — add `input-ipc-server` to mpv.conf, restart mpv, verify socket exists, play a file, check detection
- [ ] **Test Plex/Jellyfin/Emby webhooks** — configure webhook URL `http://localhost:7600/api/webhooks/{platform}`, play media, verify events received

#### Post-Setup Tuning
- [ ] **Tune confidence thresholds** — use system for 3-5 days, review unresolved queue, check for false positives in auto-logged items, adjust `ST_AUTO_LOG_THRESHOLD`/`ST_REVIEW_THRESHOLD` in `.env`
- [ ] **Seed show aliases** — add abbreviations for shows you watch via `POST /api/aliases`
- [ ] **Set up Trakt.tv sync** — get Trakt API credentials, run device auth flow, import history

---

### Remaining Code Tasks

#### Phase 2 Gaps — COMPLETE

- [x] **TVDb API client and fallback**
  - `src/show_tracker/identification/tvdb_client.py` — Full TVDb v4 client with JWT auth, search, series/episode lookup, absolute-to-season/episode mapping
  - `resolver.py` updated with `_try_tvdb_fallback()` — triggers when TMDb confidence < 0.6, no season number, episode > 50 (anime absolute numbering)
- [x] **YouTube Data API integration**
  - `src/show_tracker/identification/youtube_client.py` — YouTube Data API v3 client with video/playlist lookup, series detection from playlists/titles
  - `identification/__init__.py` updated with YouTube enrichment in `identify_media()` — tries YouTube API first for YouTube URLs, falls back to normal resolver

#### Phase 3 Remaining — COMPLETE

- [x] **Linux AppImage packaging**
  - `scripts/build_appimage.sh` — Full AppImage build script using appimagetool, bundles Python venv + all deps + data files

#### Web UI Enhancements — COMPLETE

- [x] **Stats page with charts**
  - Added Chart.js CDN to `index.html`, Stats nav link, `renderStats()` view in `app.js`
  - Daily/weekly bar charts, hourly viewing pattern chart, binge session list
- [x] **Movies tab**
  - Added Movies nav link, `renderMovies()` view with movie card grid in `app.js`

#### Testing Gaps — COMPLETE

- [x] **Browser extension automated testing**
  - `tests/e2e/test_browser_extension.py` — Playwright-based E2E tests with Chromium + extension loaded
  - Test pages served via built-in HTTP server (schema.org, OG tags, video elements, player detection)
  - Tests: metadata extraction, playback events to API, popup UI loading
  - Run: `pytest tests/e2e/test_browser_extension.py -v` (requires `pip install playwright && playwright install chromium`)
- [x] **OCR accuracy benchmarks**
  - `scripts/ocr_benchmark.py` — Benchmark script supporting Tesseract and EasyOCR engines
  - `tests/data/ocr_screenshots/manifest.json` — Ground-truth manifest (add screenshots to run)
  - Reports per-player, per-resolution accuracy with fuzzy title matching
  - Run: `python scripts/ocr_benchmark.py --engine tesseract --verbose`
- [x] **API load testing**
  - `scripts/load_test.py` — Async httpx-based load test (no extra dependencies)
  - Simulates N concurrent viewers with realistic play/heartbeat/pause/ended lifecycle
  - Also tests concurrent read endpoints (health, currently-watching)
  - Reports latency percentiles (p50/p95/p99), RPS, success rate, pass/fail assessment
  - Run: `python scripts/load_test.py --viewers 10 --duration 60 --interval 15`

#### Distribution — Automation COMPLETE, Submissions Human-Required

**Automated infrastructure (done):**
- [x] **GitHub Actions release pipeline** — `.github/workflows/release.yml` triggers on `v*` tags, builds all artifacts, creates GitHub Release
  - PyPI publish (requires `PYPI_API_TOKEN` secret)
  - Windows PyInstaller binary (ZIP)
  - Linux AppImage
  - Chrome + Firefox extension ZIPs
- [x] **Extension packaging script** — `scripts/package_extensions.sh` validates manifests and creates submission-ready ZIPs
- [x] **Version bump script** — `scripts/bump_version.sh` updates pyproject.toml, __init__.py, and both manifest.json files
- [x] **PyPI metadata** — `pyproject.toml` updated with authors, classifiers, project URLs
- [x] **Distribution guide** — `docs/DISTRIBUTION.md` with step-by-step instructions for all channels

**Human-required submissions (remaining):**
- [ ] **PyPI publication** — Run `git tag v0.1.0 && git push --tags` to trigger automated publish, or manually `python -m build && twine upload dist/*`
- [ ] **Chrome Web Store submission** — Create developer account ($5), upload `dist/show-tracker-chrome-*.zip`, see `docs/DISTRIBUTION.md`
- [ ] **Firefox Add-ons submission** — Upload `dist/show-tracker-firefox-*.zip` at https://addons.mozilla.org/developers/
