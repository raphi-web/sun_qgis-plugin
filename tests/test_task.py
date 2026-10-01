"""Tests for sun_qgis.task.run_sun_task — validate + dispatch + output list.

Uses the REAL native extension for dispatch checks (fast, tiny DEM) and a
recording fake for kwarg routing.
"""
import pytest


@pytest.fixture(scope="module")
def task_module(core):
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "sunqgis.task", str(core.__file__).replace("core.py", "task.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sunqgis.task"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sun_module(core, plugin_dir):
    return core.load_sun(plugin_dir)


@pytest.fixture(scope="module")
def dem_path(sun_module, tmp_path_factory):
    path = str(tmp_path_factory.mktemp("dem") / "dummy_elevation.tif")
    sun_module.create_dummy(path)
    return path


class _RecordingSun:
    def __init__(self):
        self.calls = []

    def compute_raster(self, **kw):
        self.calls.append(("daily", kw))

    def compute_annual_potential(self, **kw):
        self.calls.append(("annual", kw))


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
    }
    form.update(over)
    return form


def test_invalid_form_raises_valueerror_before_dispatch(task_module):
    fake = _RecordingSun()
    with pytest.raises(ValueError, match="Elevation"):
        task_module.run_sun_task(fake, {"elevation": "", "mode": "daily"})
    assert fake.calls == []


def test_daily_form_dispatches_compute_raster_and_returns_outputs(
    task_module, sun_module, dem_path, tmp_path
):
    form = _daily_form(dem_path, tmp_path)
    outputs = task_module.run_sun_task(sun_module, form)
    assert outputs == [str(tmp_path / "t_glob.tif"), str(tmp_path / "t_insol.tif")]
    for p in outputs:
        import os

        assert os.path.exists(p)


def test_annual_form_dispatches_compute_annual_potential(task_module, dem_path, tmp_path):
    fake = _RecordingSun()
    form = {
        "elevation": dem_path,
        "day_start": 80,
        "day_end": 100,
        "day_step": 20,
        "step": 0.5,
        "panel_efficiency": 0.21,
        "linke_value": 3.0,
        "albedo_value": 0.2,
        "output_dir": str(tmp_path),
        "output_prefix": "t",
        "gpu": False,
        "use_horizon": False,
        "horizon_n_az": 64,
        "mode": "annual",
    }
    outputs = task_module.run_sun_task(fake, form)
    assert fake.calls[0][0] == "annual"
    assert outputs == [str(tmp_path / "t_potential.tif")]


def test_native_error_propagates(task_module, tmp_path):
    """A missing elevation file must surface as RuntimeError, not silence."""
    form = _daily_form("/nonexistent/dem.tif", tmp_path)
    with pytest.raises(RuntimeError):
        task_module.run_sun_task(_FakeBrokenSun(), form)


class _FakeBrokenSun:
    def compute_raster(self, **kw):
        raise RuntimeError("could not open elevation")

    def compute_annual_potential(self, **kw):
        raise RuntimeError("boom")
