"""Platform-specific window screenshot capture.

Captures a screenshot of a given window handle without bringing it to the
foreground, which is important so the tracker never disrupts the user.
"""

from __future__ import annotations

import logging
import subprocess
import sys

from PIL import Image

logger = logging.getLogger(__name__)


def capture_window(hwnd_or_window_id: int, platform: str | None = None) -> Image.Image:
    """Capture a screenshot of a window by its handle/ID.

    Parameters
    ----------
    hwnd_or_window_id:
        On Windows this is an HWND (int); on Linux an X11 window ID.
    platform:
        Override platform detection.  Defaults to ``sys.platform``.

    Returns
    -------
    PIL.Image.Image
        An RGB screenshot of the target window.

    Raises
    ------
    NotImplementedError
        If the current platform is not supported.
    RuntimeError
        If the capture operation fails.
    """
    plat = platform or sys.platform
    if plat == "win32":
        return _capture_windows(hwnd_or_window_id)
    elif plat.startswith("linux"):
        return _capture_linux(hwnd_or_window_id)
    elif plat == "darwin":
        return _capture_macos(hwnd_or_window_id)
    else:
        raise NotImplementedError(f"Unsupported platform: {plat}")


# ---------------------------------------------------------------------------
# Windows: PrintWindow via ctypes Win32 API
# ---------------------------------------------------------------------------

def _capture_windows(hwnd: int) -> Image.Image:
    """Background-safe capture on Windows using PrintWindow.

    PrintWindow renders the window contents into a device context we own,
    so the target window does not need to be in the foreground.
    """
    try:
        import ctypes
        import ctypes.wintypes as wt
    except ImportError as exc:
        raise RuntimeError("ctypes is required for Windows screenshot capture") from exc

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    gdi32 = ctypes.windll.gdi32  # type: ignore[attr-defined]

    # Get window dimensions via GetWindowRect
    rect = wt.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError(f"GetWindowRect failed for hwnd={hwnd}")

    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid window dimensions: {width}x{height}")

    # Create a compatible device context and bitmap
    hwnd_dc = user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        raise RuntimeError("GetWindowDC failed")

    try:
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        if not mem_dc:
            raise RuntimeError("CreateCompatibleDC failed")

        try:
            bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
            if not bitmap:
                raise RuntimeError("CreateCompatibleBitmap failed")

            try:
                old_bitmap = gdi32.SelectObject(mem_dc, bitmap)

                # PW_RENDERFULLCONTENT = 0x00000002 (captures even DWM-composed content)
                PW_RENDERFULLCONTENT = 0x00000002
                result = user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT)
                if not result:
                    # Fall back to basic PrintWindow (flag 0)
                    logger.debug("PrintWindow with PW_RENDERFULLCONTENT failed, retrying flag=0")
                    result = user32.PrintWindow(hwnd, mem_dc, 0)
                    if not result:
                        raise RuntimeError("PrintWindow failed")

                # Read pixel data from the bitmap via GetDIBits
                class BITMAPINFOHEADER(ctypes.Structure):
                    _fields_ = [
                        ("biSize", wt.DWORD),
                        ("biWidth", wt.LONG),
                        ("biHeight", wt.LONG),
                        ("biPlanes", wt.WORD),
                        ("biBitCount", wt.WORD),
                        ("biCompression", wt.DWORD),
                        ("biSizeImage", wt.DWORD),
                        ("biXPelsPerMeter", wt.LONG),
                        ("biYPelsPerMeter", wt.LONG),
                        ("biClrUsed", wt.DWORD),
                        ("biClrImportant", wt.DWORD),
                    ]

                bmi = BITMAPINFOHEADER()
                bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.biWidth = width
                bmi.biHeight = -height  # top-down
                bmi.biPlanes = 1
                bmi.biBitCount = 32
                bmi.biCompression = 0  # BI_RGB

                buffer_size = width * height * 4
                pixel_buffer = ctypes.create_string_buffer(buffer_size)

                gdi32.GetDIBits(
                    mem_dc, bitmap, 0, height,
                    pixel_buffer, ctypes.byref(bmi), 0,  # DIB_RGB_COLORS
                )

                # BGRA -> RGBA
                img = Image.frombuffer("RGBA", (width, height), bytes(pixel_buffer), "raw", "BGRA", 0, 1)
                return img.convert("RGB")

            finally:
                gdi32.SelectObject(mem_dc, old_bitmap)
                gdi32.DeleteObject(bitmap)
        finally:
            gdi32.DeleteDC(mem_dc)
    finally:
        user32.ReleaseDC(hwnd, hwnd_dc)


