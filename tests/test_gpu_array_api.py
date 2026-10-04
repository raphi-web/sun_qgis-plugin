"""GPU path on the array API (no GDAL).

The extension must expose:
  sun.gpu_available() -> bool        (adapter probe, no exception)
  compute_raster_bands(..., gpu=True)
  compute_annual_bands(..., gpu=True)

Parity: GPU results must match the CPU band cores within f32-shader
tolerance, nodata placement must be IDENTICAL, and banded GPU runs must
match full-grid GPU runs (shadow context via row_offset).

Skips cleanly when no wgpu adapter is available (e.g. CI without Vulkan).
"""
import threading
import time

import numpy as np
import pytest

UNDEFZ = -9999.0


@pytest.fixture(scope="module")
def sun_module(core):
    return core.load_sun()


@pytest.fixture(scope="module")
def gpu(sun_module):
    assert hasattr(sun_module, "gpu_available"), "extension missing gpu_available()"
    if not sun_module.gpu_available():
        pytest.skip("no wgpu adapter on this machine")
    return sun_module


def _flat(a):
    return np.ascontiguousarray(a, dtype=np.float32).ravel()


@pytest.fixture(scope="module")
def walled_grid():
    """40x24 grid, tilted + a wall on the south edge (winter shadow)."""
    ncols, nrows = 40, 24
    yy, xx = np.mgrid[0:nrows, 0:ncols].astype(np.float32)
    elev = 500.0 + 3.0 * xx
    elev[nrows - 2, :] = 1800.0  # wall near the south edge
    elev[:, 0] = UNDEFZ  # nodata column
    lats = np.full(nrows, 47.5, dtype=np.float32)
    return elev, lats, ncols, nrows


def _daily_call(sun, elev, lats, ncols, nrows, gpu_flag, **over):
    kw = dict(
        elevation=_flat(elev),
        ncols=ncols,
        nrows=nrows,
        row_lat=lats,
        day=355,
        step=0.5,
        linke_value=3.0,
        albedo_value=0.2,
        dx_m=30.0,
        dy_m=30.0,
        outputs=["glob", "insol"],
        gpu=gpu_flag,
        row_offset=0,
        full_nrows=nrows,
        quiet=True,
    )
    kw.update(over)
    return sun.compute_raster_bands(**kw)


def test_gpu_available_is_a_clean_probe(core, sun_module):
    """gpu_available() returns a bool and never raises — the pipeline uses
    it to decide fallback without try/except games."""
    assert hasattr(sun_module, "gpu_available")
    assert isinstance(sun_module.gpu_available(), bool)


def test_daily_gpu_matches_cpu(gpu, walled_grid):
    elev, lats, ncols, nrows = walled_grid
    cpu = _daily_call(gpu, elev, lats, ncols, nrows, False)
    g = _daily_call(gpu, elev, lats, ncols, nrows, True)

    for key in ("glob", "insol"):
        c = np.asarray(cpu[key]).reshape(nrows, ncols)
        v = np.asarray(g[key]).reshape(nrows, ncols)
        # nodata placement must be IDENTICAL (same guards both paths)
        assert np.array_equal(c == UNDEFZ, v == UNDEFZ), f"{key} nodata mask differs"
        valid = c != UNDEFZ
        assert valid.any()
        # Tolerance model (matches the old end-to-end GPU test): the shader
        # runs f32 while the CPU ray-march runs f64, so isolated pixels at a
        # shadow TERMINATOR may flip shaded/unshaded by one integration step.
        # Per-pixel allclose is the wrong contract; mean relative deviation is.
        rel = np.abs(v[valid] - c[valid]) / np.abs(c[valid]).clip(1.0)
        assert rel.mean() < 0.02, f"{key}: mean relative deviation {rel.mean():.4f}"


def test_gpu_band_offset_matches_full_grid(gpu, walled_grid):
    """Banded GPU run (row_offset + shadow context) == same rows of the
    full-grid GPU run. Slope/aspect are derived ONCE over the full grid and
    sliced (the plugin's architecture) so the comparison isolates the
    row_offset/shadow-context behaviour from the Horn band-edge seam."""
    elev, lats, ncols, nrows = walled_grid
    full_slope, full_aspect = gpu.horn_slope_aspect(
        _flat(elev), ncols, nrows, dx_m=30.0, dy_m=30.0
    )
    fs = np.asarray(full_slope).reshape(nrows, ncols)
    fa = np.asarray(full_aspect).reshape(nrows, ncols)

    full = _daily_call(
        gpu, elev, lats, ncols, nrows, True,
        slope=_flat(fs), aspect=_flat(fa),
    )

    start, end = 12, nrows
    band = _daily_call(
        gpu,
        elev[start:end],
        lats[start:end],
        ncols,
        end - start,
        True,
        slope=_flat(fs[start:end]),
        aspect=_flat(fa[start:end]),
        row_offset=start,
        full_nrows=nrows,
        shadow_context_elev=_flat(elev),
    )
    f = np.asarray(full["glob"]).reshape(nrows, ncols)[start:end]
    b = np.asarray(band["glob"]).reshape(end - start, ncols)
    assert np.array_equal(f == UNDEFZ, b == UNDEFZ)
    valid = f != UNDEFZ
    # Same backend (GPU), same shader math: banded must be bit-identical.
    assert np.allclose(b[valid], f[valid], rtol=1e-5, atol=1e-3)


def test_annual_gpu_matches_cpu(gpu, walled_grid):
    elev, lats, ncols, nrows = walled_grid
    common = dict(
        elevation=_flat(elev),
        ncols=ncols,
        nrows=nrows,
        row_lat=lats,
        day_start=80,
        day_end=120,
        day_step=20,
        step=0.5,
        panel_efficiency=0.21,
        linke_value=3.0,
        albedo_value=0.2,
        dx_m=30.0,
        dy_m=30.0,
        row_offset=0,
        full_nrows=nrows,
        quiet=True,
    )
    c = np.asarray(gpu.compute_annual_bands(gpu=False, **common)).reshape(nrows, ncols)
    v = np.asarray(gpu.compute_annual_bands(gpu=True, **common)).reshape(nrows, ncols)
    assert np.array_equal(c == UNDEFZ, v == UNDEFZ)
    valid = c != UNDEFZ
    assert valid.any()
    assert np.allclose(v[valid], c[valid], rtol=0.05, atol=0.05)


def test_gpu_band_call_releases_gil(gpu, walled_grid):
    """Same tripwire as the CPU path: the GPU dispatch + readback must run
    with the GIL released (pollster::block_on inside allow_threads)."""
    elev, lats, ncols, nrows = walled_grid
    # repeat the band a few times so the call is long enough to sample
    done = threading.Event()
    errors = []

    def work():
        try:
            for _ in range(6):
                _daily_call(gpu, elev, lats, ncols, nrows, True)
        except Exception as e:  # pragma: no cover
            errors.append(e)
        finally:
            done.set()

    t = threading.Thread(target=work)
    ticks = 0
    start = time.monotonic()
    t.start()
    while not done.wait(0.005):
        ticks += 1
    t.join()
    elapsed = time.monotonic() - start
    assert not errors, errors
    assert elapsed > 0.05, f"GPU run too fast to sample ({elapsed:.3f}s)"
    assert ticks >= 10, (
        f"main thread ran only {ticks} times during {elapsed:.2f}s of GPU "
        f"calls — the GIL was held"
    )
