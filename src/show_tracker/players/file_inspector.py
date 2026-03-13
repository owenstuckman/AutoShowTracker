"""Open file handle inspection for media player processes.

When IPC interfaces (VLC HTTP, mpv JSON socket) are not available, we can
still determine what a player is watching by examining which video files
it has open.  This is a last-resort heuristic that works on any player.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Video file extensions to look for (lowercase, with leading dot)
_VIDEO_EXTENSIONS: frozenset[str] = frozenset({
    ".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".flv",
    ".webm", ".ts", ".mov", ".mpg", ".mpeg", ".ogv",
})


def get_open_media_files(pid: int) -> list[str]:
    """Return a list of video file paths that a process has open.

    Parameters
    ----------
    pid:
        The process ID to inspect.

    Returns
    -------
    list[str]
        Absolute paths of open video files.  May be empty if the process
        has no video files open or if inspection fails (e.g. permissions).
    """
    # Try psutil first (cross-platform)
    paths = _inspect_via_psutil(pid)

    # Linux fallback: read /proc/<pid>/fd/ directly
    if not paths and sys.platform.startswith("linux"):
        paths = _inspect_via_proc(pid)

    return paths


def find_media_player_pids(app_name: str) -> list[int]:
    """Find PIDs of processes matching a media player application name.

    Uses psutil to scan running processes and match against the given
    app name (case-insensitive substring match on process name and
    command line).

    Parameters
    ----------
    app_name:
        Application name to search for (e.g. ``"vlc"``, ``"mpv"``).

    Returns
    -------
    list[int]
        Matching process IDs.
    """
    try:
        import psutil
    except ImportError:
        logger.warning("psutil is not installed; cannot scan for media player PIDs")
        return []

    app_lower = app_name.lower()
    pids: list[int] = []

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            info = proc.info  # type: ignore[attr-defined]
            proc_name = (info.get("name") or "").lower()
            cmdline = info.get("cmdline") or []

            # Match on process name
            if app_lower in proc_name:
                pids.append(info["pid"])
                continue

            # Match on command line (e.g. /usr/bin/vlc or "C:\...\vlc.exe")
            cmdline_str = " ".join(cmdline).lower()
            if app_lower in cmdline_str:
                pids.append(info["pid"])

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    logger.debug("Found %d PID(s) matching '%s': %s", len(pids), app_name, pids)
    return pids


def _inspect_via_psutil(pid: int) -> list[str]:
    """Use psutil to list open files for a process."""
    try:
        import psutil
    except ImportError:
        logger.debug("psutil not available for file inspection")
        return []

    try:
        proc = psutil.Process(pid)
        open_files = proc.open_files()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as exc:
        logger.debug("Cannot inspect open files for PID %d: %s", pid, exc)
        return []

    media_files: list[str] = []
    for f in open_files:
        path = f.path
        if _is_video_file(path):
            media_files.append(path)

    logger.debug("psutil found %d media file(s) for PID %d", len(media_files), pid)
    return media_files


def _inspect_via_proc(pid: int) -> list[str]:
    """Linux fallback: read /proc/<pid>/fd/ symlinks."""
    fd_dir = Path(f"/proc/{pid}/fd")
    if not fd_dir.is_dir():
        logger.debug("/proc/%d/fd not accessible", pid)
        return []

    media_files: list[str] = []

    try:
        for entry in fd_dir.iterdir():
            try:
                target = os.readlink(entry)
            except (OSError, PermissionError):
                continue

            if _is_video_file(target):
                media_files.append(target)
    except PermissionError:
        logger.debug("Permission denied reading /proc/%d/fd", pid)
        return []

    logger.debug("/proc/fd found %d media file(s) for PID %d", len(media_files), pid)
    return media_files


def _is_video_file(path: str) -> bool:
    """Check if a file path has a known video extension."""
    ext = Path(path).suffix.lower()
    return ext in _VIDEO_EXTENSIONS
