#!/usr/bin/env bash
# Bump the version number across all project files.
#
# Usage:
#   ./scripts/bump_version.sh 0.2.0
#
# Updates:
#   - pyproject.toml
#   - src/show_tracker/__init__.py
#   - browser_extension/chrome/manifest.json
#   - browser_extension/firefox/manifest.json

set -euo pipefail

if [ $# -ne 1 ]; then
    echo "Usage: $0 <new-version>"
    echo "  Example: $0 0.2.0"
    exit 1
fi

NEW_VERSION="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Validate version format (semver-ish)
if ! echo "$NEW_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$'; then
    echo "ERROR: Version must be in format X.Y.Z or X.Y.Z-suffix"
    exit 1
fi

echo "Bumping version to $NEW_VERSION"
echo

# 1. pyproject.toml
PYPROJECT="$PROJECT_ROOT/pyproject.toml"
if [ -f "$PYPROJECT" ]; then
    sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" "$PYPROJECT"
    echo "  Updated: pyproject.toml"
fi

# 2. src/show_tracker/__init__.py
INIT_PY="$PROJECT_ROOT/src/show_tracker/__init__.py"
if [ -f "$INIT_PY" ]; then
    sed -i "s/__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" "$INIT_PY"
    echo "  Updated: src/show_tracker/__init__.py"
fi

# 3. Chrome manifest.json
CHROME_MANIFEST="$PROJECT_ROOT/browser_extension/chrome/manifest.json"
if [ -f "$CHROME_MANIFEST" ]; then
    python3 -c "
import json, pathlib
p = pathlib.Path('$CHROME_MANIFEST')
m = json.loads(p.read_text())
m['version'] = '$NEW_VERSION'
p.write_text(json.dumps(m, indent=4) + '\n')
"
    echo "  Updated: browser_extension/chrome/manifest.json"
fi

# 4. Firefox manifest.json
FIREFOX_MANIFEST="$PROJECT_ROOT/browser_extension/firefox/manifest.json"
if [ -f "$FIREFOX_MANIFEST" ]; then
    python3 -c "
import json, pathlib
p = pathlib.Path('$FIREFOX_MANIFEST')
m = json.loads(p.read_text())
m['version'] = '$NEW_VERSION'
p.write_text(json.dumps(m, indent=4) + '\n')
"
    echo "  Updated: browser_extension/firefox/manifest.json"
fi

echo
echo "Version bumped to $NEW_VERSION across all files."
echo
echo "Next steps:"
echo "  git add -A && git commit -m 'Bump version to $NEW_VERSION'"
echo "  git tag v$NEW_VERSION"
echo "  git push origin main --tags"
