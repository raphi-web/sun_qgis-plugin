"""Tests for sun_qgis.pipeline — the tiled orchestrator.

Python reads the DEM whole (shadow context), derives slope/aspect once over
the full grid, then loops row bands: read optional inputs → native band
compute → write output band. Key property: results are IDENTICAL regardless
of band_rows (tiling must not change the answer), and progress is reported
per band from Python.
"""
import numpy as np
import pytest
from osgeo import gdal, osr

gdal.UseExceptions()

UNDEFZ = -9999.0


@pytest.fixture(scope="module")
def sun_module(core, plugin_dir):
    return core.load_sun(plugin_dir)


@pytest.fixture(scope="module")
def pipeline(core):
    """Load sun_qgis.pipeline with its deps (core, raster_io) registered."""
    import importlib.util
    import sys

    pkg_dir = core.__file__.replace("core.py", "")

    def _load(name):
        full = f"sunqgis.{name}"
        if full in sys.modules:
            return sys.modules[full]
        spec = importlib.util.spec_from_file_location(full, pkg_dir + f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full] = mod
        spec.loader.exec_module(mod)
        return mod

    _load("raster_io")
    return _load("pipeline")


@pytest.fixture()
def walled_dem(tmp_path):
    """30x20 f32 DEM, EPSG:4326 over Austria, with a wall on the north edge
    so winter shadows cross band boundaries."""
    path = str(tmp_path / "dem.tif")
    ncols, nrows = 30, 20
    arr = np.full((nrows, ncols), 500.0, dtype=np.float32)
    arr[0, :] = 900.0
    arr[:, 0] = UNDEFZ  # nodata column
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
    return path


def _daily_form(dem, tmp_path, **over):
    form = {
        "mode": "daily",
        "elevation": dem,
        "day": 355,  # winter: low sun, long shadows from the wall
        "step": 0.5,
        "linke_value": 3.0,
        "albedo_value": 0.2,
        "gpu": False,
        "output_dir": str(tmp_path),
        "output_prefix": "out",
        "want_glob": True,
        "want_beam": False,
        "want_diff": False,
        "want_refl": False,
        "want_insol": False,
        "slope": None,
        "aspect": None,
        "linke": None,
        "albedo": None,
        "mask": None,
    }
    form.update(over)
    return form


def test_daily_pipeline_writes_georeferenced_output(sun_module, pipeline, walled_dem, tmp_path):
    out = tmp_path / "run1"
    out.mkdir()
    form = _daily_form(walled_dem, out)
    paths = pipeline.run_tiled(sun_module, form)
    assert paths == [str(out / "out_glob.tif")]

    ds = gdal.Open(paths[0])
    arr = ds.GetRasterBand(1).ReadAsArray()
    assert arr.shape == (20, 30)
    assert ds.GetRasterBand(1).GetNoDataValue() == UNDEFZ
    assert ds.GetGeoTransform()[0] == pytest.approx(14.0)
    assert ds.GetProjection() != ""
    # nodata column stays nodata; interior computed; winter values plausible
    assert np.all(arr[:, 0] == UNDEFZ)
    valid = arr[1:-1, 1:-1] != UNDEFZ
    assert valid.any()
    vals = arr[1:-1, 1:-1][valid]
    assert vals.min() > 0.0
    assert vals.max() < 10000.0
    ds = None


def test_tiling_does_not_change_results(sun_module, pipeline, walled_dem, tmp_path):
    """The whole point of the tiled reader: band_rows must not change output.
    Shadow context (full DEM) and full-grid slope/aspect make bands exact."""
    single = tmp_path / "single"
    single.mkdir()
    tiled = tmp_path / "tiled"
    tiled.mkdir()

    p1 = pipeline.run_tiled(sun_module, _daily_form(walled_dem, single), band_rows=20)
    p2 = pipeline.run_tiled(sun_module, _daily_form(walled_dem, tiled), band_rows=3)

    ds1 = gdal.Open(p1[0])
    a = ds1.GetRasterBand(1).ReadAsArray()
    ds2 = gdal.Open(p2[0])
    b = ds2.GetRasterBand(1).ReadAsArray()
    ds1 = ds2 = None
    assert np.allclose(a, b, rtol=1e-5, atol=1e-3), "tiled run must match single-band run"
    # Physics sanity: the north-edge wall makes row 1 a steep SOUTH-facing
    # slope, which gains winter sun (sun is in the south) vs. the flat row 15.
    assert a[1, 15] > a[15, 15]


