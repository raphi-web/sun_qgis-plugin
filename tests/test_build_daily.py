"""Tests for sun_qgis.core.build_daily_kwargs — form dict -> compute_raster kwargs."""
import pytest


def _base_form(**over):
    form = {
        "elevation": "/data/dem.tif",
        "day": 172,
        "step": 0.5,
        "linke_value": 3.0,
        "albedo_value": 0.2,
        "output_dir": "/out",
        "output_prefix": "june",
        "want_glob": True,
        "want_beam": False,
        "want_diff": False,
        "want_refl": False,
        "want_insol": True,
        "gpu": True,
    }
    form.update(over)
    return form


def test_minimal_form_maps_elevation_day_and_selected_outputs(core):
    kw = core.build_daily_kwargs(_base_form())
    assert kw["elevation"] == "/data/dem.tif"
    assert kw["day"] == 172
    assert kw["step"] == 0.5
    assert kw["gpu"] is True
    # only the two checked outputs get paths; the rest are None
    assert kw["glob_rad"] == "/out/june_glob.tif"
    assert kw["insol_time"] == "/out/june_insol.tif"
    assert kw["beam_rad"] is None
    assert kw["diff_rad"] is None
    assert kw["refl_rad"] is None


def test_all_outputs_requested_build_all_paths(core):
    form = _base_form(want_beam=True, want_diff=True, want_refl=True)
    kw = core.build_daily_kwargs(form)
    assert kw["beam_rad"] == "/out/june_beam.tif"
    assert kw["diff_rad"] == "/out/june_diff.tif"
    assert kw["refl_rad"] == "/out/june_refl.tif"


def test_scalar_params_forwarded(core):
    kw = core.build_daily_kwargs(_base_form(linke_value=4.5, albedo_value=0.35))
    assert kw["linke_value"] == 4.5
    assert kw["albedo_value"] == 0.35


def test_optional_rasters_included_when_given(core):
    form = _base_form(slope="/data/slope.tif", mask="/data/mask.tif")
    kw = core.build_daily_kwargs(form)
    assert kw["slope"] == "/data/slope.tif"
    assert kw["mask"] == "/data/mask.tif"


def test_missing_optional_rasters_default_to_none(core):
    kw = core.build_daily_kwargs(_base_form())
    assert kw["slope"] is None
    assert kw["aspect"] is None
    assert kw["linke"] is None
    assert kw["albedo"] is None
    assert kw["mask"] is None


def test_no_output_selected_raises(core):
    form = _base_form(want_glob=False, want_insol=False)
    with pytest.raises(ValueError, match="at least one output"):
        core.build_daily_kwargs(form)
