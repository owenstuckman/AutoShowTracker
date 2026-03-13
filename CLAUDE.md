# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

AutoShowTracker is an automatic TV show/episode tracker that detects what the user is watching across browsers, desktop media players, streaming services, and pirate sites. It identifies the specific episode using fuzzy matching against TMDb/TVDb and logs a unified watch history. No code exists yet — the repo currently contains design documents only.

## Architecture (Five Layers)

1. **Collection Layer**: ActivityWatch (bundled unmodified as subprocess on port 5600), SMTC/MPRIS OS media session listeners, browser extension (Chrome/Firefox), OCR fallback (per-app region crop)
2. **Parsing Layer**: `guessit` + regex + URL pattern engine — extracts show name, season, episode from raw strings
3. **Identification Layer**: TMDb/TVDb API + YouTube Data API — fuzzy matching to resolve canonical episode IDs with confidence scoring
4. **Storage Layer**: Local SQLite — two databases: `watch_history.db` (user data) and `media_cache.db` (TMDb cache, rebuildable)
5. **Presentation Layer**: Local web UI (Flask/FastAPI backend + React/Svelte frontend)

## Key Design Constraints

- **Python is the primary language** — guessit, TMDb client, OCR, SMTC/MPRIS listeners are all Python-native. Browser extension is JavaScript.
- **No audio fingerprinting** — detection is purely text-based (titles, URLs, metadata, OCR).
- **ActivityWatch is bundled as unmodified subprocess** (not forked, not a custom watcher). This keeps the MPL 2.0 license boundary clean.
- **SMTC/MPRIS is primary desktop detection** — handles background playback and auto-advancing episodes that ActivityWatch's focus-based model misses.
- **OCR is last resort** — only triggered when SMTC/MPRIS + window title both fail. Uses per-app region cropping, not full-window.
- **Windows + Chrome/Firefox first** — Linux/macOS in later phases.

## Implementation Phases

- **Phase 0 (start here)**: Standalone Python script — raw string in, canonical TMDb episode match out. Validates the core identification pipeline. Target >= 85% accuracy on 100+ test inputs. See `04_CONTENT_IDENTIFICATION.md` for pipeline design, `08_IMPLEMENTATION_ROADMAP.md` for deliverables.
- **Phase 1**: Windows desktop MVP — ActivityWatch integration, SMTC listener, browser extension, basic web UI, installer.
- **Phase 2**: Player IPC (VLC/mpv), OCR subsystem, improved identification (TVDb fallback, YouTube API).
- **Phase 3**: Linux (MPRIS/D-Bus) and macOS (MediaRemote) support.
- **Phase 4**: Stats, sync/backup, notifications, Android, Plex/Jellyfin webhooks.

## Document Index

Read `00_CLAUDE_CODE_ENTRY_POINT.md` first for a summary, then documents 01-09 in order for full context. Key references:
- Detection priority chain (six levels): `03_MEDIA_DETECTION.md`
- Identification pipeline (guessit + TMDb fuzzy matching + confidence scoring): `04_CONTENT_IDENTIFICATION.md`
- Full SQLite schema: `07_DATA_MODEL.md`
- Heartbeat-based duration tracking pattern: `07_DATA_MODEL.md` (Duration Tracking section)

## Key Dependencies

| Dependency | Purpose | License |
|------------|---------|---------|
| ActivityWatch | Window/browser event collection | MPL 2.0 |
| guessit | Parse messy media filenames/titles | LGPL 3.0 |
| TMDb API v3 | Canonical show/episode resolution | Free tier, attribution required |
| winsdk | Windows SMTC access via WinRT | MIT |
| dbus-next | Linux MPRIS via D-Bus | MIT |
| Tesseract/EasyOCR | OCR fallback | Apache 2.0 |
