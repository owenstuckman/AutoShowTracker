#!/usr/bin/env bash
# Build a Linux AppImage for AutoShowTracker.
#
# Prerequisites:
#   - Python 3.11+ installed
#   - appimagetool on PATH (download from https://github.com/AppImage/appimagetool)
#   - pip install -e ".[linux,ocr,notifications]"  (in the project venv)
#
# Usage:
#   chmod +x scripts/build_appimage.sh
#   ./scripts/build_appimage.sh
#
# Output:
#   dist/ShowTracker-x86_64.AppImage

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/build/appimage"
APPDIR="$BUILD_DIR/ShowTracker.AppDir"
DIST_DIR="$PROJECT_ROOT/dist"

echo "=== AutoShowTracker AppImage Builder ==="
echo "Project root: $PROJECT_ROOT"

# Clean previous build
rm -rf "$BUILD_DIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$DIST_DIR"

# Check for appimagetool
if ! command -v appimagetool &>/dev/null; then
    echo "ERROR: appimagetool not found on PATH."
    echo "Download from: https://github.com/AppImage/appimagetool/releases"
    exit 1
fi

# Step 1: Create a self-contained Python environment
echo "--- Creating Python virtual environment ---"
python3 -m venv "$APPDIR/usr/python"
source "$APPDIR/usr/python/bin/activate"

echo "--- Installing show-tracker ---"
pip install --upgrade pip wheel
pip install "$PROJECT_ROOT[linux,ocr,notifications]"

deactivate

# Step 2: Create the launcher script
cat > "$APPDIR/usr/bin/show-tracker" <<'LAUNCHER'
#!/usr/bin/env bash
HERE="$(dirname "$(dirname "$(readlink -f "$0")")")"
export PATH="$HERE/python/bin:$PATH"
export PYTHONPATH="$HERE/python/lib/python3.*/site-packages"
exec "$HERE/python/bin/python" -m show_tracker.main "$@"
LAUNCHER
chmod +x "$APPDIR/usr/bin/show-tracker"

# Step 3: Create AppRun entry point
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/show-tracker" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# Step 4: Desktop file
cat > "$APPDIR/usr/share/applications/show-tracker.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Show Tracker
Comment=Automatic cross-platform media tracking
Exec=show-tracker run
Icon=show-tracker
Categories=AudioVideo;Player;
Terminal=false
DESKTOP
cp "$APPDIR/usr/share/applications/show-tracker.desktop" "$APPDIR/show-tracker.desktop"

# Step 5: Icon (use bundled icon or generate a placeholder)
ICON_SRC="$PROJECT_ROOT/assets/icon.png"
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$APPDIR/usr/share/icons/hicolor/256x256/apps/show-tracker.png"
    cp "$ICON_SRC" "$APPDIR/show-tracker.png"
else
    echo "WARNING: No icon found at $ICON_SRC. Using placeholder."
    # Create a 1x1 placeholder PNG (smallest valid PNG)
    python3 -c "
from PIL import Image
img = Image.new('RGB', (256, 256), color=(99, 102, 241))
img.save('$APPDIR/show-tracker.png')
img.save('$APPDIR/usr/share/icons/hicolor/256x256/apps/show-tracker.png')
" 2>/dev/null || echo "Could not generate icon (Pillow not available outside AppDir)"
fi

# Step 6: Bundle data files
echo "--- Bundling data files ---"
for dir in config profiles web_ui; do
    if [ -d "$PROJECT_ROOT/$dir" ]; then
        cp -r "$PROJECT_ROOT/$dir" "$APPDIR/usr/"
    fi
done

# Step 7: Build the AppImage
echo "--- Building AppImage ---"
ARCH=x86_64 appimagetool "$APPDIR" "$DIST_DIR/ShowTracker-x86_64.AppImage"

echo
echo "=== Done ==="
echo "AppImage: $DIST_DIR/ShowTracker-x86_64.AppImage"
echo
echo "Test it with:"
echo "  chmod +x $DIST_DIR/ShowTracker-x86_64.AppImage"
echo "  $DIST_DIR/ShowTracker-x86_64.AppImage run"
