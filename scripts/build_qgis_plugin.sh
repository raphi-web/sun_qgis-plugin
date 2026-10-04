#!/usr/bin/env bash
# Build the release zip: plugin code + the computation engine for Linux,
# Windows and macOS, taken from the published sun-solar-radiation wheels on
# PyPI (pip checks each download against PyPI's sha256).
#
# Usage:
#   scripts/build_qgis_plugin.sh
#   ENGINE_VERSION=0.1.2 scripts/build_qgis_plugin.sh
#
# Creates: dist/sun_qgis_plugin-X.Y.Z.zip
# dist/ is gitignored: the zip is attached to the GitHub release, not committed.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_DIR="$REPO_ROOT/sun_qgis"
DIST_DIR="$REPO_ROOT/dist"
PYTHON=/usr/bin/python3

VERSION=$(grep "^version=" "$PLUGIN_DIR/metadata.txt" | cut -d'=' -f2)
ENGINE_VERSION="${ENGINE_VERSION:-0.1.1}"
ZIP_NAME="sun_qgis_plugin-${VERSION}.zip"
# QGIS 3.34+ runs Python 3.12; one engine wheel per platform.
PLATFORMS=(manylinux_2_34_x86_64 win_amd64 macosx_11_0_arm64)

echo "==> Building QGIS plugin v${VERSION} with engine v${ENGINE_VERSION}…"

rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT
PLUGIN_TEMP="$TEMP_DIR/sun_qgis"
WHEELS="$TEMP_DIR/wheels"
mkdir -p "$PLUGIN_TEMP/ui" "$WHEELS"

echo "==> Copying plugin files…"
cp "$PLUGIN_DIR"/*.py "$PLUGIN_TEMP/"
cp "$PLUGIN_DIR"/ui/*.ui "$PLUGIN_TEMP/ui/"
cp "$PLUGIN_DIR"/metadata.txt "$PLUGIN_TEMP/"
cp "$PLUGIN_DIR"/icon.png "$PLUGIN_TEMP/"
cp "$REPO_ROOT/README.md" "$REPO_ROOT/LICENSE" "$PLUGIN_TEMP/"

echo "==> Fetching engine wheels from PyPI…"
for plat in "${PLATFORMS[@]}"; do
    "$PYTHON" -m pip download "sun-solar-radiation==${ENGINE_VERSION}" \
        --no-deps --only-binary=:all: --implementation cp --python-version 3.12 \
        --platform "$plat" -d "$WHEELS" -q
done

echo "==> Extracting engine binaries…"
for whl in "$WHEELS"/*.whl; do
    unzip -q -o -j "$whl" 'sun/sun.*' -d "$PLUGIN_TEMP"
done
for expected in sun.cpython-312-x86_64-linux-gnu.so sun.cp312-win_amd64.pyd \
                sun.cpython-312-darwin.so; do
    if [ ! -f "$PLUGIN_TEMP/$expected" ]; then
        echo "ERROR: engine binary $expected missing from the wheels" >&2
        exit 1
    fi
done

echo "==> Creating zip archive…"
(cd "$TEMP_DIR" && zip -q -r "$DIST_DIR/$ZIP_NAME" sun_qgis/ -x "*.pyc" "*/__pycache__/*")

echo "==> Plugin package created: $DIST_DIR/$ZIP_NAME"
unzip -l "$DIST_DIR/$ZIP_NAME" | grep -E "sun\.(cp|cpython)"
