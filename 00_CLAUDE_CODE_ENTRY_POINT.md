# Claude Code Entry Point: Show Tracker

## What This Project Is

An automatic show/episode tracker that detects what the user is watching across browsers, desktop media players, streaming services, and pirate sites, identifies the specific episode using fuzzy matching against TMDb/TVDb, and logs a unified watch history. The user installs one application and tracking happens silently.

## Architecture Summary

ActivityWatch (bundled as unmodified subprocess, MPL 2.0) handles low-level data collection (window titles, browser tabs). Our code adds a media identification layer on top: SMTC/MPRIS OS APIs for background playback detection, a browser extension for deep metadata scraping, OCR as a last-resort fallback, and a parsing+identification pipeline using guessit + TMDb fuzzy matching. Storage is local SQLite. Frontend is a local web UI.

## Key Constraints and Decisions

- **No audio fingerprinting.** Detection is text-based: titles, URLs, metadata, OCR.
- **ActivityWatch integration is Option 1 (subprocess bundle).** Not a custom watcher (Option 2) or fork (Option 3). Keeps license boundary clean.
- **SMTC/MPRIS is the primary desktop detection mechanism** because it handles background playback and auto-advancing episodes that ActivityWatch's focus-based model misses.
- **OCR uses per-app region cropping**, not full-window OCR. Full-window is a last-resort fallback only. Training means "training where to look" (bounding boxes), not training the OCR engine.
- **Python is the primary language** for maximum code sharing across components (guessit, TMDb client, OCR, SMTC/MPRIS listeners are all Python-native).
- **Start with Windows + Chrome/Firefox.** Linux and macOS in Phase 3.

## Document Index

Read these in order for full context. Each is self-contained but references the others.

| # | Document | What It Covers |
|---|----------|---------------|
| 01 | `01_PROJECT_OVERVIEW.md` | Vision, all design decisions with rationale and tradeoffs, target platforms, success criteria |
| 02 | `02_ARCHITECTURE.md` | Five-layer architecture, process model, data flow diagrams, IPC mechanisms, technology stack |
| 03 | `03_MEDIA_DETECTION.md` | Six-level detection priority chain (SMTC → AW → player IPC → file handles → region OCR → full OCR), implementation details per level, timing, deduplication |
| 04 | `04_CONTENT_IDENTIFICATION.md` | guessit integration, URL pattern engine, TMDb/TVDb resolution, fuzzy matching, confidence scoring, YouTube handling, ambiguity resolution |
| 05 | `05_ACTIVITYWATCH_INTEGRATION.md` | Subprocess management, REST API usage, polling strategy, port conflict handling, browser extension coordination, mock client for testing |
| 06 | `06_BROWSER_EXTENSION.md` | Content script metadata extraction (schema.org, Open Graph, DOM inspection), playback monitoring with heartbeats, background service worker, manifest config, platform-specific notes |
| 07 | `07_DATA_MODEL.md` | Full SQLite schema (shows, episodes, watch_events, youtube_watches, aliases, unresolved events, caches), data flow from detection to storage, heartbeat duration tracking, frontend query patterns |
| 08 | `08_IMPLEMENTATION_ROADMAP.md` | Phase 0 (validation) through Phase 4 (polish), weekly milestones, risk register, dependency summary |
| 09 | `09_LICENSING_AND_DISTRIBUTION.md` | MPL 2.0 obligations, dependency license matrix, package structure, installer strategy per OS, privacy policy requirements |

## Where to Start Coding

Per the roadmap, begin with **Phase 0**: a standalone Python script that takes a raw string and outputs a canonical TMDb episode match. This validates the core identification pipeline before building infrastructure. See `04_CONTENT_IDENTIFICATION.md` for the pipeline design and `08_IMPLEMENTATION_ROADMAP.md` Phase 0 for specific deliverables.

After Phase 0 passes validation (>= 85% accuracy on test dataset), proceed to Phase 1 milestones in order: ActivityWatch integration → browser extension → web UI → packaging.
