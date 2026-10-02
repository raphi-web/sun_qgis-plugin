"""Tests for the array-in/array-out native API (no GDAL in the extension).

The new surface:
  sun.compute_raster_bands(...)  -> dict of selected output bands for a row band
  sun.compute_annual_bands(...)  -> annual potential band for a row band
  sun.horn_slope_aspect(...)     -> (slope, aspect) arrays derived from DEM band

All inputs are flat f32 lists/arrays; all outputs come back as Python lists
(or numpy arrays if numpy is available). Row latitudes are passed in from
Python (computed in raster_io).
"""
import numpy as np
import pytest

UNDEFZ = -9999.0


@pytest.fixture(scope="module")
def sun_module(core, plugin_dir):
    return core.load_sun(plugin_dir)


def _flat(arr):
    return np.ascontiguousarray(arr, dtype=np.float32).ravel().tolist()


def test_module_exposes_array_api(sun_module):
    for fn in ("compute_raster_bands", "compute_annual_bands", "horn_slope_aspect"):
        assert hasattr(sun_module, fn), f"missing {fn}"


def test_horn_slope_aspect_flat_terrain(sun_module):
    """A flat DEM band yields slope 0 everywhere except the nodata edge ring."""
    ncols, nrows = 20, 10
    elev = _flat(np.full((nrows, ncols), 800.0, dtype=np.float32))
    slope, aspect = sun_module.horn_slope_aspect(
        elev, ncols, nrows, 30.0, 30.0
    )
    slope = np.asarray(slope).reshape(nrows, ncols)
    interior = slope[1:-1, 1:-1]
    assert np.allclose(interior, 0.0, atol=1e-4)
    # edge ring is nodata
    assert slope[0, 0] == UNDEFZ


def test_horn_slope_aspect_nodata_propagates(sun_module):
    ncols, nrows = 20, 10
    arr = np.full((nrows, ncols), 800.0, dtype=np.float32)
    arr[5, 10] = UNDEFZ
    slope, aspect = sun_module.horn_slope_aspect(
        _flat(arr), ncols, nrows, 30.0, 30.0
    )
    slope = np.asarray(slope).reshape(nrows, ncols)
    # the nodata pixel and its 3x3 neighborhood are nodata
    assert slope[5, 10] == UNDEFZ
    assert slope[4, 9] == UNDEFZ


def test_compute_raster_bands_single_day(sun_module):
    """One band of a synthetic tilted DEM: results plausible, nodata preserved."""
    ncols, nrows = 50, 10
    yy, xx = np.mgrid[0:nrows, 0:ncols].astype(np.float32)
    elev = 500.0 + 2.0 * xx  # gentle east-rising slope
    row_lat = [47.5] * nrows

    result = sun_module.compute_raster_bands(
        elevation=_flat(elev),
        ncols=ncols,
        nrows=nrows,
        row_lat=row_lat,
        day=172,
        step=0.5,
        linke_value=3.0,
        albedo_value=0.2,
        dx_m=30.0,
        dy_m=30.0,
        gpu=False,
        outputs=["glob", "insol"],
        row_offset=0,
        full_nrows=nrows,
    )
    assert isinstance(result, dict)
    assert set(result) == {"glob", "insol"}
    glob = np.asarray(result["glob"]).reshape(nrows, ncols)
    insol = np.asarray(result["insol"]).reshape(nrows, ncols)
    valid = glob != UNDEFZ
    assert valid.any()
    # summer solstice at 47.5N: 1000..12000 Wh/m2/day
    assert glob[valid].min() > 500
    assert glob[valid].max() < 15000
    assert insol[valid].max() <= 24.0


def test_compute_raster_bands_nodata_passthrough(sun_module):
    ncols, nrows = 50, 10
    elev = np.full((nrows, ncols), 600.0, dtype=np.float32)
    elev[:, :10] = UNDEFZ
    result = sun_module.compute_raster_bands(
        elevation=_flat(elev),
        ncols=ncols,
        nrows=nrows,
        row_lat=[47.5] * nrows,
        day=172,
        step=0.5,
        linke_value=3.0,
        albedo_value=0.2,
        dx_m=30.0,
        dy_m=30.0,
        gpu=False,
        outputs=["glob"],
        row_offset=0,
        full_nrows=nrows,
    )
    glob = np.asarray(result["glob"]).reshape(nrows, ncols)
    assert np.all(glob[:, :10] == UNDEFZ)
    assert np.all(glob[:, 15:] != UNDEFZ)


