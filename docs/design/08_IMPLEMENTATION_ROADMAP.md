# Implementation Roadmap

## Guiding Principle

Ship the highest-value, lowest-risk slice first, then expand. The riskiest component is the content identification pipeline (fuzzy matching accuracy). Validate that before building the full product.

## Phase 0: Identification Pipeline Validation (1-2 weeks)

**Goal:** Prove that the parsing + identification pipeline works accurately enough to be useful, before building any infrastructure around it.

**Deliverables:**
1. A standalone Python script that takes a raw string (simulating a window title, URL, or page title) and outputs a canonical TMDb episode match with confidence score.
2. A test dataset of 100+ real-world inputs covering:
   - Clean Plex-style titles.
   - Messy pirate filenames (download 100 torrent names from public trackers).
   - Browser tab titles from Netflix, YouTube, Crunchyroll, Hulu, Disney+.
   - Abbreviated and alternate show names.
   - Edge cases: no season number, absolute episode numbering, date-based episodes.
3. Accuracy measurement: what percentage resolve correctly? Target >= 85% for auto-log quality.

**Components built:**
- `guessit` integration with preprocessing.
- TMDb API client with fuzzy matching.
- Confidence scoring logic.
- Show alias table (initial seed of ~50 common abbreviations).
- TMDb response caching (SQLite).

**Why this is Phase 0:** If identification accuracy is below ~80%, the product is unusable regardless of how good the detection infrastructure is. This phase de-risks the core value proposition with minimal investment.

## Phase 1: Windows Desktop MVP (3-4 weeks)

**Goal:** Working end-to-end system on Windows that tracks viewing in Chrome/Firefox and VLC, packaged as a single installable application.

### Milestone 1A: ActivityWatch Integration + Basic Detection (Week 1-2)

**Deliverables:**
1. Launcher process that starts bundled ActivityWatch (aw-server-rust + aw-watcher-window).
2. Media identification service that polls ActivityWatch REST API for window events.
3. SMTC listener daemon that subscribes to Windows media session changes.
4. Events from both sources feed into the Phase 0 identification pipeline.
5. Identified episodes written to SQLite watch_history.db.

**Validation:** Open VLC, play a file with an episode-like filename. Verify it appears in the database. Switch to another app, let VLC auto-advance. Verify the new episode is detected via SMTC.

### Milestone 1B: Browser Extension (Week 2-3)

**Deliverables:**
1. Chrome extension (Manifest V3) with content script that extracts metadata.
2. Background service worker that posts events to the media identification service.
3. URL pattern matching for Netflix, YouTube, Crunchyroll.
4. Generic fallback: page title + URL slug parsing for unrecognized sites.
5. Video playback detection (play/pause/ended events) with 30-second heartbeats.

**Validation:** Open Netflix in Chrome, play an episode. Verify detection and logging. Open a pirate streaming site, play an episode. Verify detection from URL slug and/or page title.

### Milestone 1C: Basic Web UI (Week 3-4)

**Deliverables:**
1. Local web server (Flask or FastAPI) serving a frontend on localhost.
2. Dashboard: recently watched episodes, shows in progress.
3. Show detail view: season/episode grid with watch status.
4. Unresolved events queue: list of low-confidence detections for user review.
5. Manual correction: user can assign an unresolved event to a specific show/episode.

**Validation:** User can see their watch history, correct misidentifications, and browse their show progress.

### Milestone 1D: Packaging (Week 4)

**Deliverables:**
1. Windows installer (NSIS, Inno Setup, or PyInstaller + NSIS wrapper).
2. Bundles: Python runtime, ActivityWatch binaries, browser extension (sideloaded or CRX).
3. System tray icon with start/stop/open UI.
4. Auto-start on Windows login (optional, user-configurable).

## Phase 2: Robust Detection + OCR Fallback (2-3 weeks)

**Goal:** Handle edge cases that Phase 1 misses.

### Milestone 2A: Direct Player IPC

**Deliverables:**
1. VLC web interface integration (poll `localhost:8080/requests/status.json`).
2. mpv JSON IPC integration (connect to IPC socket).
3. Player detection: identify when VLC or mpv is running (from ActivityWatch app name or `psutil` process list).
4. IPC data feeds into the same identification pipeline.

### Milestone 2B: OCR Subsystem

