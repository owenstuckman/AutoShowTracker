# Human TODO

Tasks that require manual testing, external accounts, or hardware access. These cannot be automated and need a human to complete.

---

## Before First Real Use (Critical Path)

### 1. Get a TMDb API key and validate end-to-end
- Create free account at https://www.themoviedb.org/signup
- Go to Settings > API > Create > Developer
- Copy the API Key (v3 auth) value
- Add to `.env`: `TMDB_API_KEY=your_key_here`
- Test: `show-tracker identify "Breaking Bad S05E14"`
- Test: `show-tracker identify "law.and.order.svu.s03e07.720p.bluray.mkv"`
- Verify the resolver returns correct TMDb IDs, episode titles, and confidence scores

### 2. Test SMTC listener on Windows
- Run `show-tracker run` on Windows 10/11
- Play media in VLC, Spotify, or a browser
- Check logs for SMTC events being detected
- Verify the media title/artist metadata is captured correctly
- Test pause/resume detection

### 3. Test MPRIS listener on Linux
- Run `show-tracker run` on a Linux desktop with D-Bus
- Play media in VLC, mpv, or a browser
- Check logs for MPRIS events
- Verify playback state changes are captured

### 4. Test browser extension in Chrome
- Load `browser_extension/chrome/` as unpacked extension in Chrome
- Start `show-tracker run`
- Verify extension popup shows "Connected"
- Test on each platform:
  - [ ] Netflix — play a show, verify detection
  - [ ] YouTube — play a video, verify URL pattern match
  - [ ] Crunchyroll — play an anime, verify detection
  - [ ] Disney+ — verify URL pattern match
  - [ ] Hulu — verify URL pattern match
  - [ ] Amazon Prime — verify URL pattern match
  - [ ] HBO Max — verify URL pattern match
  - [ ] A pirate site — verify generic pattern detection
- Verify heartbeats arrive every 15 seconds during playback
- Verify pause/ended events are sent

### 5. Test VLC web interface integration
- Enable VLC's web interface (Tools > Preferences > All > Interface > Main interfaces > Web)
- Set a password in Lua settings
- Play a TV show file in VLC
- Verify `show-tracker run` detects the playback via VLC HTTP API

### 6. Test mpv IPC integration
- Configure mpv IPC socket (add `input-ipc-server=/tmp/mpv-socket` to mpv.conf)
- Play a TV show file in mpv
- Verify `show-tracker run` detects the playback

---

## Confidence Tuning (After ~1 Week of Use)

### 7. Tune confidence thresholds
- Use the system for a week with default thresholds (auto_log=0.9, review=0.7)
- Review the unresolved queue at http://localhost:7600/#/unresolved
- Check for:
  - False positives in auto-logged events (score >= 0.9 but wrong show/episode)
  - Items in the review queue that should have been auto-logged
  - Items in the unresolved queue that had obvious correct matches
- Adjust `ST_AUTO_LOG_THRESHOLD` and `ST_REVIEW_THRESHOLD` in `.env` as needed

---

## Packaging (When Ready to Distribute)

### 8. PyInstaller bundling
- Test `pyinstaller` or `cx_Freeze` bundling into a single executable
- Verify the bundled app starts and all features work
- Note: guessit's data files and SQLAlchemy's dialect need to be included

### 9. Windows installer
- Build with Inno Setup or NSIS
- Include Start Menu shortcuts, uninstaller
- Test on a clean Windows 10 VM

### 10. System tray icon
- Implement via `pystray` library
- Start/stop service, open web UI, show status indicator
- Test on Windows and Linux

### 11. Auto-start on login
- Windows: Registry entry or Startup folder shortcut
- Linux: systemd user service (file provided at `contrib/show-tracker.service`)

### 12. Bundle ActivityWatch
- Download ActivityWatch release binaries
- Include alongside the installer
- Add first-run setup that starts AW if not already running

---

## Platform Testing

### 13. Test on macOS (if adding macOS support)
- macOS MediaRemote listener needs implementation via pyobjc or Swift helper
- Screenshot capture via CGWindowListCreateImage
- DMG packaging, code signing, notarization

---

## Distribution

### 14. Chrome Web Store submission
- Requires a privacy policy URL (PRIVACY_POLICY.md is ready, host it somewhere)
- Create Chrome Web Store developer account ($5 one-time fee)
- Prepare store listing screenshots
- Submit `browser_extension/chrome/` for review

### 15. Firefox extension port
- Adapt Manifest V3 to Firefox's WebExtension format
- Test in Firefox
- Submit to Firefox Add-ons

### 16. PyPI publication
- Verify `pyproject.toml` metadata is complete
- Test: `pip install build && python -m build`
- Test: `pip install dist/show_tracker-*.whl` in a clean venv
- Upload to TestPyPI first, then PyPI

---

## Optional Enhancements

### 17. TVDb fallback for anime
- Get a TVDb API key
- Integrate for anime with absolute episode numbering (e.g., "Naruto 135")

### 18. YouTube Data API
- Get a YouTube Data API v3 key from Google Cloud Console
- Set `YOUTUBE_API_KEY` in `.env`
- Enables playlist/series detection for YouTube original series

### 19. Trakt.tv integration
- Create Trakt.tv API application at https://trakt.tv/oauth/applications
- Implement OAuth2 flow for two-way sync
- Test import/export with existing Trakt history

### 20. OCR profile tuning
- Take screenshots of each supported player at various resolutions
- Test OCR crop regions in `profiles/default_profiles.json`
- Adjust coordinates as needed for your specific setup