def test_compute_raster_bands_mask_zero_skips(sun_module):
    ncols, nrows = 50, 10
    elev = np.full((nrows, ncols), 600.0, dtype=np.float32)
    mask = np.ones((nrows, ncols), dtype=np.float32)
    mask[:, 40:] = 0.0
    result = sun_module.compute_raster_bands(
        elevation=_flat(elev),
        ncols=ncols,
        nrows=nrows,
        row_lat=[47.5] * nrows,
        day=172,
        step=0.5,
        linke_value=3.0,
        albedo_value=0.2,
        dx_m=30.0,
        dy_m=30.0,
        mask=_flat(mask),
        gpu=False,
        outputs=["glob"],
        row_offset=0,
        full_nrows=nrows,
    )
    glob = np.asarray(result["glob"]).reshape(nrows, ncols)
    assert np.all(glob[:, 40:] == UNDEFZ)
    assert np.all(glob[:, :40] != UNDEFZ)


def test_compute_annual_bands(sun_module):
    ncols, nrows = 50, 10
    elev = np.full((nrows, ncols), 600.0, dtype=np.float32)
    result = sun_module.compute_annual_bands(
        elevation=_flat(elev),
        ncols=ncols,
        nrows=nrows,
        row_lat=[47.5] * nrows,
        day_start=80,
        day_end=100,
        day_step=20,
        step=0.5,
        panel_efficiency=0.21,
        linke_value=3.0,
        albedo_value=0.2,
        dx_m=30.0,
        dy_m=30.0,
        gpu=False,
        use_horizon=False,
        horizon_n_az=64,
        row_offset=0,
        full_nrows=nrows,
    )
    potential = np.asarray(result).reshape(nrows, ncols)
    valid = potential != UNDEFZ
    assert valid.any()
    # ~20 days at 21% efficiency: positive, bounded
    assert potential[valid].min() >= 0.0
    assert potential[valid].max() < 60.0


def test_row_offset_indexes_full_grid_for_shadows(sun_module):
    """A band with row_offset must shadow against the FULL grid context:
    a tall wall at full-grid row 0 shades rows in later bands."""
    ncols = 30
    total_rows = 20
    full = np.full((total_rows, ncols), 100.0, dtype=np.float32)
    full[0, :] = 900.0  # wall on the north edge
    lats = [47.5] * total_rows

    # band = rows 10..20
    band_elev = full[10:]
    result_band = sun_module.compute_raster_bands(
        elevation=_flat(band_elev),
        ncols=ncols,
        nrows=10,
        row_lat=lats[10:],
        day=355,  # winter: low sun, long shadows
        step=0.5,
        linke_value=3.0,
        albedo_value=0.2,
        dx_m=30.0,
        dy_m=30.0,
        gpu=False,
        outputs=["glob"],
        row_offset=10,
        full_nrows=total_rows,
        shadow_context_elev=_flat(full),
    )
    band_glob = np.asarray(result_band["glob"]).reshape(10, ncols)

    # same rows computed as part of the full grid
    result_full = sun_module.compute_raster_bands(
        elevation=_flat(full),
        ncols=ncols,
        nrows=total_rows,
        row_lat=lats,
        day=355,
        step=0.5,
        linke_value=3.0,
        albedo_value=0.2,
        dx_m=30.0,
        dy_m=30.0,
        gpu=False,
        outputs=["glob"],
        row_offset=0,
        full_nrows=total_rows,
        shadow_context_elev=_flat(full),
    )
    full_glob = np.asarray(result_full["glob"]).reshape(total_rows, ncols)

    assert np.allclose(
        band_glob, full_glob[10:], rtol=1e-4, equal_nan=True
    ), "band results must match the same rows of a full-grid computation"
