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
