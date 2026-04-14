# Human TODO

Tasks that require manual testing, external accounts, or hardware access.

---

## 1. Environment Setup

### Automatic Setup (Recommended)

The auto-setup script detects your OS, creates a virtual environment, installs the right dependencies, configures `.env`, and initializes databases — all in one command:

```bash
python scripts/auto_setup.py
```

Options:
- `--skip-venv` — Use the current Python instead of creating a `.venv`
- `--extras ocr notifications` — Add optional dependency groups
- `--no-interactive` — Skip the TMDb API key prompt (set it later in `.env`)

The script auto-detects WSL and adjusts accordingly (see [WSL notes](#wsl-notes) below).

After it completes, activate and run:
```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows cmd
.venv\Scripts\activate.bat

# Linux / macOS / WSL
source .venv/bin/activate

# Start tracking
show-tracker run
```

### WSL Notes

AutoShowTracker runs under WSL2 but with some limitations:

- **No SMTC or MPRIS**: WSL cannot access Windows System Media Transport Controls or Linux D-Bus. The auto-setup script detects WSL and skips these.
- **Primary detection**: Use the **browser extension** as your main detection source. Load it in your Windows browser and point it at the WSL service.
- **Dashboard access from Windows**: Open `http://localhost:7600` in your Windows browser. WSL2 automatically forwards localhost ports. If that doesn't work, find your WSL IP with `hostname -I` and use `http://<WSL_IP>:7600`.
- **VLC/mpv IPC**: Works only if the player runs inside WSL (not the Windows-side install). Most users will rely on the browser extension instead.
- **ActivityWatch**: If you run ActivityWatch on Windows, the WSL service can poll it — set `ST_ACTIVITYWATCH_PORT=5600` in `.env` and ensure the AW server is reachable from WSL.
- **OCR**: Not functional under WSL (no X11/Wayland display server by default).
- **File paths**: The project can live on the Windows filesystem (`/mnt/c/...`) or the WSL filesystem (`~/...`). Performance is better on the WSL filesystem.

### Manual Setup (Step-by-Step)

If you prefer to set up manually or the auto-setup doesn't cover your environment:

#### 1a. Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| Python | 3.11+ | `python --version` |
| pip | 21+ | `pip --version` |
| Git | any | `git --version` |
| SQLite | 3.35+ | Ships with Python 3.11 |

#### 1b. Clone and Create Virtual Environment

```bash
git clone https://github.com/owenstuckman/AutoShowTracker.git
cd AutoShowTracker
python -m venv .venv
```

Activate:
```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows cmd
.venv\Scripts\activate.bat

# Linux / macOS
source .venv/bin/activate
```

#### 1c. Install Dependencies

Pick the extras for your platform:

```bash
# Windows (core + SMTC + dev tools)
pip install -e ".[dev,windows]"

# Linux (core + MPRIS + dev tools)
pip install -e ".[dev,linux]"

# WSL (core + dev tools — SMTC/MPRIS not available)
pip install -e ".[dev]"

# Add OCR support
pip install -e ".[dev,windows,ocr]"      # Windows + OCR
pip install -e ".[dev,linux,ocr]"        # Linux + OCR

# Add desktop notifications
pip install -e ".[dev,windows,notifications]"

# Everything
pip install -e ".[dev,windows,ocr,notifications]"
```

Verify:
```bash
show-tracker --version
# Expected: show-tracker, version 0.1.0
```

#### 1d. Get a TMDb API Key

1. Go to https://www.themoviedb.org/signup — create a free account
2. Verify your email (check spam)
3. Go to https://www.themoviedb.org/settings/api
4. Click **Create** > **Developer** > accept Terms
5. Fill in: name "AutoShowTracker", URL "http://localhost", summary "Personal media tracking", type "Personal"
6. Copy the **API Key (v3 auth)** — this is a 32-character hex string

#### 1e. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and paste your TMDb key:
```
TMDB_API_KEY=your_32_character_key_here
```

Optional keys:
```
YOUTUBE_API_KEY=           # YouTube series/playlist detection
ST_DATA_DIR=~/.show-tracker  # Override data directory
ST_MEDIA_SERVICE_PORT=7600   # Override API port
```

#### 1f. Initialize Databases

Option A — Interactive wizard (prompts for TMDb key if not set):
```bash
show-tracker setup
```

Option B — Direct initialization:
```bash
show-tracker init-db
```

Verify files were created:
- `~/.show-tracker/watch_history.db`
- `~/.show-tracker/media_cache.db`

#### 1g. Validate the Pipeline

```bash
# Clean filename
show-tracker identify "Breaking Bad S05E14"
# Expected: show_name "Breaking Bad", season 5, episode 14, tmdb_show_id 1396

# Messy filename
show-tracker identify "law.and.order.svu.s03e07.720p.bluray.mkv"
# Expected: "Law & Order: Special Victims Unit", S03E07

# Browser title
show-tracker identify "Stranger Things | Netflix" --source browser_title
# Expected: "Stranger Things" with a TMDb ID

# Should fail gracefully
show-tracker identify "random gibberish text"
# Expected: "No match found."
```

#### 1h. Start the Service and Verify

```bash
show-tracker run
```

Check output shows:
- `TMDb key set   : True`
- `HTTP API       : http://127.0.0.1:7600`

Open http://127.0.0.1:7600 — dashboard should load.

Test API:
```bash
curl http://127.0.0.1:7600/api/health
# Expected: {"status":"ok","version":"0.1.0"}
```

Visit http://127.0.0.1:7600/docs for Swagger UI.

Press `Ctrl+C` to stop.

---

## 2. Detection Source Testing

> The `DetectionService` starts automatically with `show-tracker run`. It activates SMTC (Windows), MPRIS (Linux), and ActivityWatch polling alongside the browser extension and webhook endpoints.

Test each source that's relevant to your setup. Start `show-tracker run` first, then open a second terminal to watch logs:

```bash
# Windows PowerShell
Get-Content -Wait "$env:USERPROFILE\.show-tracker\logs\show_tracker.log"

# Linux
tail -f ~/.show-tracker/logs/show_tracker.log
```

### 2a. SMTC Listener (Windows)

**What it does**: Captures "Now Playing" metadata from any app that reports to Windows System Media Transport Controls — the highest-priority desktop detection source. Starts automatically with `show-tracker run` on Windows.

#### Verification

1. Verify `winsdk` is installed:
   ```powershell
   pip show winsdk
   # Should show: Name: winsdk, Version: 1.0.0b10 (or similar)
   ```
   If missing: `pip install -e ".[windows]"`

2. Verify SMTC is reporting on your system:
   - Play audio/video in any app (VLC, Spotify, Edge, Chrome, etc.)
   - Press a media key (Play/Pause) — a Windows overlay should appear with track info
   - If no overlay: that player doesn't report to SMTC (older apps, some games)

3. Verify the listener can import and instantiate:
   ```powershell
   python -c "from show_tracker.detection.smtc_listener import SMTCListener; print('OK')"
   # Expected: OK
   # If ImportError: winsdk not installed or wrong platform
   ```

4. Quick smoke test (standalone, outside `show-tracker run`):
   ```powershell
   python -c "
   import asyncio
   from show_tracker.detection.smtc_listener import SMTCListener

   async def test():
       listener = SMTCListener()
       listener.register_callback(lambda e: print(f'  Got: {e.title} [{e.playback_status.value}]'))
       await listener.start()
       print('Listening for 15 seconds... play something in VLC/Spotify/browser')
       await asyncio.sleep(15)
       await listener.stop()

   asyncio.run(test())
   "
   ```
   - If it prints media titles: the listener works and wiring it into the app will enable detection
   - If no output: check that media is actively playing and the app reports to SMTC

#### Troubleshooting SMTC itself

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ImportError: winsdk` | Package not installed | `pip install -e ".[windows]"` |
| `SMTCListener` instantiates but no events | Player doesn't report to SMTC | Try Windows Media Player or Edge (they always report). VLC reports if "System Media Transport Controls" is enabled in Preferences > Interface > Control Interfaces |
| Events show but title is empty | Some apps report playback status without metadata | Normal for some games/apps — the resolver will skip these |
| `RuntimeError: SMTCListener is only supported on Windows` | Running on WSL or Linux | Expected — use browser extension instead |
| Smoke test hangs or crashes | `winsdk` version mismatch or Python version issue | Try `pip install --force-reinstall winsdk==1.0.0b10` |

#### Full test procedure

1. Start `show-tracker run`
2. Open VLC and play a TV show file (e.g., `Breaking.Bad.S01E01.720p.mkv`)
3. Watch the log for lines containing `smtc` or `media_session`
   - Should show: media title, artist (if any), playback status
4. Pause playback → verify a pause event appears in logs
5. Resume → verify a playing event appears
6. Test with other apps:
   - Windows Media Player
   - Edge/Chrome playing Netflix or YouTube
   - Spotify (will detect music — resolver discards non-TV content)

### 2b. MPRIS Listener (Linux)

**What it does**: Captures media metadata from any app using the MPRIS D-Bus interface — the primary desktop detection source on Linux. Starts automatically with `show-tracker run` on Linux (not WSL).

#### Verification

1. Verify D-Bus is running:
   ```bash
   echo $DBUS_SESSION_BUS_ADDRESS
   # Should print: unix:path=/run/user/1000/bus (or similar)
   # If empty: D-Bus session bus is not available (common on headless servers and WSL)
   ```

2. Verify `dbus-next` is installed:
   ```bash
   pip show dbus-next
   ```
   If missing: `pip install -e ".[linux]"`

3. List active MPRIS players:
   ```bash
   dbus-send --session --dest=org.freedesktop.DBus --type=method_call \
     --print-reply /org/freedesktop/DBus org.freedesktop.DBus.ListNames \
     | grep mpris
   # Should show entries like: org.mpris.MediaPlayer2.vlc
   ```

4. Quick smoke test:
   ```bash
   python -c "
   import asyncio
   from show_tracker.detection.mpris_listener import MPRISListener

   async def test():
       listener = MPRISListener()
       listener.register_callback(lambda e: print(f'  Got: {e.title} [{e.playback_status.value}]'))
       await listener.start()
       print('Listening for 15 seconds... play something in VLC/mpv')
       await asyncio.sleep(15)
       await listener.stop()

   asyncio.run(test())
   "
   ```

#### Full test procedure

1. Start `show-tracker run`
2. Play a TV show file in VLC or mpv
3. Watch log for `mpris` or `media_session` entries
4. Pause/resume → verify state change events
5. **Troubleshooting**:
   - On Wayland: MPRIS works via D-Bus regardless of display server
   - Check logs for `dbus` import errors
   - On WSL: MPRIS is not available (no D-Bus session bus)

### 2c. Browser Extension — Chrome

**What it does**: Content script injects into every page, extracts metadata (URL patterns, JSON-LD, Open Graph, video elements), and sends events to the local API.

#### Loading
1. Open `chrome://extensions/`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** → select `browser_extension/chrome/`
4. Verify "Show Tracker" appears with no errors
5. Pin the extension icon (puzzle piece → pin)

#### Testing connection
1. Start `show-tracker run`
2. Click the extension icon → should show **Connected** (green dot)
3. If "Disconnected":
   - Is `show-tracker run` running on port 7600?
   - Open DevTools on the service worker: chrome://extensions → "Inspect views: service worker" → check console

#### Testing on streaming sites
For each platform, play a video and check:

1. Open Chrome DevTools → Network tab → filter for `localhost:7600`
2. Navigate to a streaming site and play something
3. Verify you see POST requests to `/api/media-event`
4. Check the request payload for `url_match.platform` and metadata

Platforms to test:
- [ ] **Netflix** — `url_match.platform: "netflix"`, `content_id` present
- [ ] **YouTube** — `platform: "youtube"`, `video_id` present
- [ ] **Crunchyroll** — verify title captured from page
- [ ] **Disney+** — verify URL match
- [ ] **Hulu** — verify URL match
- [ ] **Amazon Prime** — verify URL match
- [ ] **HBO Max** — verify URL match
- [ ] **Any site with `<video>`** — verify video element detection

#### Verifying heartbeats
1. Play a video on any platform
2. Watch the `show-tracker run` terminal
3. `heartbeat` events should arrive every ~30 seconds
4. Pause video → heartbeats stop
5. Resume → heartbeats restart

#### Verifying API state
```bash
curl http://localhost:7600/api/currently-watching
# Expected (while playing): is_watching: true, title, position, duration
```

### 2d. Browser Extension — Firefox

1. Open `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on** → select `browser_extension/firefox/manifest.json`
3. Same verification steps as Chrome above
4. Note: extension is Manifest V2 with `browser.*` APIs

### 2e. VLC Web Interface

**What it does**: Reads playback metadata (file path, title, duration, position) via VLC's HTTP API.

#### Enable VLC web interface
1. Open VLC → **Tools** → **Preferences**
2. Bottom-left: click **All** under "Show settings"
3. Left tree: **Interface** → **Main interfaces** → check **Web**
4. Left tree: **Interface** → **Main interfaces** → **Lua** → set an HTTP password (e.g., `vlcpass`)
5. Click **Save** → restart VLC completely

#### Verify web interface
1. Open http://localhost:8080 in a browser
2. Enter empty username, your password → VLC web UI should load
3. If it doesn't:
   - VLC must be running
   - Check if port 8080 is in use: `netstat -an | findstr 8080` (Windows) or `ss -tlnp | grep 8080` (Linux)

#### Test detection
1. Start `show-tracker run`
2. Play a TV show file in VLC
3. Watch logs for VLC detection events
4. File path should be captured and parsed for show/episode info

### 2f. mpv IPC Socket

**What it does**: Reads playback metadata from mpv via its JSON IPC protocol.

#### Configure
Add to mpv config:

```bash
# Linux/macOS: ~/.config/mpv/mpv.conf
input-ipc-server=/tmp/mpv-socket

# Windows: %APPDATA%\mpv\mpv.conf
input-ipc-server=\\.\pipe\mpv-pipe
```

#### Test
1. Restart mpv so it picks up the config
2. Verify socket exists:
   ```bash
   # Linux
   ls -la /tmp/mpv-socket

   # Test manually
   echo '{"command":["get_property","media-title"]}' | socat - /tmp/mpv-socket
   ```
3. Start `show-tracker run`
4. Play a TV show file in mpv
5. Watch logs for mpv detection events

### 2g. Plex/Jellyfin/Emby Webhooks

**What it does**: Receives structured playback events directly from media servers — highest accuracy source.

#### Plex
1. Go to Plex Settings → Webhooks
2. Add URL: `http://YOUR_IP:7600/api/webhooks/plex`
   - Use your machine's LAN IP, not `localhost` (Plex server may be on a different device)
3. Play media → check logs for webhook events
4. Events: `media.play`, `media.pause`, `media.resume`, `media.stop`, `media.scrobble`

#### Jellyfin
1. Install the Jellyfin **Webhook** plugin (Dashboard → Plugins → Catalog)
2. Configure: add a "Generic Destination" with URL `http://YOUR_IP:7600/api/webhooks/jellyfin`
3. Enable events: `Playback Start`, `Playback Stop`, `Playback Progress`
4. Play media → check logs

#### Emby
1. Go to Emby Dashboard → Webhooks
2. Add URL: `http://YOUR_IP:7600/api/webhooks/emby`
3. Select events: `playback.start`, `playback.stop`, `playback.progress`
4. Play media → check logs

### 2h. macOS Listener (macOS hardware required)

**What it does**: `MacOSMediaListener` polls `MPNowPlayingInfoCenter.defaultCenter()` every 2 seconds via `pyobjc-framework-MediaPlayer` and emits `MediaSessionEvent` on title or playback-state changes. The code exists but has never been tested on real hardware.

#### Prerequisites

```bash
pip install -e ".[macos]"
# Installs pyobjc-framework-MediaPlayer>=9.0
```

#### Verify import

```bash
python -c "from show_tracker.detection.macos_listener import MacOSMediaListener; print('OK')"
# Expected: OK
# If ImportError: pyobjc not installed or wrong platform
```

#### Quick smoke test

```python
import asyncio
from show_tracker.detection.macos_listener import MacOSMediaListener

async def test():
    listener = MacOSMediaListener()
    listener.register_callback(lambda e: print(f"  Got: {e.title} [{e.playback_status.value}]"))
    await listener.start()
    print("Listening for 15 seconds... play something in VLC/IINA/Safari")
    await asyncio.sleep(15)
    await listener.stop()

asyncio.run(test())
```

#### Full test procedure

1. Start `show-tracker run`
2. For each app below, play a TV show file or stream and watch logs for `macos` or `media_session` entries:
   - [ ] **Safari** — stream on Netflix or YouTube
   - [ ] **Chrome** — stream on Netflix or YouTube
   - [ ] **VLC** — local file with episode filename
   - [ ] **IINA** — local file with episode filename
   - [ ] **Music.app / TV.app** — confirm non-TV content is discarded by resolver
3. Pause playback → verify pause event in logs
4. Resume → verify playing event
5. Verify auto-advancing episodes are detected without window focus

#### Known limitations

- `MPNowPlayingInfoCenter` is a polling-based approach (2 s interval) rather than the push-based native `MPRemoteCommandCenter`. This means up to a 2 s lag between actual playback state change and detection.
- macOS 14+ may require explicit Screen Recording permission for OCR (`CGWindowListCreateImage`). Grant it in **System Settings → Privacy & Security → Screen Recording**.
- `MacOSMediaListener` is the first known user of this code path — report any crashes or unexpected behavior.

#### macOS packaging (not yet done)

The roadmap calls for a DMG or `.pkg` installer. No build script exists yet:

- [ ] Create `scripts/build_macos.sh` — `pyinstaller show_tracker.spec` + `create-dmg` or `pkgbuild`
- [ ] Add `macos` matrix entry to `.github/workflows/release.yml`

---

## 3. Post-Setup Tuning

### 3a. Tune Confidence Thresholds

**When**: After 3-5 days of regular use.

1. Open the **Unresolved** queue at http://localhost:7600/#/unresolved
2. For each item, evaluate:
   - Items with confidence 0.7-0.9 that are obviously correct → lower `ST_AUTO_LOG_THRESHOLD`
   - Items with confidence 0.5-0.7 that have good guesses → lower `ST_REVIEW_THRESHOLD`
3. Check **Dashboard** for auto-logged items — any wrong matches mean threshold is too low
4. Adjust in `.env`:
   ```
   ST_AUTO_LOG_THRESHOLD=0.85
   ST_REVIEW_THRESHOLD=0.65
   ```
5. Restart `show-tracker run`
6. Re-evaluate after another week

### 3b. Seed Show Aliases

Add abbreviations for shows you watch. 50+ common aliases are pre-seeded, but add your own:

```bash
# Find your show's ID
curl http://localhost:7600/api/history/shows

# Add aliases
curl -X POST http://localhost:7600/api/aliases \
  -H "Content-Type: application/json" \
  -d '{"show_id": 1, "alias": "BrBa"}'
```

Common ones to add:
- "GoT" → Game of Thrones
- "HIMYM" → How I Met Your Mother
- "IASIP" → It's Always Sunny in Philadelphia
- "SVU" → Law & Order: Special Victims Unit

### 3c. Set Up Trakt.tv Sync

1. Create a Trakt API application at https://trakt.tv/oauth/applications
   - Redirect URI: `urn:ietf:wg:oauth:2.0:oob`
2. Add to `.env`:
   ```
   TRAKT_CLIENT_ID=your_client_id
   TRAKT_CLIENT_SECRET=your_client_secret
   ```
3. Run the device auth flow (prompted on first sync)
4. Import existing Trakt history into local database
5. Export local history to Trakt

---

## 4. Packaging & Distribution

All build tooling is automated. See [docs/DISTRIBUTION.md](DISTRIBUTION.md) for comprehensive instructions.

### Quick release workflow

```bash
# Bump version everywhere
./scripts/bump_version.sh 0.2.0

# Commit and tag
git add -A && git commit -m "Bump version to 0.2.0"
git tag v0.2.0
git push origin main --tags
# CI builds everything and creates a GitHub Release
```

### Build locally

```bash
# Windows binary
pip install pyinstaller && pyinstaller show_tracker.spec

# Linux AppImage
./scripts/build_appimage.sh

# Browser extension ZIPs
./scripts/package_extensions.sh

# Python package
pip install build && python -m build
```

### Auto-start on login

**Windows**:
- Copy a shortcut to `show-tracker run` into `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`
- Or for the PyInstaller binary: shortcut to `dist\show-tracker\show-tracker.exe run`

**Linux (systemd)**:
```bash
cp contrib/show-tracker.service ~/.config/systemd/user/
# Edit ExecStart= to point to your venv's show-tracker
# Edit Environment= to set TMDB_API_KEY
systemctl --user daemon-reload
systemctl --user enable --now show-tracker
systemctl --user status show-tracker
journalctl --user -u show-tracker -f
```

### Store submissions

- **PyPI**: Push a `v*` tag (CI publishes automatically if `PYPI_API_TOKEN` repo secret is set)
- **Chrome Web Store**: Developer account ($5), upload ZIP, see [DISTRIBUTION.md](DISTRIBUTION.md#chrome-web-store)
- **Firefox Add-ons**: Upload ZIP at https://addons.mozilla.org/developers/

---

## 5. Optional: OCR Profile Tuning

The crop regions in `profiles/default_profiles.json` are estimated defaults. To improve for your setup:

1. For each player (VLC, mpv, Plex, MPC-HC, Kodi):
   - Play a show, pause where the title overlay is visible
   - Screenshot the player window
   - Open in an image editor, note pixel coordinates of title text region
   - Compare with and adjust `profiles/default_profiles.json`
2. Test at multiple resolutions (1080p, 1440p, 4K)
3. Run the benchmark:
   ```bash
   python scripts/ocr_benchmark.py --engine tesseract --verbose
   ```

---

## 6. Optional: YouTube API Key

Enables series detection from YouTube playlists and video metadata.

1. Go to https://console.cloud.google.com/
2. Create a project (or use existing)
3. Enable **YouTube Data API v3**
4. Create an API key under **Credentials**
5. Add to `.env`:
   ```
   YOUTUBE_API_KEY=your_key_here
   ```
6. Quota: 10,000 units/day on free tier (1 unit per `videos.list` call — plenty for personal use)

---

## 7. Optional: TVDb API Key (Anime)

Improves identification for anime with absolute episode numbering (e.g., "Naruto 135" instead of "S06E12").

1. Get a free key at https://thetvdb.com/api-information
2. Add to `.env`:
   ```
   TVDB_API_KEY=your_key_here
   ```
3. The resolver automatically tries TVDb when TMDb confidence is low, no season number is present, and episode > 50
