# Media Detection Pipeline

## Detection Priority Chain

Detection sources are ordered by reliability and resource cost. The system tries each in order and stops at the first successful identification. Each layer is a progressively more invasive fallback.

```
Priority 1: SMTC / MPRIS / MediaRemote (OS Now-Playing APIs)
    ↓ if unavailable or metadata insufficient
Priority 2: ActivityWatch window title + browser tab data
    ↓ if window title doesn't resolve to a known show
Priority 3: Direct player IPC (VLC web interface, mpv JSON IPC, Plex webhooks)
    ↓ if no player integration available
Priority 4: Open file handle inspection (what file does the media player process have open)
    ↓ if not a local file (streaming) or file name is opaque
Priority 5: Region-cropped OCR using known app profile
    ↓ if no app profile exists
Priority 6: Full-window OCR with spatial filtering heuristics
```

For most users, priorities 1-2 cover the vast majority of cases. Priorities 3-4 handle local media edge cases. Priorities 5-6 are safety nets for truly opaque apps.

## Priority 1: SMTC / MPRIS / MediaRemote

### What These APIs Provide

These are OS-level media session APIs. When a media player reports "now playing" info (the same data that appears on keyboard media overlays, lock screens, Bluetooth device displays), these APIs expose it programmatically.

### Windows: System Media Transport Controls (SMTC)

**API:** `Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager` via WinRT.

**Access from Python:** Use the `winsdk` package (or `winrt-Windows.Media.Control` for typed bindings).

```python
# Conceptual flow (not production code)
import asyncio
from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as SessionManager
)

async def get_now_playing():
    manager = await SessionManager.request_async()
    session = manager.get_current_session()
    if session:
        info = await session.try_get_media_properties_async()
        return {
            "title": info.title,           # e.g., "Law and Order SVU - S03E07"
            "artist": info.artist,          # Often the show name or channel
            "album_title": info.album_title,  # Sometimes season info
            "playback_status": session.get_playback_info().playback_status,
            "source_app": session.source_app_user_model_id  # Which app is playing
        }
```

**Event-driven approach:** Register a callback on `session.media_properties_changed` to get notified when the track/episode changes rather than polling. This is the preferred approach — it catches background episode transitions immediately.

**Coverage:** VLC, mpv (with SMTC plugin), Chromium-based browsers (Netflix, YouTube in Edge/Chrome), Plex, Windows Media Player, Spotify, most modern media apps. Some older or niche players may not report.

### Linux: MPRIS (Media Player Remote Interfacing Specification)

**API:** D-Bus interface `org.mpris.MediaPlayer2.Player`. Most Linux media players implement this.

**Access from Python:** Use `dbus-next` (async) or `pydbus`.

```python
# Conceptual flow
from dbus_next.aio import MessageBus

async def get_now_playing():
    bus = await MessageBus().connect()
    # List all MPRIS-capable players
    # Names follow pattern: org.mpris.MediaPlayer2.<player_name>
    introspection = await bus.introspect("org.mpris.MediaPlayer2.vlc",
                                          "/org/mpris/MediaPlayer2")
    player = bus.get_proxy_object("org.mpris.MediaPlayer2.vlc",
                                  "/org/mpris/MediaPlayer2",
                                  introspection)
    properties = player.get_interface("org.freedesktop.DBus.Properties")
    metadata = await properties.call_get("org.mpris.MediaPlayer2.Player", "Metadata")
    # metadata contains: xesam:title, xesam:artist, xesam:album, mpris:length, etc.
```

**Event-driven approach:** Subscribe to `PropertiesChanged` signal on the D-Bus interface to get real-time updates when tracks change.

**Coverage:** VLC, mpv, Celluloid, Totem, Clementine, Chromium (via browser MPRIS integration), Firefox (limited), Plex HTPC, and most GTK/Qt media players.

### macOS: MediaRemote (Private Framework)

**API:** `MRMediaRemoteGetNowPlayingInfo` from the MediaRemote private framework.

**Access from Python:** Use `pyobjc` to call the framework, or write a small Swift helper that outputs JSON.

