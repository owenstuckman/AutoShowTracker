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
- [ ] Wire automatic scrobble on watch completion (optional per setting — low priority)

### Notifications — DONE

- [x] Added periodic new-episode check to FastAPI lifespan (hourly async background task)
- [x] Task cancels cleanly on shutdown
- [x] Notification preference via `notifications_enabled` user setting (checked by background task)
- [x] Added notification toggle to web UI Settings page
- [ ] "Continue watching" prompt on app open (design doc 4C — low priority)

### Alembic Migrations — DONE

- [x] Wrote initial migration: `alembic/versions/001_initial_schema.py`
- [x] Tested `alembic upgrade head` on fresh DB
- [x] Tested `alembic stamp head` on existing DB
- [x] Documented migration workflow in SETUP.md

### Windows Installer — DONE

- [x] Created `scripts/inno_setup.iss` — Inno Setup script with Start Menu shortcuts, optional desktop icon, optional startup entry, database init on install, user data preservation on uninstall

### macOS Support — Stub Only (Low Priority)

- [ ] Implement `MacOSMediaListener` using pyobjc or Swift helper binary
- [ ] Add `pyobjc-framework-MediaPlayer` to `[macos]` optional dependency group
- [ ] Add macOS screenshot capture for OCR
- [ ] Test on macOS: Safari, Music.app, VLC, IINA

### Cloud Sync / Backup — Not Implemented (Low Priority)

- [ ] Document recommended backup strategy (copy `watch_history.db` to cloud folder)
- [ ] Consider: Syncthing/Dropbox-compatible data directory setting (`ST_DATA_DIR`)

### Simkl Import — Not Implemented (Low Priority)

- [ ] Consider adding Simkl import support

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

### Remaining Low-Priority Detection Tests

- [ ] SMTC listener async integration — mock `winsdk`, verify session attachment/detachment
- [ ] MPRIS listener async integration — mock `dbus-next`, verify D-Bus connection
- [ ] ActivityWatch subprocess management — process mocking

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
