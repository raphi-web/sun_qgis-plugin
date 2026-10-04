"""Tests for sun_qgis.core — pure logic + loading the pip-installed engine."""
import inspect
import sys
import types

import pytest


def test_load_sun_returns_module_with_expected_api(core):
    """Tracer bullet: the pip-installed engine (sun-solar-radiation) imports
    under QGIS's Python and exposes the array API the plugin calls."""
    sun = core.load_sun()
    for attr in core.REQUIRED_API:
        assert hasattr(sun, attr), f"sun module missing {attr}"
    assert callable(sun.compute_raster_bands)


def test_load_sun_takes_no_plugin_dir(core):
    """The engine comes from pip, not from a file next to the plugin.
    A leftover plugin_dir parameter would invite bundling binaries again."""
    assert list(inspect.signature(core.load_sun).parameters) == []


def test_required_api_is_gdal_free_surface(core):
    """The required surface must be the array API only — a path-based
    function creeping back in means GDAL linkage came back with it."""
    for attr in core.REQUIRED_API:
        assert attr in (
            "compute_raster_bands",
            "compute_annual_bands",
            "horn_slope_aspect",
            "compute_pixel",
        ), f"unexpected entry in REQUIRED_API: {attr}"


def test_engine_not_installed_explains_pip_install(core, monkeypatch):
    monkeypatch.setitem(sys.modules, "sun", None)  # makes `import sun` fail
    with pytest.raises(ImportError) as exc:
        core.load_sun()
    assert "pip install sun-solar-radiation" in str(exc.value)


def test_unrelated_sun_module_is_rejected(core, monkeypatch):
    """Another package named `sun` (e.g. an old pre-release build with the
    path API) must not be mistaken for the engine."""
    fake = types.ModuleType("sun")
    fake.__file__ = "/somewhere/site-packages/sun/__init__.py"
    fake.compute_raster = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "sun", fake)
    with pytest.raises(ImportError) as exc:
        core.load_sun()
    msg = str(exc.value)
    assert "/somewhere/site-packages/sun/__init__.py" in msg
    assert "pip install --upgrade sun-solar-radiation" in msg
    assert "pip uninstall sun" in msg


@pytest.mark.parametrize("old", ["0.1.0", "0.0.9"])
def test_outdated_engine_is_rejected(core, monkeypatch, old):
    """0.1.0 lacks the never-sunlit and east-aspect fixes: refuse it."""
    monkeypatch.setattr(core, "engine_version", lambda: old)
    with pytest.raises(ImportError) as exc:
        core.load_sun()
    msg = str(exc.value)
    assert old in msg
    assert "pip install --upgrade sun-solar-radiation" in msg


@pytest.mark.parametrize("ok", ["0.1.1", "0.1.10", "0.2.0", "1.0.0", "0.1.2.dev3"])
def test_current_engine_versions_accepted(core, monkeypatch, ok):
    monkeypatch.setattr(core, "engine_version", lambda: ok)
    assert core.load_sun() is not None


def test_engine_version_reads_installed_distribution(core):
    from importlib import metadata

    assert core.engine_version() == metadata.version("sun-solar-radiation")
