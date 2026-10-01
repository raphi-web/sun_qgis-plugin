"""End-to-end tests: real sun extension + real GDAL, no mocks.

These run the production path (build kwargs -> call native compute_raster ->
open outputs with osgeo.gdal) on a small synthetic DEM.
"""
import pytest
from osgeo import gdal

gdal.UseExceptions()


@pytest.fixture(scope="module")
def sun_module(core, plugin_dir):
    return core.load_sun(plugin_dir)


@pytest.fixture(scope="module")
def dem_path(sun_module, tmp_path_factory):
    path = str(tmp_path_factory.mktemp("dem") / "dummy_elevation.tif")
    sun_module.create_dummy(path)
    return path


def _open_and_stats(path):
    ds = gdal.Open(path)
    assert ds is not None, f"output missing: {path}"
    band = ds.GetRasterBand(1)
    stats = band.ComputeStatistics(False)  # min, max, mean, stddev
    return ds, band, stats


def test_daily_cpu_glob_and_insol_end_to_end(core, sun_module, dem_path, tmp_path):
    form = {
        "elevation": dem_path,
        "day": 172,
        "step": 0.5,
        "linke_value": 3.0,
        "albedo_value": 0.2,
        "output_dir": str(tmp_path),
        "output_prefix": "e2e",
        "want_glob": True,
        "want_beam": False,
        "want_diff": False,
        "want_refl": False,
        "want_insol": True,
        "gpu": False,
    }
    kwargs = core.build_daily_kwargs(form)
    sun_module.compute_raster(**kwargs)

    ds, band, (mn, mx, mean, _) = _open_and_stats(kwargs["glob_rad"])
    nodata = band.GetNoDataValue()
    assert nodata == pytest.approx(-9999.0)
    # Summer solstice, central Austria: plausible Wh/m²/day range, valid pixels present
    assert mx > mn
    assert 1000.0 < mean < 12000.0
    # Insolation time in hours, <= day length at 47.5°N mid-June (~15.8h)
    _, _, (imn, imx, _, _) = _open_and_stats(kwargs["insol_time"])
    assert 0.0 <= imn <= imx <= 24.0
    # Same geometry as the input DEM
    assert ds.RasterXSize == 100 and ds.RasterYSize == 100


def test_unselected_outputs_are_not_written(core, sun_module, dem_path, tmp_path):
    import os

    form = {
        "elevation": dem_path,
        "day": 80,
        "step": 0.5,
        "linke_value": 3.0,
        "albedo_value": 0.2,
        "output_dir": str(tmp_path),
        "output_prefix": "e2e",
        "want_glob": True,
        "want_beam": False,
        "want_diff": False,
        "want_refl": False,
        "want_insol": False,
        "gpu": False,
    }
    kwargs = core.build_daily_kwargs(form)
    sun_module.compute_raster(**kwargs)
    assert os.path.exists(kwargs["glob_rad"])
    assert kwargs["beam_rad"] is None
    assert not os.path.exists(str(tmp_path / "e2e_beam.tif"))


def test_annual_cpu_end_to_end(core, sun_module, dem_path, tmp_path):
    """Annual potential with a coarse DOY stride keeps runtime test-friendly."""
    form = {
        "elevation": dem_path,
        "day_start": 80,
        "day_end": 280,
        "day_step": 40,
        "step": 0.5,
        "panel_efficiency": 0.21,
        "linke_value": 3.0,
        "albedo_value": 0.2,
        "output_dir": str(tmp_path),
        "output_prefix": "e2e",
        "gpu": False,
        "use_horizon": False,
        "horizon_n_az": 64,
    }
    kwargs = core.build_annual_kwargs(form)
    sun_module.compute_annual_potential(**kwargs)

    ds, band, (mn, mx, mean, _) = _open_and_stats(kwargs["out_path"])
    assert ds.RasterXSize == 100 and ds.RasterYSize == 100
    # kWh/m² over ~200 days with 21% efficiency: plausible, positive, ordered
    assert mx > mn >= 0.0
    assert mean < 300.0


@pytest.mark.gpu
def test_daily_gpu_matches_cpu_within_tolerance(core, sun_module, dem_path, tmp_path):
    """GPU (wgpu) path must agree with the CPU path on the same inputs."""
    form = {
        "elevation": dem_path,
        "day": 172,
        "step": 0.5,
        "linke_value": 3.0,
        "albedo_value": 0.2,
        "output_dir": str(tmp_path),
        "output_prefix": "cmp",
        "want_glob": True,
        "want_beam": False,
        "want_diff": False,
        "want_refl": False,
        "want_insol": False,
        "gpu": False,
    }
    core_kwargs = core.build_daily_kwargs(form)
    gpu_kwargs = core.build_daily_kwargs({**form, "gpu": True})
    gpu_kwargs["glob_rad"] = str(tmp_path / "cmp_glob_gpu.tif")

    sun_module.compute_raster(**core_kwargs)
    sun_module.compute_raster(**gpu_kwargs)

    # Hold every GDAL handle in a named local: chaining lets the Dataset be
    # GC'd while the Band proxy is alive -> GDALRasterBandShadow TypeError.
    cpu_ds = gdal.Open(core_kwargs["glob_rad"])
    cpu_band = cpu_ds.GetRasterBand(1)
    cpu_arr = cpu_band.ReadAsArray()
    gpu_ds = gdal.Open(gpu_kwargs["glob_rad"])
    gpu_band = gpu_ds.GetRasterBand(1)
    gpu_arr = gpu_band.ReadAsArray()
    valid = (cpu_arr != -9999.0) & (gpu_arr != -9999.0)
    assert valid.any(), "no valid pixels to compare"
    rel = abs(gpu_arr[valid] - cpu_arr[valid]) / abs(cpu_arr[valid]).clip(1.0)
    assert rel.mean() < 0.02, f"mean relative deviation {rel.mean():.4f} too large"
