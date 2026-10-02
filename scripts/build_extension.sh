#!/usr/bin/env bash
# Build the sun Rust extension for QGIS's interpreter and install the .so
# into the plugin directory.
#
# QGIS 3.34 runs Python 3.12 (/usr/bin/python3). maturin must build against
# THAT interpreter (-i). The extension is built WITHOUT the gdal-io feature:
# raster I/O happens in Python, so the .so has no GDAL linkage at all and
# --skip-auditwheel yields a small, portable binary.
set -euo pipefail

RUST_REPO="${1:-/home/raphi/Dokumente/Programming/Rust/sun}"
PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)/sun_qgis"
QGIS_PYTHON=/usr/bin/python3

cd "$RUST_REPO"
echo "==> Building sun extension against $($QGIS_PYTHON --version 2>&1)…"
maturin build --release -i "$QGIS_PYTHON" --skip-auditwheel

WHEEL="$(ls -t target/wheels/sun_solar_radiation-*-linux_x86_64.whl 2>/dev/null | head -1)"
if [ -z "$WHEEL" ]; then
  echo "ERROR: no sun_solar_radiation wheel in target/wheels — did maturin build succeed?" >&2
  exit 1
fi
echo "==> Extracting $WHEEL"
TMP="$(mktemp -d)"
unzip -q -o "$WHEEL" -d "$TMP"

SO="$(find "$TMP" -name 'sun.cpython-*.so' | head -1)"
[ -n "$SO" ] || { echo "ERROR: no sun.cpython-*.so in wheel" >&2; exit 1; }
cp "$SO" "$PLUGIN_DIR/"
rm -rf "$TMP"

echo "==> Verifying linkage (must NOT link libgdal — extension is GDAL-free)"
if ldd "$PLUGIN_DIR/$(basename "$SO")" | grep -qi "gdal"; then
  echo "ERROR: extension links GDAL — build without the gdal-io feature" >&2
  ldd "$PLUGIN_DIR/$(basename "$SO")" | grep -i gdal >&2
  exit 1
fi
ldd "$PLUGIN_DIR/$(basename "$SO")" | grep "not found" && { echo "ERROR: unresolved libs" >&2; exit 1; } || true

echo "==> Smoke-importing under QGIS's Python…"
"$QGIS_PYTHON" - <<PYEOF
import importlib.util
spec = importlib.util.spec_from_file_location("sun", "$PLUGIN_DIR/$(basename "$SO")")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert hasattr(mod, "compute_raster_bands") and hasattr(mod, "compute_annual_bands")
assert hasattr(mod, "horn_slope_aspect") and hasattr(mod, "compute_pixel")
assert not hasattr(mod, "compute_raster"), "path API leaked back into the extension"
print("OK: sun extension imports, GDAL-free array API present")
PYEOF
