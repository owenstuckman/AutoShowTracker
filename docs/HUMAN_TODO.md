# Human TODO

Tasks that require manual testing, external accounts, or hardware access. These cannot be automated and need a human to complete. Items are ordered by priority — complete the "Critical Path" section first before moving on.

---

## Critical Path: First Working Setup (COMPLETE)

All critical path tasks have been completed. The system is installed, TMDb key is configured, databases are initialized, pipeline is validated, and the web UI is working.

### ~~1. Set up your Python environment~~ DONE

1. Open a terminal in the project root (`AutoShowTracker/`)
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```
3. Activate it:
   - **Windows PowerShell**: `.venv\Scripts\Activate.ps1`
   - **Windows cmd**: `.venv\Scripts\activate.bat`
   - **Linux/macOS**: `source .venv/bin/activate`
4. Install with your platform extras:
   - **Windows**: `pip install -e ".[dev,ocr,windows]"`
   - **Linux**: `pip install -e ".[dev,ocr,linux]"`
5. Verify the CLI works:
   ```bash
   show-tracker --version
   # Should print: show-tracker, version 0.1.0
   ```

### ~~2. Get a TMDb API key~~ DONE

1. Go to https://www.themoviedb.org/signup and create a free account
2. Verify your email address (check spam folder if needed)
3. Log in, then go to https://www.themoviedb.org/settings/api
4. Click **"Create"** under "Request an API Key"
5. Select **"Developer"**
6. Accept the Terms of Use
7. Fill in the application form:
   - **Application Name**: AutoShowTracker
   - **Application URL**: http://localhost (or your GitHub repo URL)
   - **Application Summary**: "Personal media tracking tool"
   - **Type of Use**: Personal
8. Copy the **API Key (v3 auth)** value (NOT the API Read Access Token)
9. In the project root, copy the example env file:
   ```bash
   cp .env.example .env
   ```
10. Edit `.env` and paste your key:
    ```
    TMDB_API_KEY=your_32_character_key_here
    ```

### ~~3. Initialize databases and validate the pipeline~~ DONE

1. Initialize the databases:
   ```bash
   show-tracker init-db
   ```
2. Verify the output shows both database paths and "Databases initialised successfully"
3. Check the files were created:
   - `~/.show-tracker/watch_history.db` should exist
   - `~/.show-tracker/media_cache.db` should exist
4. Test the identification pipeline with known inputs:
   ```bash
   show-tracker identify "Breaking Bad S05E14"
   ```
   - **Expected**: JSON output with `show_name: "Breaking Bad"`, `season: 5`, `episode: 14`, `tmdb_show_id: 1396`, confidence >= 0.85
5. Test with a messy filename:
   ```bash
   show-tracker identify "law.and.order.svu.s03e07.720p.bluray.mkv"
   ```
   - **Expected**: Resolves to "Law & Order: Special Victims Unit", S03E07
6. Test with a browser title:
   ```bash
   show-tracker identify "Stranger Things | Netflix" --source browser_title
   ```
   - **Expected**: Resolves to "Stranger Things" with a TMDb ID
7. Test with something that should fail:
   ```bash
   show-tracker identify "random gibberish text"
   ```
   - **Expected**: "No match found." message
8. If any of steps 4-6 fail, check:
   - Is `TMDB_API_KEY` set correctly in `.env`? (no quotes, no spaces)
   - Can you reach `api.themoviedb.org` from your network?
   - Run with `--source manual` and check the JSON output for `confidence` values

### ~~4. Start the full service and verify the web UI~~ DONE

1. Start all services:
   ```bash
   show-tracker run
   ```
2. Check the startup output shows:
   - `TMDb key set   : True`
   - `HTTP API       : http://127.0.0.1:7600`
3. Open http://127.0.0.1:7600 in your browser
4. Verify you see the dashboard with an empty state (no watch history yet)
5. Click through each nav section:
   - **Dashboard** (`#/dashboard`) — should load without errors
   - **Shows** (`#/shows`) — empty grid, no errors
   - **Unresolved** (`#/unresolved`) — empty list
   - **Settings** (`#/settings`) — settings form loads
6. Test the API directly:
   ```bash
   curl http://127.0.0.1:7600/api/health
   # Should return: {"status":"ok","version":"0.1.0"}
   ```
7. Test the Swagger docs at http://127.0.0.1:7600/docs — should show all endpoints
8. Press Ctrl+C to stop

---

## Detection Source Testing (NEXT UP)

Test each detection source individually. You only need to test the ones relevant to your setup.

