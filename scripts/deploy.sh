#!/usr/bin/env bash
# Deploy sun_qgis into every QGIS profile's plugin directory and verify.
# Usage: scripts/deploy.sh [profiles-root]
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO/sun_qgis"
PROFILES_ROOT="${1:-$HOME/.local/share/QGIS/QGIS3/profiles}"

for profile in "$PROFILES_ROOT"/*/; do
  dest="${profile}python/plugins/sun_qgis"
  [ -d "${profile}python/plugins" ] || { echo "skip $(basename "$profile") (no plugins dir)"; continue; }
  mkdir -p "$dest"
  # runtime files only (no tests, no repo cruft)
  cp "$SRC"/__init__.py "$SRC"/core.py "$SRC"/plugin.py "$SRC"/sun_dialog.py "$SRC"/task.py \
     "$SRC"/metadata.txt "$SRC"/icon.png "$dest/"
  mkdir -p "$dest/ui"
  cp "$SRC"/ui/sun_dialog.ui "$dest/ui/"
  cp "$SRC"/sun.cpython-*.so "$dest/"
  find "$dest" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

  # verify byte-identical
  differ=0
  for f in __init__.py core.py plugin.py sun_dialog.py task.py metadata.txt ui/sun_dialog.ui; do
    cmp -s "$SRC/$f" "$dest/$f" || { echo "  DIFFERS: $f"; differ=$((differ+1)); }
  done
  cmp -s "$SRC/$(cd "$SRC" && ls sun.cpython-*.so)" "$dest/$(cd "$dest" && ls sun.cpython-*.so)" \
    || { echo "  DIFFERS: .so"; differ=$((differ+1)); }
  echo "$(basename "$profile"): deployed, $differ file(s) differ"
done

echo "Restart QGIS (or use Plugin Reloader), then enable 'Solar Radiation (sun)' in Plugins → Manage."
