# TODO

For completed features, see [FEATURES.md](FEATURES.md).

## Missing Functionality

### Movie API Routes — DONE

- [x] Created `src/show_tracker/api/routes_movies.py`
- [x] Added `MovieWatchOut` and `MovieStats` Pydantic schemas
- [x] Registered movie router in `app.py`
- [x] Updated web UI `renderMovies()` to use dedicated `/api/movies/*` endpoints with stats cards

### Trakt Sync — DONE

- [x] Created `src/show_tracker/api/routes_sync.py` (auth, status, sync, disconnect)
- [x] Registered sync router in `app.py`
- [x] Added `trakt_client_id` and `trakt_client_secret` to Settings config
- [x] Added Trakt section to web UI Settings page (connect, import, disconnect flow)
- [x] Wired automatic scrobble on watch completion via `trakt_scrobble_enabled` setting (opt-in, default false); `DetectionService.register_finalize_callback()` + scrobble hook in `app.py` lifespan

### Notifications — DONE

- [x] Added periodic new-episode check to FastAPI lifespan (hourly async background task)
- [x] Task cancels cleanly on shutdown
- [x] Notification preference via `notifications_enabled` user setting (checked by background task)
- [x] Added notification toggle to web UI Settings page
- [x] "Continue watching" prompt on app open (design doc 4C) — implemented as "Next Up" card on the dashboard, populated from `/api/history/next-to-watch`

### Alembic Migrations — DONE

- [x] Wrote initial migration: `alembic/versions/001_initial_schema.py`
- [x] Tested `alembic upgrade head` on fresh DB
- [x] Tested `alembic stamp head` on existing DB
- [x] Documented migration workflow in SETUP.md

### Windows Installer — DONE

- [x] Created `scripts/inno_setup.iss` — Inno Setup script with Start Menu shortcuts, optional desktop icon, optional startup entry, database init on install, user data preservation on uninstall

### macOS Support — DONE (functional stubs; untested on real hardware)

- [x] Added `pyobjc-framework-MediaPlayer>=9.0` to `[macos]` optional dependency group in `pyproject.toml`
- [x] Implemented `MacOSMediaListener` — polls `MPNowPlayingInfoCenter.defaultCenter()` every 2s, emits `MediaSessionEvent` on title/playback change, wired into `get_media_listener()` factory
- [x] macOS screenshot capture — `_capture_macos()` uses Quartz `CGWindowListCreateImage` with `screencapture` CLI fallback (already in `ocr/screenshot.py`)
- [ ] Test on macOS: Safari, Music.app, VLC, IINA (requires hardware)

### Cloud Sync / Backup — DONE

- [x] Documented backup strategy in `docs/SETUP.md` — manual `cp`, cron daily backup, and `ST_DATA_DIR` cloud folder approach (Dropbox/OneDrive/Syncthing)

### Simkl Import — DONE (stub implementation)

- [x] Created `src/show_tracker/sync/simkl.py` — OAuth2 PIN device flow, `get_all_items()`, `import_history()` that maps Simkl episodes to WatchRepository records

### Android Support — Not Implemented (Future/Exploratory)

- [ ] Future scope — not a current gap

---

## Missing Test Coverage

### Detection — DONE (78 tests)

- [x] DetectionService deduplication, confidence scoring, routing, callbacks, AW event conversion, lifecycle, SMTC/MPRIS callbacks, EventPoller, bucket discovery, browser events, ActiveWatch
- [x] Fixed heartbeat emission test (capture `old_heartbeat` before `touch()` call)

### Parsing — DONE (81 tests)

- [x] Date-based episode parsing (e.g., `show.2024.03.15`)
- [x] Absolute episode numbering (e.g., `naruto.150.720p`)
- [x] URL pattern completeness for all platforms
- [x] Platform suffix stripping, noise word removal, whitespace normalization

### Identification — DONE

- [x] TMDb fuzzy matching threshold (FUZZY_THRESHOLD=0.80 constant verified)
- [x] Alias table lookup (INITIAL_ALIASES seed data, all well-known aliases verified)
- [x] Cache TTL (6-month max per TMDb ToS, failed lookup 24h)
- [x] Resolver dataclasses (IdentificationResult, MovieIdentificationResult)
- [x] Fuzzy matching logic (rapidfuzz.fuzz.ratio against threshold)
- [x] Movie identification pipeline

### Storage — DONE

- [x] Dual database isolation (separate files, cache rebuildable)
- [x] WatchRepository CRUD for all models
- [x] Unresolved event lifecycle
- [x] Watch event completion (completed flag at >= 90%)
- [x] Cache TTL (is_cache_fresh, TMDb max 6 months)
- [x] FailedLookup TTL (24h)

### API Endpoints — DONE

- [x] `GET /api/health`
- [x] `POST /api/media-event` — all event types
- [x] `GET /api/currently-watching`
- [x] `GET /api/history/recent`, `/shows`, `/shows/{id}`, `/shows/{id}/progress`, `/next-to-watch`, `/stats`
- [x] `GET /api/unresolved`, `POST .../resolve`, `POST .../dismiss`, `POST .../search`
- [x] `GET /api/settings`, `PUT /api/settings/{key}`
- [x] `POST /api/aliases`, `GET /api/aliases/{show_id}`, `DELETE /api/aliases/{alias_id}`
- [x] `GET /api/export/history.json`
- [x] `GET /api/stats/daily`, `/weekly`
- [x] Webhook routes (structural tests)

### Confidence Scoring — DONE