**Coverage:** Safari, Music.app, TV.app, VLC, IINA, Plex, QuickTime, and Chromium-based browsers. Coverage is generally good because macOS's Now Playing widget relies on this.

**Caveat:** Private framework means Apple can change it without notice. Monitor for breakage on macOS updates. Consider a Swift helper binary for stability — it can be a 50-line program that outputs now-playing info to stdout or a socket.

### Handling SMTC/MPRIS Metadata Quality

The metadata quality varies wildly by player:

| Player | Title field typically contains |
|--------|-------------------------------|
| VLC (local file) | Filename: `law.and.order.svu.s03e07.720p.mkv` |
| VLC (with metadata tags) | Embedded title: `Law & Order: SVU - Sacrifice` |
| mpv | Filename or stream title |
| Plex | Clean title: `Law & Order: SVU - S3:E7 - Sacrifice` |
| Chrome (YouTube) | Video title: `Law & Order SVU Season 3 Episode 7 Full` |
| Chrome (Netflix) | `Netflix - Law & Order: SVU` (limited episode info) |
| Spotify (podcasts) | Episode title + show name |

The parsing layer must handle all of these formats. The key insight: even messy filenames like `law.and.order.svu.s03e07.720p.mkv` are reliably parseable by `guessit`.

## Priority 2: ActivityWatch Data

### Window Watcher Events

Poll `GET http://localhost:5600/api/0/buckets/aw-watcher-window_<hostname>/events?limit=1` to get the most recent active window.

Response contains:
```json
{
    "timestamp": "2025-01-15T20:30:00.000Z",
    "duration": 45.0,
    "data": {
        "app": "vlc",
        "title": "law.and.order.svu.s03e07.720p.mkv - VLC media player"
    }
}
```

**Limitation:** Only reports the *focused* window. If VLC is playing in the background while the user browses, you get the browser info, not VLC. This is why SMTC/MPRIS is priority 1.

### Web Watcher Events

Poll `GET http://localhost:5600/api/0/buckets/aw-watcher-web-<browser>_<hostname>/events?limit=1`.

Response contains:
```json
{
    "timestamp": "2025-01-15T20:30:00.000Z",
    "duration": 30.0,
    "data": {
        "url": "https://www.netflix.com/watch/80001234",
        "title": "Law & Order: Special Victims Unit | Netflix",
        "audible": true,
        "incognito": false
    }
}
```

The URL alone is often enough for legitimate streaming sites (Netflix, YouTube, Crunchyroll all encode content IDs in URLs).

## Priority 3: Direct Player IPC

### VLC Web Interface

VLC has a built-in HTTP interface (must be enabled by user in Preferences > All > Main Interfaces > Web).

```
GET http://localhost:8080/requests/status.json
Authorization: Basic (password configured by user)
```

Returns currently playing file, title, duration, position, playlist info. Very reliable when enabled.

### mpv JSON IPC

mpv supports a JSON-based IPC protocol over a Unix socket or named pipe.

```bash
# Start mpv with IPC enabled
mpv --input-ipc-server=/tmp/mpv-socket video.mkv

# Query current file
echo '{"command": ["get_property", "media-title"]}' | socat - /tmp/mpv-socket
```

### Plex Webhooks

Plex server can send webhooks on media.play, media.pause, media.stop, media.scrobble events. These contain full metadata including show, season, episode, and TVDB/TMDB IDs. Requires Plex Pass.

## Priority 4: Open File Handle Inspection

For locally stored media files, check which file the media player process has open.

- **Linux:** Read `/proc/<pid>/fd/` symlinks. Filter for video file extensions.
- **Windows:** Use `psutil.Process(pid).open_files()` or `handle.exe` from Sysinternals.
- **macOS:** Use `lsof -p <pid>` and filter.

This is player-agnostic — works with any player as long as the file is local. Does not work for streaming content.

Get the media player PID from ActivityWatch's window watcher data (it includes the app name, which you can resolve to a PID via `psutil`).

## Priority 5: Region-Cropped OCR

### App Profile Format

Store profiles as JSON. Each profile maps an app identifier to a bounding box (as percentages of window dimensions) where the title is rendered.

