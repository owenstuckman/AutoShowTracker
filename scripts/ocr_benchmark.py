#!/usr/bin/env python3
"""OCR accuracy benchmark for AutoShowTracker.

Evaluates OCR extraction accuracy against a ground-truth dataset of
screenshots from various media players.

Directory structure (create before running):

    tests/data/ocr_screenshots/
    ├── manifest.json          <- ground truth labels
    ├── vlc_720p_01.png
    ├── vlc_1080p_01.png
    ├── mpv_720p_01.png
    └── ...

manifest.json format:
    [
        {
            "file": "vlc_720p_01.png",
            "player": "vlc",
            "resolution": "720p",
            "expected_title": "Breaking Bad S01E01 - Pilot",
            "expected_show": "Breaking Bad",
            "expected_season": 1,
            "expected_episode": 1
        },
        ...
    ]

Usage:
    python scripts/ocr_benchmark.py
    python scripts/ocr_benchmark.py --engine tesseract
    python scripts/ocr_benchmark.py --engine easyocr
    python scripts/ocr_benchmark.py --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = PROJECT_ROOT / "tests" / "data" / "ocr_screenshots"
MANIFEST_PATH = DATASET_DIR / "manifest.json"

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkResult:
    file: str
    player: str
    resolution: str
    expected_title: str
    ocr_text: str
    title_match: bool
    show_match: bool
    season_match: bool
    episode_match: bool
    elapsed_ms: float
    error: str | None = None


@dataclass
class BenchmarkSummary:
    total: int = 0
    title_correct: int = 0
    show_correct: int = 0
    season_correct: int = 0
    episode_correct: int = 0
    errors: int = 0
    total_time_ms: float = 0.0
    results: list[BenchmarkResult] = field(default_factory=list)
    by_player: dict[str, dict] = field(default_factory=dict)
    by_resolution: dict[str, dict] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# OCR engines
# ---------------------------------------------------------------------------


def _ocr_tesseract(image_path: Path, region: tuple[int, int, int, int] | None = None) -> str:
    """Run Tesseract OCR on an image, optionally cropped to a region."""
    try:
        from PIL import Image
        import pytesseract  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError("Install Pillow and pytesseract: pip install Pillow pytesseract")

    img = Image.open(image_path)
    if region:
        img = img.crop(region)

    text: str = pytesseract.image_to_string(img, config="--psm 7")  # single line mode
    return text.strip()


def _ocr_easyocr(image_path: Path, region: tuple[int, int, int, int] | None = None) -> str:
    """Run EasyOCR on an image."""
    try:
        from PIL import Image
        import easyocr  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError("Install Pillow and easyocr: pip install Pillow easyocr")

    img = Image.open(image_path)
    if region:
        img = img.crop(region)

    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    results = reader.readtext(str(image_path) if not region else img)
    # Concatenate all detected text
    texts = [r[1] for r in results]
    return " ".join(texts).strip()


ENGINE_MAP = {
    "tesseract": _ocr_tesseract,
    "easyocr": _ocr_easyocr,
}

# ---------------------------------------------------------------------------
# Title / episode matching
# ---------------------------------------------------------------------------


def _normalize(s: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    import re
    return re.sub(r"\s+", " ", s.strip().lower())


def _fuzzy_contains(ocr_text: str, expected: str, threshold: float = 0.8) -> bool:
    """Check if expected text is approximately contained in OCR output."""
    try:
        from rapidfuzz import fuzz
    except ImportError:
        # Fall back to simple substring check
        return _normalize(expected) in _normalize(ocr_text)

    norm_ocr = _normalize(ocr_text)
    norm_exp = _normalize(expected)

    # Direct substring
    if norm_exp in norm_ocr:
        return True

    # Fuzzy partial match
    score = fuzz.partial_ratio(norm_exp, norm_ocr)
    return score >= threshold * 100


def _check_episode(ocr_text: str, season: int | None, episode: int | None) -> tuple[bool, bool]:
    """Check if OCR text contains the expected season/episode numbers."""
    import re

    text = _normalize(ocr_text)
    season_ok = season is None
    episode_ok = episode is None

    if season is not None:
        patterns = [
            rf"s0?{season}",
            rf"season\s*{season}",
        ]
        for p in patterns:
            if re.search(p, text):
                season_ok = True
                break

    if episode is not None:
        patterns = [
            rf"e0?{episode}\b",
            rf"episode\s*{episode}",
            rf"ep\.?\s*{episode}\b",
        ]
        for p in patterns:
            if re.search(p, text):
                episode_ok = True
                break

    return season_ok, episode_ok


# ---------------------------------------------------------------------------
# Load OCR profiles for region cropping
# ---------------------------------------------------------------------------


def _load_regions() -> dict[str, tuple[int, int, int, int]]:
    """Load player-specific OCR crop regions from default_profiles.json."""
    profiles_path = PROJECT_ROOT / "profiles" / "default_profiles.json"
    if not profiles_path.exists():
        return {}

    with open(profiles_path) as f:
        profiles = json.load(f)

    regions: dict[str, tuple[int, int, int, int]] = {}
    for profile in profiles:
        name = profile.get("app_name", "").lower()
        roi = profile.get("title_region")
        if roi and len(roi) == 4:
            regions[name] = tuple(roi)  # type: ignore[arg-type]

    return regions


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def run_benchmark(
    engine: str = "tesseract",
    verbose: bool = False,
) -> BenchmarkSummary:
    """Run the OCR benchmark against the ground-truth dataset."""

    if not DATASET_DIR.is_dir():
        print(f"ERROR: Dataset directory not found: {DATASET_DIR}")
        print("Create it and add screenshots + manifest.json. See script docstring for format.")
        sys.exit(1)

    if not MANIFEST_PATH.is_file():
        print(f"ERROR: manifest.json not found at {MANIFEST_PATH}")
        sys.exit(1)

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    if not manifest:
        print("ERROR: manifest.json is empty")
        sys.exit(1)

    ocr_func = ENGINE_MAP.get(engine)
    if ocr_func is None:
        print(f"ERROR: Unknown engine '{engine}'. Available: {list(ENGINE_MAP.keys())}")
        sys.exit(1)

    regions = _load_regions()
    summary = BenchmarkSummary()

    print(f"=== OCR Accuracy Benchmark ===")
    print(f"Engine: {engine}")
    print(f"Dataset: {DATASET_DIR}")
    print(f"Samples: {len(manifest)}")
    print()

    for entry in manifest:
        img_path = DATASET_DIR / entry["file"]
        player = entry.get("player", "unknown")
        resolution = entry.get("resolution", "unknown")
        expected_title = entry.get("expected_title", "")
        expected_show = entry.get("expected_show", "")
        expected_season = entry.get("expected_season")
        expected_episode = entry.get("expected_episode")

        summary.total += 1

        if not img_path.is_file():
            result = BenchmarkResult(
                file=entry["file"], player=player, resolution=resolution,
                expected_title=expected_title, ocr_text="",
                title_match=False, show_match=False,
                season_match=False, episode_match=False,
                elapsed_ms=0, error=f"File not found: {img_path}",
            )
            summary.errors += 1
            summary.results.append(result)
            continue

        # Get crop region for this player
        region = regions.get(player)

        t0 = time.perf_counter()
        try:
            ocr_text = ocr_func(img_path, region=region)
        except Exception as e:
            result = BenchmarkResult(
                file=entry["file"], player=player, resolution=resolution,
                expected_title=expected_title, ocr_text="",
                title_match=False, show_match=False,
                season_match=False, episode_match=False,
                elapsed_ms=0, error=str(e),
            )
            summary.errors += 1
            summary.results.append(result)
            continue
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Evaluate
        title_match = _fuzzy_contains(ocr_text, expected_title) if expected_title else True
        show_match = _fuzzy_contains(ocr_text, expected_show) if expected_show else True
        season_ok, episode_ok = _check_episode(ocr_text, expected_season, expected_episode)

        if title_match:
            summary.title_correct += 1
        if show_match:
            summary.show_correct += 1
        if season_ok:
            summary.season_correct += 1
        if episode_ok:
            summary.episode_correct += 1

        summary.total_time_ms += elapsed_ms

        result = BenchmarkResult(
            file=entry["file"], player=player, resolution=resolution,
            expected_title=expected_title, ocr_text=ocr_text,
            title_match=title_match, show_match=show_match,
            season_match=season_ok, episode_match=episode_ok,
            elapsed_ms=elapsed_ms,
        )
        summary.results.append(result)

        # Track per-player and per-resolution stats
        for group_key, group_val, group_dict in [
            ("player", player, summary.by_player),
            ("resolution", resolution, summary.by_resolution),
        ]:
            if group_val not in group_dict:
                group_dict[group_val] = {"total": 0, "title": 0, "show": 0, "season": 0, "episode": 0}
            group_dict[group_val]["total"] += 1
            if title_match:
                group_dict[group_val]["title"] += 1
            if show_match:
                group_dict[group_val]["show"] += 1
            if season_ok:
                group_dict[group_val]["season"] += 1
            if episode_ok:
                group_dict[group_val]["episode"] += 1

        if verbose:
            status = "PASS" if (title_match and show_match and season_ok and episode_ok) else "FAIL"
            print(f"  [{status}] {entry['file']} ({elapsed_ms:.0f}ms)")
            if not title_match:
                print(f"         Title mismatch: expected '{expected_title}', got '{ocr_text[:80]}'")

    return summary


def _print_summary(summary: BenchmarkSummary) -> None:
    """Print a formatted benchmark report."""
    total = summary.total or 1  # avoid division by zero

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Total samples:     {summary.total}")
    print(f"  Errors:            {summary.errors}")
    print(f"  Title accuracy:    {summary.title_correct}/{summary.total} ({100*summary.title_correct/total:.1f}%)")
    print(f"  Show name:         {summary.show_correct}/{summary.total} ({100*summary.show_correct/total:.1f}%)")
    print(f"  Season number:     {summary.season_correct}/{summary.total} ({100*summary.season_correct/total:.1f}%)")
    print(f"  Episode number:    {summary.episode_correct}/{summary.total} ({100*summary.episode_correct/total:.1f}%)")
    print(f"  Avg OCR time:      {summary.total_time_ms/total:.0f}ms per image")
    print()

    if summary.by_player:
        print("Per-player breakdown:")
        for player, stats in sorted(summary.by_player.items()):
            t = stats["total"] or 1
            print(f"  {player:12s}  title={stats['title']}/{stats['total']} ({100*stats['title']/t:.0f}%)  "
                  f"show={stats['show']}/{stats['total']}  season={stats['season']}/{stats['total']}  "
                  f"episode={stats['episode']}/{stats['total']}")
        print()

    if summary.by_resolution:
        print("Per-resolution breakdown:")
        for res, stats in sorted(summary.by_resolution.items()):
            t = stats["total"] or 1
            print(f"  {res:12s}  title={stats['title']}/{stats['total']} ({100*stats['title']/t:.0f}%)  "
                  f"show={stats['show']}/{stats['total']}  season={stats['season']}/{stats['total']}  "
                  f"episode={stats['episode']}/{stats['total']}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="OCR accuracy benchmark for AutoShowTracker")
    parser.add_argument("--engine", choices=list(ENGINE_MAP.keys()), default="tesseract",
                        help="OCR engine to benchmark (default: tesseract)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print per-image results")
    parser.add_argument("--json", dest="json_out", metavar="PATH",
                        help="Write results to a JSON file")
    args = parser.parse_args()

    summary = run_benchmark(engine=args.engine, verbose=args.verbose)
    _print_summary(summary)

    if args.json_out:
        out_path = Path(args.json_out)
        out_data = {
            "engine": args.engine,
            "total": summary.total,
            "title_accuracy": summary.title_correct / max(summary.total, 1),
            "show_accuracy": summary.show_correct / max(summary.total, 1),
            "season_accuracy": summary.season_correct / max(summary.total, 1),
            "episode_accuracy": summary.episode_correct / max(summary.total, 1),
            "errors": summary.errors,
            "avg_time_ms": summary.total_time_ms / max(summary.total, 1),
            "by_player": summary.by_player,
            "by_resolution": summary.by_resolution,
        }
        out_path.write_text(json.dumps(out_data, indent=2))
        print(f"\nJSON results written to: {out_path}")


if __name__ == "__main__":
    main()
