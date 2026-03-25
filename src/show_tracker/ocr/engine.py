"""OCR engine abstraction layer.

Provides a uniform interface over Tesseract and EasyOCR, with image
preprocessing optimised for reading media-player title bars and overlays.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageFilter, ImageOps

logger = logging.getLogger(__name__)

# Target DPI-equivalent width for upscaling small crops.  OCR engines
# perform best when text is at least ~30 px tall, which roughly
# corresponds to 300 DPI rendering of 10 pt font.
_MIN_WIDTH_PX = 600


@dataclass(frozen=True, slots=True)
class OCRResult:
    """A single OCR detection."""

    text: str
    confidence: float
    bounding_box: tuple[int, int, int, int] | None = None
    """(x1, y1, x2, y2) pixel coordinates, or None if unavailable."""


class OCREngine(ABC):
    """Protocol for OCR backends."""

    @abstractmethod
    def extract_text(self, image: Image.Image) -> list[OCRResult]:
        """Run OCR on an image and return detected text segments.

        Parameters
        ----------
        image:
            An RGB PIL Image.

        Returns
        -------
        list[OCRResult]
            Detected text segments, ordered by position (top-to-bottom,
            left-to-right).
        """
        ...


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------

def preprocess(
    image: Image.Image,
    *,
    invert: bool = False,
    upscale: bool = True,
    adaptive_threshold: bool = True,
) -> Image.Image:
    """Prepare an image for OCR.

    Steps (in order):
    1. Convert to grayscale.
    2. Upscale small images so text meets the ~300 DPI minimum.
    3. Optionally invert (for light text on dark backgrounds).
    4. Apply adaptive-threshold-like sharpening to improve contrast.

    Parameters
    ----------
    image:
        Input RGB or RGBA image.
    invert:
        If True, invert the image (for dark-theme UIs with light text).
    upscale:
        If True, upscale images narrower than ``_MIN_WIDTH_PX``.
    adaptive_threshold:
        If True, apply contrast enhancement and sharpening.
    """
    # 1. Grayscale
    gray = image.convert("L")

    # 2. Upscale if too small
    if upscale and gray.width < _MIN_WIDTH_PX:
        scale = _MIN_WIDTH_PX / gray.width
        new_w = int(gray.width * scale)
        new_h = int(gray.height * scale)
        gray = gray.resize((new_w, new_h), Image.LANCZOS)  # type: ignore[attr-defined]
        logger.debug("Upscaled image to %dx%d (%.1fx)", new_w, new_h, scale)

    # 3. Invert for dark themes
    if invert:
        gray = ImageOps.invert(gray)

    # 4. Adaptive threshold approximation
    #    PIL doesn't have a true adaptive threshold, so we use autocontrast
    #    plus an unsharp mask which achieves a similar effect for OCR.
    if adaptive_threshold:
        gray = ImageOps.autocontrast(gray, cutoff=1)
        gray = gray.filter(ImageFilter.SHARPEN)

    return gray


def _detect_dark_theme(image: Image.Image) -> bool:
    """Heuristic: returns True if the image appears to have a dark background.

    Checks whether the median pixel intensity of the border region is below
    a threshold, suggesting light-on-dark text.
    """
    gray = image.convert("L")
    w, h = gray.size

    # Sample a thin border strip (top 5 rows, bottom 5 rows, left/right 5 cols)
    border_pixels: list[int] = []
    for x in range(w):
        for y in range(min(5, h)):
            px = gray.getpixel((x, y))
            border_pixels.append(int(px) if isinstance(px, (int, float)) else 0)
        for y in range(max(0, h - 5), h):
            px = gray.getpixel((x, y))
            border_pixels.append(int(px) if isinstance(px, (int, float)) else 0)

    if not border_pixels:
        return False

    median = sorted(border_pixels)[len(border_pixels) // 2]
    return median < 80


# ---------------------------------------------------------------------------
# Tesseract backend
# ---------------------------------------------------------------------------

class TesseractEngine(OCREngine):
    """OCR engine backed by Tesseract (via pytesseract)."""

    def __init__(self, *, lang: str = "eng", config: str = "--psm 6") -> None:
        """
        Parameters
        ----------
        lang:
            Tesseract language code.
        config:
            Extra Tesseract CLI flags.  ``--psm 6`` assumes a single uniform
            block of text, which works well for title bars.
        """
        try:
            import pytesseract  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            raise ImportError(
                "pytesseract is required for TesseractEngine. "
                "Install it with: pip install 'show-tracker[ocr]'"
            )

        self._lang = lang
        self._config = config

    def extract_text(self, image: Image.Image) -> list[OCRResult]:
        import pytesseract

        is_dark = _detect_dark_theme(image)
        processed = preprocess(image, invert=is_dark)

        try:
            data: dict[str, list[Any]] = pytesseract.image_to_data(
                processed, lang=self._lang, config=self._config,
                output_type=pytesseract.Output.DICT,
            )
        except pytesseract.TesseractError as exc:
            logger.error("Tesseract failed: %s", exc)
            return []

        results: list[OCRResult] = []
        n_items = len(data.get("text", []))

        for i in range(n_items):
            text = str(data["text"][i]).strip()
            if not text:
                continue

            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                conf = 0.0

            # Tesseract reports confidence as 0-100; normalise to 0-1
            conf_norm = max(0.0, min(conf / 100.0, 1.0))

            if conf_norm < 0.10:
                continue

            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
            bbox = (x, y, x + w, y + h)

            results.append(OCRResult(text=text, confidence=conf_norm, bounding_box=bbox))

        logger.debug("Tesseract extracted %d text segments", len(results))
        return results


# ---------------------------------------------------------------------------
# EasyOCR backend
# ---------------------------------------------------------------------------

class EasyOCREngine(OCREngine):
    """OCR engine backed by EasyOCR.

    The EasyOCR model is lazy-loaded on first use to avoid the heavy
    import and GPU initialisation penalty at startup.
    """

    def __init__(self, *, languages: list[str] | None = None, gpu: bool = False) -> None:
        """
        Parameters
        ----------
        languages:
            List of language codes.  Defaults to ``["en"]``.
        gpu:
            Whether to use GPU acceleration.
        """
        try:
            import easyocr  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            raise ImportError(
                "easyocr is required for EasyOCREngine. "
                "Install it with: pip install 'show-tracker[ocr]'"
            )

        self._languages = languages or ["en"]
        self._gpu = gpu
        self._reader: Any = None  # Lazy-loaded easyocr.Reader

    def _get_reader(self) -> Any:
        if self._reader is None:
            import easyocr

            logger.info(
                "Initialising EasyOCR reader (languages=%s, gpu=%s) ...",
                self._languages, self._gpu,
            )
            self._reader = easyocr.Reader(self._languages, gpu=self._gpu)
        return self._reader

    def extract_text(self, image: Image.Image) -> list[OCRResult]:
        import numpy as np  # type: ignore[import-not-found]

        is_dark = _detect_dark_theme(image)
        processed = preprocess(image, invert=is_dark)

        # EasyOCR expects a numpy array
        img_array = np.array(processed)

        reader = self._get_reader()
        try:
            raw_results = reader.readtext(img_array)
        except Exception:
            logger.exception("EasyOCR failed")
            return []

        results: list[OCRResult] = []
        for bbox_points, text, confidence in raw_results:
            text = text.strip()
            if not text or confidence < 0.10:
                continue

            # bbox_points is a list of 4 corner points [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            xs = [int(p[0]) for p in bbox_points]
            ys = [int(p[1]) for p in bbox_points]
            bbox = (min(xs), min(ys), max(xs), max(ys))

            results.append(OCRResult(text=text, confidence=float(confidence), bounding_box=bbox))

        logger.debug("EasyOCR extracted %d text segments", len(results))
        return results


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_ocr_engine(preferred: str = "tesseract") -> OCREngine:
    """Create an OCR engine, falling back if the preferred one is unavailable.

    Parameters
    ----------
    preferred:
        ``"tesseract"`` or ``"easyocr"``.

    Returns
    -------
    OCREngine
        An initialised engine instance.

    Raises
    ------
    RuntimeError
        If no OCR backend is available.
    """
    engines: list[tuple[str, type[OCREngine]]] = [
        ("tesseract", TesseractEngine),
        ("easyocr", EasyOCREngine),
    ]

    # Put preferred engine first
    if preferred.lower() == "easyocr":
        engines.reverse()

    errors: list[str] = []
    for name, cls in engines:
        try:
            engine = cls()
            logger.info("Using OCR engine: %s", name)
            return engine
        except ImportError as exc:
            errors.append(f"{name}: {exc}")
            logger.debug("OCR engine '%s' not available: %s", name, exc)

    raise RuntimeError(
        "No OCR backend available. Install one of:\n"
        "  pip install pytesseract  (requires Tesseract binary)\n"
        "  pip install easyocr\n"
        f"Errors: {'; '.join(errors)}"
    )
