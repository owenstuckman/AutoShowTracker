"""Unit tests for the OCR subsystem.

Covers:
- Region cropping (load_profiles, find_profile, crop_regions)
- Engine selection (get_ocr_engine, OCRResult dataclass)
- Preprocessing (preprocess function)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from PIL import Image

from show_tracker.ocr.engine import OCRResult, preprocess
from show_tracker.ocr.region_crop import (
    AppProfile,
    Region,
    crop_regions,
    find_profile,
    load_profiles,
)

# ---------------------------------------------------------------------------
# TestRegionCropping
# ---------------------------------------------------------------------------


class TestRegionCropping:
    """Tests for load_profiles, find_profile, and crop_regions."""

    def _make_profiles_json(self, tmp_path: Path) -> Path:
        """Write a minimal valid profiles JSON file and return its path."""
        data = {
            "profiles": [
                {
                    "app_name": "vlc",
                    "match_app_names": ["vlc media player", "vlc.exe"],
                    "regions": [
                        {
                            "name": "title_bar",
                            "description": "Top title bar",
                            "x_pct": 0.0,
                            "y_pct": 0.0,
                            "w_pct": 100.0,
                            "h_pct": 10.0,
                        }
                    ],
                },
                {
                    "app_name": "mpv",
                    "match_app_names": ["mpv.exe"],
                    "regions": [
                        {
                            "name": "osd",
                            "description": "On-screen display",
                            "x_pct": 0.0,
                            "y_pct": 85.0,
                            "w_pct": 80.0,
                            "h_pct": 10.0,
                        }
                    ],
                },
            ]
        }
        profiles_file = tmp_path / "profiles.json"
        profiles_file.write_text(json.dumps(data), encoding="utf-8")
        return profiles_file

    def test_load_profiles_valid_file(self, tmp_path: Path) -> None:
        """load_profiles() with a valid JSON file loads all profiles."""
        profiles_file = self._make_profiles_json(tmp_path)
        profiles = load_profiles(profiles_file)

        assert len(profiles) == 2
        assert "vlc" in profiles
        assert "mpv" in profiles

    def test_load_profiles_app_name_and_regions(self, tmp_path: Path) -> None:
        """Loaded profiles have the expected app_name and regions."""
        profiles_file = self._make_profiles_json(tmp_path)
        profiles = load_profiles(profiles_file)

        vlc = profiles["vlc"]
        assert vlc.app_name == "vlc"
        assert len(vlc.regions) == 1
        assert vlc.regions[0].name == "title_bar"
        assert vlc.regions[0].y_pct == 0.0
        assert vlc.regions[0].h_pct == 10.0

    def test_load_profiles_missing_file_returns_empty(self) -> None:
        """load_profiles() returns {} for a non-existent path."""
        profiles = load_profiles("/non/existent/path/profiles.json")
        assert profiles == {}

    def test_load_profiles_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        """load_profiles() returns {} when the JSON is malformed."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json}", encoding="utf-8")
        profiles = load_profiles(bad_file)
        assert profiles == {}

    def test_find_profile_exact_match(self, tmp_path: Path) -> None:
        """find_profile() returns the matching profile for an exact app name."""
        profiles_file = self._make_profiles_json(tmp_path)
        profiles = load_profiles(profiles_file)

        result = find_profile("vlc", profiles)
        assert result is not None
        assert result.app_name == "vlc"

    def test_find_profile_case_insensitive_canonical(self, tmp_path: Path) -> None:
        """find_profile() matches the canonical name case-insensitively."""
        profiles_file = self._make_profiles_json(tmp_path)
        profiles = load_profiles(profiles_file)

        result = find_profile("VLC", profiles)
        assert result is not None
        assert result.app_name == "vlc"

    def test_find_profile_match_app_names(self, tmp_path: Path) -> None:
        """find_profile() matches against match_app_names list."""
        profiles_file = self._make_profiles_json(tmp_path)
        profiles = load_profiles(profiles_file)

        result = find_profile("vlc.exe", profiles)
        assert result is not None
        assert result.app_name == "vlc"

    def test_find_profile_no_match_returns_none(self, tmp_path: Path) -> None:
        """find_profile() returns None when no profile matches."""
        profiles_file = self._make_profiles_json(tmp_path)
        profiles = load_profiles(profiles_file)

        result = find_profile("unknown_player_xyz", profiles)
        assert result is None

    def test_find_profile_empty_profiles(self) -> None:
        """find_profile() returns None for an empty profiles dict."""
        result = find_profile("vlc", {})
        assert result is None

    def test_crop_regions_dimensions(self) -> None:
        """crop_regions() crops to expected pixel dimensions."""
        # 200 x 100 image; region covers top 50% of width and top 20% of height
        img = Image.new("RGB", (200, 100), color=(128, 64, 32))
        region = Region(
            name="test_region",
            description="",
            x_pct=0.0,
            y_pct=0.0,
            w_pct=50.0,
            h_pct=20.0,
        )
        profile = AppProfile(app_name="test_app", match_app_names=[], regions=[region])

        crops = crop_regions(img, profile)
        assert len(crops) == 1

        name, cropped = crops[0]
        assert name == "test_region"
        # 50% of 200 = 100, 20% of 100 = 20
        assert cropped.size == (100, 20)

    def test_crop_regions_multiple_regions(self) -> None:
        """crop_regions() returns one entry per valid region."""
        img = Image.new("RGB", (400, 200))
        regions = [
            Region(name="top", description="", x_pct=0.0, y_pct=0.0, w_pct=100.0, h_pct=15.0),
            Region(name="bottom", description="", x_pct=0.0, y_pct=85.0, w_pct=100.0, h_pct=15.0),
        ]
        profile = AppProfile(app_name="multi", match_app_names=[], regions=regions)

        crops = crop_regions(img, profile)
        assert len(crops) == 2
        assert crops[0][0] == "top"
        assert crops[1][0] == "bottom"

    def test_crop_regions_no_regions(self) -> None:
        """crop_regions() returns empty list when profile has no regions."""
        img = Image.new("RGB", (100, 50))
        profile = AppProfile(app_name="empty", match_app_names=[], regions=[])
        crops = crop_regions(img, profile)
        assert crops == []

    def test_region_validation_out_of_bounds(self) -> None:
        """Region raises ValueError when percentages exceed 100."""
        with pytest.raises(ValueError):
            Region(
                name="bad",
                description="",
                x_pct=50.0,
                y_pct=0.0,
                w_pct=60.0,  # 50 + 60 > 100
                h_pct=10.0,
            )

    def test_region_validation_negative(self) -> None:
        """Region raises ValueError for negative percentages."""
        with pytest.raises(ValueError):
            Region(name="bad", description="", x_pct=-1.0, y_pct=0.0, w_pct=50.0, h_pct=10.0)


