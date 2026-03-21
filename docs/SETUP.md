# Setup and Running Instructions

## Prerequisites

- **Python 3.11 or later** (3.12+ also works)
- **SQLite 3.35+** (ships with Python 3.11+)
- **Git** (for cloning the repository)
- **Operating System**: Windows 10/11, Linux (Ubuntu 20.04+, Fedora 38+, Arch), or macOS 13+ (partial support)

### Optional Prerequisites

| Feature | Requirement |
|---------|-------------|
| OCR fallback | Tesseract OCR 5.x installed and on PATH, or EasyOCR (installed via pip) |
| Windows media detection | Windows 10 1809+ (for SMTC/System Media Transport Controls) |
| Linux media detection | D-Bus session bus running (for MPRIS) |
| Browser tracking | Google Chrome or Chromium-based browser |
| VLC IPC | VLC media player with web interface enabled |
| mpv IPC | mpv media player with JSON IPC socket configured |

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/<your-username>/AutoShowTracker.git
cd AutoShowTracker
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv

# Activate it:
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (cmd)
.venv\Scripts\activate.bat

# Linux / macOS
source .venv/bin/activate
```

### 3. Install Dependencies

**Core installation** (all platforms):

```bash
pip install -e .
```

**With optional dependency groups** (pick the ones you need):

```bash
# OCR support (Tesseract and EasyOCR engines)
pip install -e ".[ocr]"

# Windows-specific (SMTC listener via winsdk)
pip install -e ".[windows]"

# Linux-specific (MPRIS listener via dbus-next)
pip install -e ".[linux]"

# Development tools (pytest, ruff, mypy)
pip install -e ".[dev]"

# Multiple groups at once
pip install -e ".[ocr,windows,dev]"
```

---

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `TMDB_API_KEY` | Your TMDb v3 API key. Required for content identification. |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `YOUTUBE_API_KEY` | YouTube Data API v3 key. Enables playlist/series detection for YouTube content. | _(empty)_ |
| `ST_DATA_DIR` | Override the default data directory. | `~/.show-tracker` |
| `ST_MEDIA_SERVICE_PORT` | Port for the HTTP API. | `7600` |
| `ST_ACTIVITYWATCH_PORT` | Port where ActivityWatch aw-server listens. | `5600` |
| `ST_AUTO_LOG_THRESHOLD` | Confidence score at or above which detections are auto-logged. | `0.9` |
| `ST_REVIEW_THRESHOLD` | Confidence score below which detections go to the unresolved queue. | `0.7` |
| `ST_OCR_ENABLED` | Enable or disable the OCR fallback. | `true` |
| `ST_HEARTBEAT_INTERVAL` | Seconds between heartbeat pulses during playback. | `30` |
| `ST_GRACE_PERIOD` | Seconds after last heartbeat before finalizing a watch event. | `120` |
| `ST_POLLING_INTERVAL` | Seconds between ActivityWatch polling cycles. | `10` |

You can also place these in a `.env` file in the project root. The `ST_` prefix applies to all settings except `TMDB_API_KEY` and `YOUTUBE_API_KEY`, which use their exact names.

### How to Get a TMDb API Key

1. Create a free account at [https://www.themoviedb.org/signup](https://www.themoviedb.org/signup).
2. Go to **Settings > API** in your account dashboard.
3. Click **Create** under the "Request an API Key" section.
4. Choose **Developer** and accept the terms of use.
5. Fill in the application details (personal/hobby use is fine).
6. Copy the **API Key (v3 auth)** value.
7. Set it in your environment:

```bash
# Linux / macOS
export TMDB_API_KEY="your_key_here"

# Windows PowerShell
$env:TMDB_API_KEY = "your_key_here"

# Or add to .env file
echo 'TMDB_API_KEY=your_key_here' >> .env
```

---

## First-Run Setup

The easiest way to get started is the interactive setup wizard:

```bash
show-tracker setup
```

This walks you through TMDb API key configuration, validates connectivity, and initializes the databases. It also runs automatically the first time you call `show-tracker run`.

### Manual Database Initialization

Alternatively, initialize the databases directly:

```bash
show-tracker init-db
```

This creates:
- `~/.show-tracker/watch_history.db` -- user's watch log, show metadata, aliases, settings
- `~/.show-tracker/media_cache.db` -- cached TMDb data (rebuildable, safe to delete)

To reset all data and start fresh:

```bash
show-tracker init-db --force
```

To use a custom data directory:

```bash
show-tracker --data-dir /path/to/custom/dir init-db
```

---

## Running the Application

### Start All Services

```bash
show-tracker run
```

This launches:
- The FastAPI HTTP API on `http://127.0.0.1:7600`
- The web UI dashboard at `http://127.0.0.1:7600/`
- ActivityWatch integration (polling)
- SMTC listener (Windows) or MPRIS listener (Linux)

