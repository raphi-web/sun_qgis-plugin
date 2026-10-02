#!/usr/bin/env bash
# Build a QGIS plugin zip file for distribution.
#
# Usage:
#   scripts/build_qgis_plugin.sh
#
# Creates: dist/sun_qgis_plugin-X.Y.Z.zip
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_DIR="$REPO_ROOT/sun_qgis"
DIST_DIR="$REPO_ROOT/dist"

# Read version from metadata.txt
VERSION=$(grep "^version=" "$PLUGIN_DIR/metadata.txt" | cut -d'=' -f2)
ZIP_NAME="sun_qgis_plugin-${VERSION}.zip"

echo "==> Building QGIS plugin v${VERSION}…"

# Clean and create dist directory
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

# Create temporary directory for plugin contents
TEMP_DIR=$(mktemp -d)
PLUGIN_TEMP="$TEMP_DIR/sun_qgis"
mkdir -p "$PLUGIN_TEMP/ui"

# Copy plugin files
echo "==> Copying plugin files…"
cp "$PLUGIN_DIR"/*.py "$PLUGIN_TEMP/"
cp "$PLUGIN_DIR"/ui/*.ui "$PLUGIN_TEMP/ui/"
cp "$PLUGIN_DIR"/metadata.txt "$PLUGIN_TEMP/"
cp "$PLUGIN_DIR"/icon.png "$PLUGIN_TEMP/"

# Copy the compiled extension
echo "==> Copying compiled extension…"
SO_FILE=$(ls "$PLUGIN_DIR"/sun.cpython-312-x86_64-linux-gnu.so 2>/dev/null || echo "")
if [ -z "$SO_FILE" ]; then
    echo "ERROR: Compiled extension not found. Run scripts/build_extension.sh first."
    exit 1
fi
cp "$SO_FILE" "$PLUGIN_TEMP/"

# Copy README and LICENSE
echo "==> Copying documentation…"
cp "$REPO_ROOT/README.md" "$PLUGIN_TEMP/" 2>/dev/null || echo "No README.md found"
cp "$REPO_ROOT/LICENSE" "$PLUGIN_TEMP/" 2>/dev/null || echo "No LICENSE found"

# Create zip file
echo "==> Creating zip archive…"
cd "$TEMP_DIR"
zip -r "$DIST_DIR/$ZIP_NAME" sun_qgis/ -x "*.pyc" "__pycache__/*"

# Cleanup
rm -rf "$TEMP_DIR"

echo "==> Plugin package created: $DIST_DIR/$ZIP_NAME"
echo ""
echo "To install in QGIS:"
echo "  1. Open QGIS"
echo "  2. Plugins → Manage and Install Plugins"
echo "  3. Install from ZIP → select $DIST_DIR/$ZIP_NAME"
echo ""
echo "To publish to QGIS plugin repository:"
echo "  1. Upload $DIST_DIR/$ZIP_NAME to your hosting"
echo "  2. Submit to plugins.qgis.org (requires account)"
