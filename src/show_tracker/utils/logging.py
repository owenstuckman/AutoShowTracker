"""Logging configuration for Show Tracker.

Provides a single ``setup_logging`` function that wires up:
- A concise **console** handler (level + message) for interactive use.
- A detailed **rotating file** handler (timestamp, level, logger name, message)
  for post-mortem debugging.

Call once at application startup; subsequent calls are idempotent.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False

# 10 MB per file, keep 3 backups
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 3

_CONSOLE_FORMAT = "%(levelname)-8s %(message)s"
_FILE_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: int | str = logging.INFO,
    log_dir: str | Path | None = None,
) -> None:
    """Configure application-wide logging with console and file handlers.

    Safe to call multiple times; the second and subsequent calls are no-ops
    unless the root logger has been reset externally.

    Parameters
    ----------
    level:
        Logging level for the root ``show_tracker`` logger.  Accepts
        standard :mod:`logging` constants or their string names
        (e.g. ``"DEBUG"``).
    log_dir:
        Directory in which to write ``show_tracker.log``.  When *None*,
        only the console handler is attached (useful for tests and
        short-lived CLI invocations).
    """
    global _CONFIGURED

    if _CONFIGURED:
        return

    # Resolve string level names like "DEBUG" -> logging.DEBUG
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger("show_tracker")
    root_logger.setLevel(level)

    # Prevent duplicate handlers if the function is somehow called again
    # after _CONFIGURED was externally toggled.
    if root_logger.handlers:
        _CONFIGURED = True
        return

    # -- Console handler (concise) -----------------------------------------
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    root_logger.addHandler(console)

    # -- File handler (detailed, rotating) ---------------------------------
    if log_dir is not None:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        log_file = log_path / "show_tracker.log"

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)  # always capture everything to disk
        file_handler.setFormatter(
            logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT)
        )
        root_logger.addHandler(file_handler)

    # Stop propagation to the root logger to avoid duplicate output when
    # other libraries configure logging globally.
    root_logger.propagate = False

    _CONFIGURED = True
