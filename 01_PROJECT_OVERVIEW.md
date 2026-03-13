# Project Overview: Show Tracker

## Vision

A cross-platform media tracking application that automatically detects what a user is watching — across browsers, desktop media players, streaming services, and pirated content — normalizes it against a canonical media database, and logs episode-level watch history. The user launches one application and all tracking begins silently in the background.

## Core Problem

No existing tracker reliably handles *all* viewing sources. Dedicated trackers (Trakt, Simkl) require manual input or only integrate with specific apps. ActivityWatch tracks *time* but doesn't understand *media*. This project bridges the gap: automatic detection of what's playing, identification of the specific episode regardless of source, and unified watch history.

## Key Design Decisions (Rationale Included)

### 1. ActivityWatch as the Data Collection Layer (Option 1: Subprocess Bundle)

**Decision:** Bundle ActivityWatch binaries as a subprocess rather than writing custom OS-level watchers or forking ActivityWatch's server.

**Reasoning:**
- ActivityWatch already solves window title monitoring, browser tab tracking, and cross-platform support (Windows/macOS/Linux/Android).
- Writing custom watchers for each OS is a massive effort with diminishing returns — ActivityWatch has years of edge-case handling baked in.
- Bundling as a subprocess keeps the MPL 2.0 license boundary clean: no modification of their source files, so our code can be any license.
- The REST API on `localhost:5600` provides a stable integration surface.

**Tradeoffs:**
- Adds ~50-100MB to installer size (ActivityWatch binaries + dependencies).
- Must handle port conflicts if the user already runs ActivityWatch independently.
- We depend on their release cycle for OS-level bug fixes.

**Rejected Alternatives:**
- Option 2 (custom watcher plugin): More idiomatic but ties us into their ecosystem. Harder to package as a standalone product.
- Option 3 (fork aw-server-rust): Tightest integration but inherits MPL 2.0 on modified files and couples us to their internal APIs.

### 2. SMTC/MPRIS as Primary Desktop Detection

**Decision:** Use OS-level "Now Playing" APIs (Windows SMTC, Linux MPRIS, macOS MediaRemote) as the primary mechanism for detecting media playback in desktop apps.

**Reasoning:**
- These APIs report what's currently playing regardless of window focus, solving the "background episode auto-advance" problem that ActivityWatch's focus-based model misses.
- Most major media players (VLC, mpv, Plex, Chromium-based apps) report to these APIs automatically.
- Event-driven rather than polling-based, so resource usage is minimal.
- No per-player integration work — one API covers many players.

**Tradeoffs:**
- Not all players report to SMTC/MPRIS (some obscure or outdated players won't).
- macOS MediaRemote is a private framework — less stable API surface.
- The metadata reported varies by player: some report full titles, some report filenames, some report minimal info.

### 3. OCR as Fallback (Not Primary)

**Decision:** Use OCR only when SMTC/MPRIS and ActivityWatch window titles both fail to identify the content. Use region-of-interest cropping per app rather than full-window OCR.

**Reasoning:**
- Full-window OCR produces noisy results: subtitles, UI chrome, "up next" suggestions, timestamps all get captured and create ambiguity.
- Region-cropped OCR on the title bar or transport controls area gives clean, parseable text.
- OCR is resource-intensive — running it constantly is wasteful when SMTC/MPRIS covers 80%+ of cases.
- Per-app region profiles are simple to define (one-time bounding box as percentage of window dimensions) and scale with window resizing.

**Tradeoffs:**
- Requires predefined profiles for each app, or a user calibration step for unknown apps.
- OCR accuracy depends on font rendering, DPI, and theme (light vs dark mode affects contrast).
- Screenshot capture of background windows varies by OS and compositor.

### 4. No Audio Fingerprinting

**Decision:** Explicitly exclude audio-based identification from the architecture.

**Reasoning:**
- Requires capturing system audio output (virtual audio devices), which is invasive and platform-specific.
- Needs a reference fingerprint database, which is a massive undertaking to build and maintain.
- Text-based identification (titles, filenames, metadata, OCR) covers the vast majority of cases.
- Privacy implications of audio capture are significant.

### 5. Browser Extension for Web-Based Viewing

**Decision:** Build a browser extension (Chrome/Firefox) that scrapes page metadata, URL patterns, and DOM content to identify what's being watched in a browser.

**Reasoning:**
- Browsers are the most common viewing platform for streaming services and pirated content.
- Structured metadata (Open Graph tags, schema.org VideoObject, YouTube API) is available on legitimate sites.
- URL pattern matching handles most cases without DOM parsing.
- ActivityWatch's browser extension only provides tab title and URL — we need deeper scraping for episode identification.

### 6. TMDb/TVDb + guessit for Content Identification

**Decision:** Use TMDb (The Movie Database) and TVDb as canonical media databases, with the `guessit` Python library for parsing messy title strings.

**Reasoning:**
- TMDb has a free API tier, episode-level data, and broad coverage.
- `guessit` is battle-tested for parsing media filenames from torrent/piracy naming conventions (handles patterns like `S01E03`, `1x03`, `Episode 3`, etc.).
- Fuzzy string matching (Levenshtein distance) handles minor title variations.
- YouTube content uses the YouTube Data API directly (no need for fuzzy matching).

## Target Platforms

- **Phase 1:** Windows + Chrome/Firefox (largest user base, SMTC available)
- **Phase 2:** Linux (MPRIS), macOS (MediaRemote)
- **Phase 3:** Android (ActivityWatch Android app exists, limited detection possible)
- **Phase 4:** iOS (manual entry / share sheet only due to sandboxing)

## Success Criteria

The system should correctly identify and log an episode in these scenarios without manual user input:
1. User watches Netflix in Chrome.
2. User watches a YouTube video/series.
3. User watches a pirated episode in Chrome from an arbitrary streaming site.
4. User watches a local file in VLC that auto-advances to the next episode while VLC is in the background.
5. User watches via Plex desktop app.
