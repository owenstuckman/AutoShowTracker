"""System tray icon for Show Tracker.

Uses pystray to provide a system tray icon with menu items for
starting/stopping the service, opening the dashboard, and quitting.
"""

from __future__ import annotations

import logging
import sys
import threading
import webbrowser
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)



def _load_icon_image() -> Any:
    """Load the tray icon image, falling back to a generated icon."""
    try:
        # Try loading a bundled icon file
        from pathlib import Path

        from PIL import Image

        icon_dir = Path(__file__).resolve().parent.parent.parent / "assets"
        for name in ("icon.png", "icon.ico"):
            icon_path = icon_dir / name
            if icon_path.exists():
                return Image.open(icon_path)

        # Generate a simple colored square as fallback
        img = Image.new("RGB", (64, 64), color=(99, 102, 241))  # indigo
        return img
    except ImportError:
        return None


class TrayIcon:
    """Manages the pystray system tray icon lifecycle.

    Args:
        dashboard_url: URL to open when "Open Dashboard" is clicked.
        on_quit: Callback invoked when the user clicks "Quit".
    """

    def __init__(
        self,
        dashboard_url: str = "http://localhost:7600/",
        on_quit: Callable[[], Any] | None = None,
    ) -> None:
        self.dashboard_url = dashboard_url
        self._on_quit = on_quit
        self._icon = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the tray icon in a background thread."""
        try:
            import pystray  # type: ignore[import-not-found,import-untyped,unused-ignore]
        except ImportError:
            logger.warning("pystray not installed — skipping system tray icon")
            return

        image = _load_icon_image()
        if image is None:
            logger.warning("Pillow not installed — skipping system tray icon")
            return

        menu = pystray.Menu(
            pystray.MenuItem("Open Dashboard", self._open_dashboard, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

        icon = pystray.Icon(
            name="show-tracker",
            icon=image,
            title="Show Tracker",
            menu=menu,
        )
        self._icon = icon

        self._thread = threading.Thread(target=icon.run, daemon=True)
        self._thread.start()
        logger.info("System tray icon started")

    def stop(self) -> None:
        """Stop the tray icon."""
        if self._icon is not None:
            self._icon.stop()
            self._icon = None
            logger.info("System tray icon stopped")

    def _open_dashboard(self, icon: Any = None, item: Any = None) -> None:
        """Open the web dashboard in the default browser."""
        webbrowser.open(self.dashboard_url)

    def _quit(self, icon: Any = None, item: Any = None) -> None:
        """Stop the icon and invoke the quit callback."""
        self.stop()
        if self._on_quit is not None:
            self._on_quit()
        else:
            sys.exit(0)