**Deliverables:**
1. ✅ Background-safe window screenshot capture using `PrintWindow` (Win32 API).
2. ✅ Per-app region profiles for VLC, mpv, Plex (JSON config).
3. ✅ OCR via Tesseract (with EasyOCR fallback).
4. ✅ Image preprocessing: grayscale, adaptive threshold, upscale.
5. ✅ Trigger logic: only OCR when SMTC + window title both fail for a detected media player.
6. ❌ User calibration UI: allow user to define region-of-interest for unknown apps. **Not implemented** — see [TODO.md](../TODO.md#ocr-user-calibration-ui--not-implemented).

### Milestone 2C: Full-Window OCR Fallback

**Deliverables:**
1. Full-window OCR with bounding box output.
2. Spatial filtering: keep text from top 15% and bottom 15% of window.
3. Font size filtering.
4. Candidate scoring against media title patterns.

### Milestone 2D: Improved Identification

**Deliverables:**
1. TVDb fallback for anime and shows missing from TMDb.
2. YouTube Data API integration for series/playlist detection.
3. Expanded show alias table based on Phase 1 user feedback / misidentifications.
4. Handling of ambiguous cases: no season number, multiple show candidates.

## Phase 3: Linux and macOS Support (2-3 weeks)

**Goal:** Cross-platform parity.

### Milestone 3A: Linux

**Deliverables:**
1. ✅ MPRIS listener (D-Bus, `dbus-next`).
2. ✅ File handle inspection via `/proc/<pid>/fd/`.
3. ❌ X11 window capture for OCR (Wayland: assess feasibility, may defer). **X11 implemented; Wayland not addressed** — see [TODO.md](../TODO.md#wayland-ocr-capture--not-implemented).
4. ✅ Linux packaging: AppImage build script (`scripts/build_appimage.sh`).
5. ❌ Test with VLC, mpv, Celluloid, Firefox, Chromium. **Manual testing not yet done** — see [HUMAN_TODO.md](../HUMAN_TODO.md#2b-mpris-listener-linux).

### Milestone 3B: macOS

**Deliverables:**
1. ✅ MediaRemote listener (`macos_listener.py` via `pyobjc-framework-MediaPlayer`). **Implemented as stub; untested on real hardware.**
2. ✅ `CGWindowListCreateImage` for OCR window capture (with `screencapture` CLI fallback).
3. ❌ macOS packaging: DMG or pkg installer. **Not implemented** — no build script exists.
4. ❌ Test with VLC, IINA, Safari, Chrome. **Requires macOS hardware** — see [HUMAN_TODO.md](../HUMAN_TODO.md#2h-macos-listener-macos-hardware-required).

## Phase 4: Polish and Advanced Features (Ongoing)

### 4A: Statistics and Insights
- ✅ Total watch time per show, per week, per month.
- ✅ Viewing patterns (time of day, day of week).
- ✅ Binge detection (multiple episodes of same show in one session).
- ❌ "Time to finish" estimates for shows in progress. **Not implemented** — see [TODO.md](../TODO.md#time-to-finish-estimates--not-implemented).

### 4B: Sync and Backup
- ✅ Export watch history as JSON/CSV.
- ✅ Import from Trakt and Simkl.
- ✅ Cloud sync via `ST_DATA_DIR` pointing to a Dropbox/OneDrive/Syncthing folder (documented in SETUP.md).

### 4C: Notifications and Recommendations
- ✅ Notify when a new episode of a tracked show airs (hourly background task, `plyer`).
- ✅ "Continue watching" prompt — dashboard "Next Up" card from `/api/history/next-to-watch`.

### 4D: Android (Exploratory)
- ❌ Not implemented. No code exists. Deferred until core platform gaps are closed.

### 4E: Plex/Jellyfin/Emby Webhooks
- ✅ Direct webhook integration for Plex, Jellyfin, and Emby (`routes_webhooks.py`).
- ❌ Manual testing against real media servers not yet done — see [HUMAN_TODO.md](../HUMAN_TODO.md#2g-plexjellyfinemby-webhooks).

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| guessit + TMDb fuzzy matching below 80% accuracy | Medium | High (product is unusable) | Phase 0 validation before building infrastructure |
| SMTC doesn't cover enough players | Low | Medium | Player IPC and OCR fallbacks exist |
| Browser extension rejected from Chrome Web Store | Medium | Medium | Sideloading as fallback; justify `<all_urls>` in review |
| TMDb API rate limits or deprecation | Low | High | Aggressive caching; TVDb as backup; local metadata DB |
| OCR accuracy on dark themes / stylized fonts | Medium | Low (OCR is last resort) | Preprocessing pipeline; EasyOCR as Tesseract fallback |
| ActivityWatch breaking changes across versions | Low | Medium | Pin to a known-good AW version; test before upgrading bundle |
| macOS MediaRemote private API changes | Medium | Medium | Swift helper can be updated independently; feature-flag macOS support |

## Dependency Summary

| Dependency | Version Strategy | License |
|------------|-----------------|---------|
| ActivityWatch (binaries) | Pin to specific release | MPL 2.0 |
| guessit | Latest via pip | LGPL 3.0 |
| TMDb API | v3 (stable) | Free tier, attribution required |
| YouTube Data API | v3 | Google API ToS, quota limits |
| Tesseract OCR | System package | Apache 2.0 |
| EasyOCR | Latest via pip | Apache 2.0 |
| winsdk (Python) | Latest via pip | MIT |
| dbus-next (Python) | Latest via pip | MIT |
| Flask/FastAPI | Latest via pip | BSD / MIT |
| SQLite | System (Python built-in) | Public domain |
