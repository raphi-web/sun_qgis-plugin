"""The native sun extension must RELEASE THE GIL during computation.

Without py.allow_threads(), the whole raster run holds the GIL: the QGIS GUI
thread freezes, the progress-parsing thread starves, and every progress
update arrives in one burst at the end (bar jumps 0 -> 100).

Test strategy: run compute_raster on a worker thread; the main thread ticks
a counter every 5 ms until the worker finishes. time.sleep() releases the
GIL, so if the native call also releases it the main thread keeps ticking
(tens+ of ticks); if the native call HOLDS the GIL the main thread blocks on
re-acquisition and sees ~1 tick total.
"""
import threading
import time

import pytest
from osgeo import gdal

gdal.UseExceptions()


@pytest.fixture(scope="module")
def sun_module(core, plugin_dir):
    return core.load_sun(plugin_dir)


@pytest.fixture(scope="module")
def big_dem(sun_module, tmp_path_factory):
    """200x200 DEM (2x2 tiling of the 100x100 dummy) so the CPU run lasts
    long enough (~0.5 s+) to sample the GIL."""
    import numpy as np

    tmp = tmp_path_factory.mktemp("gildem")
    small = str(tmp / "small.tif")
    sun_module.create_dummy(small)
    ds = gdal.Open(small)
    band = ds.GetRasterBand(1)
    arr = band.ReadAsArray()
    gt = ds.GetGeoTransform()
    proj = ds.GetProjection()
    ds = band = None

    big = np.tile(arr, (2, 2))
    out_path = str(tmp / "big.tif")
    drv = gdal.GetDriverByName("GTiff")
    out = drv.Create(out_path, big.shape[1], big.shape[0], 1, gdal.GDT_Float32)
    out.SetGeoTransform((gt[0], gt[1] * 2, 0.0, gt[3], 0.0, gt[5] * 2))
    out.SetProjection(proj)
    out_band = out.GetRasterBand(1)
    out_band.WriteArray(big)
    out.FlushCache()
    out = out_band = None
    return out_path


def test_compute_raster_releases_gil(core, sun_module, big_dem, tmp_path):
    kwargs = core.build_daily_kwargs(
        {
            "elevation": big_dem,
            "day": 172,
            "step": 0.5,
            "linke_value": 3.0,
            "albedo_value": 0.2,
            "output_dir": str(tmp_path),
            "output_prefix": "gil",
            "want_glob": True,
            "want_beam": False,
            "want_diff": False,
            "want_refl": False,
            "want_insol": False,
            "gpu": False,
        }
    )
    done = threading.Event()
    errors = []

    def work():
        try:
            sun_module.compute_raster(**kwargs)
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
    import os

    assert os.path.exists(kwargs["glob_rad"]), "computation did not run"
    assert elapsed > 0.05, f"computation too fast to sample ({elapsed:.3f}s)"
    # GIL held -> main thread starves (~1-2 wakeups total).
    # GIL released -> one wakeup per 5 ms (>= 10 needs only 50 ms).
    assert ticks >= 10, (
        f"main thread ran only {ticks} times during a {elapsed:.2f}s native "
        f"call — the GIL was held; wrap the computation in py.allow_threads()"
    )


def test_compute_annual_potential_releases_gil(core, sun_module, big_dem, tmp_path):
    """Same tripwire for the annual entry point (CPU path, coarse DOY grid)."""
    kwargs = core.build_annual_kwargs(
        {
            "elevation": big_dem,
            "day_start": 1,
            "day_end": 365,
            "day_step": 180,
            "step": 0.5,
            "panel_efficiency": 0.21,
            "linke_value": 3.0,
            "albedo_value": 0.2,
            "output_dir": str(tmp_path),
            "output_prefix": "gil",
            "gpu": False,
            "use_horizon": False,
            "horizon_n_az": 64,
        }
    )
    done = threading.Event()
    errors = []

    def work():
        try:
            sun_module.compute_annual_potential(**kwargs)
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
    import os

    assert os.path.exists(kwargs["out_path"]), "computation did not run"
    assert elapsed > 0.05, f"computation too fast to sample ({elapsed:.3f}s)"
    assert ticks >= 10, (
        f"main thread ran only {ticks} times during a {elapsed:.2f}s annual "
        f"call — the GIL was held"
    )
