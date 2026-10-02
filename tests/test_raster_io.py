"""Tests for sun_qgis.raster_io — GDAL-based tiled raster I/O in Python.

The native extension no longer does file I/O: Python reads rasters (tiled for
large DEMs), passes numpy arrays to Rust, and writes the returned band arrays
back to GeoTIFFs.
"""
import numpy as np
import pytest
from osgeo import gdal, osr

gdal.UseExceptions()

UNDEFZ = -9999.0


@pytest.fixture(scope="module")
def raster_io_module(core):
    """Load sun_qgis.raster_io (leaf module; osgeo stays real)."""
    import importlib.util
    import sys

    assert sys.modules.get("sunqgis") is not None
    spec = importlib.util.spec_from_file_location(
        "sunqgis.raster_io", str(core.__file__).replace("core.py", "raster_io.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sunqgis.raster_io"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def small_dem(tmp_path):
    """40x30 f32 DEM, EPSG:4326 over Austria, with a nodata corner."""
    path = str(tmp_path / "dem.tif")
    ncols, nrows = 40, 30
    arr = np.full((nrows, ncols), 500.0, dtype=np.float32)
    arr += np.linspace(0, 300, ncols, dtype=np.float32)[None, :]
    arr[0, 0] = UNDEFZ
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(path, ncols, nrows, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((14.0, 0.01, 0.0, 48.0, 0.0, -0.01))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(UNDEFZ)
    band.WriteArray(arr)
    ds = band = None
    return path, arr, ncols, nrows


def test_raster_meta(small_dem, raster_io_module):
    path, _, ncols, nrows = small_dem
    meta = raster_io_module.raster_meta(path)
    assert meta["ncols"] == ncols
    assert meta["nrows"] == nrows
    assert meta["gt"][0] == pytest.approx(14.0)
    assert meta["gt"][5] == pytest.approx(-0.01)
    assert "WGS 84" in meta["wkt"] or "4326" in meta["wkt"]


def test_read_full_normalizes_nodata(small_dem, raster_io_module):
    """Declared nodata AND NaN both map to UNDEFZ; shape stays (nrows, ncols)."""
    path, arr, ncols, nrows = small_dem
    full = raster_io_module.read_full(path)
    assert full.shape == (nrows, ncols)
    assert full.dtype == np.float32
    assert full[0, 0] == UNDEFZ
    assert full[5, 5] == pytest.approx(arr[5, 5], abs=1e-4)


def test_read_band_matches_full_slice(small_dem, raster_io_module):
    path, arr, ncols, nrows = small_dem
    band = raster_io_module.read_band(path, 10, 20)
    assert band.shape == (10, ncols)
    assert np.allclose(band, arr[10:20], equal_nan=True)


def test_read_band_clips_to_extent(small_dem, raster_io_module):
    path, arr, ncols, nrows = small_dem
    band = raster_io_module.read_band(path, 25, 100)  # only 5 rows left
    assert band.shape == (5, ncols)


def test_band_plan_covers_all_rows_exactly(raster_io_module):
    plan = raster_io_module.band_plan(100, 30)
    assert plan == [(0, 30), (30, 60), (60, 90), (90, 100)]
    # every row covered exactly once
    covered = sum(end - start for start, end in plan)
    assert covered == 100


def test_row_latitudes_geographic_crs(small_dem, raster_io_module):
    """For EPSG:4326 the row centre latitude comes straight from the gt."""
    path, _, ncols, nrows = small_dem
    meta = raster_io_module.raster_meta(path)
    lats = raster_io_module.row_latitudes(meta, ncols, nrows)
    assert len(lats) == nrows
    # first row centre: 48.0 - 0.005
    assert lats[0] == pytest.approx(47.995, abs=1e-9)
    assert lats[-1] < lats[0]


def test_write_band_roundtrip(small_dem, tmp_path, raster_io_module):
    """create_output + write_band per tile == writing the whole array."""
    path, arr, ncols, nrows = small_dem
    meta = raster_io_module.raster_meta(path)
    out_path = str(tmp_path / "out.tif")

    ds = raster_io_module.create_output(out_path, meta)
    data = (arr * 2.0).astype(np.float32)
    for start, end in raster_io_module.band_plan(nrows, 8):
        raster_io_module.write_band(ds, data[start:end], start)
    ds = None

    ds2 = gdal.Open(out_path)
    band2 = ds2.GetRasterBand(1)
    back = band2.ReadAsArray()
    assert band2.GetNoDataValue() == UNDEFZ
    assert np.allclose(back, data)
    assert ds2.GetProjection() != ""
    gt2 = ds2.GetGeoTransform()
    assert gt2[0] == pytest.approx(14.0)
    ds2 = band2 = None
