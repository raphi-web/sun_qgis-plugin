#!/usr/bin/env bash
# Development: build the computation engine from the local Rust repo and
# install it into QGIS's Python (user site-packages), replacing the PyPI
# version until you reinstall from PyPI.
#
# QGIS 3.34 runs Python 3.12 (/usr/bin/python3). maturin must build against
# THAT interpreter (-i). The engine is built WITHOUT the gdal-io feature:
# raster I/O happens in Python, so it has no GDAL linkage at all.
#
# Back to the released engine:
#   /usr/bin/python3 -m pip install --user --break-system-packages \
#       --force-reinstall sun-solar-radiation
set -euo pipefail

RUST_REPO="${1:-/home/raphi/Dokumente/Programming/Rust/sun}"
QGIS_PYTHON=/usr/bin/python3

cd "$RUST_REPO"
echo "==> Building sun engine against $($QGIS_PYTHON --version 2>&1)…"
maturin build --release -i "$QGIS_PYTHON" --skip-auditwheel

WHEEL="$(ls -t target/wheels/sun_solar_radiation-*-linux_x86_64.whl 2>/dev/null | head -1)"
if [ -z "$WHEEL" ]; then
  echo "ERROR: no sun_solar_radiation wheel in target/wheels — did maturin build succeed?" >&2
  exit 1
fi

echo "==> Installing $WHEEL into $QGIS_PYTHON user site-packages"
# Debian/Ubuntu mark the system Python as externally managed (PEP 668);
# --user keeps the install out of /usr, --break-system-packages allows it.
"$QGIS_PYTHON" -m pip install --user --break-system-packages --force-reinstall \
  --no-deps "$WHEEL"

echo "==> Verifying the installed engine"
"$QGIS_PYTHON" - <<'PYEOF'
import importlib, subprocess
from importlib import metadata
import sun
native = importlib.import_module("sun.sun").__file__
assert all(hasattr(sun, a) for a in
           ("compute_raster_bands", "compute_annual_bands", "horn_slope_aspect", "compute_pixel"))
assert not hasattr(sun, "compute_raster"), "path API leaked back into the engine"
ldd = subprocess.run(["ldd", native], capture_output=True, text=True, check=True).stdout
assert "gdal" not in ldd.lower(), "engine links GDAL — build without the gdal-io feature"
assert "not found" not in ldd, ldd
print(f"OK: sun-solar-radiation {metadata.version('sun-solar-radiation')} at {native}")
PYEOF
