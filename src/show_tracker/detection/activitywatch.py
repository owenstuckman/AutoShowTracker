"""ActivityWatch integration for Show Tracker.

Provides process management for bundled ActivityWatch binaries, a REST API
client for fetching window/web events, an incremental event poller, and a
mock client for testing.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Port helpers
# ---------------------------------------------------------------------------


def _is_aw_server(port: int, timeout: float = 2.0) -> bool:
    """Return *True* if an ActivityWatch server is reachable on *port*."""
    try:
        resp = requests.get(
            f"http://localhost:{port}/api/0/info",
            timeout=timeout,
        )
        return resp.status_code == 200 and "hostname" in resp.json()
    except (requests.ConnectionError, requests.Timeout, ValueError):
        return False


def _port_is_free(port: int) -> bool:
    """Return *True* if *port* is available for binding on localhost."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("localhost", port))
        return True
    except OSError:
        return False


def find_available_port(preferred: int = 5600, search_range: int = 10) -> int:
    """Find a port for the AW server.

    If an existing ActivityWatch server is already on *preferred*, reuse it.
    Otherwise scan *preferred* .. *preferred + search_range - 1* for a free
    port.

    Raises
    ------
    RuntimeError
        If no port in the range is available.
    """
    if _is_aw_server(preferred):
        logger.info("Reusing existing ActivityWatch server on port %d", preferred)
        return preferred

    for port in range(preferred, preferred + search_range):
        if _port_is_free(port):
            return port

    raise RuntimeError(
        f"No available port for ActivityWatch server in range "
        f"{preferred}-{preferred + search_range - 1}"
    )


# ---------------------------------------------------------------------------
# ActivityWatch process manager
# ---------------------------------------------------------------------------

_MAX_CRASH_RETRIES = 3
_BACKOFF_BASE = 2  # seconds


class ActivityWatchManager:
    """Starts and stops bundled ActivityWatch processes.

    Parameters
    ----------
    aw_dir:
        Directory containing the AW binaries (``aw-server-rust``,
        ``aw-watcher-window``).
    port:
        Preferred port for ``aw-server-rust``.
    """

    def __init__(self, aw_dir: str, port: int = 5600) -> None:
        self.aw_dir = aw_dir
        self.port = port
        self.processes: list[subprocess.Popen[bytes]] = []
        self._using_external: bool = False
        self._crash_counts: dict[str, int] = {}

    # -- public API ---------------------------------------------------------

    def start(self) -> None:
        """Launch ActivityWatch components (or attach to an existing server)."""
        if _is_aw_server(self.port):
            logger.info(
                "ActivityWatch server already running on port %d — using it",
                self.port,
            )
            self._using_external = True
            return

        self.port = find_available_port(self.port)
        self._start_process("aw-server-rust", ["--port", str(self.port)])
        self._wait_for_server()
        self._start_process("aw-watcher-window", ["--port", str(self.port)])
        self._using_external = False

    def shutdown(self) -> None:
        """Gracefully terminate all managed child processes."""
        for proc in reversed(self.processes):
            try:
                proc.terminate()
            except OSError:
                pass
        for proc in self.processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.processes.clear()

    def health_check(self) -> None:
        """Check child processes and restart any that have crashed."""
        alive: list[subprocess.Popen[bytes]] = []
        for proc in self.processes:
            if proc.poll() is None:
                alive.append(proc)
            else:
                name = os.path.basename(proc.args[0]) if isinstance(proc.args, list) else "unknown"
                logger.warning(
                    "ActivityWatch process %s (pid %d) exited with code %s",
                    name,
                    proc.pid,
                    proc.returncode,
                )
                self._attempt_restart(name)
        self.processes = alive

    # -- internals ----------------------------------------------------------

    def _start_process(self, binary_name: str, extra_args: list[str] | None = None) -> None:
        binary_path = os.path.join(self.aw_dir, binary_name)
        cmd = [binary_path, *(extra_args or [])]
        logger.info("Starting %s: %s", binary_name, " ".join(cmd))
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.processes.append(proc)

    def _wait_for_server(self, timeout: int = 15) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _is_aw_server(self.port):
                logger.info("ActivityWatch server ready on port %d", self.port)
                return
            time.sleep(0.5)
        raise RuntimeError(
            f"ActivityWatch server did not become ready within {timeout}s"
        )

    def _attempt_restart(self, binary_name: str) -> None:
        count = self._crash_counts.get(binary_name, 0) + 1
        self._crash_counts[binary_name] = count

        if count > _MAX_CRASH_RETRIES:
            logger.error(
                "Giving up restarting %s after %d consecutive failures",
                binary_name,
                _MAX_CRASH_RETRIES,
            )
            return

        backoff = _BACKOFF_BASE ** count
        logger.info(
            "Restarting %s (attempt %d/%d) after %.1fs backoff",
            binary_name,
            count,
            _MAX_CRASH_RETRIES,
            backoff,
        )
        time.sleep(backoff)

        extra_args = ["--port", str(self.port)]
        try:
            self._start_process(binary_name, extra_args)
        except Exception:
            logger.exception("Failed to restart %s", binary_name)

    @property
    def using_external(self) -> bool:
        """Whether we are connected to a pre-existing AW server."""
        return self._using_external