**Options:**

```bash
# Bind to a different address
show-tracker run --host 0.0.0.0

# Use a different port
show-tracker run --port 8080

# Custom data directory
show-tracker --data-dir ~/my-tracker run
```

### Phase 0: Standalone Identification

Test the identification pipeline against a single string without starting the full service:

```bash
show-tracker identify "law.and.order.svu.s03e07.720p.bluray.mkv"
show-tracker identify "Breaking Bad S05E14" --source filename
show-tracker identify "Stranger Things - Netflix" --source browser_title
```

The `--source` flag provides a hint about where the string came from (`browser_title`, `filename`, `window_title`, `smtc`, `mpris`, `ocr`, `manual`).

### Test Pipeline

Run the full test dataset through the identification pipeline:

```bash
# Use the default test dataset
show-tracker test-pipeline

# Use a custom dataset
show-tracker test-pipeline --dataset tests/data/my_dataset.json

# Verbose output (show per-case results)
show-tracker test-pipeline -v
```

---

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=show_tracker

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run a specific test file
pytest tests/unit/test_parser.py

# Run tests matching a keyword
pytest -k "url_patterns"

# Run with verbose output
pytest -v
```

The project uses `pytest-asyncio` with `asyncio_mode = "auto"`, so async test functions are handled automatically.

---

## Browser Extension Installation

Extensions are available for both Chrome and Firefox in `browser_extension/`.

### Chrome

1. Open Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked**.
4. Select the `browser_extension/chrome/` directory from this repository.
5. The extension icon should appear in your toolbar.

### Firefox

1. Open Firefox and navigate to `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on**.
3. Select `browser_extension/firefox/manifest.json`.
4. The extension icon should appear in your toolbar.

### Verify Connection

1. Start the Show Tracker service (`show-tracker run`).
2. Click the extension icon in the Chrome toolbar.
3. The popup should show **Connected** status.
4. Navigate to any streaming site (Netflix, YouTube, etc.) and play a video.
5. The extension will send media events to `http://localhost:7600/api/media-event`.

### Extension Permissions

The extension requests:
- `activeTab` and `tabs` -- to read the current tab URL and title
- `storage` -- to persist the tracking enabled/disabled toggle
- `<all_urls>` host permission -- to inject the content script on streaming sites

---

## Optional: Enabling VLC Web Interface

The VLC web interface allows Show Tracker to read playback metadata via HTTP.

1. Open VLC and go to **Tools > Preferences**.
2. At the bottom, select **All** under "Show settings".
3. Navigate to **Interface > Main interfaces**.
4. Check **Web**.
5. Navigate to **Interface > Main interfaces > Lua** and set a password.
6. Restart VLC.
7. VLC's web interface will be available at `http://localhost:8080/`.

Show Tracker's VLC integration reads the currently playing file and metadata from this interface.

---

## Optional: Enabling mpv IPC Socket

mpv's JSON IPC socket allows Show Tracker to query playback state.

### Linux / macOS

Add to `~/.config/mpv/mpv.conf`:

```
input-ipc-server=/tmp/mpv-socket
```

### Windows

Add to `%APPDATA%\mpv\mpv.conf`:

```
input-ipc-server=\\.\pipe\mpv-pipe
```

After restarting mpv, Show Tracker will connect to the socket/pipe to read the current file path, playback position, and metadata.

---

## Configuration

### Configuration Priority (Highest to Lowest)

1. **Environment variables** (prefixed with `ST_`, or exact name for API keys)
2. **`.env` file** in the project root
3. **Programmatic overrides** (CLI flags like `--data-dir`, `--port`)
4. **`config/default_settings.json`** (shipped defaults)
5. **Pydantic field defaults** in `config.py`

### Data Directory Layout

```
~/.show-tracker/
  watch_history.db    # User's watch log (irreplaceable)
  media_cache.db      # TMDb cache (rebuildable)
  logs/               # Application log files
```

### Settings API

At runtime, user settings are stored in the `user_settings` table and accessible via the HTTP API:

```bash
# Get all settings
curl http://localhost:7600/api/settings

# Update a setting
curl -X PUT http://localhost:7600/api/settings/theme \
  -H "Content-Type: application/json" \
  -d '{"value": "dark"}'
```

### Show Aliases

Aliases map alternate show names to canonical entries for improved identification:

```bash
# Add an alias
curl -X POST http://localhost:7600/api/aliases \
  -H "Content-Type: application/json" \
  -d '{"show_id": 1, "alias": "SVU"}'

# List aliases for a show
curl http://localhost:7600/api/aliases/1

# Delete an alias
curl -X DELETE http://localhost:7600/api/aliases/42
```

Default aliases are seeded from `profiles/default_profiles.json`.
