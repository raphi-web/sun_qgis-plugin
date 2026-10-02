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
    """Contiguous flat float32 ndarray — the native API takes numpy arrays
    (zero-copy via the numpy crate), not Python lists."""
    return np.ascontiguousarray(arr, dtype=np.float32).ravel()


def test_module_exposes_array_api(sun_module):
    for fn in ("compute_raster_bands", "compute_annual_bands", "horn_slope_aspect"):
        assert hasattr(sun_module, fn), f"missing {fn}"


def test_horn_slope_aspect_flat_terrain(sun_module):
    """A flat DEM band yields slope 0 everywhere except the nodata edge ring."""
    ncols, nrows = 20, 10
    elev = _flat(np.full((nrows, ncols), 800.0, dtype=np.float32))
    slope, aspect = sun_module.horn_slope_aspect(
        elev, ncols, nrows, dx_m=30.0, dy_m=30.0
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
        _flat(arr), ncols, nrows, dx_m=30.0, dy_m=30.0
    )
    slope = np.asarray(slope).reshape(nrows, ncols)
    # A nodata pixel propagates to the 8 NEIGHBOURS whose 3×3 window contains
    # it (their slope becomes nodata). The nodata pixel's OWN slope is still
    # computed from its valid ring (Horn excludes the centre from its window);
    # that value is irrelevant downstream because the radiation loop skips any
    # pixel with nodata elevation. Assert the neighbour propagation:
    assert slope[4, 9] == UNDEFZ  # (5,10) is the SE neighbour of (4,9)
    assert slope[6, 11] == UNDEFZ  # (5,10) is the NW neighbour of (6,11)


def test_compute_raster_bands_single_day(sun_module):
    """One band of a synthetic tilted DEM: results plausible, nodata preserved."""
    ncols, nrows = 50, 10
    yy, xx = np.mgrid[0:nrows, 0:ncols].astype(np.float32)
    elev = 500.0 + 2.0 * xx  # gentle east-rising slope
    row_lat = np.full(nrows, 47.5, dtype=np.float32)

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
        row_lat=np.full(nrows, 47.5, dtype=np.float32),
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
    # Interior only: slope/aspect are derived internally via Horn, whose
    # 1-px edge ring is nodata by design (matches the path-based engine).
    assert np.all(glob[1:-1, 15:-1] != UNDEFZ)


def test_compute_raster_bands_mask_zero_skips(sun_module):
    ncols, nrows = 50, 10
    elev = np.full((nrows, ncols), 600.0, dtype=np.float32)
    mask = np.ones((nrows, ncols), dtype=np.float32)
    mask[:, 40:] = 0.0
    result = sun_module.compute_raster_bands(
        elevation=_flat(elev),
        ncols=ncols,
        nrows=nrows,
        row_lat=np.full(nrows, 47.5, dtype=np.float32),
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
    # Valid region: interior rows (Horn-derived slope/aspect edge ring is
    # nodata by design) and columns left of the mask cutoff at 40.
    assert np.all(glob[1:-1, 1:40] != UNDEFZ)


def test_compute_annual_bands(sun_module):
    ncols, nrows = 50, 10
    elev = np.full((nrows, ncols), 600.0, dtype=np.float32)
    result = sun_module.compute_annual_bands(
        elevation=_flat(elev),
        ncols=ncols,
        nrows=nrows,
        row_lat=np.full(nrows, 47.5, dtype=np.float32),
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
    a tall wall at full-grid row 0 shades rows in later bands.

    Slope/aspect are derived ONCE over the full grid (as the plugin does,
    since the whole DEM is in memory) and sliced per band, so this test
    isolates the row_offset/shadow-context behaviour from the Horn
    band-edge seam that would otherwise appear at the band boundary.
    """
    ncols = 30
    total_rows = 20
    full = np.full((total_rows, ncols), 100.0, dtype=np.float32)
    full[0, :] = 900.0  # wall on the north edge
    lats = np.full(total_rows, 47.5, dtype=np.float32)

    # Derive slope/aspect once over the full grid.
    full_slope, full_aspect = sun_module.horn_slope_aspect(
        _flat(full), ncols, total_rows, dx_m=30.0, dy_m=30.0
    )

    # band = rows 10..20
    band_elev = full[10:]
    result_band = sun_module.compute_raster_bands(
        elevation=_flat(band_elev),
        ncols=ncols,
        nrows=10,
        row_lat=np.asarray(lats[10:], dtype=np.float32),
        day=355,  # winter: low sun, long shadows
        step=0.5,
        linke_value=3.0,
        albedo_value=0.2,
        dx_m=30.0,
        dy_m=30.0,
        slope=_flat(np.asarray(full_slope).reshape(total_rows, ncols)[10:]),
        aspect=_flat(np.asarray(full_aspect).reshape(total_rows, ncols)[10:]),
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
        row_lat=np.asarray(lats, dtype=np.float32),
        day=355,
        step=0.5,
        linke_value=3.0,
        albedo_value=0.2,
        dx_m=30.0,
        dy_m=30.0,
        slope=_flat(full_slope),
        aspect=_flat(full_aspect),
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