# ---------------------------------------------------------------------------
# REST API client
# ---------------------------------------------------------------------------


class ActivityWatchClient:
    """Thin wrapper around the ActivityWatch REST API."""

    def __init__(self, port: int = 5600) -> None:
        self.base = f"http://localhost:{port}/api/0"

    def get_buckets(self) -> dict[str, Any]:
        """Return all available buckets as a mapping of id -> metadata."""
        resp = requests.get(f"{self.base}/buckets", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def get_recent_window_events(self, hostname: str, limit: int = 5) -> list[dict[str, Any]]:
        """Get recent window watcher events."""
        bucket_id = f"aw-watcher-window_{hostname}"
        return self._get_events(bucket_id, limit=limit)

    def get_recent_web_events(
        self,
        browser: str,
        hostname: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Get recent web watcher events for a specific browser."""
        bucket_id = f"aw-watcher-web-{browser}_{hostname}"
        return self._get_events(bucket_id, limit=limit)

    def get_events_since(
        self,
        bucket_id: str,
        since: datetime,
    ) -> list[dict[str, Any]]:
        """Get all events in *bucket_id* after *since*."""
        params = {
            "start": since.isoformat(),
            "end": datetime.now(timezone.utc).isoformat(),
        }
        resp = requests.get(
            f"{self.base}/buckets/{bucket_id}/events",
            params=params,
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()

    # -- internal -----------------------------------------------------------

    def _get_events(
        self,
        bucket_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        resp = requests.get(
            f"{self.base}/buckets/{bucket_id}/events",
            params={"limit": limit},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Incremental event poller
# ---------------------------------------------------------------------------


class EventPoller:
    """Tracks last-processed timestamp per bucket and returns only new events.

    Parameters
    ----------
    aw_client:
        An :class:`ActivityWatchClient` (or :class:`MockActivityWatchClient`).
    """

    def __init__(self, aw_client: ActivityWatchClient | MockActivityWatchClient) -> None:
        self.client = aw_client
        self.last_processed: dict[str, datetime] = {}

    def poll_new_events(self, bucket_id: str) -> list[dict[str, Any]]:
        """Return events in *bucket_id* newer than the last poll.

        On the very first call for a bucket, only the single most recent event
        is returned (to avoid replaying history).
        """
        since = self.last_processed.get(bucket_id)
        if since is not None:
            events: list[dict[str, Any]] = self.client.get_events_since(bucket_id, since)
        else:
            # First poll — just get the latest event.
            events = self.client._get_events(bucket_id, limit=1)

        if events:
            # AW events are returned newest-first.
            newest_ts = events[0].get("timestamp", "")
            if newest_ts:
                self.last_processed[bucket_id] = datetime.fromisoformat(newest_ts)

        return events


# ---------------------------------------------------------------------------
# Bucket discovery
# ---------------------------------------------------------------------------


def discover_media_relevant_buckets(
    client: ActivityWatchClient | MockActivityWatchClient,
) -> dict[str, list[str]]:
    """Discover window and web-watcher buckets on the AW server.

    Returns a dict with keys ``"window"`` and ``"web"``, each containing a
    list of matching bucket IDs.
    """
    buckets = client.get_buckets()
    result: dict[str, list[str]] = {"window": [], "web": []}

    for bucket_id, info in buckets.items():
        bucket_type = info.get("type", "")
        if bucket_type == "currentwindow":
            result["window"].append(bucket_id)
        elif bucket_type == "web.tab.current":
            result["web"].append(bucket_id)

    return result


# ---------------------------------------------------------------------------
# Mock client for testing
# ---------------------------------------------------------------------------


class MockActivityWatchClient:
    """Drop-in replacement for :class:`ActivityWatchClient` in tests.

    Allows injecting synthetic events without a running AW server.
    """

    def __init__(self) -> None:
        self.mock_events: list[dict[str, Any]] = []
        self._buckets: dict[str, dict[str, Any]] = {}

    def inject_event(
        self,
        app: str,
        title: str,
        url: str | None = None,
        duration: float = 10.0,
    ) -> None:
        """Simulate an ActivityWatch event."""
        data: dict[str, Any] = {"app": app, "title": title}
        if url is not None:
            data["url"] = url
        self.mock_events.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration": duration,
                "data": data,
            }
        )

    def inject_bucket(self, bucket_id: str, bucket_type: str) -> None:
        """Register a fake bucket for :meth:`get_buckets`."""
        self._buckets[bucket_id] = {"type": bucket_type}

    # -- API surface matching ActivityWatchClient ---------------------------

    def get_buckets(self) -> dict[str, Any]:
        return dict(self._buckets)

    def get_recent_window_events(self, hostname: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.mock_events[-limit:]

    def get_recent_web_events(
        self,
        browser: str,
        hostname: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        return self.mock_events[-limit:]

    def get_events_since(
        self,
        bucket_id: str,
        since: datetime,
    ) -> list[dict[str, Any]]:
        return [
            e
            for e in self.mock_events
            if datetime.fromisoformat(e["timestamp"]) > since
        ]

    def _get_events(
        self,
        bucket_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        return self.mock_events[-limit:]
