# Human TODO

Tasks that require manual testing, external accounts, or hardware access. These cannot be automated by code and need a human to complete.

---

## Critical Path (COMPLETE)

All critical path tasks have been completed: Python environment, TMDb API key, database initialization, pipeline validation, and web UI verification.

---

## Detection Source Testing

Test each detection source relevant to your setup. Start `show-tracker run`, then open a second terminal to tail the log.

### SMTC Listener (Windows)

1. Play media in VLC or a browser
2. Watch log for `smtc` or `media_session` entries — should show title, artist, playback status
3. Pause/resume — verify state change events appear
4. Try other players: Windows Media Player, Edge, Chrome
5. **If nothing appears**: verify `winsdk` is installed (`pip show winsdk`), check if player reports to SMTC (press Win + media key — does the overlay appear?)

### MPRIS Listener (Linux)

1. Verify D-Bus: `echo $DBUS_SESSION_BUS_ADDRESS` should print a path
2. Play media in VLC or mpv
3. Watch log for `mpris` entries
4. Debug: `dbus-send --session --dest=org.freedesktop.DBus --type=method_call --print-reply /org/freedesktop/DBus org.freedesktop.DBus.ListNames | grep mpris`
5. **If nothing appears**: verify `dbus-next` is installed, check log for import errors

### Browser Extension (Chrome)

1. Load unpacked from `browser_extension/chrome/` at `chrome://extensions/` (Developer mode on)
2. Click extension icon — should show **Connected** (green) while `show-tracker run` is active
3. Test on streaming sites: play a video, verify POST requests to `localhost:7600/api/media-event` in DevTools Network tab
4. Verify heartbeats every ~30 seconds while playing, pause/ended events on stop
5. Check: `curl http://localhost:7600/api/currently-watching`

### Browser Extension (Firefox)

1. Load from `browser_extension/firefox/` via `about:debugging` > "This Firefox" > "Load Temporary Add-on"
2. Same verification steps as Chrome

### VLC Web Interface

1. Enable in VLC: Tools > Preferences > All > Interface > Main interfaces > check **Web**
2. Set Lua HTTP password under Main interfaces > Lua
3. Restart VLC, verify http://localhost:8080 loads
4. Play a TV show file, check detection in logs

### mpv IPC Socket

1. Add `input-ipc-server=/tmp/mpv-socket` to `~/.config/mpv/mpv.conf` (Linux) or `input-ipc-server=\\.\pipe\mpv-pipe` to `%APPDATA%\mpv\mpv.conf` (Windows)
2. Restart mpv, verify socket exists
3. Play a TV show file, check detection in logs
4. Debug: `echo '{"command":["get_property","media-title"]}' | socat - /tmp/mpv-socket`

### Plex/Jellyfin/Emby Webhooks

1. Configure webhook URL in your media server: `http://localhost:7600/api/webhooks/{plex|jellyfin|emby}`
2. Play media, verify events received in logs

---

## Post-Setup Tuning

### Tune Confidence Thresholds

After 3-5 days of use:
1. Review the **Unresolved** queue at `#/unresolved` — should items have been auto-logged?
2. Check **Dashboard** for auto-logged items — any wrong matches?
3. Adjust in `.env`: `ST_AUTO_LOG_THRESHOLD` (default 0.9), `ST_REVIEW_THRESHOLD` (default 0.7)
4. Restart `show-tracker run`

### Seed Show Aliases

Add abbreviations for shows you watch via `POST /api/aliases` or the Settings page. 50+ common aliases are pre-seeded.

### Set Up Trakt.tv Sync

1. Create a Trakt.tv API application at https://trakt.tv/oauth/applications (redirect URI: `urn:ietf:wg:oauth:2.0:oob`)
2. Add credentials to `.env`
3. Run the device auth flow to import/export history

---

## Packaging & Auto-Start

### Build a Release

All build tooling is automated. See [docs/DISTRIBUTION.md](DISTRIBUTION.md) for full instructions.

```bash
# Build everything
pyinstaller show_tracker.spec        # Windows binary
./scripts/build_appimage.sh          # Linux AppImage
./scripts/package_extensions.sh      # Browser extension ZIPs
python -m build                      # PyPI wheel

# Or push a tag to trigger CI:
./scripts/bump_version.sh 0.2.0
git add -A && git commit -m "Bump version to 0.2.0"
git tag v0.2.0 && git push origin main --tags
```

### Auto-Start on Login

**Windows**: Place a shortcut to `show-tracker run` (or the PyInstaller binary) in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`

**Linux**:
```bash
cp contrib/show-tracker.service ~/.config/systemd/user/
# Edit ExecStart path, then:
systemctl --user daemon-reload
systemctl --user enable --now show-tracker
```

### Bundle ActivityWatch

1. Download from https://github.com/ActivityWatch/activitywatch/releases
2. Extract alongside your install; the startup script checks if `aw-server` is already running
3. MPL 2.0 — bundled unmodified as a subprocess

---

## Store Submissions

### Chrome Web Store

1. Create developer account at https://chrome.google.com/webstore/devconsole/ ($5 one-time)
2. Host `PRIVACY_POLICY.md` at a public URL
3. Prepare assets: 128x128 icon, 1280x800 screenshots, store description
4. Upload `dist/show-tracker-chrome-*.zip`, fill in listing, submit for review

### Firefox Add-ons

1. Upload `dist/show-tracker-firefox-*.zip` at https://addons.mozilla.org/developers/
2. Fill in listing, submit for review

### PyPI

Automated via CI when you push a `v*` tag (requires `PYPI_API_TOKEN` repo secret). Or manually:
```bash
pip install build twine
python -m build
twine upload dist/*
```

---

## Optional: OCR Profile Tuning

The OCR crop regions in `profiles/default_profiles.json` are estimated defaults. To improve accuracy for your setup:

1. For each player (VLC, mpv, Plex, MPC-HC, Kodi):
   - Play a show, pause where the title overlay is visible
   - Screenshot the player window
   - Note pixel coordinates of the title text region
   - Compare with and adjust `profiles/default_profiles.json`
2. Test at multiple resolutions (1080p, 1440p, 4K)
3. Run the benchmark: `python scripts/ocr_benchmark.py --engine tesseract --verbose`
