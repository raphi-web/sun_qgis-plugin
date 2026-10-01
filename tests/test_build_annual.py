"""Tests for sun_qgis.core.build_annual_kwargs — form dict -> compute_annual_potential kwargs."""
import pytest


def _base_form(**over):
    form = {
        "elevation": "/data/dem.tif",
        "day_start": 1,
        "day_end": 365,
        "day_step": 10,
        "step": 0.5,
        "panel_efficiency": 0.21,
        "linke_value": 3.0,
        "albedo_value": 0.2,
        "output_dir": "/out",
        "output_prefix": "annual",
        "gpu": False,
        "use_horizon": True,
        "horizon_n_az": 128,
    }
    form.update(over)
    return form


def test_minimal_form_maps_scalars_and_output_path(core):
    kw = core.build_annual_kwargs(_base_form())
    assert kw["elevation"] == "/data/dem.tif"
    assert kw["out_path"] == "/out/annual_potential.tif"
    assert kw["day_start"] == 1
    assert kw["day_end"] == 365
    assert kw["day_step"] == 10
    assert kw["panel_efficiency"] == 0.21
    assert kw["gpu"] is False
    assert kw["use_horizon"] is True
    assert kw["horizon_n_az"] == 128


def test_inverted_day_range_raises(core):
    form = _base_form(day_start=200, day_end=100)
    with pytest.raises(ValueError, match="day_start"):
        core.build_annual_kwargs(form)


def test_optional_rasters_included_when_given(core):
    form = _base_form(slope="/data/slope.tif", mask="/data/mask.tif")
    kw = core.build_annual_kwargs(form)
    assert kw["slope"] == "/data/slope.tif"
    assert kw["mask"] == "/data/mask.tif"
    assert kw["aspect"] is None


def test_horizon_flag_off_still_forwards_bins(core):
    kw = core.build_annual_kwargs(_base_form(use_horizon=False))
    assert kw["use_horizon"] is False
    assert kw["horizon_n_az"] == 128
