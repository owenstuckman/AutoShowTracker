# ActivityWatch Integration

## Integration Strategy: Option 1 (Subprocess Bundle)

ActivityWatch is bundled as unmodified binaries shipped alongside our application. Our launcher starts ActivityWatch processes as children and communicates via its REST API. No modification of ActivityWatch source code.

## Bundled Components

From the ActivityWatch distribution, bundle these executables:

- `aw-server-rust` — the main data server (REST API on localhost:5600)
- `aw-watcher-window` — reports active window title + app name
- `aw-watcher-web` — backend for the browser extension (receives data from Chrome/Firefox extension)

Do NOT bundle:
- `aw-qt` (the ActivityWatch system tray GUI) — unnecessary; our app provides its own UI
- `aw-watcher-afk` (AFK detection) — not needed for media tracking; adds noise

## Launcher Subprocess Management

### Startup Sequence

```python
import subprocess
import requests
import time
import sys
import os

class ActivityWatchManager:
    def __init__(self, aw_dir: str, port: int = 5600):
        self.aw_dir = aw_dir  # Directory containing AW binaries
        self.port = port
        self.processes: list[subprocess.Popen] = []

    def start(self):
        """Start ActivityWatch components. Handle existing instances."""

        # 1. Check if aw-server is already running
        if self._is_server_running():
            print(f"ActivityWatch server already running on port {self.port}")
            # Option A: Use existing instance (user has AW installed independently)
            # Option B: Use a different port for our bundled instance
            # Recommendation: Use existing instance to avoid duplication
            self._using_external = True
            return

        # 2. Start aw-server-rust
        server_bin = os.path.join(self.aw_dir, "aw-server-rust")
        server_proc = subprocess.Popen(
            [server_bin, "--port", str(self.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.processes.append(server_proc)
        self._wait_for_server()

        # 3. Start aw-watcher-window
        window_bin = os.path.join(self.aw_dir, "aw-watcher-window")
        window_proc = subprocess.Popen(
            [window_bin, "--port", str(self.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.processes.append(window_proc)

        # 4. aw-watcher-web is passive — it receives data from browser extension
        # No need to start it as a process; the browser extension posts directly to aw-server

        self._using_external = False

    def _is_server_running(self) -> bool:
        try:
            r = requests.get(f"http://localhost:{self.port}/api/0/info", timeout=2)
            return r.status_code == 200
        except requests.ConnectionError:
            return False

    def _wait_for_server(self, timeout: int = 15):
        start = time.time()
        while time.time() - start < timeout:
            if self._is_server_running():
                return
            time.sleep(0.5)
        raise RuntimeError("ActivityWatch server failed to start")

    def shutdown(self):
        """Gracefully terminate all child processes."""
        for proc in reversed(self.processes):
            proc.terminate()
        for proc in self.processes:
            proc.wait(timeout=5)
        self.processes.clear()
```

### Crash Recovery

If an ActivityWatch child process dies unexpectedly:
1. Log the crash with stderr output.
2. Attempt restart (up to 3 times with exponential backoff).
3. If restart fails, continue running without that component and log a warning in the UI (e.g., "Window tracking temporarily unavailable").
4. The media identification service should handle missing data sources gracefully — if window events stop arriving, it still processes SMTC/MPRIS and browser events.

## REST API Usage

### Fetching Recent Events

```python
import requests
from datetime import datetime, timezone, timedelta

class ActivityWatchClient:
    def __init__(self, port: int = 5600):
        self.base = f"http://localhost:{port}/api/0"

    def get_buckets(self) -> list[dict]:
        """List all available buckets."""
        return requests.get(f"{self.base}/buckets").json()

    def get_recent_window_events(self, hostname: str, limit: int = 5) -> list[dict]:
        """Get recent window watcher events."""
        bucket_id = f"aw-watcher-window_{hostname}"
        return requests.get(
            f"{self.base}/buckets/{bucket_id}/events",
            params={"limit": limit}
        ).json()

    def get_recent_web_events(self, browser: str, hostname: str, limit: int = 5) -> list[dict]:
        """Get recent web watcher events."""
        # Browser name is typically "chrome" or "firefox"
        bucket_id = f"aw-watcher-web-{browser}_{hostname}"
        return requests.get(
            f"{self.base}/buckets/{bucket_id}/events",
            params={"limit": limit}
        ).json()

    def get_events_since(self, bucket_id: str, since: datetime) -> list[dict]:
        """Get all events after a given timestamp."""
        return requests.get(
            f"{self.base}/buckets/{bucket_id}/events",
            params={
                "start": since.isoformat(),
                "end": datetime.now(timezone.utc).isoformat()
            }
        ).json()
```

