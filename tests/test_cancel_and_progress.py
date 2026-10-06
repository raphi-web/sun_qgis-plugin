"""Tests for cancellation (task.isCanceled honoured) and intra-band progress."""
import numpy as np
import pytest
from osgeo import gdal, osr

gdal.UseExceptions()
UNDEFZ = -9999.0


@pytest.fixture()
def walled_dem(tmp_path):
    """30×20 f32 DEM, EPSG:4326, with a wall on the north edge."""
    path = str(tmp_path / "dem.tif")
    ncols, nrows = 30, 20
    arr = np.full((nrows, ncols), 500.0, dtype=np.float32)
    arr[0, :] = 900.0
    arr[:, 0] = UNDEFZ
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


@pytest.fixture(scope="module")
def sun_module(core):
    return core.load_sun()


@pytest.fixture(scope="module")
def pipeline(core):
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


def _daily_form(dem, tmp_path, **over):
    form = {
        "mode": "daily",
        "elevation": dem,
        "day": 172,
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
        "slope": None, "aspect": None, "linke": None, "albedo": None, "mask": None,
    }
    form.update(over)
    return form


# ── Cancel ────────────────────────────────────────────────────────────────


def test_cancel_stops_band_loop_early(sun_module, pipeline, walled_dem, tmp_path, monkeypatch):
    """A canceled_check that returns True mid-loop must halt the pipeline
    and not compute remaining bands."""
    out = tmp_path / "cancel"
    out.mkdir()
    band_calls = []
    real = sun_module.compute_raster_bands

    def spy(**kw):
        band_calls.append(kw["row_offset"])
        return real(**kw)

    monkeypatch.setattr(sun_module, "compute_raster_bands", spy)

    # band_plan with 20 rows, band_rows=5 => 4 bands at offsets 0,5,10,15
    seen_checks = []

    def stopped_after_second():
        seen_checks.append(True)
        return len(band_calls) >= 2

    with pytest.raises(RuntimeError, match="cancel"):
        pipeline.run_tiled(
            sun_module,
            _daily_form(walled_dem, out),
            progress_cb=lambda pct: None,
            canceled_check=stopped_after_second,
            band_rows=5,
        )

    assert len(band_calls) == 2, "stopped after band 2, not 4"
    assert band_calls == [0, 5]


def test_cancel_is_checked_before_first_band(sun_module, pipeline, walled_dem, tmp_path, monkeypatch):
    """If canceled_check returns True even before band 1, nothing is computed."""
    out = tmp_path / "cancelpre"
    out.mkdir()
    calls = []
    real = sun_module.compute_raster_bands

    def spy(**kw):
        calls.append(kw["row_offset"])
        return real(**kw)

    monkeypatch.setattr(sun_module, "compute_raster_bands", spy)

    with pytest.raises(RuntimeError, match="cancel"):
        pipeline.run_tiled(
            sun_module,
            _daily_form(walled_dem, out),
            progress_cb=lambda pct: None,
            canceled_check=lambda: True,
            band_rows=5,
        )
    assert calls == []


def test_cancel_callable_defaults_to_noop(sun_module, pipeline, walled_dem, tmp_path, monkeypatch):
    """When no canceled_check is given, the pipeline still works (backward compat)."""
    out = tmp_path / "nodefault"
    out.mkdir()
    # Must not raise: existing callers don't pass canceled_check
    paths = pipeline.run_tiled(sun_module, _daily_form(walled_dem, out), band_rows=10)
    assert len(paths) == 1
    ds = gdal.Open(paths[0])
    a = ds.GetRasterBand(1).ReadAsArray()
    ds = None
    assert np.any(a != UNDEFZ)


# ── Progress ──────────────────────────────────────────────────────────────


def test_fine_progress_fires_per_band(sun_module, pipeline, walled_dem, tmp_path, monkeypatch):
    """The primary progress_cb fires after every completed band, same as today.
    This test just pins the current contract so the finer-progress addition
    is a backward-compatible extension."""
    out = tmp_path / "fineprog"
    out.mkdir()
    pcts = []

    real = sun_module.compute_raster_bands

    def spy(**kw):
        return real(**kw)

    monkeypatch.setattr(sun_module, "compute_raster_bands", spy)
    pipeline.run_tiled(
        sun_module,
        _daily_form(walled_dem, out),
        progress_cb=pcts.append,
        band_rows=5,  # 4 bands for a 20-row DEM
    )
    assert len(pcts) == 4, "one progress callback per band"
    assert pcts == pytest.approx([25.0, 50.0, 75.0, 100.0])


def test_fine_progress_accepts_extra_fine_cb(sun_module, pipeline, walled_dem, tmp_path, monkeypatch):
    """A second callback `fine_progress_cb` fires more often: once after the
    first band (as baseline timing) and then after every subsequent band,
    called with (pct_start, pct_end, elapsed_previous_band_s).

    This lets the dialog interpolate progress during long GPU bands, fixing
    the '0% for minutes' problem."""
    out = tmp_path / "finecb"
    out.mkdir()
    fine = []

    real = sun_module.compute_raster_bands

    def spy(**kw):
        return real(**kw)

    monkeypatch.setattr(sun_module, "compute_raster_bands", spy)
    monkeypatch.setattr(
        sun_module, "gpu_last_run_stats",
        lambda: {"submissions": 5, "max_submit_seconds": 0.05},
    )
    pipeline.run_tiled(
        sun_module,
        _daily_form(walled_dem, out),
        progress_cb=lambda pct: None,
        fine_progress_cb=lambda pct_s, pct_e, el: fine.append((pct_s, pct_e, el)),
        band_rows=5,
    )
    # First call after band 0: baseline
    # Then after each subsequent band: (pct_start, pct_end, elapsed_s)
    assert len(fine) > 0, "fine_progress_cb was never called"
    for entry in fine:
        assert len(entry) == 3, f"expected (pct_start, pct_end, elapsed_s), got {entry}"
        pct_start, pct_end, elapsed = entry
        assert 0.0 <= pct_start < pct_end <= 100.0
        assert elapsed >= 0.0