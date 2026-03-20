#!/usr/bin/env bash
# Package browser extensions for Chrome Web Store and Firefox Add-ons submission.
#
# Usage:
#   chmod +x scripts/package_extensions.sh
#   ./scripts/package_extensions.sh
#
# Output:
#   dist/show-tracker-chrome-vX.Y.Z.zip
#   dist/show-tracker-firefox-vX.Y.Z.zip

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_ROOT/dist"

CHROME_DIR="$PROJECT_ROOT/browser_extension/chrome"
FIREFOX_DIR="$PROJECT_ROOT/browser_extension/firefox"

mkdir -p "$DIST_DIR"

# Read version from Chrome manifest
CHROME_VERSION=$(python3 -c "
import json, pathlib
m = json.loads(pathlib.Path('$CHROME_DIR/manifest.json').read_text())
print(m['version'])
" 2>/dev/null || echo "0.0.0")

FIREFOX_VERSION=$(python3 -c "
import json, pathlib
m = json.loads(pathlib.Path('$FIREFOX_DIR/manifest.json').read_text())
print(m['version'])
" 2>/dev/null || echo "0.0.0")

echo "=== Browser Extension Packager ==="
echo

# --- Chrome ---
if [ -d "$CHROME_DIR" ]; then
    CHROME_ZIP="$DIST_DIR/show-tracker-chrome-v${CHROME_VERSION}.zip"
    echo "Packaging Chrome extension v${CHROME_VERSION}..."

    # Validate manifest
    python3 -c "import json; json.load(open('$CHROME_DIR/manifest.json'))" 2>/dev/null \
        || { echo "ERROR: Chrome manifest.json is invalid JSON"; exit 1; }

    # Create ZIP (exclude hidden files, __pycache__, etc.)
    (cd "$CHROME_DIR" && zip -r "$CHROME_ZIP" . \
        -x ".*" "__pycache__/*" "*.pyc" "node_modules/*" ".DS_Store")

    echo "  -> $CHROME_ZIP ($(du -h "$CHROME_ZIP" | cut -f1))"
else
    echo "WARNING: Chrome extension directory not found: $CHROME_DIR"
fi

# --- Firefox ---
if [ -d "$FIREFOX_DIR" ]; then
    FIREFOX_ZIP="$DIST_DIR/show-tracker-firefox-v${FIREFOX_VERSION}.zip"
    echo "Packaging Firefox extension v${FIREFOX_VERSION}..."

    # Validate manifest
    python3 -c "import json; json.load(open('$FIREFOX_DIR/manifest.json'))" 2>/dev/null \
        || { echo "ERROR: Firefox manifest.json is invalid JSON"; exit 1; }

    # Create ZIP
    (cd "$FIREFOX_DIR" && zip -r "$FIREFOX_ZIP" . \
        -x ".*" "__pycache__/*" "*.pyc" "node_modules/*" ".DS_Store")

    echo "  -> $FIREFOX_ZIP ($(du -h "$FIREFOX_ZIP" | cut -f1))"
else
    echo "WARNING: Firefox extension directory not found: $FIREFOX_DIR"
fi

echo
echo "Done. Extension packages are in $DIST_DIR/"
