"""GIL tripwire for the ARRAY API — the path the plugin actually uses.

pipeline.run_tiled calls compute_raster_bands / compute_annual_bands from
the QgsTask worker thread. If those native calls held the GIL, the QGIS
GUI thread would freeze for the duration of each band. The same sampling
strategy as test_gil.py: worker thread runs the native call, main thread
ticks every 5 ms; GIL held -> starvation (~1-2 ticks).
"""
import threading
import time

import numpy as np
import pytest
from osgeo import gdal

gdal.UseExceptions()


@pytest.fixture(scope="module")
def sun_module(core, plugin_dir):
    return core.load_sun(plugin_dir)


@pytest.fixture(scope="module")
def big_arrays(sun_module, dummy_dem):
    """Flat f32 inputs for a 400x400 grid — long enough (~0.3s+) to sample."""
    ds = gdal.Open(dummy_dem)
    arr = ds.GetRasterBand(1).ReadAsArray()
    ds = None

    elev = np.tile(arr, (4, 4))  # 400x400
    ncols, nrows = elev.shape[1], elev.shape[0]
    flat = np.ascontiguousarray(elev, dtype=np.float32).ravel()
    lats = np.full(nrows, 47.5, dtype=np.float32)
    return flat, ncols, nrows, lats


def _sample_gil(work):
    """Run work() on a thread; return (ticks, elapsed, errors)."""
    done = threading.Event()
    errors = []

    def runner():
        try:
            work()
        except Exception as e:  # pragma: no cover
            errors.append(e)
        finally:
            done.set()

    t = threading.Thread(target=runner)
    ticks = 0
    start = time.monotonic()
    t.start()
    while not done.wait(0.005):
        ticks += 1
    t.join()
    return ticks, time.monotonic() - start, errors


def test_compute_raster_bands_releases_gil(sun_module, big_arrays):
    flat, ncols, nrows, lats = big_arrays

    def work():
        sun_module.compute_raster_bands(
            elevation=flat,
            ncols=ncols,
            nrows=nrows,
            row_lat=lats,
            day=172,
            step=0.5,
            linke_value=3.0,
            albedo_value=0.2,
            dx_m=30.0,
            dy_m=30.0,
            outputs=["glob"],
            gpu=False,
            row_offset=0,
            full_nrows=nrows,
            quiet=True,
        )

    ticks, elapsed, errors = _sample_gil(work)
    assert not errors, errors
    assert elapsed > 0.05, f"computation too fast to sample ({elapsed:.3f}s)"
    assert ticks >= 10, (
        f"main thread ran only {ticks} times during a {elapsed:.2f}s "
        f"compute_raster_bands call — the GIL was held"
    )


def test_compute_annual_bands_releases_gil(sun_module, big_arrays):
    flat, ncols, nrows, lats = big_arrays

    def work():
        sun_module.compute_annual_bands(
            elevation=flat,
            ncols=ncols,
            nrows=nrows,
            row_lat=lats,
            day_start=1,
            day_end=365,
            day_step=90,
            step=0.5,
            panel_efficiency=0.21,
            linke_value=3.0,
            albedo_value=0.2,
            dx_m=30.0,
            dy_m=30.0,
            gpu=False,
            row_offset=0,
            full_nrows=nrows,
            quiet=True,
        )

    ticks, elapsed, errors = _sample_gil(work)
    assert not errors, errors
    assert elapsed > 0.05, f"computation too fast to sample ({elapsed:.3f}s)"
    assert ticks >= 10, (
        f"main thread ran only {ticks} times during a {elapsed:.2f}s "
        f"compute_annual_bands call — the GIL was held"
    )
