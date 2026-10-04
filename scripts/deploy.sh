#!/usr/bin/env bash
# Deploy sun_qgis into every QGIS profile's plugin directory and verify.
# Usage: scripts/deploy.sh [profiles-root]
#
# Copies plugin source only. The computation engine is the pip package
# sun-solar-radiation in QGIS's Python; leftover engine copies from older
# plugin versions are removed so they cannot shadow it.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO/sun_qgis"
PROFILES_ROOT="${1:-$HOME/.local/share/QGIS/QGIS3/profiles}"
FILES=(__init__.py core.py pipeline.py plugin.py raster_io.py sun_dialog.py task.py
       metadata.txt icon.png ui/sun_dialog.ui)

for profile in "$PROFILES_ROOT"/*/; do
  dest="${profile}python/plugins/sun_qgis"
  [ -d "${profile}python/plugins" ] || { echo "skip $(basename "$profile") (no plugins dir)"; continue; }
  mkdir -p "$dest/ui"
  for f in "${FILES[@]}"; do
    cp "$SRC/$f" "$dest/$f"
  done
  rm -f "$dest"/sun*.so "$dest"/sun*.pyd
  find "$dest" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

  # verify byte-identical
  differ=0
  for f in "${FILES[@]}"; do
    cmp -s "$SRC/$f" "$dest/$f" || { echo "  DIFFERS: $f"; differ=$((differ+1)); }
  done
  echo "$(basename "$profile"): deployed, $differ file(s) differ"
done

echo "Restart QGIS (or use Plugin Reloader), then enable 'Solar Radiation' in Plugins → Manage."
