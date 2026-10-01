"""Tests for sun_qgis.core — pure logic + native module loading."""


def test_load_sun_returns_module_with_expected_api(core, plugin_dir):
    """Tracer bullet: the bundled extension imports under QGIS's Python
    and exposes the functions the plugin calls."""
    sun = core.load_sun(plugin_dir)
    for attr in ("compute_raster", "compute_annual_potential", "create_dummy"):
        assert hasattr(sun, attr), f"sun module missing {attr}"
    assert callable(sun.compute_raster)


def test_load_sun_raises_helpful_error_when_extension_missing(core, tmp_path):
    """A plugin dir without the .so must fail with an actionable message,
    not a bare ImportError."""
    import pytest

    with pytest.raises(FileNotFoundError, match="sun extension"):
        core.load_sun(tmp_path)
