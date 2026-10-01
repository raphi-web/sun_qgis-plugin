"""Tests for sun_qgis.core.validate_form — dialog inputs -> list of error strings."""


def _form(**over):
    base = {
        "elevation": "/data/dem.tif",
        "day": 172,
        "step": 0.5,
        "day_start": 1,
        "day_end": 365,
        "output_dir": "/out",
        "output_prefix": "sol",
        "mode": "daily",
        "want_glob": True,
        "gpu": False,
    }
    base.update(over)
    return base


def test_valid_daily_form_has_no_errors(core):
    assert core.validate_form(_form()) == []


def test_missing_elevation_is_an_error(core):
    errors = core.validate_form(_form(elevation=""))
    assert any("elevation" in e.lower() for e in errors)


def test_day_out_of_range_daily(core):
    assert any("day" in e.lower() for e in core.validate_form(_form(day=0)))
    assert any("day" in e.lower() for e in core.validate_form(_form(day=366)))


def test_step_out_of_range(core):
    assert any("step" in e.lower() for e in core.validate_form(_form(step=0.0)))
    assert any("step" in e.lower() for e in core.validate_form(_form(step=24.5)))


def test_missing_output_dir(core):
    assert any("output" in e.lower() for e in core.validate_form(_form(output_dir="")))


def test_missing_prefix(core):
    assert any("prefix" in e.lower() for e in core.validate_form(_form(output_prefix="  ")))


def test_no_outputs_checked_daily(core):
    errors = core.validate_form(_form(want_glob=False))
    assert any("output" in e.lower() for e in errors)


def test_annual_mode_checks_doy_range(core):
    errors = core.validate_form(_form(mode="annual", day_start=200, day_end=100))
    assert any("day_start" in e or "range" in e.lower() for e in errors)


def test_annual_mode_does_not_require_daily_outputs(core):
    form = _form(mode="annual", want_glob=False)
    assert core.validate_form(form) == []


def test_multiple_errors_all_reported(core):
    errors = core.validate_form(_form(elevation="", day=999, step=0.0))
    assert len(errors) >= 3
