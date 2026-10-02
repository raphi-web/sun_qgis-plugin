"""Headless test bootstrap for the sun_qgis plugin.

The plugin folder `sun_qgis` is deployed into QGIS profiles and uses relative
imports; here we register it as a synthetic package and mock qgis/PyQt, while
keeping osgeo (real GDAL) and the bundled native `sun` extension unmocked.
"""
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_MOCK_MODULES = [
    "qgis", "qgis.core", "qgis._core", "qgis._gui", "qgis.utils",
    "qgis.PyQt", "qgis.PyQt.QtCore", "qgis.PyQt.QtGui", "qgis.PyQt.QtWidgets",
    "PyQt5", "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets",
    "processing", "sip",
]
for name in _MOCK_MODULES:
    sys.modules.setdefault(name, MagicMock())

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO_ROOT / "sun_qgis"
PKG = "sunqgis"


def _register_package(name, path):
    mod = types.ModuleType(name)
    mod.__path__ = [str(path)]
    mod.__file__ = str(path / "__init__.py")
    mod.__package__ = name
    sys.modules[name] = mod


def _load_module(full_name, filepath):
    spec = importlib.util.spec_from_file_location(full_name, str(filepath))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def plugin_dir():
    return PLUGIN_DIR


@pytest.fixture(scope="session")
def core():
    """Load sun_qgis.core as sunqgis.core (leaf module, no qgis deps)."""
    _register_package(PKG, PLUGIN_DIR)
    return _load_module(f"{PKG}.core", PLUGIN_DIR / "core.py")


def make_dummy_dem(path, ncols=100, nrows=100):
    """Write a synthetic alpine DEM (GeoTIFF, EPSG:4326 over Austria).

    Python port of the old Rust create_dummy_elevation (which lived behind
    the gdal-io feature and is no longer in the extension). Same formula:
    600 m base + 400 m ridge + 80 m detail; 0.01°/px from (14°E, 48°N).
    """
    import numpy as np
    from osgeo import gdal, osr

    fy, fx = np.mgrid[0:nrows, 0:ncols].astype(np.float64)
    fx /= ncols - 1
    fy /= nrows - 1
    elev = (
        600.0
        + 400.0 * np.sin(np.pi * fx) * np.sin(np.pi * fy)
        + 80.0 * np.sin(4 * np.pi * fx) * np.cos(3 * np.pi * fy)
    ).astype(np.float32)

    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(str(path), ncols, nrows, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((14.0, 0.01, 0.0, 48.0, 0.0, -0.01))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).WriteArray(elev)
    ds = None
    return str(path)


@pytest.fixture(scope="session")
def dummy_dem(tmp_path_factory):
    """Session-wide 100x100 synthetic DEM path."""
    return make_dummy_dem(tmp_path_factory.mktemp("dem") / "dummy_elevation.tif")
