#!/usr/bin/env bash
# Build the sun Rust extension for QGIS's interpreter and install the .so
# into the plugin directory.
#
# QGIS 3.34 runs Python 3.12 (/usr/bin/python3). maturin must build against
# THAT interpreter (-i), and --skip-auditwheel keeps the .so linked against
# the system libgdal.so.34 that QGIS already loads — no 56 MB vendored GDAL.
set -euo pipefail

RUST_REPO="${1:-/home/raphi/Dokumente/Programming/Rust/sun}"
PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)/sun_qgis"
QGIS_PYTHON=/usr/bin/python3

cd "$RUST_REPO"
echo "==> Building sun extension against $($QGIS_PYTHON --version 2>&1)…"
maturin build --release -i "$QGIS_PYTHON" --skip-auditwheel

WHEEL="$(ls -t target/wheels/sun-*-linux_x86_64.whl | head -1)"
echo "==> Extracting $WHEEL"
TMP="$(mktemp -d)"
unzip -q -o "$WHEEL" -d "$TMP"

SO="$(find "$TMP" -name 'sun.cpython-*.so' | head -1)"
[ -n "$SO" ] || { echo "ERROR: no sun.cpython-*.so in wheel" >&2; exit 1; }
cp "$SO" "$PLUGIN_DIR/"
rm -rf "$TMP"

echo "==> Verifying linkage (must resolve against system libgdal, no 'not found')"
ldd "$PLUGIN_DIR/$(basename "$SO")" | grep -E "gdal|not found" || true

echo "==> Smoke-importing under QGIS's Python…"
"$QGIS_PYTHON" - <<PYEOF
import importlib.util
spec = importlib.util.spec_from_file_location("sun", "$PLUGIN_DIR/$(basename "$SO")")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert hasattr(mod, "compute_raster") and hasattr(mod, "compute_annual_potential")
print("OK: sun extension imports, API present")
PYEOF
