"""Never-sunlit slopes must keep diffuse + reflected radiation.

Where the sun never rises above the slope plane (steep north-facing slopes
in winter), GRASS r.sun still integrates diffuse and reflected over the
HORIZONTAL day (beam = 0, insolation = 0). The engine used to write nodata
for those pixels, dropping sky radiation entirely — the validation run
against GRASS 8.3.2 showed 472/40000 pixels (all north-facing) missing on
day 355, and uniform north/east planes coming back fully nodata.

Reference numbers (GRASS 8.3.2, raster aspect path, linke 3.0, albedo 0.2,
step 0.5 h, day 355, 1000 m, slope ~20°):
  north-facing global ≈ 414 Wh/m²/day  (≈0.95 × horizontal diffuse 435)
  horizontal diffuse  = 435.2 Wh/m²/day
"""
import numpy as np
import pytest

UNDEFZ = -9999.0


@pytest.fixture(scope="module")
def sun_module(core):
    return core.load_sun()


def _flat(a):
    return np.ascontiguousarray(a, dtype=np.float32).ravel()


def _uniform(sun, aspect_ccw_from_east, day=355, slope_deg=20.0, n=40):
    """Uniform tilted plane at 1000 m, lat 47.37N."""
    elev = _flat(np.full(n * n, 1000.0, dtype=np.float32))
    slope = _flat(np.full(n * n, slope_deg, dtype=np.float32))
    aspect = _flat(np.full(n * n, aspect_ccw_from_east, dtype=np.float32))
    lats = np.full(n, 47.37, dtype=np.float32)
    return sun.compute_raster_bands(
        elevation=elev, ncols=n, nrows=n, row_lat=lats, day=day, step=0.5,
        linke_value=3.0, albedo_value=0.2, dx_m=30.0, dy_m=30.0,
        slope=slope, aspect=aspect,
        outputs=["glob", "beam", "diff", "insol"],
        gpu=False, row_offset=0, full_nrows=n, quiet=True,
    )


def test_north_facing_winter_keeps_diffuse(sun_module):
    """aspect 90 (CCW-from-east) = north. Day 355: sun never clears the
    plane, but the sky is visible — diffuse+reflected must survive."""
    out = _uniform(sun_module, 90.0)
    glob = np.asarray(out["glob"])
    beam = np.asarray(out["beam"])
    diff = np.asarray(out["diff"])
    insol = np.asarray(out["insol"])

    assert np.all(glob != UNDEFZ), "north-facing slope must not be nodata"
    assert np.all(beam == 0.0), "no beam on a never-sunlit slope"
    assert np.all(insol == 0.0), "no insolation time on a never-sunlit slope"
    assert np.all(diff > 0.0), "diffuse must be integrated over the day"
    # GRASS reference: ~414 Wh/m2/day (shaded-sky anisotropic diffuse)
    assert 390.0 < glob.mean() < 440.0, f"glob mean {glob.mean():.1f} vs GRASS ~414"


def test_east_facing_winter_keeps_morning_beam(sun_module):
    """aspect 0 (CCW-from-east) = east. The sun DOES clear an east-facing
    plane in the morning — beam must be non-zero, not nodata."""
    out = _uniform(sun_module, 0.0)
    glob = np.asarray(out["glob"])
    beam = np.asarray(out["beam"])
    insol = np.asarray(out["insol"])

    assert np.all(glob != UNDEFZ), "east-facing slope must not be nodata"
    assert beam.mean() > 100.0, f"east-facing winter morning beam missing ({beam.mean():.1f})"
    assert insol.mean() > 1.0, "east-facing slope must collect insolation hours"


def test_south_facing_winter_unchanged(sun_module):
    """Regression guard: the fix must not perturb slopes the sun clears."""
    out = _uniform(sun_module, 270.0)
    glob = np.asarray(out["glob"])
    assert np.all(glob != UNDEFZ)
    # established value from the validation run (GRASS scalar-south parity)
    assert 3000.0 < glob.mean() < 3150.0, glob.mean()


def test_annual_north_facing_not_nodata(sun_module):
    """Annual potential on a never-sunlit slope: diffuse-only but > 0."""
    n = 40
    elev = _flat(np.full(n * n, 1000.0, dtype=np.float32))
    slope = _flat(np.full(n * n, 20.0, dtype=np.float32))
    aspect = _flat(np.full(n * n, 90.0, dtype=np.float32))
    lats = np.full(n, 47.37, dtype=np.float32)
    pot = np.asarray(sun_module.compute_annual_bands(
        elevation=elev, ncols=n, nrows=n, row_lat=lats,
        day_start=1, day_end=365, day_step=10, step=0.5,
        panel_efficiency=0.21, linke_value=3.0, albedo_value=0.2,
        dx_m=30.0, dy_m=30.0, slope=slope, aspect=aspect,
        gpu=False, row_offset=0, full_nrows=n, quiet=True,
    ))
    assert np.all(pot != UNDEFZ), "annual potential must not be nodata on north slopes"
    assert pot.mean() > 0.0


def test_pixel_api_north_facing_returns_diffuse(sun_module):
    """compute_pixel must not raise for never-sunlit orientations."""
    r = sun_module.compute_pixel(
        lat_deg=47.37, elevation_m=1000.0, day=355,
        slope_deg=20.0, aspect_deg=90.0, linke=3.0, albedo=0.2,
    )
    assert r.beam == 0.0
    assert r.insol_time == 0.0
    assert 390.0 < r.global_rad < 440.0, r.global_rad