```json
{
    "profiles": {
        "vlc": {
            "match_app_names": ["vlc", "vlc media player"],
            "regions": [
                {
                    "name": "title_bar",
                    "description": "Window title bar area",
                    "x_pct": 0.0,
                    "y_pct": 0.0,
                    "w_pct": 1.0,
                    "h_pct": 0.05
                },
                {
                    "name": "transport_controls",
                    "description": "Bottom control strip with filename",
                    "x_pct": 0.05,
                    "y_pct": 0.92,
                    "w_pct": 0.90,
                    "h_pct": 0.08
                }
            ]
        },
        "plex": {
            "match_app_names": ["plex", "plex htpc"],
            "regions": [
                {
                    "name": "now_playing_title",
                    "x_pct": 0.02,
                    "y_pct": 0.02,
                    "w_pct": 0.50,
                    "h_pct": 0.08
                }
            ]
        }
    }
}
```

### Screenshot Capture (Background-Safe)

Capture the player's window without bringing it to the foreground:

- **Windows:** `PrintWindow` via Win32 API (ctypes) — captures by window handle (HWND).
- **macOS:** `CGWindowListCreateImage` with the specific window ID.
- **Linux (X11):** `xdotool` to get window ID + `import` (ImageMagick) to capture by ID. Under Wayland, this is compositor-dependent and may require user permissions.

### OCR Engine Recommendations

| Engine | Speed | Accuracy on Screen Text | Installation Complexity |
|--------|-------|------------------------|------------------------|
| Tesseract (tesserocr) | Fast | Good for clean text, struggles with stylized fonts | Low (system package) |
| EasyOCR | Moderate | Better on varied fonts and dark backgrounds | Medium (Python package, downloads models) |
| PaddleOCR | Moderate | Best overall accuracy on screen captures | Medium-High (larger dependency) |

**Recommendation:** Start with Tesseract for speed. Fall back to EasyOCR if Tesseract returns low-confidence results. Both return bounding box data for each detected text region.

### Preprocessing for Better OCR

Before running OCR on the cropped region:
1. Convert to grayscale.
2. Apply adaptive thresholding (handles both light and dark UI themes).
3. Upscale to at least 300 DPI equivalent (OCR engines work better on larger text).
4. Optionally invert if the text is light-on-dark (common in media player UIs).

## Priority 6: Full-Window OCR with Spatial Filtering

When no app profile exists and the user hasn't calibrated a region:

1. Capture the full window.
2. Run OCR with bounding box output (both Tesseract and EasyOCR support this).
3. Filter text blocks by position:
   - Keep text in the top 15% of window height (title bar region).
   - Keep text in the bottom 15% of window height (transport controls).
   - Discard text from the center (video content, subtitles).
4. Filter by estimated font size: discard very small text (UI labels like "Settings") and very large text (likely subtitles rendered over video).
5. Score remaining text blocks by how well they match media title patterns (contains season/episode notation, matches a known show name, etc.).
6. Pass the highest-scoring text block to the parsing layer.

This is the least reliable method but provides a catch-all for unknown apps.

## Detection Loop Timing

The detection loop runs in the media identification service with these intervals:

| Source | Check Interval | Rationale |
|--------|---------------|-----------|
| SMTC/MPRIS | Event-driven (0 latency) | OS pushes events on change; no polling needed |
| ActivityWatch window events | Every 10 seconds | AW watcher already polls every 5s; 10s is sufficient |
| ActivityWatch web events | Every 10 seconds | Same as above |
| Player IPC (VLC/mpv) | Every 30 seconds | Only checked if player is detected running |
| File handle check | Every 60 seconds | Only checked if player is active and title unresolved |
| OCR | On-demand only | Triggered when all above fail for an active media player |

## Deduplication Logic

Multiple detection sources may identify the same episode simultaneously (e.g., SMTC reports it AND ActivityWatch window title matches). The service deduplicates by:

1. Maintaining a "currently watching" state per canonical episode ID.
2. If a new detection matches the current episode, update the duration (heartbeat pattern).
3. If a new detection matches a *different* episode, finalize the previous one and start tracking the new one.
4. Grace period: if all signals disappear for less than 2 minutes (e.g., user paused), keep the episode active. After 2 minutes of no signal, mark the episode as stopped.
