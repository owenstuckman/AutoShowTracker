#!/usr/bin/env python3
"""Automated environment setup for AutoShowTracker.

Detects the OS and platform, creates a virtual environment, installs the
correct dependency groups, copies .env.example, and runs database initialization.

Usage:
    python scripts/auto_setup.py
    python scripts/auto_setup.py --skip-venv       # Use current Python environment
    python scripts/auto_setup.py --extras ocr       # Add extra dependency groups
    python scripts/auto_setup.py --no-interactive   # Skip TMDb key prompt
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = PROJECT_ROOT / ".venv"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
ENV_FILE = PROJECT_ROOT / ".env"


def _header(msg: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")


def _step(n: int, msg: str) -> None:
    print(f"[{n}] {msg}")


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def _is_wsl() -> bool:
    """Detect if running inside Windows Subsystem for Linux."""
    if platform.system().lower() != "linux":
        return False
    try:
        with open("/proc/version", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def detect_platform() -> dict[str, str]:
    """Detect OS and return platform info."""
    system = platform.system().lower()
    wsl = _is_wsl()
    info = {
        "system": system,
        "platform_extra": "",
        "python": sys.executable,
        "python_version": platform.python_version(),
        "is_wsl": str(wsl),
    }

    if system == "windows":
        info["platform_extra"] = "windows"
    elif system == "linux":
        if wsl:
            # WSL reports as Linux but cannot use D-Bus/MPRIS or X11.
            # Install minimal linux extras; skip dbus-next (will fail at runtime).
            info["platform_extra"] = "linux"
        else:
            info["platform_extra"] = "linux"
    elif system == "darwin":
        info["platform_extra"] = "linux"  # macOS uses linux extras (dbus-next won't install but that's ok)
    else:
        info["platform_extra"] = ""

    return info


def check_python_version() -> bool:
    """Verify Python 3.11+."""
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 11):
        print(f"ERROR: Python 3.11+ required, found {platform.python_version()}")
        return False
    return True


def create_venv() -> Path:
    """Create a virtual environment and return the Python path inside it."""
    _step(2, f"Creating virtual environment at {VENV_DIR}")

    if VENV_DIR.exists():
        print(f"  Virtual environment already exists at {VENV_DIR}")
    else:
        _run([sys.executable, "-m", "venv", str(VENV_DIR)])

    # Determine the Python executable inside the venv
    if platform.system().lower() == "windows":
        venv_python = VENV_DIR / "Scripts" / "python.exe"
        venv_pip = VENV_DIR / "Scripts" / "pip.exe"
    else:
        venv_python = VENV_DIR / "bin" / "python"
        venv_pip = VENV_DIR / "bin" / "pip"

    if not venv_python.exists():
        print(f"ERROR: Expected Python at {venv_python} but not found")
        sys.exit(1)

    # Upgrade pip
    print("  Upgrading pip...")
    _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "wheel"],
         stdout=subprocess.DEVNULL)

    return venv_python


def install_dependencies(
    python: Path,
    platform_extra: str,
    extra_groups: list[str],
    *,
    is_wsl: bool = False,
) -> None:
    """Install the project with appropriate extras."""
    _step(3, "Installing dependencies")

    groups = ["dev"]

    if platform_extra:
        groups.append(platform_extra)

    groups.extend(extra_groups)

    # De-duplicate
    groups = list(dict.fromkeys(groups))

    extras = ",".join(groups)
    install_spec = f"{PROJECT_ROOT}[{extras}]"

    print(f"  Installing: pip install -e \".[{extras}]\"")
    _run([str(python), "-m", "pip", "install", "-e", install_spec])

    if is_wsl:
        print()
        print("  WSL detected — installing without D-Bus/MPRIS support.")
        print("  SMTC (Windows) and MPRIS (Linux) media listeners are unavailable in WSL.")
        print("  Detection will rely on: browser extension, ActivityWatch, VLC/mpv IPC.")


def setup_env_file() -> None:
    """Copy .env.example to .env if it doesn't exist."""
    _step(4, "Setting up .env file")

    if ENV_FILE.exists():
        print(f"  .env already exists at {ENV_FILE}")
        return

    if ENV_EXAMPLE.exists():
        shutil.copy2(ENV_EXAMPLE, ENV_FILE)
        print(f"  Copied {ENV_EXAMPLE.name} -> {ENV_FILE.name}")
    else:
        # Create a minimal .env
        ENV_FILE.write_text(
            "# AutoShowTracker Environment Configuration\n"
            "TMDB_API_KEY=\n"
            "YOUTUBE_API_KEY=\n",
            encoding="utf-8",
        )
        print(f"  Created minimal .env at {ENV_FILE}")


