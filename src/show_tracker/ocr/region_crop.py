"""Region-of-interest cropping for OCR.

App profiles define named rectangular regions (as percentages of the window
dimensions) where media titles are typically rendered.  This avoids running
OCR on the entire window and dramatically improves both speed and accuracy.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Region:
    """A rectangular region defined as percentages of the source image."""

    name: str
    description: str
    x_pct: float
    y_pct: float
    w_pct: float
    h_pct: float

    def __post_init__(self) -> None:
        for attr in ("x_pct", "y_pct", "w_pct", "h_pct"):
            val = getattr(self, attr)
            if not (0.0 <= val <= 100.0):
                raise ValueError(f"{attr} must be between 0 and 100, got {val}")
        if self.x_pct + self.w_pct > 100.0:
            raise ValueError(
                f"Region '{self.name}' exceeds image width: "
                f"x_pct({self.x_pct}) + w_pct({self.w_pct}) > 100"
            )
        if self.y_pct + self.h_pct > 100.0:
            raise ValueError(
                f"Region '{self.name}' exceeds image height: "
                f"y_pct({self.y_pct}) + h_pct({self.h_pct}) > 100"
            )


@dataclass(frozen=True, slots=True)
class AppProfile:
    """OCR profile for a specific media player application."""

    app_name: str
    match_app_names: list[str] = field(default_factory=list)
    regions: list[Region] = field(default_factory=list)


def load_profiles(profiles_path: str | Path) -> dict[str, AppProfile]:
    """Load app profiles from a JSON file.

    Parameters
    ----------
    profiles_path:
        Path to the JSON profiles file.

    Returns
    -------
    dict[str, AppProfile]
        Mapping from canonical app name to its profile.
    """
    path = Path(profiles_path)
    if not path.exists():
        logger.warning("Profiles file not found: %s", path)
        return {}

    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load profiles from %s: %s", path, exc)
        return {}

    profiles: dict[str, AppProfile] = {}
    for entry in data.get("profiles", []):
        try:
            profile = _parse_profile(entry)
            profiles[profile.app_name] = profile
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping invalid profile entry: %s", exc)

    logger.info("Loaded %d OCR app profile(s) from %s", len(profiles), path)
    return profiles


def _parse_profile(entry: dict[str, Any]) -> AppProfile:
    """Parse a single profile entry from JSON."""
    regions = [
        Region(
            name=r["name"],
            description=r.get("description", ""),
            x_pct=float(r["x_pct"]),
            y_pct=float(r["y_pct"]),
            w_pct=float(r["w_pct"]),
            h_pct=float(r["h_pct"]),
        )
        for r in entry.get("regions", [])
    ]
    return AppProfile(
        app_name=entry["app_name"],
        match_app_names=entry.get("match_app_names", []),
        regions=regions,
    )


def find_profile(
    app_name: str, profiles: dict[str, AppProfile]
) -> AppProfile | None:
    """Find a matching profile for the given application name.

    Performs case-insensitive matching against both the canonical app_name
    and the match_app_names list.

    Parameters
    ----------
    app_name:
        The application name to match (e.g. from ActivityWatch).
    profiles:
        Loaded profiles dictionary.

    Returns
    -------
    AppProfile or None
        The matching profile, or None if no match is found.
    """
    app_lower = app_name.lower()

    # Exact canonical match
    for profile in profiles.values():
        if profile.app_name.lower() == app_lower:
            return profile

    # Check match_app_names (substring matching for flexibility)
    for profile in profiles.values():
        for name in profile.match_app_names:
            if name.lower() in app_lower or app_lower in name.lower():
                return profile

    return None


def crop_regions(
    image: Image.Image, profile: AppProfile
) -> list[tuple[str, Image.Image]]:
    """Crop the named regions from an image according to a profile.

    Parameters
    ----------
    image:
        The source screenshot.
    profile:
        The app profile defining regions to crop.

    Returns
    -------
    list of (region_name, cropped_image)
        Each cropped sub-image and its region name.  Regions with zero
        area are silently skipped.
    """
    img_w, img_h = image.size
    results: list[tuple[str, Image.Image]] = []

    for region in profile.regions:
        x = int(img_w * region.x_pct / 100.0)
        y = int(img_h * region.y_pct / 100.0)
        w = int(img_w * region.w_pct / 100.0)
        h = int(img_h * region.h_pct / 100.0)

        # Clamp to image bounds
        x2 = min(x + w, img_w)
        y2 = min(y + h, img_h)

        if x2 <= x or y2 <= y:
            logger.debug("Skipping zero-area region '%s'", region.name)
            continue

        cropped = image.crop((x, y, x2, y2))
        results.append((region.name, cropped))
        logger.debug(
            "Cropped region '%s': (%d, %d, %d, %d) from %dx%d image",
            region.name, x, y, x2, y2, img_w, img_h,
        )

    return results