### 5. Test SMTC listener (Windows only)

**What it does**: Captures media metadata from any Windows app that reports to System Media Transport Controls (the overlay that appears when you press media keys).

1. Start the service: `show-tracker run`
2. Open a **second terminal** and tail the log file:
   ```powershell
   Get-Content -Wait "$env:USERPROFILE\.show-tracker\logs\show_tracker.log"
   ```
3. Open VLC and play a TV show file (e.g., `Breaking.Bad.S01E01.720p.mkv`)
4. Watch the log for lines containing `smtc` or `media_session`:
   - You should see: media title, artist (if any), playback status (playing/paused)
5. Pause playback in VLC — verify a pause event appears in logs
6. Resume playback — verify a playing event appears
7. Try with other players:
   - [ ] Windows Media Player
   - [ ] Spotify (will detect music — that's expected, the resolver will discard non-TV content)
   - [ ] A browser playing Netflix/YouTube (Chrome, Edge)
8. **If no SMTC events appear**:
   - Verify `winsdk` is installed: `pip show winsdk`
   - Check if the player reports to SMTC (press Win+media key — does an overlay appear?)
   - Check for import errors in the log: search for `smtc` or `winsdk`

### 6. Test MPRIS listener (Linux only)

**What it does**: Captures media metadata from any Linux app that implements the MPRIS D-Bus interface.

1. Verify D-Bus is running:
   ```bash
   echo $DBUS_SESSION_BUS_ADDRESS
   # Should print something like: unix:path=/run/user/1000/bus
   ```
2. Start the service: `show-tracker run`
3. Open a second terminal and tail the log:
   ```bash
   tail -f ~/.show-tracker/logs/show_tracker.log
   ```
4. Open VLC or mpv and play a TV show file
5. Watch for MPRIS events in the log (lines containing `mpris` or `media_session`)
6. Verify you see: media title, playback status, metadata changes
7. Pause/resume — verify state change events
8. Test with other players:
   - [ ] VLC
   - [ ] mpv
   - [ ] Firefox or Chromium playing video
   - [ ] Celluloid / GNOME Videos
9. **Useful debug command** — list all MPRIS players currently running:
   ```bash
   dbus-send --session --dest=org.freedesktop.DBus --type=method_call \
     --print-reply /org/freedesktop/DBus org.freedesktop.DBus.ListNames \
     | grep mpris
   ```
10. **If no MPRIS events appear**:
    - Verify `dbus-next` is installed: `pip show dbus-next`
    - Verify the player supports MPRIS (most Linux media players do)
    - Check the log for `dbus` import errors

### 7. Test browser extension in Chrome

**What it does**: Extracts structured metadata (URL patterns, JSON-LD, Open Graph tags, video element state) from streaming sites and sends events to the local API.

#### Loading the extension
1. Open Chrome and navigate to `chrome://extensions/`
2. Enable **Developer mode** (toggle in top-right corner)
3. Click **Load unpacked**
4. Navigate to and select the `browser_extension/chrome/` directory
5. Verify the "Show Tracker" extension appears in the list with no errors
6. Pin the extension icon to your toolbar (click the puzzle piece icon > pin)

#### Testing connection
1. Start `show-tracker run` in a terminal
2. Click the Show Tracker extension icon in the toolbar
3. The popup should show **"Connected"** status (green)
4. If it shows "Disconnected":
   - Is `show-tracker run` actually running?
   - Is it on port 7600? Check the terminal output
   - Open DevTools on the extension's background page (chrome://extensions > "Inspect views: service worker") and check the console for errors

#### Testing on streaming platforms
For each platform, play a video and check the terminal running `show-tracker run` for incoming events:

- [ ] **Netflix**: Navigate to a show, play an episode
  - Open Chrome DevTools Network tab, filter for `localhost:7600`
  - You should see POST requests to `/api/media-event`
  - Check that the event includes `url_match.platform: "netflix"` and a `content_id`
- [ ] **YouTube**: Play any video
  - Verify URL pattern matches with `platform: "youtube"` and `video_id`
- [ ] **Crunchyroll**: Play an anime episode
  - Verify detection captures the show/episode title
- [ ] **Disney+**: Play something
  - Verify URL pattern match
- [ ] **Hulu**: Play something
  - Verify URL pattern match
- [ ] **Amazon Prime Video**: Play something
  - Verify URL pattern match
- [ ] **HBO Max**: Play something
  - Verify URL pattern match
- [ ] **A pirate/torrent streaming site**: Play something
  - Verify the generic pattern detector picks up video playback
  - This relies on `<video>` element detection and page title extraction

#### Verifying heartbeats
1. Start playing a video on any platform
2. Watch the `show-tracker run` terminal
3. You should see `heartbeat` events arriving approximately every 15 seconds
4. Pause the video — heartbeats should stop
5. Resume — heartbeats should restart

#### Verifying metadata quality
1. While a video is playing, send a test request to check what the extension captured:
   ```bash
   curl http://localhost:7600/api/currently-watching
   ```
2. Check the response for:
   - `is_watching: true`
   - `title` — should contain the show/episode name
   - `tab_url` — should be the streaming site URL
   - `position` and `duration` — should be numeric values

### 8. Test VLC web interface integration

**What it does**: Reads playback metadata (file path, title, position, duration) directly from VLC via its HTTP API. More reliable than window titles for local files.

#### Enable VLC web interface
1. Open VLC
2. Go to **Tools > Preferences**
3. At the bottom-left, click **"All"** under "Show settings" (switches to advanced mode)
4. In the left tree, navigate to **Interface > Main interfaces**
5. Check the **Web** checkbox
6. In the left tree, expand **Main interfaces** and click **Lua**
7. In the **"Lua HTTP"** section, set a **password** (e.g., `vlcpass`)
8. Click **Save**
9. Restart VLC completely (close and reopen)
10. Verify the web interface works: open http://localhost:8080 in a browser
    - It should prompt for a username/password
    - Username is empty, password is what you set in step 7
    - You should see the VLC web UI

#### Test detection
1. Start `show-tracker run`
2. In VLC, play a TV show file (e.g., `Game.of.Thrones.S01E01.1080p.BluRay.mkv`)
3. Watch the log for VLC detection events
4. The file path should be captured and parsed for show/episode info
5. **If VLC detection doesn't work**:
   - Is VLC's web interface accessible at http://localhost:8080?
   - Check the log for connection errors to VLC
   - The VLC client in `src/show_tracker/players/vlc.py` connects to `localhost:8080` by default

### 9. Test mpv IPC integration

**What it does**: Reads playback metadata from mpv via its JSON IPC socket. Provides file path, media title, position, and duration.

#### Configure mpv IPC socket

**Linux/macOS**: Add to `~/.config/mpv/mpv.conf`:
```
input-ipc-server=/tmp/mpv-socket
```

**Windows**: Add to `%APPDATA%\mpv\mpv.conf`:
```
input-ipc-server=\\.\pipe\mpv-pipe
```

#### Test detection
1. Restart mpv (close and reopen) so it picks up the new config
2. Verify the socket exists:
   - **Linux**: `ls -la /tmp/mpv-socket` (should exist while mpv is running)
   - **Windows**: The named pipe `\\.\pipe\mpv-pipe` is created when mpv starts
3. Start `show-tracker run`
4. In mpv, play a TV show file
5. Watch the log for mpv detection events
6. The file path and media-title should be captured
7. **If mpv detection doesn't work**:
   - Is the socket file created when mpv starts? (`ls /tmp/mpv-socket`)
   - Test the socket manually:
     ```bash
     echo '{"command":["get_property","media-title"]}' | socat - /tmp/mpv-socket
     ```

---

## Post-Setup Tuning

### 10. Tune confidence thresholds

**When**: After using the system for at least 3-5 days of regular viewing.

**Why**: The default thresholds (auto_log >= 0.9, review >= 0.7) are conservative estimates. Your specific viewing habits may need different values.

1. Use the system normally for 3-5 days
2. Open the web UI at http://localhost:7600
3. Go to the **Unresolved** queue (`#/unresolved`)
4. For each unresolved item, evaluate:
   - **Should this have been auto-logged?** If many items with confidence 0.7-0.9 are obviously correct, lower `ST_AUTO_LOG_THRESHOLD` (e.g., to 0.85 or 0.80)
   - **Should this have been in the review queue instead of unresolved?** If items with confidence 0.5-0.7 often have good guesses, lower `ST_REVIEW_THRESHOLD` (e.g., to 0.6)
5. Check the **Dashboard** for auto-logged items:
   - Are any entries wrong show/episode? If so, the auto-log threshold might be too low
6. Adjust thresholds in `.env`:
   ```
   ST_AUTO_LOG_THRESHOLD=0.85
   ST_REVIEW_THRESHOLD=0.65
   ```
7. Restart `show-tracker run` for changes to take effect
8. Re-evaluate after another week

### 11. Seed show aliases for your library

**Why**: If you watch shows with common abbreviations or alternate names, adding aliases improves identification accuracy.

1. Start `show-tracker run`
2. For shows you watch that have abbreviations, add aliases via the API:
   ```bash
   # First, find the show's internal ID from the shows page or API
   curl http://localhost:7600/api/history/shows

   # Then add aliases
   curl -X POST http://localhost:7600/api/aliases \
     -H "Content-Type: application/json" \
     -d '{"show_id": 1, "alias": "BrBa"}'
   ```
3. Common aliases to add for shows you watch:
   - "GoT" / "Game of Thrones"
   - "HIMYM" / "How I Met Your Mother"
   - "IASIP" / "It's Always Sunny in Philadelphia"
   - "SVU" / "Law & Order: Special Victims Unit"
4. Note: 50+ common aliases are pre-seeded in `src/show_tracker/utils/aliases.py`

---

## Packaging (When Ready to Distribute)

### 12. PyInstaller bundling

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Create a spec file:
   ```bash
   pyi-makespec --onefile --name show-tracker src/show_tracker/main.py
   ```
3. Edit the `.spec` file to include data files:
   - Add `config/default_settings.json` to `datas`
   - Add `profiles/default_profiles.json` to `datas`
   - Add `web_ui/` directory to `datas`
   - Add guessit's data directory to `datas` (find with `python -c "import guessit; print(guessit.__path__)"`)
4. Build:
   ```bash
   pyinstaller show-tracker.spec
   ```
5. Test the binary:
   ```bash
   dist/show-tracker --version
   dist/show-tracker init-db
   dist/show-tracker identify "Breaking Bad S05E14"
   dist/show-tracker run
   ```
6. Known issues to watch for:
   - guessit's YAML data files must be bundled (hidden imports: `guessit`, `rebulk`)
   - SQLAlchemy dialect for SQLite needs explicit inclusion
   - winsdk/dbus-next conditional imports may need `--hidden-import` flags

### 13. Windows installer (Inno Setup)

1. Download Inno Setup from https://jrsoftware.org/isinfo.php
2. Create an install script that:
   - Bundles the PyInstaller output from step 12
   - Creates a Start Menu shortcut for `show-tracker run`
   - Adds an uninstaller
   - Optionally adds a "Start with Windows" checkbox (creates a Startup folder shortcut)
3. Test on a clean Windows 10 VM (no Python installed)
4. Verify: install, run, open web UI, uninstall — all should work cleanly

### 14. System tray icon (pystray)

1. Add `pystray` to dependencies in `pyproject.toml`
2. Implement a tray icon module at `src/show_tracker/tray.py`:
   - Icon states: running (green), stopped (gray), error (red)
   - Menu items: "Open Dashboard" (opens browser to localhost:7600), "Start/Stop Service", "Quit"
3. Integrate with the `show-tracker run` command — launch tray icon alongside uvicorn
4. Test on Windows (system tray) and Linux (uses AppIndicator or StatusNotifier)

### 15. Auto-start on login

**Windows**:
1. Create a shortcut to `show-tracker run` (or the PyInstaller binary)
2. Place in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`
3. Or add a registry key: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`

**Linux**:
1. Copy the provided service file:
   ```bash
   cp contrib/show-tracker.service ~/.config/systemd/user/
   ```
2. Edit the `ExecStart` path to point to your actual venv:
   ```bash
   nano ~/.config/systemd/user/show-tracker.service
   # Change ExecStart to your actual path, e.g.:
   # ExecStart=/home/you/AutoShowTracker/.venv/bin/show-tracker run
   ```
3. Set your TMDb key in the service file's `Environment` line
4. Enable and start:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now show-tracker
   ```
5. Check status:
   ```bash
   systemctl --user status show-tracker
   journalctl --user -u show-tracker -f
   ```

### 16. Bundle ActivityWatch

1. Download the latest ActivityWatch release from https://github.com/ActivityWatch/activitywatch/releases
2. Extract the binaries to a known location alongside your installer
3. In your first-run setup or startup script:
   - Check if `aw-server` and `aw-watcher-window` processes are running
   - If not, start them from the bundled location
4. Note: ActivityWatch is MPL 2.0 licensed — we bundle it unmodified as a separate subprocess, which is permitted

---

## Distribution

### 17. Chrome Web Store submission

1. Host `PRIVACY_POLICY.md` at a public URL (e.g., on your GitHub Pages or in the repo's raw view)
2. Create a Chrome Web Store developer account:
   - Go to https://chrome.google.com/webstore/devconsole/
   - Pay the one-time $5 registration fee
3. Prepare store assets:
   - Create a 128x128 icon at `browser_extension/chrome/icon.png` (or update the existing one)
   - Take screenshots of the extension popup and the web dashboard (1280x800 or 640x400)
   - Write a store description (can adapt from README.md)
4. Create a ZIP of the extension directory:
   ```bash
   cd browser_extension/chrome && zip -r ../../show-tracker-extension.zip .
   ```
5. Upload to the Chrome Web Store developer console
6. Fill in the listing: description, screenshots, privacy policy URL, category ("Productivity")
7. Submit for review (typically takes 1-3 business days)

### 18. Firefox extension port

1. Review Firefox's Manifest V3 differences: https://extensionworkshop.com/documentation/develop/manifest-v3-migration-guide/
2. Key changes needed in `browser_extension/firefox/manifest.json`:
   - `"background": { "scripts": ["background.js"] }` instead of `service_worker`
   - Firefox uses `browser.*` API namespace (though Chrome's `chrome.*` is polyfilled)
3. Copy Chrome extension files to `browser_extension/firefox/`
4. Modify `manifest.json` for Firefox compatibility
5. Test in Firefox: `about:debugging` > "This Firefox" > "Load Temporary Add-on"
6. Submit to Firefox Add-ons: https://addons.mozilla.org/developers/

### 19. PyPI publication

1. Verify pyproject.toml metadata:
   - `[project]` section has: name, version, description, authors, license, urls, classifiers
   - `readme` points to README.md
2. Install build tools:
   ```bash
   pip install build twine
   ```
3. Build the package:
   ```bash
   python -m build
   ```
4. Check the built files:
   ```bash
   ls dist/
   # Should see: show_tracker-0.1.0.tar.gz and show_tracker-0.1.0-py3-none-any.whl
   ```
5. Test upload to TestPyPI first:
   ```bash
   twine upload --repository testpypi dist/*
   ```
6. Test install from TestPyPI:
   ```bash
   pip install --index-url https://test.pypi.org/simple/ show-tracker
   ```
7. If everything works, upload to real PyPI:
   ```bash
   twine upload dist/*
   ```

---

## Optional Enhancements

### 20. TVDb fallback for anime

**Why**: guessit sometimes interprets absolute episode numbers (e.g., "Naruto 135") incorrectly. TVDb has better anime episode mapping.

1. Get a TVDb API key at https://thetvdb.com/api-information
2. Add a `tvdb_client.py` alongside `tmdb_client.py` in `src/show_tracker/identification/`
3. In the resolver, add a fallback path: if TMDb match confidence is low AND the content looks like anime (no season number, high episode number, Japanese title), try TVDb
4. Map TVDb absolute episode numbers to season/episode format

### 21. YouTube Data API integration

**Why**: Enables detection of YouTube original series and playlist-based series content.

1. Go to https://console.cloud.google.com/
2. Create a new project (or use an existing one)
3. Enable the "YouTube Data API v3"
4. Create an API key under Credentials
5. Add to `.env`: `YOUTUBE_API_KEY=your_key_here`
6. The existing URL pattern matcher already extracts YouTube video IDs — the API integration would fetch video details, playlist info, and channel metadata to improve identification

### 22. Trakt.tv two-way sync

1. Create a Trakt.tv API application at https://trakt.tv/oauth/applications
   - Set redirect URI to `urn:ietf:wg:oauth:2.0:oob` (for local apps)
2. Implement OAuth2 flow:
   - User visits a URL, gets a code, pastes it into the app
   - App exchanges code for access/refresh tokens
   - Store tokens in `user_settings` table
3. Implement sync:
   - **Export**: Push local watch history to Trakt's scrobble API
   - **Import**: Pull Trakt history and merge into local database
   - Handle conflicts (same episode watched at different times)

### 23. OCR profile tuning

**Why**: The OCR crop regions in `profiles/default_profiles.json` are estimated defaults. Real-world testing is needed to verify accuracy.

1. For each player you use (VLC, mpv, Plex, MPC-HC, Kodi):
   a. Play a TV show and pause on a frame where the title overlay is visible
   b. Take a screenshot of the player window
   c. Open the screenshot in an image editor
   d. Note the pixel coordinates of the title/overlay text region
   e. Compare with the regions in `profiles/default_profiles.json`
   f. Adjust the `x`, `y`, `width`, `height` values if needed
2. Test at multiple resolutions (1080p, 1440p, 4K) — the regions may need to be relative (percentage-based) rather than absolute pixels
3. Test with different player themes/skins (dark mode, light mode, custom skins)
