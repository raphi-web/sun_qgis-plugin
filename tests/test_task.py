"""Tests for sun_qgis.task.run_sun_task — validate + delegate to the tiled
pipeline + output list.

The path-based dispatch is gone: the task now hands the form to
pipeline.run_tiled (Python GDAL I/O around the native array API). These
tests use the REAL extension for end-to-end runs and monkeypatched fakes
for routing/validation checks.
"""
import pytest


@pytest.fixture(scope="module")
def task_module(core):
    import importlib.util
    import sys

    pkg_dir = str(core.__file__).replace("core.py", "")

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
    _load("pipeline")
    return _load("task")


@pytest.fixture(scope="module")
def sun_module(core, plugin_dir):
    return core.load_sun(plugin_dir)


@pytest.fixture(scope="module")
def dem_path(dummy_dem):
    """Session-wide synthetic DEM (written by Python GDAL — the extension
    no longer ships create_dummy)."""
    return dummy_dem


def _daily_form(dem_path, tmp_path, **over):
    form = {
        "elevation": dem_path,
        "day": 172,
        "step": 0.5,
        "linke_value": 3.0,
        "albedo_value": 0.2,
        "output_dir": str(tmp_path),
        "output_prefix": "t",
        "want_glob": True,
        "want_beam": False,
        "want_diff": False,
        "want_refl": False,
        "want_insol": True,
        "gpu": False,
        "mode": "daily",
        "slope": None,
        "aspect": None,
        "linke": None,
        "albedo": None,
        "mask": None,
    }
    form.update(over)
    return form


def test_invalid_form_raises_valueerror_before_any_io(task_module):
    """Validation lives in pipeline.run_tiled and fires before any file is
    opened — run_sun_task must propagate it."""
    with pytest.raises(ValueError, match="Elevation"):
        task_module.run_sun_task(object(), {"elevation": "", "mode": "daily"})


def test_run_sun_task_delegates_to_pipeline(task_module, monkeypatch):
    recorded = {}

    def fake_run(sun, form, progress_cb=None, band_rows=None):
        recorded["sun"] = sun
        recorded["form"] = form
        recorded["cb"] = progress_cb
        recorded["band_rows"] = band_rows
        return ["/x/out.tif"]

    monkeypatch.setattr(task_module.pipeline, "run_tiled", fake_run)
    form = _daily_form("/data/dem.tif", "/tmp")
    sentinel = object()
    cb = lambda p: None
    outputs = task_module.run_sun_task(sentinel, form, progress_cb=cb, band_rows=512)
    assert outputs == ["/x/out.tif"]
    assert recorded["sun"] is sentinel
    assert recorded["form"] is form
    assert recorded["cb"] is cb
    assert recorded["band_rows"] == 512


def test_daily_run_end_to_end_writes_outputs(task_module, sun_module, dem_path, tmp_path):
    import os

    form = _daily_form(dem_path, tmp_path)
    outputs = task_module.run_sun_task(sun_module, form)
    assert outputs == [str(tmp_path / "t_glob.tif"), str(tmp_path / "t_insol.tif")]
    for p in outputs:
        assert os.path.exists(p)


def test_annual_run_end_to_end(task_module, sun_module, dem_path, tmp_path):
    form = _daily_form(dem_path, tmp_path, output_prefix="a")
    form.update(
        mode="annual",
        day_start=80,
        day_end=100,
        day_step=20,
        panel_efficiency=0.21,
        use_horizon=False,
        horizon_n_az=64,
    )
    outputs = task_module.run_sun_task(sun_module, form)
    assert outputs == [str(tmp_path / "a_potential.tif")]
    import os

    assert os.path.exists(outputs[0])


def test_native_error_propagates(task_module, sun_module, tmp_path):
    """A missing elevation file must surface, not silence."""
    form = _daily_form("/nonexistent/dem.tif", tmp_path)
    with pytest.raises(Exception):
        task_module.run_sun_task(sun_module, form)


def test_progress_callback_receives_updates(task_module, sun_module, dem_path, tmp_path):
    """run_sun_task streams 0..100 progress from the tiled pipeline."""
    seen = []
    form = _daily_form(dem_path, tmp_path, output_prefix="prog")
    task_module.run_sun_task(sun_module, form, progress_cb=seen.append, band_rows=25)
    assert seen, "no progress updates received"
    assert seen[-1] == pytest.approx(100.0)
    assert all(0.0 <= p <= 100.0 for p in seen)
    assert seen == sorted(seen), "progress must be monotonic"
