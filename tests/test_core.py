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


# The release zip bundles one engine binary per platform. Loading must pick
# the file THIS interpreter can import, never "the first sun* file".
_LINUX = "sun.cpython-312-x86_64-linux-gnu.so"
_MACOS = "sun.cpython-312-darwin.so"
_WINDOWS = "sun.cp312-win_amd64.pyd"


def _multi_platform_dir(core, tmp_path, plugin_dir):
    import shutil

    real = core.find_extension(plugin_dir)
    shutil.copy(real, tmp_path / real.name)
    for foreign in (_MACOS, _WINDOWS):
        (tmp_path / foreign).write_bytes(b"not a binary for this platform")
    return tmp_path


def test_load_sun_picks_binary_for_this_interpreter(core, plugin_dir, tmp_path):
    """macOS's file sorts first alphabetically; Linux must still load its own."""
    d = _multi_platform_dir(core, tmp_path, plugin_dir)
    sun = core.load_sun(d)
    assert callable(sun.compute_raster_bands)


def test_find_extension_windows_suffixes(core, tmp_path):
    for name in (_LINUX, _MACOS, _WINDOWS):
        (tmp_path / name).write_bytes(b"x")
    found = core.find_extension(tmp_path, suffixes=[".cp312-win_amd64.pyd", ".pyd"])
    assert found.name == _WINDOWS


def test_find_extension_macos_suffixes(core, tmp_path):
    for name in (_LINUX, _MACOS, _WINDOWS):
        (tmp_path / name).write_bytes(b"x")
    found = core.find_extension(
        tmp_path, suffixes=[".cpython-312-darwin.so", ".abi3.so", ".so"]
    )
    assert found.name == _MACOS


def test_load_sun_foreign_binaries_only_names_the_mismatch(core, tmp_path):
    """Binaries exist but none fits this interpreter (e.g. wrong Python
    version): the error must list what was found and what was needed."""
    import pytest

    (tmp_path / "sun.cpython-311-x86_64-linux-gnu.so").write_bytes(b"x")
    (tmp_path / _WINDOWS).write_bytes(b"x")
    with pytest.raises(ImportError) as exc:
        core.load_sun(tmp_path)
    msg = str(exc.value)
    assert "sun.cpython-311-x86_64-linux-gnu.so" in msg
    import importlib.machinery

    assert importlib.machinery.EXTENSION_SUFFIXES[0] in msg