# ---------------------------------------------------------------------------
# TestEngineSelection
# ---------------------------------------------------------------------------


class TestEngineSelection:
    """Tests for get_ocr_engine and OCRResult."""

    def test_ocr_result_fields(self) -> None:
        """OCRResult has text, confidence, and bounding_box fields."""
        result = OCRResult(text="Breaking Bad S01E01", confidence=0.95)
        assert result.text == "Breaking Bad S01E01"
        assert result.confidence == 0.95
        assert result.bounding_box is None

    def test_ocr_result_with_bounding_box(self) -> None:
        """OCRResult stores the bounding_box tuple."""
        bbox = (10, 20, 100, 40)
        result = OCRResult(text="hello", confidence=0.8, bounding_box=bbox)
        assert result.bounding_box == bbox

    def test_ocr_result_is_frozen(self) -> None:
        """OCRResult is immutable (frozen dataclass)."""
        result = OCRResult(text="test", confidence=0.5)
        with pytest.raises((AttributeError, TypeError)):
            result.text = "other"  # type: ignore[misc]

    def test_get_ocr_engine_raises_when_no_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_ocr_engine raises RuntimeError when neither backend is available."""
        import show_tracker.ocr.engine as engine_mod

        # Patch both engine constructors to raise ImportError

        class _FakeEngine(engine_mod.OCREngine):
            def __init__(self) -> None:
                raise ImportError("not available")

            def extract_text(self, image: Image.Image) -> list[OCRResult]:
                return []

        monkeypatch.setattr(engine_mod, "TesseractEngine", _FakeEngine)
        monkeypatch.setattr(engine_mod, "EasyOCREngine", _FakeEngine)

        with pytest.raises(RuntimeError, match="No OCR backend available"):
            engine_mod.get_ocr_engine()

    def test_get_ocr_engine_returns_engine_if_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_ocr_engine returns an OCREngine when a backend succeeds."""
        import show_tracker.ocr.engine as engine_mod

        class _WorkingEngine(engine_mod.OCREngine):
            def __init__(self) -> None:
                pass

            def extract_text(self, image: Image.Image) -> list[OCRResult]:
                return []

        monkeypatch.setattr(engine_mod, "TesseractEngine", _WorkingEngine)

        engine = engine_mod.get_ocr_engine("tesseract")
        assert isinstance(engine, engine_mod.OCREngine)


# ---------------------------------------------------------------------------
# TestPreprocessing
# ---------------------------------------------------------------------------


class TestPreprocessing:
    """Tests for the preprocess() image preparation function."""

    def test_preprocess_returns_grayscale(self) -> None:
        """preprocess() converts the image to grayscale (mode 'L')."""
        img = Image.new("RGB", (200, 50), color=(100, 150, 200))
        result = preprocess(img)
        assert result.mode == "L"

    def test_preprocess_upscales_small_image(self) -> None:
        """preprocess() upscales images narrower than the minimum width."""
        img = Image.new("RGB", (100, 20))  # narrower than 600 px
        result = preprocess(img, upscale=True)
        assert result.width >= 600

    def test_preprocess_no_upscale(self) -> None:
        """preprocess() skips upscaling when upscale=False."""
        img = Image.new("RGB", (100, 20))
        result = preprocess(img, upscale=False)
        # Should not be upscaled, but grayscale is still applied
        assert result.mode == "L"
        assert result.width == 100

    def test_preprocess_large_image_unchanged_size(self) -> None:
        """preprocess() does not change size of already-large images."""
        img = Image.new("RGB", (800, 100))
        result = preprocess(img, upscale=True)
        assert result.width == 800

    def test_preprocess_invert(self) -> None:
        """preprocess(invert=True) inverts pixel values."""
        # Create a white image; after inversion it should become black
        img = Image.new("RGB", (200, 50), color=(255, 255, 255))
        result = preprocess(img, invert=True, upscale=False, adaptive_threshold=False)
        pixel = result.getpixel((0, 0))
        # After inversion white becomes black
        assert pixel == 0

    def test_preprocess_adaptive_threshold_no_error(self) -> None:
        """preprocess(adaptive_threshold=True) runs without error."""
        img = Image.new("RGB", (200, 50))
        result = preprocess(img, adaptive_threshold=True, upscale=False)
        assert result is not None