def prompt_tmdb_key() -> None:
    """Prompt user for TMDb API key and write to .env."""
    _step(5, "TMDb API Key configuration")

    # Check if key is already set
    if ENV_FILE.exists():
        content = ENV_FILE.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("TMDB_API_KEY=") and line.split("=", 1)[1].strip():
                print("  TMDb API key is already configured in .env")
                return

    print()
    print("  You need a free TMDb API key for content identification.")
    print("  Get one at: https://www.themoviedb.org/settings/api")
    print()

    try:
        key = input("  Enter your TMDb API key (or press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Skipped. You can set TMDB_API_KEY in .env later.")
        return

    if not key:
        print("  Skipped. Set TMDB_API_KEY in .env before running.")
        return

    # Validate
    try:
        import httpx
        print("  Validating key...", end="", flush=True)
        r = httpx.get(
            "https://api.themoviedb.org/3/configuration",
            params={"api_key": key},
            timeout=10.0,
        )
        if r.status_code == 200:
            print(" OK")
        else:
            print(f" WARNING: Got HTTP {r.status_code} (key may be invalid)")
    except Exception:
        print(" (could not validate — network issue or httpx not yet available)")

    # Write to .env
    content = ENV_FILE.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    found = False
    for i, line in enumerate(lines):
        if line.startswith("TMDB_API_KEY="):
            lines[i] = f"TMDB_API_KEY={key}\n"
            found = True
            break
    if not found:
        lines.append(f"TMDB_API_KEY={key}\n")
    ENV_FILE.write_text("".join(lines), encoding="utf-8")
    print(f"  Saved to {ENV_FILE}")


def init_databases(python: Path) -> None:
    """Initialize the SQLite databases."""
    _step(6, "Initializing databases")
    _run([str(python), "-m", "show_tracker.main", "init-db"])


def verify_installation(python: Path) -> None:
    """Run a quick smoke test."""
    _step(7, "Verifying installation")

    # Check CLI version
    result = subprocess.run(
        [str(python), "-m", "show_tracker.main", "--version"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"  CLI: {result.stdout.strip()}")
    else:
        print(f"  WARNING: CLI version check failed: {result.stderr.strip()}")

    # Check imports
    result = subprocess.run(
        [str(python), "-c", "from show_tracker.config import load_settings; s = load_settings(); print(f'  Data dir: {s.data_dir}'); print(f'  TMDb key set: {s.has_tmdb_key()}')"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(result.stdout.strip())
    else:
        print(f"  WARNING: Config import failed: {result.stderr.strip()}")


def print_next_steps(plat: dict[str, str]) -> None:
    """Print what the user should do next."""
    _header("Setup Complete!")

    system = plat["system"]
    activate = ""
    if system == "windows":
        activate = ".venv\\Scripts\\activate"
    else:
        activate = "source .venv/bin/activate"

    print("Next steps:\n")
    print(f"  1. Activate the environment:  {activate}")
    print("  2. Start the service:         show-tracker run")
    print("  3. Open the dashboard:        http://127.0.0.1:7600")
    print()
    print("Optional:")
    print("  - Load browser extension:     See browser_extension/chrome/ or firefox/")
    print("  - Run tests:                  pytest")
    print("  - Identify a title:           show-tracker identify \"Breaking Bad S05E14\"")
    print()

    is_wsl = plat.get("is_wsl") == "True"

    if is_wsl:
        print("WSL-specific:")
        print("  - SMTC and MPRIS media listeners are NOT available in WSL")
        print("  - Use the browser extension as your primary detection source")
        print("  - VLC/mpv IPC works if the player runs inside WSL (not Windows-side)")
        print("  - To access the dashboard from Windows: http://localhost:7600")
        print("  - If the Windows browser can't reach WSL, try http://$(hostname -I | awk '{print $1}'):7600")
    elif system == "windows":
        print("Windows-specific:")
        print("  - SMTC detection is enabled automatically (play media to test)")
        print("  - System tray icon appears when running")
    elif system == "linux":
        print("Linux-specific:")
        print("  - MPRIS detection requires D-Bus session bus")
        print("  - For auto-start: cp contrib/show-tracker.service ~/.config/systemd/user/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-setup for AutoShowTracker")
    parser.add_argument("--skip-venv", action="store_true",
                        help="Skip venv creation, use current Python")
    parser.add_argument("--extras", nargs="*", default=[],
                        help="Additional extras to install (e.g. ocr notifications)")
    parser.add_argument("--no-interactive", action="store_true",
                        help="Skip interactive prompts (TMDb key)")
    args = parser.parse_args()

    _header("AutoShowTracker Environment Setup")

    # Step 1: Check Python
    _step(1, "Checking Python version")
    if not check_python_version():
        sys.exit(1)

    plat = detect_platform()
    is_wsl = plat["is_wsl"] == "True"
    print(f"  Python {plat['python_version']} on {plat['system']}")
    if is_wsl:
        print("  Environment: WSL (Windows Subsystem for Linux)")
    print(f"  Platform extras: {plat['platform_extra'] or 'none'}")

    # Step 2: Create venv
    if args.skip_venv:
        python = Path(sys.executable)
        print(f"\n  Using current Python: {python}")
    else:
        python = create_venv()

    # Step 3: Install dependencies
    install_dependencies(python, plat["platform_extra"], args.extras, is_wsl=is_wsl)

    # Step 4: Setup .env
    setup_env_file()

    # Step 5: TMDb key
    if not args.no_interactive:
        prompt_tmdb_key()
    else:
        print(f"\n[5] Skipping TMDb key prompt (--no-interactive)")
        print(f"    Set TMDB_API_KEY in {ENV_FILE} manually")

    # Step 6: Init databases
    init_databases(python)

    # Step 7: Verify
    verify_installation(python)

    # Done
    print_next_steps(plat)


if __name__ == "__main__":
    main()