- [x] Base confidence by source (all source types verified)
- [x] Bonus scoring (URL match +0.15, season+episode +0.10, fuzzy>=0.95 +0.08)
- [x] Penalty scoring (OCR -0.10, no season -0.10, abbreviated title -0.05)
- [x] Confidence capped at 1.0
- [x] Confidence routing thresholds

### OCR Pipeline — DONE

- [x] Region cropping from JSON profiles (load_profiles, find_profile, crop_regions)
- [x] Preprocessing (grayscale, threshold, upscale, invert)
- [x] Full-window fallback
- [x] Engine selection (Tesseract primary, EasyOCR fallback, graceful degradation)

### Player IPC — DONE

- [x] VLC web interface — mock HTTP, metadata extraction
- [x] mpv JSON IPC — mock socket/pipe, response parsing

### CLI — DONE

- [x] `show-tracker identify` with `--source` flag
- [x] `show-tracker test-pipeline`
- [x] `show-tracker init-db`
- [x] `show-tracker setup` wizard flow

### Configuration — DONE

- [x] Config priority (programmatic overrides > env vars > JSON file defaults > pydantic defaults)
- [x] All ST_ env vars (programmatic override verified)
- [x] has_tmdb_key(), data_dir paths, ensure_directories()

### Sync & Notifications — DONE

- [x] Trakt.tv sync router structure (all 4 endpoints, HTTP methods, tags)
- [x] send_notification() (plyer success, plyer missing, plyer exception)
- [x] check_new_episodes() (today/tomorrow filtering, skip no tmdb_id, skip no air_date)

### Remaining Low-Priority Detection Tests — DONE

- [x] SMTC listener async integration — mock `winsdk`, verify session attachment/detachment, event emission, start/stop, callbacks (`test_platform_listeners.py`)
- [x] MPRIS listener async integration — mock `dbus-next`, verify D-Bus connection, player discovery, signal dispatch (`test_platform_listeners.py`)
- [x] ActivityWatch subprocess management — process mocking, launch, shutdown, health check, crash retry (`test_platform_listeners.py`)

---

## Missing Features

These items were specified in the original roadmap but were never implemented.

### OCR User Calibration UI — Not Implemented

Roadmap Milestone 2B item 6 called for a UI that lets users draw a region-of-interest bounding box for player apps not covered by `profiles/default_profiles.json`. Currently the only way to add a new profile is to hand-edit the JSON file with pixel coordinates.

- [ ] Settings page "OCR Profiles" section — list existing profiles, allow add/edit/delete
- [ ] Visual region picker: screenshot the target window and draw a bounding box via the web UI
- [ ] Save custom profiles to a user-owned `profiles/user_profiles.json` (separate from shipped `default_profiles.json` so upgrades don't clobber user data)
- [ ] `GET /api/ocr/profiles` and `PUT /api/ocr/profiles/{app_name}` API routes

### Wayland OCR Capture — Not Implemented

`ocr/screenshot.py` only implements X11 window capture on Linux (via `xwd`/`scrot`). Wayland does not expose per-window capture to arbitrary processes without a portal. This blocks OCR fallback for users on GNOME/KDE Wayland sessions.

- [ ] Assess `xdg-desktop-portal` screenshot portal as a Wayland path
- [ ] Assess `grim` + `slurp` (wlroots compositors) as an alternative
- [ ] If neither is feasible, gate OCR as X11-only and log a clear warning when `WAYLAND_DISPLAY` is set

### "Time to Finish" Estimates — Not Implemented

Phase 4A listed this as a stats feature. All other 4A analytics are done; this one was skipped.

- [ ] `GET /api/history/shows/{show_id}/time-to-finish` — sum of remaining episode runtimes (from TMDb) for unwatched episodes
- [ ] Surface on the show detail page alongside the season/episode grid

### Android Support — Future / Exploratory

No code exists. Defer until the above gaps are addressed.

---

## Manual Testing

- [ ] Test SMTC listener (Windows) — see [HUMAN_TODO.md](HUMAN_TODO.md) 2a
- [ ] Test MPRIS listener (Linux) — see [HUMAN_TODO.md](HUMAN_TODO.md) 2b
- [ ] Test macOS listener (macOS hardware required) — see [HUMAN_TODO.md](HUMAN_TODO.md) 2h
- [ ] Test browser extension (Chrome + Firefox)
- [ ] Test VLC web interface
- [ ] Test mpv IPC socket
- [ ] Test Plex/Jellyfin/Emby webhooks

---

## Distribution

- [ ] **PyPI publication** — `git tag v0.1.0 && git push --tags` or `python -m build && twine upload dist/*`
- [ ] **Chrome Web Store** — developer account ($5), upload ZIP — see [DISTRIBUTION.md](DISTRIBUTION.md)
- [ ] **Firefox Add-ons** — upload ZIP at https://addons.mozilla.org/developers/

---

## Documentation Gaps — DONE

- [x] **TMDb API attribution** — added to web UI sidebar footer (data provided by TMDb & YouTube)
- [x] **YouTube API attribution** — added alongside TMDb attribution in sidebar footer
- [x] **TMDb cache max 6 months** — `get_cached_show` and `get_cached_episode` now default to `TMDB_MAX_CACHE_HOURS = 24*30*6` (6 months); `TMDB_MAX_CACHE_HOURS` constant documented in `CacheRepository`
- [x] **YouTube API quota tracking** — `YouTubeClient` now tracks requests via class-level `_quota_used` counter; warns at 80%, errors at 100% of 10,000 unit/day free tier
- [x] **SETUP.md migration section** — documented `alembic upgrade head` workflow

---

## Post-Setup Tuning

- [ ] Tune confidence thresholds after 3-5 days of use
- [ ] Seed show aliases for your library
- [ ] Set up Trakt.tv sync