### Bucket Discovery

On first run, discover available buckets dynamically:

```python
def discover_media_relevant_buckets(client: ActivityWatchClient) -> dict:
    """Find window and web watcher buckets."""
    buckets = client.get_buckets()
    result = {"window": [], "web": []}

    for bucket_id, info in buckets.items():
        if info["type"] == "currentwindow":
            result["window"].append(bucket_id)
        elif info["type"] == "web.tab.current":
            result["web"].append(bucket_id)

    return result
```

### Polling Strategy

The media identification service polls ActivityWatch at a 10-second interval. To avoid re-processing events, track the timestamp of the last processed event per bucket.

```python
class EventPoller:
    def __init__(self, aw_client: ActivityWatchClient):
        self.client = aw_client
        self.last_processed: dict[str, datetime] = {}  # bucket_id -> timestamp

    def poll_new_events(self, bucket_id: str) -> list[dict]:
        since = self.last_processed.get(bucket_id)
        if since:
            events = self.client.get_events_since(bucket_id, since)
        else:
            # First poll — only get the most recent event
            events = requests.get(
                f"{self.client.base}/buckets/{bucket_id}/events",
                params={"limit": 1}
            ).json()

        if events:
            # Events are returned newest-first
            self.last_processed[bucket_id] = datetime.fromisoformat(events[0]["timestamp"])

        return events
```

## Port Conflict Handling

If port 5600 is already in use by an independent ActivityWatch instance:

1. **Preferred:** Connect to the existing instance. The user already has ActivityWatch; our data is additive.
2. **Fallback:** If the existing instance is not ActivityWatch (some other service on 5600), start our bundled instance on port 5601. Store the port in a config file so all our components know where to connect.

```python
def find_available_port(preferred: int = 5600) -> int:
    """Find a port for aw-server. Use existing AW if found."""
    try:
        r = requests.get(f"http://localhost:{preferred}/api/0/info", timeout=2)
        data = r.json()
        if "hostname" in data:  # This is an AW server
            return preferred  # Reuse it
    except (requests.ConnectionError, ValueError):
        pass

    # Port 5600 is free or occupied by non-AW service
    # Try 5600 first, then increment
    for port in range(preferred, preferred + 10):
        try:
            import socket
            s = socket.socket()
            s.bind(("localhost", port))
            s.close()
            return port
        except OSError:
            continue

    raise RuntimeError("No available port for ActivityWatch server")
```

## Browser Extension Coordination

ActivityWatch's browser extension (`aw-watcher-web`) posts events to the AW server. Our custom browser extension (see `05_BROWSER_EXTENSION.md`) is separate and posts to our media identification service. Both can run simultaneously without conflict — they serve different purposes:

- **aw-watcher-web extension:** Generic tab URL + title tracking. Feeds into ActivityWatch's general activity tracking.
- **Our extension:** Deep media identification — scrapes metadata, Open Graph tags, DOM content, video player state. Posts richer data to our service.

If the user already has aw-watcher-web installed, we still benefit from its data via the AW API (as a secondary signal). Our extension provides the primary browser detection with richer metadata.

## Data Retention and Cleanup

ActivityWatch stores all events indefinitely by default. Our application does not need to manage AW's data retention. However, for our own event processing:

- Process AW events in near-real-time (10-second poll interval).
- Do not store raw AW events in our database — only store the identified episode results.
- If the user uninstalls our application, ActivityWatch data remains untouched (it's their data, managed by their instance).

## Testing Without ActivityWatch

For development and testing, mock the ActivityWatch API:

```python
class MockActivityWatchClient:
    """Drop-in replacement for development without running AW."""

    def __init__(self):
        self.mock_events = []

    def inject_event(self, app: str, title: str, url: str | None = None):
        """Simulate an AW event for testing."""
        self.mock_events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration": 10.0,
            "data": {"app": app, "title": title, "url": url}
        })

    def get_recent_window_events(self, hostname: str, limit: int = 5):
        return self.mock_events[-limit:]
```
