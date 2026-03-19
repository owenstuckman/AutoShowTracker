# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Show Tracker.

Build with:
    pyinstaller show_tracker.spec

This bundles the application into a single directory with all
required data files, hidden imports, and the web UI.
"""

import os
import sys
from pathlib import Path

block_cipher = None

# Paths
PROJECT_ROOT = Path(SPECPATH)
SRC_DIR = PROJECT_ROOT / "src" / "show_tracker"

# Collect data files
datas = []

# Web UI templates and static files
web_ui = PROJECT_ROOT / "web_ui"
if web_ui.exists():
    datas.append((str(web_ui), "web_ui"))

# Config defaults
config_dir = PROJECT_ROOT / "config"
if config_dir.exists():
    datas.append((str(config_dir), "config"))

# OCR region profiles
profiles_dir = PROJECT_ROOT / "profiles"
if profiles_dir.exists():
    datas.append((str(profiles_dir), "profiles"))

# guessit data files (rebulk rules)
try:
    import guessit
    guessit_path = Path(guessit.__file__).parent
    datas.append((str(guessit_path), "guessit"))
except ImportError:
    pass

try:
    import rebulk
    rebulk_path = Path(rebulk.__file__).parent
    datas.append((str(rebulk_path), "rebulk"))
except ImportError:
    pass

# Hidden imports that PyInstaller may miss
hiddenimports = [
    "guessit",
    "rebulk",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.sql.default_comparator",
    "pydantic",
    "pydantic_settings",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "httpx",
    "httpx._transports.default",
    "click",
    "rapidfuzz",
    "rapidfuzz.fuzz",
    "apscheduler",
    "psutil",
    "aiosqlite",
]

# Platform-specific hidden imports
if sys.platform == "win32":
    hiddenimports.extend([
        "winsdk",
        "pystray",
        "pystray._win32",
    ])
elif sys.platform == "linux":
    hiddenimports.extend([
        "dbus_next",
        "pystray",
        "pystray._xorg",
    ])

a = Analysis(
    [str(SRC_DIR / "main.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="show-tracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=str(PROJECT_ROOT / "assets" / "icon.ico")
    if (PROJECT_ROOT / "assets" / "icon.ico").exists()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="show-tracker",
)
