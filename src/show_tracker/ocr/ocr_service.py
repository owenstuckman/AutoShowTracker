"""OCR orchestrator -- the public interface for the OCR subsystem.

Ties together screenshot capture, region cropping, and OCR engine execution
to extract the most likely media title from a running player window.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from show_tracker.ocr.engine import OCRResult, get_ocr_engine
from show_tracker.ocr.region_crop import crop_regions, find_profile, load_profiles
from show_tracker.ocr.screenshot import capture_window

if TYPE_CHECKING:
    from show_tracker.ocr.engine import OCREngine
    from show_tracker.ocr.region_crop import AppProfile

logger = logging.getLogger(__name__)

_DEFAULT_PROFILES_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "profiles" / "default_profiles.json"
)

# Patterns that look like media file names or episode strings
_MEDIA_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"S\d{1,2}\s*E\d{1,2}", re.IGNORECASE),        # S01E02
    re.compile(r"\b\d{1,2}x\d{1,2}\b"),                         # 1x02
    re.compile(r"(?:season|series)\s*\d+", re.IGNORECASE),       # Season 3
    re.compile(r"(?:episode|ep\.?)\s*\d+", re.IGNORECASE),       # Episode 5
    re.compile(r"\.\w{2,4}$"),                                    # .mkv, .mp4
    re.compile(r"\b(?:720|1080|2160)[pi]?\b", re.IGNORECASE),    # Resolution hints
    re.compile(r"\b(?:HDTV|WEB-?DL|BluRay|BRRip)\b", re.IGNORECASE),
]

# Strings commonly found in player chrome (not media titles)
_NOISE_STRINGS = {
    "file", "edit", "view", "playback", "audio", "video", "subtitle",
    "tools", "help", "menu", "open", "close", "pause", "play", "stop",
    "volume", "mute", "fullscreen", "preferences", "settings",
}


class OCRService:
    """High-level OCR service for extracting media titles from player windows.

    Usage::

        service = OCRService()
        title = service.process("vlc.exe", hwnd=0x12345)
    """

    def __init__(
        self,
        *,
        profiles_path: str | Path | None = None,
        preferred_engine: str = "tesseract",
        platform: str | None = None,
    ) -> None:
        """
        Parameters
        ----------
        profiles_path:
            Path to the JSON app profiles file.  Defaults to the bundled
            ``profiles/default_profiles.json``.
        preferred_engine:
            Which OCR engine to prefer (``"tesseract"`` or ``"easyocr"``).
        platform:
            Override platform detection for screenshot capture.
        """
        path = Path(profiles_path) if profiles_path else _DEFAULT_PROFILES_PATH
        self._profiles = load_profiles(path)
        self._platform = platform

        self._engine: OCREngine | None = None
        self._preferred_engine = preferred_engine

    @property
    def engine(self) -> OCREngine:
        """Lazy-load the OCR engine on first use."""
        if self._engine is None:
            self._engine = get_ocr_engine(self._preferred_engine)
        return self._engine

    def process(self, app_name: str, hwnd_or_window_id: int) -> str | None:
        """Extract the most likely media title from a player window.

        Parameters
        ----------
        app_name:
            The application name (e.g. ``"vlc.exe"``, ``"mpv"``).
        hwnd_or_window_id:
            Window handle (Windows) or X11 window ID (Linux).

        Returns
        -------
        str or None
            The best candidate media title, or None if OCR could not
            extract a usable result.
        """
        # 1. Capture the window
        try:
            screenshot = capture_window(hwnd_or_window_id, platform=self._platform)
        except (RuntimeError, NotImplementedError) as exc:
            logger.error("Screenshot capture failed for %s: %s", app_name, exc)
            return None

        # 2. Try profile-guided region cropping
        profile = find_profile(app_name, self._profiles)
        if profile and profile.regions:
            return self._process_with_profile(screenshot, profile)

        # 3. Fall back to full-window OCR with spatial filtering
        logger.debug("No profile for '%s', using full-window fallback", app_name)
        return self._process_full_window(screenshot)

    def _process_with_profile(
        self, screenshot: Image.Image, profile: AppProfile
    ) -> str | None:
        """Run OCR on profiled regions and return the best candidate."""
        regions = crop_regions(screenshot, profile)
        if not regions:
            logger.warning("No valid regions cropped for profile '%s'", profile.app_name)
            return self._process_full_window(screenshot)

        all_results: list[tuple[str, list[OCRResult]]] = []
        for region_name, cropped_img in regions:
            results = self.engine.extract_text(cropped_img)
            if results:
                all_results.append((region_name, results))
                logger.debug(
                    "Region '%s': %d text segments",
                    region_name, len(results),
                )

        if not all_results:
            logger.debug("No text found in profiled regions, falling back to full window")
            return self._process_full_window(screenshot)

        # Concatenate text from each region and score
        best_text: str | None = None
        best_score = -1.0

        for region_name, results in all_results:
            combined = " ".join(r.text for r in results)
            avg_conf = sum(r.confidence for r in results) / len(results)
            media_score = _score_media_text(combined)
            total_score = avg_conf * 0.4 + media_score * 0.6

            logger.debug(
                "Region '%s': text='%s', conf=%.2f, media_score=%.2f, total=%.2f",
                region_name, combined[:80], avg_conf, media_score, total_score,
            )

            if total_score > best_score:
                best_score = total_score
                best_text = combined

        if best_text and best_score > 0.15:
            return _clean_title(best_text)

        return None

    def _process_full_window(self, screenshot: Image.Image) -> str | None:
        """Full-window OCR with spatial filtering.

        Keeps text found in the top/bottom 15% of the window (where title
        bars and status bars typically live) and applies a media-pattern
        scoring heuristic.
        """
        results = self.engine.extract_text(screenshot)
        if not results:
            return None

        img_h = screenshot.height

        # Spatial filter: keep results in top or bottom 15%
        top_cutoff = img_h * 0.15
        bottom_cutoff = img_h * 0.85
        spatial_filtered: list[OCRResult] = []

        for r in results:
            if r.bounding_box is None:
                # Without position info, include it but with reduced weight
                spatial_filtered.append(r)
                continue

            _, y1, _, y2 = r.bounding_box
            center_y = (y1 + y2) / 2
            if center_y <= top_cutoff or center_y >= bottom_cutoff:
                spatial_filtered.append(r)

        if not spatial_filtered:
            # If spatial filtering removed everything, fall back to all results
            spatial_filtered = results

        # Font size heuristic: prefer larger text (likely the title)
        scored: list[tuple[str, float]] = []
        for r in spatial_filtered:
            text = r.text.strip()
            if not text or text.lower() in _NOISE_STRINGS:
                continue
            if len(text) < 3:
                continue

            # Estimate "font size" from bounding box height
            font_size_score = 0.0
            if r.bounding_box:
                _, y1, _, y2 = r.bounding_box
                height = y2 - y1
                # Normalise: assume title text is 15-60 px tall in a typical window
                font_size_score = min(height / 40.0, 1.0)

            media_score = _score_media_text(text)
            conf_score = r.confidence

            total = conf_score * 0.3 + media_score * 0.4 + font_size_score * 0.3
            scored.append((text, total))

        if not scored:
            return None

        scored.sort(key=lambda x: x[1], reverse=True)

        # Try to assemble a title from the top-scoring segments
        best_text = scored[0][0]
        best_score = scored[0][1]

        if best_score > 0.15:
            return _clean_title(best_text)

        return None


# ---------------------------------------------------------------------------
# Scoring and cleaning helpers
# ---------------------------------------------------------------------------

def _score_media_text(text: str) -> float:
    """Score how likely a text string is to be a media title.

    Returns a value between 0.0 and 1.0.
    """
    if not text:
        return 0.0

    score = 0.0
    matches = 0

    for pattern in _MEDIA_PATTERNS:
        if pattern.search(text):
            matches += 1

    if matches > 0:
        score += min(matches * 0.25, 0.75)

    # Length heuristic: media titles are usually 5-100 chars
    text_len = len(text)
    if 5 <= text_len <= 100:
        score += 0.15
    elif text_len > 100:
        score += 0.05

    # Penalise if the text is a common noise string
    words = set(text.lower().split())
    noise_overlap = words & _NOISE_STRINGS
    if noise_overlap:
        score -= len(noise_overlap) * 0.15

    return max(0.0, min(score, 1.0))


def _clean_title(text: str) -> str:
    """Clean up raw OCR text into a plausible media title.

    Removes common artefacts like leading/trailing dashes, extra whitespace,
    and player-specific chrome text.
    """
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Remove common player prefixes
    for prefix in ("VLC media player -", "mpv -", "MPC-HC -", "Plex -"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()

    # Remove trailing " - VLC media player" etc.
    for suffix in ("- VLC media player", "- mpv", "- MPC-HC", "- Plex"):
        if text.lower().endswith(suffix.lower()):
            text = text[: -len(suffix)].strip()

    # Strip leading/trailing dashes and dots
    text = text.strip("-. ")

    return text if text else ""
