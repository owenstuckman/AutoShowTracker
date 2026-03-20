#!/usr/bin/env python3
"""API load test for AutoShowTracker.

Simulates multiple concurrent browser extension "viewers" sending heartbeat
events every N seconds to the FastAPI server, and measures latency, throughput,
and error rates.

Uses httpx (already a project dependency) — no external load testing framework needed.

Prerequisites:
    - The API server must be running: show-tracker run
    - Or: uvicorn show_tracker.api.app:app --host 127.0.0.1 --port 7600

Usage:
    python scripts/load_test.py
    python scripts/load_test.py --viewers 20 --duration 120 --interval 15
    python scripts/load_test.py --url http://192.168.1.10:7600
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://127.0.0.1:7600"
DEFAULT_VIEWERS = 10
DEFAULT_DURATION_SECONDS = 60
DEFAULT_HEARTBEAT_INTERVAL = 15  # seconds

# Sample show data for generating realistic events
SAMPLE_SHOWS = [
    ("Breaking Bad S01E01 - Pilot", "https://www.netflix.com/watch/70143836"),
    ("Stranger Things S04E07 - The Massacre at Hawkins Lab", "https://www.netflix.com/watch/81002431"),
    ("The Office S03E16 - Business School", "https://www.netflix.com/watch/70080613"),
    ("Attack on Titan S04E28 - The Dawn of Humanity", "https://www.crunchyroll.com/watch/GK9U3KWZ7"),
    ("Game of Thrones S08E03 - The Long Night", "https://play.hbomax.com/episode/urn:hbo:episode:GVU2cggagzYNJjhsJATwo"),
    ("The Mandalorian S03E08 - The Return", "https://www.disneyplus.com/video/98765432-abcd-1234"),
    ("Succession S04E10 - With Open Eyes", "https://play.hbomax.com/episode/urn:hbo:episode:GYdj8xgF3zsPDwwEAAAch"),
    ("One Piece Episode 1089", "https://www.crunchyroll.com/watch/G9DUE5X54"),
    ("Jujutsu Kaisen S02E23", "https://www.crunchyroll.com/watch/GRDV0P1EY"),
    ("The Bear S02E06 - Fishes", "https://www.hulu.com/watch/abcdef12-3456-7890"),
]


# ---------------------------------------------------------------------------
# Event builder
# ---------------------------------------------------------------------------


def _build_media_event(
    event_type: str,
    show_index: int,
    position: float = 0.0,
    duration: float = 2700.0,
) -> dict[str, Any]:
    """Build a MediaEventIn-compatible JSON payload."""
    title, url = SAMPLE_SHOWS[show_index % len(SAMPLE_SHOWS)]

    return {
        "type": event_type,
        "timestamp": int(time.time() * 1000),
        "tab_url": url,
        "tab_id": 100 + show_index,
        "metadata": {
            "url": url,
            "url_match": None,
            "schema": [],
            "og": {},
            "title": title,
            "video": [
                {
                    "playing": event_type not in ("pause", "ended"),
                    "currentTime": position,
                    "duration": duration,
                    "src": "",
                    "playerType": "unknown",
                }
            ],
        },
        "position": position,
        "duration": duration,
        "source": "show-tracker-content",
    }


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


@dataclass
class RequestResult:
    status_code: int
    latency_ms: float
    error: str | None = None


@dataclass
class LoadTestResults:
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time

    @property
    def requests_per_second(self) -> float:
        d = self.duration_seconds
        return self.total_requests / d if d > 0 else 0

    @property
    def success_rate(self) -> float:
        return self.successful / self.total_requests if self.total_requests > 0 else 0

    @property
    def p50_ms(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0

    @property
    def p95_ms(self) -> float:
        if not self.latencies_ms:
            return 0
        sorted_l = sorted(self.latencies_ms)
        idx = int(len(sorted_l) * 0.95)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def p99_ms(self) -> float:
        if not self.latencies_ms:
            return 0
        sorted_l = sorted(self.latencies_ms)
        idx = int(len(sorted_l) * 0.99)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def max_ms(self) -> float:
        return max(self.latencies_ms) if self.latencies_ms else 0

    @property
    def avg_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0


# ---------------------------------------------------------------------------
# Viewer coroutine
# ---------------------------------------------------------------------------


async def _simulate_viewer(
    viewer_id: int,
    client: httpx.AsyncClient,
    base_url: str,
    duration: float,
    interval: float,
    results: LoadTestResults,
) -> None:
    """Simulate a single browser extension viewer sending events."""

    show_index = viewer_id
    position = 0.0
    episode_duration = random.uniform(1200, 3600)  # 20-60 min

    # Send initial play event
    payload = _build_media_event("play", show_index, position, episode_duration)
    await _send_event(client, base_url, payload, results)

    start = time.monotonic()
    while time.monotonic() - start < duration:
        await asyncio.sleep(interval + random.uniform(-1, 1))  # jitter

        position += interval
        if position >= episode_duration:
            # Episode ended
            payload = _build_media_event("ended", show_index, episode_duration, episode_duration)
            await _send_event(client, base_url, payload, results)
            # Start next episode
            show_index = (show_index + 1) % len(SAMPLE_SHOWS)
            position = 0.0
            episode_duration = random.uniform(1200, 3600)
            payload = _build_media_event("play", show_index, position, episode_duration)
            await _send_event(client, base_url, payload, results)
        else:
            # Heartbeat
            payload = _build_media_event("heartbeat", show_index, position, episode_duration)
            await _send_event(client, base_url, payload, results)

    # Send pause at end
    payload = _build_media_event("pause", show_index, position, episode_duration)
    await _send_event(client, base_url, payload, results)


async def _send_event(
    client: httpx.AsyncClient,
    base_url: str,
    payload: dict[str, Any],
    results: LoadTestResults,
) -> None:
    """Send a single event and record the result."""
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{base_url}/api/media-event", json=payload, timeout=10.0)
        latency_ms = (time.perf_counter() - t0) * 1000
        results.total_requests += 1
        results.latencies_ms.append(latency_ms)
        if r.status_code == 200:
            results.successful += 1
        else:
            results.failed += 1
            results.errors.append(f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000
        results.total_requests += 1
        results.failed += 1
        results.latencies_ms.append(latency_ms)
        results.errors.append(str(e))


# ---------------------------------------------------------------------------
# Health check + read endpoints
# ---------------------------------------------------------------------------


async def _check_health_and_reads(
    client: httpx.AsyncClient,
    base_url: str,
    duration: float,
    results: LoadTestResults,
) -> None:
    """Periodically hit read endpoints to test concurrent read/write."""
    start = time.monotonic()
    while time.monotonic() - start < duration:
        await asyncio.sleep(5)

        for endpoint in ["/api/health", "/api/currently-watching"]:
            t0 = time.perf_counter()
            try:
                r = await client.get(f"{base_url}{endpoint}", timeout=10.0)
                latency_ms = (time.perf_counter() - t0) * 1000
                results.total_requests += 1
                results.latencies_ms.append(latency_ms)
                if r.status_code == 200:
                    results.successful += 1
                else:
                    results.failed += 1
            except Exception as e:
                latency_ms = (time.perf_counter() - t0) * 1000
                results.total_requests += 1
                results.failed += 1
                results.latencies_ms.append(latency_ms)
                results.errors.append(str(e))


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


async def run_load_test(
    base_url: str = DEFAULT_BASE_URL,
    num_viewers: int = DEFAULT_VIEWERS,
    duration: int = DEFAULT_DURATION_SECONDS,
    interval: int = DEFAULT_HEARTBEAT_INTERVAL,
) -> LoadTestResults:
    """Run the load test with the given parameters."""

    results = LoadTestResults()

    # Verify server is reachable
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{base_url}/api/health", timeout=5.0)
            if r.status_code != 200:
                print(f"ERROR: Server returned {r.status_code} on health check")
                return results
        except Exception as e:
            print(f"ERROR: Cannot reach server at {base_url}: {e}")
            print("Start the server first: show-tracker run")
            return results

    print(f"=== AutoShowTracker API Load Test ===")
    print(f"Server:     {base_url}")
    print(f"Viewers:    {num_viewers}")
    print(f"Duration:   {duration}s")
    print(f"Interval:   {interval}s heartbeats")
    print(f"Expected:   ~{num_viewers * (duration // interval)} heartbeat events + play/pause/ended")
    print()
    print("Running...")

    results.start_time = time.time()

    async with httpx.AsyncClient() as client:
        tasks = []

        # Create viewer tasks
        for i in range(num_viewers):
            tasks.append(
                asyncio.create_task(
                    _simulate_viewer(i, client, base_url, duration, interval, results)
                )
            )

        # Also run read endpoint checks
        tasks.append(
            asyncio.create_task(
                _check_health_and_reads(client, base_url, duration, results)
            )
        )

        await asyncio.gather(*tasks)

    results.end_time = time.time()
    return results


def _print_results(results: LoadTestResults) -> None:
    """Print formatted load test results."""
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Duration:          {results.duration_seconds:.1f}s")
    print(f"  Total requests:    {results.total_requests}")
    print(f"  Successful:        {results.successful}")
    print(f"  Failed:            {results.failed}")
    print(f"  Success rate:      {results.success_rate*100:.1f}%")
    print(f"  Requests/sec:      {results.requests_per_second:.1f}")
    print()
    print("  Latency:")
    print(f"    Average:         {results.avg_ms:.1f}ms")
    print(f"    P50 (median):    {results.p50_ms:.1f}ms")
    print(f"    P95:             {results.p95_ms:.1f}ms")
    print(f"    P99:             {results.p99_ms:.1f}ms")
    print(f"    Max:             {results.max_ms:.1f}ms")

    if results.failed > 0:
        print()
        print(f"  Errors ({results.failed} total):")
        # Show unique errors
        unique_errors = list(set(results.errors[:20]))
        for err in unique_errors[:5]:
            print(f"    - {err[:120]}")

    # Pass/fail assessment
    print()
    passed = True
    if results.success_rate < 0.99:
        print("  FAIL: Success rate below 99%")
        passed = False
    if results.p95_ms > 500:
        print("  FAIL: P95 latency above 500ms")
        passed = False
    if results.max_ms > 5000:
        print("  WARN: Max latency above 5000ms (possible database lock)")

    if passed:
        print("  PASS: All targets met")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="API load test for AutoShowTracker")
    parser.add_argument("--url", default=DEFAULT_BASE_URL,
                        help=f"Base URL of the API server (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--viewers", type=int, default=DEFAULT_VIEWERS,
                        help=f"Number of concurrent viewers (default: {DEFAULT_VIEWERS})")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION_SECONDS,
                        help=f"Test duration in seconds (default: {DEFAULT_DURATION_SECONDS})")
    parser.add_argument("--interval", type=int, default=DEFAULT_HEARTBEAT_INTERVAL,
                        help=f"Heartbeat interval in seconds (default: {DEFAULT_HEARTBEAT_INTERVAL})")
    parser.add_argument("--json", dest="json_out", metavar="PATH",
                        help="Write results to a JSON file")
    args = parser.parse_args()

    results = asyncio.run(run_load_test(
        base_url=args.url,
        num_viewers=args.viewers,
        duration=args.duration,
        interval=args.interval,
    ))

    _print_results(results)

    if args.json_out:
        from pathlib import Path
        out_data = {
            "url": args.url,
            "viewers": args.viewers,
            "duration": args.duration,
            "interval": args.interval,
            "total_requests": results.total_requests,
            "successful": results.successful,
            "failed": results.failed,
            "success_rate": results.success_rate,
            "rps": results.requests_per_second,
            "latency_avg_ms": results.avg_ms,
            "latency_p50_ms": results.p50_ms,
            "latency_p95_ms": results.p95_ms,
            "latency_p99_ms": results.p99_ms,
            "latency_max_ms": results.max_ms,
        }
        Path(args.json_out).write_text(json.dumps(out_data, indent=2))
        print(f"\nJSON results written to: {args.json_out}")


if __name__ == "__main__":
    main()