# ---------------------------------------------------------------------------
# Linux: xdotool + xwd or import (ImageMagick) for X11
# ---------------------------------------------------------------------------

def _capture_linux(window_id: int) -> Image.Image:
    """Capture a window on Linux/X11 using xdotool + import.

    Note: Wayland compositors generally do not allow capturing arbitrary
    windows from other processes.  This function targets X11 / XWayland.
    """
    import io

    hex_id = hex(window_id)

    # Try xdotool getwindowgeometry to verify the window exists
    try:
        subprocess.run(
            ["xdotool", "getwindowgeometry", "--shell", str(window_id)],
            capture_output=True,
            check=True,
            timeout=5,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "xdotool is not installed. Install it with: sudo apt install xdotool"
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Window {hex_id} does not exist or is not accessible: {exc.stderr.decode()}"
        ) from exc
    except subprocess.TimeoutExpired:
        raise RuntimeError("xdotool timed out verifying window geometry")

    # Use ImageMagick's 'import' command to capture the window
    # -silent suppresses the crosshair cursor, -window targets a specific window
    try:
        proc = subprocess.run(
            ["import", "-silent", "-window", str(window_id), "png:-"],
            capture_output=True,
            check=True,
            timeout=10,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "ImageMagick 'import' is not installed. "
            "Install it with: sudo apt install imagemagick"
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Failed to capture window {hex_id}: {exc.stderr.decode()}"
        ) from exc
    except subprocess.TimeoutExpired:
        raise RuntimeError("Window capture timed out")

    img = Image.open(io.BytesIO(proc.stdout))
    return img.convert("RGB")


# ---------------------------------------------------------------------------
# macOS: screencapture CLI or Quartz CGWindowListCreateImage
# ---------------------------------------------------------------------------

def _capture_macos(window_id: int) -> Image.Image:
    """Capture a window on macOS.

    Tries pyobjc Quartz framework first (CGWindowListCreateImage),
    then falls back to the screencapture CLI tool.
    """
    import tempfile

    # Try Quartz framework first
    try:
        import CoreGraphics  # type: ignore[import-not-found]
        import Quartz  # type: ignore[import-not-found]

        cg_image = Quartz.CGWindowListCreateImage(
            Quartz.CGRectNull,
            Quartz.kCGWindowListOptionIncludingWindow,
            window_id,
            Quartz.kCGWindowImageBoundsIgnoreFraming,
        )

        if cg_image is not None:
            width = CoreGraphics.CGImageGetWidth(cg_image)
            height = CoreGraphics.CGImageGetHeight(cg_image)
            bytes_per_row = CoreGraphics.CGImageGetBytesPerRow(cg_image)

            data_provider = CoreGraphics.CGImageGetDataProvider(cg_image)
            data = CoreGraphics.CGDataProviderCopyData(data_provider)

            img = Image.frombuffer("RGBA", (width, height), data, "raw", "BGRA", bytes_per_row, 1)
            return img.convert("RGB")
    except ImportError:
        logger.debug("pyobjc-framework-Quartz not available, falling back to screencapture CLI")
    except Exception:
        logger.debug("Quartz capture failed, falling back to screencapture CLI", exc_info=True)

    # Fallback: use macOS screencapture CLI
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        proc = subprocess.run(
            ["screencapture", "-l", str(window_id), "-o", "-x", tmp_path],
            capture_output=True,
            check=True,
            timeout=10,
        )
        img = Image.open(tmp_path)
        return img.convert("RGB")
    except FileNotFoundError:
        raise RuntimeError("screencapture command not found (expected on macOS)")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"screencapture failed for window {window_id}: {exc.stderr.decode()}"
        ) from exc
    except subprocess.TimeoutExpired:
        raise RuntimeError("screencapture timed out")
    finally:
        import os
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
