#!/usr/bin/env bash
# Build the release zip: plugin source only, no binaries.
#
# The computation engine is the pip package sun-solar-radiation, installed
# by the user into QGIS's Python (see README, Installation). plugins.qgis.org
# rejects plugins that ship binaries, so this script refuses to zip one.
#
# Usage:
#   scripts/build_qgis_plugin.sh
#   DIST_DIR=/some/dir scripts/build_qgis_plugin.sh
#
# Creates: $DIST_DIR/sun_qgis_plugin-X.Y.Z.zip (default dist/, gitignored;
# the zip is attached to the GitHub release, not committed).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_DIR="$REPO_ROOT/sun_qgis"
DIST_DIR="${DIST_DIR:-$REPO_ROOT/dist}"

VERSION=$(grep "^version=" "$PLUGIN_DIR/metadata.txt" | cut -d'=' -f2)
ZIP_NAME="sun_qgis_plugin-${VERSION}.zip"

echo "==> Building QGIS plugin v${VERSION}…"

rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT
PLUGIN_TEMP="$TEMP_DIR/sun_qgis"
mkdir -p "$PLUGIN_TEMP/ui"

echo "==> Copying plugin files…"
cp "$PLUGIN_DIR"/*.py "$PLUGIN_TEMP/"
cp "$PLUGIN_DIR"/ui/*.ui "$PLUGIN_TEMP/ui/"
cp "$PLUGIN_DIR"/metadata.txt "$PLUGIN_TEMP/"
cp "$PLUGIN_DIR"/icon.png "$PLUGIN_TEMP/"
cp "$REPO_ROOT/README.md" "$REPO_ROOT/LICENSE" "$PLUGIN_TEMP/"

BINARIES=$(find "$PLUGIN_TEMP" -type f \( -name '*.so' -o -name '*.pyd' \
    -o -name '*.dll' -o -name '*.dylib' -o -name '*.exe' -o -name '*.whl' \))
if [ -n "$BINARIES" ]; then
    echo "ERROR: binaries would be shipped in the release zip:" >&2
    echo "$BINARIES" >&2
    exit 1
fi

echo "==> Creating zip archive…"
(cd "$TEMP_DIR" && zip -q -r "$DIST_DIR/$ZIP_NAME" sun_qgis/ -x "*.pyc" "*/__pycache__/*")

echo "==> Plugin package created: $DIST_DIR/$ZIP_NAME"