def test_south_wall_casts_shadow_across_bands(sun_module, pipeline, tmp_path):
    """A wall on the SOUTH edge shades rows to its north in winter, and the
    shadow crosses band boundaries — proving shadow_context_elev + row_offset
    index the full grid, not just the local band."""
    path = str(tmp_path / "southwall.tif")
    ncols, nrows = 30, 20
    arr = np.full((nrows, ncols), 500.0, dtype=np.float32)
    arr[nrows - 1, :] = 2000.0  # tall wall on the SOUTH edge
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(path, ncols, nrows, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((14.0, 0.01, 0.0, 48.0, 0.0, -0.01))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).SetNoDataValue(UNDEFZ)
    ds.GetRasterBand(1).WriteArray(arr)
    ds = None

    single = tmp_path / "s_single"
    single.mkdir()
    tiled = tmp_path / "s_tiled"
    tiled.mkdir()

    p1 = pipeline.run_tiled(sun_module, _daily_form(path, single), band_rows=20)
    p2 = pipeline.run_tiled(sun_module, _daily_form(path, tiled), band_rows=3)
    d1 = gdal.Open(p1[0])
    a = d1.GetRasterBand(1).ReadAsArray()
    d2 = gdal.Open(p2[0])
    b = d2.GetRasterBand(1).ReadAsArray()
    d1 = d2 = None
    assert np.allclose(a, b, rtol=1e-5, atol=1e-3)
    # Row 18 sits just north of the 2000 m wall → heavily shaded at the low
    # winter sun; row 2 is far from it → much brighter.
    assert a[18, 15] < a[2, 15]


def test_multiple_outputs(sun_module, pipeline, walled_dem, tmp_path):
    out = tmp_path / "multi"
    out.mkdir()
    form = _daily_form(walled_dem, out, want_beam=True, want_insol=True)
    paths = pipeline.run_tiled(sun_module, form, band_rows=7)
    names = sorted(p.rsplit("_", 1)[-1] for p in paths)
    assert names == ["beam.tif", "glob.tif", "insol.tif"]
    for p in paths:
        ds = gdal.Open(p)
        arr = ds.GetRasterBand(1).ReadAsArray()
        assert arr.shape == (20, 30)
        ds = None


