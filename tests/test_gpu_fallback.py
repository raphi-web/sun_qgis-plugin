"""GPU RuntimeError → auto CPU fallback (todo #7)."""
import numpy as np
import pytest
from osgeo import gdal, osr

gdal.UseExceptions()
UNDEFZ = -9999.0


@pytest.fixture()
def walled_dem(tmp_path):
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
        "gpu": True,
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


def test_gpu_failure_falls_back_to_cpu(sun_module, pipeline, walled_dem, tmp_path, monkeypatch):
    """When the GPU call raises RuntimeError('GPU computation failed'),
    the pipeline must retry with gpu=False and produce output."""
    out = tmp_path / "gpufail"
    out.mkdir()
    calls = []
    real = sun_module.compute_raster_bands

    def spy(**kw):
        calls.append(kw["gpu"])
        if kw["gpu"] and len([c for c in calls if c]) == 1:
            raise RuntimeError("GPU computation failed: the device was lost")
        return real(**kw)

    monkeypatch.setattr(sun_module, "compute_raster_bands", spy)
    monkeypatch.setattr(sun_module, "gpu_available", lambda: True)
    paths = pipeline.run_tiled(sun_module, _daily_form(walled_dem, out))
    assert len(paths) >= 1, "must produce output after CPU fallback"
    assert True in calls, "GPU was attempted"
    assert False in calls, "CPU fallback was used"
    # Output must be valid
    ds = gdal.Open(paths[0])
    a = ds.GetRasterBand(1).ReadAsArray()
    ds = None
    assert np.any(a != UNDEFZ)


def test_gpu_fallback_only_catches_gpu_errors(sun_module, pipeline, walled_dem, tmp_path, monkeypatch):
    """A non-GPU RuntimeError must still propagate (not be silently retried)."""
    out = tmp_path / "gpumisc"
    out.mkdir()
    real = sun_module.compute_raster_bands

    def spy(**kw):
        raise RuntimeError("something else broke")

    monkeypatch.setattr(sun_module, "compute_raster_bands", spy)
    monkeypatch.setattr(sun_module, "gpu_available", lambda: True)
    with pytest.raises(RuntimeError, match="something else broke"):
        pipeline.run_tiled(sun_module, _daily_form(walled_dem, out))