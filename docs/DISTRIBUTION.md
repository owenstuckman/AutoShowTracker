# Distribution Guide

How to build, package, and publish AutoShowTracker across all channels.

---

## Quick Reference

| Channel | Command | Output |
|---------|---------|--------|
| PyPI | `python -m build` | `dist/show_tracker-*.whl` |
| Windows binary | `pyinstaller show_tracker.spec` | `dist/show-tracker/` |
| Linux AppImage | `./scripts/build_appimage.sh` | `dist/ShowTracker-x86_64.AppImage` |
| Chrome extension | `./scripts/package_extensions.sh` | `dist/show-tracker-chrome-v*.zip` |
| Firefox extension | `./scripts/package_extensions.sh` | `dist/show-tracker-firefox-v*.zip` |
| GitHub Release | Push a `v*` tag | All artifacts via CI |

---

## 1. PyPI Package

### Prerequisites

```bash
pip install build twine
```

### Build

```bash
python -m build
```

This produces:
- `dist/show_tracker-0.1.0.tar.gz` (source distribution)
- `dist/show_tracker-0.1.0-py3-none-any.whl` (wheel)

### Test on TestPyPI

```bash
# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Test install in a clean venv
python -m venv /tmp/test-install && source /tmp/test-install/bin/activate
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ show-tracker
show-tracker --version
show-tracker identify "Breaking Bad S05E14"
deactivate && rm -rf /tmp/test-install
```

### Publish to PyPI

```bash
twine upload dist/*
```

You'll need a PyPI API token. Create one at https://pypi.org/manage/account/token/ and configure:

```bash
# ~/.pypirc
[pypi]
username = __token__
password = pypi-YOUR_TOKEN_HERE

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-YOUR_TESTPYPI_TOKEN_HERE
```

Or use `TWINE_USERNAME` / `TWINE_PASSWORD` environment variables.

### Automated via CI

The GitHub Actions release workflow handles this automatically when you push a version tag. Set the `PYPI_API_TOKEN` secret in your repo settings.

---

## 2. Windows Binary (PyInstaller)

### Prerequisites

```bash
pip install pyinstaller
pip install -e ".[windows,ocr,notifications]"
```

### Build

```bash
pyinstaller show_tracker.spec
```

Output: `dist/show-tracker/` directory containing `show-tracker.exe` and all dependencies.

### Test

```bash
dist\show-tracker\show-tracker.exe --version
dist\show-tracker\show-tracker.exe init-db
dist\show-tracker\show-tracker.exe identify "Breaking Bad S05E14"
dist\show-tracker\show-tracker.exe run
```

Verify:
- CLI commands work
- Web UI loads at http://localhost:7600
- System tray icon appears
- SMTC detection works when media is playing

### Create a ZIP for distribution

```bash
cd dist && zip -r show-tracker-windows-x86_64.zip show-tracker/
```

### Windows Installer (Optional — Inno Setup)

For a polished Windows installer with Start Menu shortcuts and uninstaller:

