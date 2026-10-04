"""The computation engine (pip package sun-solar-radiation) must be GDAL-FREE.

Raster I/O lives in Python (raster_io.py); the native module only receives
flat f32 arrays. That is what makes the engine installable from PyPI on
Windows/macOS/Linux without a system GDAL.

Guards:
  * `ldd` on the engine's native library must not show libgdal (or any 'not found')
  * the module exposes the array API + pure compute_pixel
  * the removed path-based API (compute_raster / compute_annual_potential /
    create_dummy) is gone — plugin code must not grow back a dependency on it
"""
import importlib
import subprocess
import sys

import pytest


@pytest.fixture(scope="module")
def so_path(sun_module):
    # The wheel's sun/__init__.py re-exports the native submodule sun.sun.
    return importlib.import_module("sun.sun").__file__


@pytest.fixture(scope="module")
def sun_module(core):
    return core.load_sun()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="ldd is Linux-specific")
def test_so_has_no_gdal_linkage(so_path):
    out = subprocess.run(
        ["ldd", str(so_path)], capture_output=True, text=True, check=True
    ).stdout
    gdal_lines = [ln for ln in out.splitlines() if "gdal" in ln.lower()]
    assert not gdal_lines, f"extension links GDAL: {gdal_lines}"
    assert "not found" not in out, f"unresolved libraries:\n{out}"


def test_array_api_present(sun_module):
    for fn in ("compute_raster_bands", "compute_annual_bands", "horn_slope_aspect",
               "compute_pixel"):
        assert hasattr(sun_module, fn), f"missing {fn}"


def test_path_api_removed(sun_module):
    for fn in ("compute_raster", "compute_annual_potential", "create_dummy"):
        assert not hasattr(sun_module, fn), (
            f"{fn} is back in the extension — it needs GDAL; keep file I/O in Python"
        )
