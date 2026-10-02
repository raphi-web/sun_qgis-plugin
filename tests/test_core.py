"""Tests for sun_qgis.core — pure logic + native module loading."""


def test_load_sun_returns_module_with_expected_api(core, plugin_dir):
    """Tracer bullet: the bundled extension imports under QGIS's Python
    and exposes the array API the plugin calls."""
    sun = core.load_sun(plugin_dir)
    for attr in core.REQUIRED_API:
        assert hasattr(sun, attr), f"sun module missing {attr}"
    assert callable(sun.compute_raster_bands)


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


def test_load_sun_raises_helpful_error_when_extension_missing(core, tmp_path):
    """A plugin dir without the .so must fail with an actionable message,
    not a bare ImportError."""
    import pytest

    with pytest.raises(FileNotFoundError, match="sun extension"):
        core.load_sun(tmp_path)