1. Install [Inno Setup](https://jrsoftware.org/isinfo.php)
2. Use the template at `scripts/inno_setup.iss` (or create from Inno Setup Wizard)
3. Key settings:
   - Source: `dist\show-tracker\*`
   - Default install dir: `{autopf}\ShowTracker`
   - Create Start Menu shortcut for `show-tracker.exe run`
   - Optional: "Start with Windows" checkbox → creates Startup folder shortcut
4. Compile: `iscc scripts/inno_setup.iss`

---

## 3. Linux AppImage

### Prerequisites

```bash
# Python 3.11+ and pip
sudo apt install python3 python3-pip python3-venv

# appimagetool
wget https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool
```

### Build

```bash
chmod +x scripts/build_appimage.sh
./scripts/build_appimage.sh
```

Output: `dist/ShowTracker-x86_64.AppImage`

### Test

```bash
chmod +x dist/ShowTracker-x86_64.AppImage
./dist/ShowTracker-x86_64.AppImage --version
./dist/ShowTracker-x86_64.AppImage identify "Breaking Bad S05E14"
./dist/ShowTracker-x86_64.AppImage run
```

### Automated via CI

The release workflow builds the AppImage on `ubuntu-latest` and attaches it to the GitHub Release.

---

## 4. Browser Extensions

### Package both extensions

```bash
chmod +x scripts/package_extensions.sh
./scripts/package_extensions.sh
```

This produces:
- `dist/show-tracker-chrome-v0.1.0.zip`
- `dist/show-tracker-firefox-v0.1.0.zip`

### Chrome Web Store

#### First-time setup

1. Create a developer account at https://chrome.google.com/webstore/devconsole/ ($5 one-time fee)
2. Host the privacy policy at a public URL:
   - Option A: GitHub raw URL — `https://raw.githubusercontent.com/YOUR_USER/AutoShowTracker/main/PRIVACY_POLICY.md`
   - Option B: GitHub Pages
3. Prepare store assets:
   - **Icon**: 128x128 PNG at `assets/icon-128.png`
   - **Screenshots**: 1280x800 or 640x400 PNG showing the popup and dashboard
   - **Description**: See template below

#### Submit

1. Go to the [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole/)
2. Click "New Item" → upload `dist/show-tracker-chrome-v*.zip`
3. Fill in:
   - **Category**: Productivity
   - **Language**: English
   - **Description**: (see template below)
   - **Privacy policy URL**: your hosted URL
   - **Single purpose**: "Tracks TV show and movie viewing activity across streaming sites"
   - **Permissions justification**:
     - `activeTab` / `tabs`: "Needed to read the current tab URL and page title for media detection"
     - `<all_urls>`: "Content script must run on streaming sites to extract video metadata (schema.org, Open Graph tags, video elements)"
     - `storage`: "Stores user preferences (tracking on/off, API connection URL)"
4. Upload screenshots and icon
5. Submit for review (1-3 business days)

#### Updates

1. Bump `version` in `browser_extension/chrome/manifest.json`
2. Re-run `./scripts/package_extensions.sh`
3. Upload new ZIP in the developer dashboard → "Package" tab → "Upload new package"

### Firefox Add-ons (AMO)

#### First-time setup

1. Create a developer account at https://addons.mozilla.org/developers/
2. No fee required

#### Submit

1. Go to https://addons.mozilla.org/developers/addon/submit/distribution
2. Choose "On this site" for distribution
3. Upload `dist/show-tracker-firefox-v*.zip`
4. AMO will run automated validation — fix any warnings
5. Fill in listing details (same as Chrome store)
6. Submit for review

#### Updates

1. Bump `version` in `browser_extension/firefox/manifest.json`
2. Re-run `./scripts/package_extensions.sh`
3. Upload at https://addons.mozilla.org/developers/addon/show-tracker/versions/submit/

---

## 5. GitHub Releases (Automated)

The release workflow at `.github/workflows/release.yml` triggers on version tags.

### Creating a release

```bash
# 1. Update version in pyproject.toml and both manifest.json files
# 2. Commit the version bump
git add -A && git commit -m "Bump version to 0.2.0"

# 3. Create and push a version tag
git tag v0.2.0
git push origin main --tags
```

This automatically:
1. Runs the full test suite
2. Builds the PyPI package and uploads to PyPI
3. Builds PyInstaller binaries on Windows
4. Builds Linux AppImage on Ubuntu
5. Packages both browser extensions
6. Creates a GitHub Release with all artifacts attached

### Required secrets

Set these in your repo's Settings → Secrets and variables → Actions:

| Secret | Purpose |
|--------|---------|
| `PYPI_API_TOKEN` | Publishing to PyPI |

The `GITHUB_TOKEN` is provided automatically.

---

## 6. Version Bumping

Versions must be updated in three places:

| File | Field |
|------|-------|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `browser_extension/chrome/manifest.json` | `"version": "X.Y.Z"` |
| `browser_extension/firefox/manifest.json` | `"version": "X.Y.Z"` |

The `src/show_tracker/__init__.py` should also export `__version__` matching this value.

A helper script bumps all locations:

```bash
./scripts/bump_version.sh 0.2.0
```

---

## Store Listing Template

Use this for both Chrome Web Store and Firefox Add-ons:

```
Show Tracker — Automatic Episode Tracking

Automatically detects what you're watching across Netflix, YouTube, Crunchyroll,
Disney+, Hulu, Amazon Prime Video, HBO Max, and more. Logs episode-level watch
history to a local dashboard — no cloud account required.

Features:
• Detects shows via URL patterns, schema.org metadata, Open Graph tags, and video elements
• Sends playback events (play, pause, heartbeat, ended) to the local Show Tracker service
• Works on all major streaming platforms
• Zero data leaves your machine — all processing is local
• Lightweight — minimal CPU/memory footprint

Requirements:
• Show Tracker desktop service running locally (free, open-source)
• Download at: https://github.com/YOUR_USER/AutoShowTracker

How it works:
1. Install and run the Show Tracker desktop app
2. Install this extension
3. Watch shows normally — they appear in your local dashboard automatically

Privacy:
• All data stays on your computer
• No analytics, no tracking, no cloud sync (unless you opt in to Trakt.tv)
• See full privacy policy: [URL]
```

---

## Troubleshooting

### PyInstaller: "Module not found" at runtime

Add the missing module to `hiddenimports` in `show_tracker.spec`. Common culprits:
- `sqlalchemy.dialects.sqlite`
- `uvicorn.protocols.http.auto`
- `guessit` / `rebulk` data files

### AppImage: "No such file" errors

The bundled Python venv uses absolute paths. The launcher script in `AppRun` sets `PATH` and `PYTHONPATH` relative to `$HERE` to work around this.

### Chrome extension: "Could not load manifest"

Ensure `manifest.json` is valid JSON with no trailing commas. Use `jq . manifest.json` to validate.

### Firefox extension: "strict_min_version" warning

The extension requires Firefox 109+ for WebExtension API compatibility. Older versions are not supported.

### PyPI: "File already exists" on upload

You cannot overwrite a version on PyPI. Bump the version number and rebuild.