def test_mask_raster_respected(sun_module, pipeline, walled_dem, tmp_path):
    mask_path = str(tmp_path / "mask.tif")
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(mask_path, 30, 20, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((14.0, 0.01, 0.0, 48.0, 0.0, -0.01))
    m = np.ones((20, 30), dtype=np.float32)
    m[:, 20:] = 0.0
    ds.GetRasterBand(1).WriteArray(m)
    ds = None

    out = tmp_path / "masked"
    out.mkdir()
    form = _daily_form(walled_dem, out, mask=mask_path)
    paths = pipeline.run_tiled(sun_module, form, band_rows=6)
    ds = gdal.Open(paths[0])
    arr = ds.GetRasterBand(1).ReadAsArray()
    ds = None
    assert np.all(arr[:, 20:] == UNDEFZ)
    assert (arr[5:-5, 5:15] != UNDEFZ).all()


def test_progress_reported_per_band(sun_module, pipeline, walled_dem, tmp_path):
    out = tmp_path / "prog"
    out.mkdir()
    seen = []
    pipeline.run_tiled(
        sun_module, _daily_form(walled_dem, out), progress_cb=seen.append, band_rows=5
    )
    assert seen == pytest.approx([25.0, 50.0, 75.0, 100.0])


def test_annual_pipeline(sun_module, pipeline, walled_dem, tmp_path):
    out = tmp_path / "annual"
    out.mkdir()
    form = _daily_form(walled_dem, out)
    form.update(
        mode="annual",
        day_start=80,
        day_end=100,
        day_step=10,
        panel_efficiency=0.21,
        use_horizon=False,
        horizon_n_az=64,
    )
    paths = pipeline.run_tiled(sun_module, form, band_rows=4)
    assert paths == [str(out / "out_potential.tif")]
    ds = gdal.Open(paths[0])
    arr = ds.GetRasterBand(1).ReadAsArray()
    ds = None
    assert np.all(arr[:, 0] == UNDEFZ)
    valid = arr != UNDEFZ
    assert valid.any()
    assert arr[valid].min() >= 0.0
    assert arr[valid].max() < 100.0  # ~20 days * 0.21 efficiency bound


def test_validation_errors_propagate(sun_module, pipeline, walled_dem, tmp_path):
    form = _daily_form(walled_dem, tmp_path)
    form["day"] = 999
    with pytest.raises(ValueError, match="Day of year"):
        pipeline.run_tiled(sun_module, form)


@pytest.fixture(scope="module")
def gpu_flag(sun_module):
    return bool(sun_module.gpu_available())


def test_gpu_form_flag_reaches_native_call(sun_module, pipeline, walled_dem, tmp_path, monkeypatch):
    """form['gpu']=True must be passed to the native band call (the dialog's
    GPU checkbox is honored), and False keeps the CPU path."""
    out = tmp_path / "gpuflag"
    out.mkdir()
    seen = []
    real = sun_module.compute_raster_bands

    def spy(**kw):
        seen.append(kw["gpu"])
        return real(**kw)

    monkeypatch.setattr(sun_module, "compute_raster_bands", spy)
    pipeline.run_tiled(sun_module, _daily_form(walled_dem, out, gpu=True), band_rows=10)
    assert seen and all(g is True for g in seen)

    seen.clear()
    out2 = tmp_path / "gpuflag2"
    out2.mkdir()
    pipeline.run_tiled(sun_module, _daily_form(walled_dem, out2, gpu=False), band_rows=10)
    assert seen and all(g is False for g in seen)


def test_gpu_run_produces_same_shape_and_nodata(sun_module, pipeline, walled_dem, tmp_path, gpu_flag):
    """A gpu=True run writes the same georeferenced output with the same
    nodata placement as gpu=False (values may differ at shadow terminators)."""
    if not gpu_flag:
        pytest.skip("no wgpu adapter")
    cpu_dir = tmp_path / "gcpu"
    gpu_dir = tmp_path / "ggpu"
    cpu_dir.mkdir()
    gpu_dir.mkdir()
    p1 = pipeline.run_tiled(sun_module, _daily_form(walled_dem, cpu_dir, gpu=False), band_rows=7)
    p2 = pipeline.run_tiled(sun_module, _daily_form(walled_dem, gpu_dir, gpu=True), band_rows=7)
    d1 = gdal.Open(p1[0])
    a = d1.GetRasterBand(1).ReadAsArray()
    d2 = gdal.Open(p2[0])
    b = d2.GetRasterBand(1).ReadAsArray()
    d1 = d2 = None
    assert np.array_equal(a == UNDEFZ, b == UNDEFZ)
    valid = a != UNDEFZ
    rel = np.abs(b[valid] - a[valid]) / np.abs(a[valid]).clip(1.0)
    # This fixture is shadow-terminator-dominated (huge wall, low winter
    # sun), so f32-shader vs f64-CPU ray-march flips a noticeable MINORITY
    # of pixels fully shaded/unshaded (rel == 1.0). The contract here is
    # pass-through, not precision (that's test_gpu_array_api): most pixels
    # must agree closely, and hard flips stay a small fraction.
    assert (rel < 0.02).mean() > 0.8, f"only {(rel < 0.02).mean():.2%} of pixels agree"
    assert (rel > 0.5).mean() < 0.15, f"{(rel > 0.5).mean():.2%} of pixels hard-flipped"


def test_gpu_falls_back_to_cpu_when_unavailable(sun_module, pipeline, walled_dem, tmp_path, monkeypatch):
    """When gpu_available() is False (no adapter/drivers), a gpu=True form
    must still compute — silently falling back to the CPU path."""
    out = tmp_path / "fallback"
    out.mkdir()
    monkeypatch.setattr(sun_module, "gpu_available", lambda: False)
    seen = []
    real = sun_module.compute_raster_bands

    def spy(**kw):
        seen.append(kw["gpu"])
        return real(**kw)

    monkeypatch.setattr(sun_module, "compute_raster_bands", spy)
    paths = pipeline.run_tiled(sun_module, _daily_form(walled_dem, out, gpu=True), band_rows=10)
    assert seen and all(g is False for g in seen), "must fall back to CPU"
    import os
    assert os.path.exists(paths[0])
