"""GPU progress reporting: the wgpu paths must emit 'Progress: NN%' on stderr
like the CPU paths, so the plugin streams percentages for GPU runs too.
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


@pytest.mark.gpu
def test_daily_gpu_reports_progress_percentages(core, sun_module, dem_path, tmp_path):
    seen = []
    kwargs = core.build_daily_kwargs(
        {
            "elevation": dem_path,
            "day": 172,
            "step": 0.5,
            "linke_value": 3.0,
            "albedo_value": 0.2,
            "output_dir": str(tmp_path),
            "output_prefix": "gprog",
            "want_glob": True,
            "want_beam": False,
            "want_diff": False,
            "want_refl": False,
            "want_insol": False,
            "gpu": True,
        }
    )
    kwargs["quiet"] = False
    core.run_capturing_stderr(
        lambda: sun_module.compute_raster(**kwargs), seen.append
    )
    assert seen, "GPU daily path emitted no Progress: N% reports"
    assert seen[-1] == 100.0
    assert all(0.0 <= p <= 100.0 for p in seen)
    # A single-tile run must still stream intermediate phases, not just 100%.
    assert len(seen) >= 2, (
        f"only {seen} reported — single-tile GPU runs should emit phase "
        f"checkpoints (post-setup, post-dispatch) before the final 100%"
    )
    assert seen[0] < 100.0
    assert all(b >= a for a, b in zip(seen, seen[1:])), f"not monotonic: {seen}"


@pytest.mark.gpu
def test_annual_gpu_reports_progress_percentages(core, sun_module, dem_path, tmp_path):
    seen = []
    kwargs = core.build_annual_kwargs(
        {
            "elevation": dem_path,
            "day_start": 100,
            "day_end": 200,
            "day_step": 25,
            "step": 0.5,
            "panel_efficiency": 0.21,
            "linke_value": 3.0,
            "albedo_value": 0.2,
            "output_dir": str(tmp_path),
            "output_prefix": "gprog",
            "gpu": True,
            "use_horizon": False,
            "horizon_n_az": 64,
        }
    )
    kwargs["quiet"] = False
    core.run_capturing_stderr(
        lambda: sun_module.compute_annual_potential(**kwargs), seen.append
    )
    assert seen, "GPU annual path emitted no Progress: N% reports"
    assert seen[-1] == 100.0
    # monotonic non-decreasing
    assert all(b >= a for a, b in zip(seen, seen[1:]))
