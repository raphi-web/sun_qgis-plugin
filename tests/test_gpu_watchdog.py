"""GPU work must be split so no single GPU submission runs long.

Desktop GPU drivers kill submissions that run longer than ~2 s (amdgpu
lockup_timeout, Windows TDR). The Vienna DEM (4456x2603 @ 10 m, wide
shadow search) sent one 2048-row band as ONE submission: ~10 s of GPU time
on a Radeon 740M, the driver reset the GPU and QGIS aborted.

SUN_GPU_MAX_SUBMIT_SECONDS lowers the per-submission budget so this can be
tested on a fixture that stays far below the real watchdog.
"""
import json
import os
import subprocess
import sys
import textwrap

import numpy as np
import pytest

UNDEFZ = -9999.0


@pytest.fixture(scope="module")
def sun_module(core):
    sun = core.load_sun()
    if not sun.gpu_available():
        pytest.skip("no GPU adapter")
    return sun


def _run_child(code, env_extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SUN_")}
    env.update(env_extra)
    src = textwrap.dedent(_FIXTURE) + textwrap.dedent(code)
    out = subprocess.run([sys.executable, "-c", src],
                         capture_output=True, text=True, env=env, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


# 1024x1024 @ 10 m with one 600 m block: one unsplit submission takes
# ~0.85 s on a Radeon 740M (well under the 2 s watchdog, well over 0.15 s).
_FIXTURE = """
import json, time
import numpy as np
import sun
n = 1024
elev = np.zeros((n, n), dtype=np.float32)
elev[:8, :8] = 600.0
flat = np.ascontiguousarray(elev).ravel()
lat = np.full(n, 48.2, dtype=np.float32)
"""


def test_daily_gpu_submissions_stay_under_budget(sun_module):
    code = """
    sun.compute_raster_bands(elevation=flat, ncols=n, nrows=n, row_lat=lat,
        day=355, step=0.5, linke_value=3.0, albedo_value=0.2, dx_m=10.0,
        dy_m=10.0, outputs=["glob"], gpu=True, row_offset=0, full_nrows=n,
        quiet=True)
    s = sun.gpu_last_run_stats()
    print(json.dumps(s))
    """
    stats = _run_child(code, {"SUN_GPU_MAX_SUBMIT_SECONDS": "0.15"})
    assert stats["submissions"] > 1, stats
    assert stats["max_submit_seconds"] < 0.4, stats


def test_annual_gpu_submissions_stay_under_budget(sun_module):
    code = """
    sun.compute_annual_bands(elevation=flat, ncols=n, nrows=n, row_lat=lat,
        day_start=172, day_end=355, day_step=183, step=0.5,
        panel_efficiency=0.2, linke_value=3.0, albedo_value=0.2, dx_m=10.0,
        dy_m=10.0, gpu=True, row_offset=0, full_nrows=n, quiet=True)
    s = sun.gpu_last_run_stats()
    print(json.dumps(s))
    """
    stats = _run_child(code, {"SUN_GPU_MAX_SUBMIT_SECONDS": "0.15"})
    assert stats["submissions"] > 2, stats
    assert stats["max_submit_seconds"] < 0.4, stats


# The window size is learned from previous windows. These two inputs make
# the cost per pixel jump between windows; unsplit, each runs as a single
# ~0.4-0.5 s submission on a Radeon 740M.
def test_budget_holds_when_next_day_starts_on_costly_rows(sun_module):
    """Annual: day N ends on cheap rows, day N+1 starts on expensive ones."""
    code = """
    elev[:8, :8] = 1500.0
    full = np.ascontiguousarray(elev).ravel()
    band = np.ascontiguousarray(elev[512:]).ravel()
    sun.compute_annual_bands(elevation=band, ncols=n, nrows=512,
        row_lat=lat[512:], day_start=330, day_end=365, day_step=7, step=0.5,
        panel_efficiency=0.2, linke_value=3.0, albedo_value=0.2, dx_m=10.0,
        dy_m=10.0, shadow_context_elev=full, row_offset=512, full_nrows=n,
        gpu=True, quiet=True)
    print(json.dumps(sun.gpu_last_run_stats()))
    """
    stats = _run_child(code, {"SUN_GPU_MAX_SUBMIT_SECONDS": "0.1"})
    assert stats["max_submit_seconds"] < 0.3, stats


def test_budget_holds_after_nodata_region(sun_module):
    """Nodata pixels are nearly free; the terrain after them is not."""
    code = """
    e = elev.copy()
    e[:8, :8] = 0.0
    e[-8:, -8:] = 1500.0
    e[: n // 2, :] = -9999.0
    sun.compute_raster_bands(elevation=np.ascontiguousarray(e).ravel(),
        ncols=n, nrows=n, row_lat=lat, day=355, step=0.5, linke_value=3.0,
        albedo_value=0.2, dx_m=10.0, dy_m=10.0, outputs=["glob"], gpu=True,
        row_offset=0, full_nrows=n, quiet=True)
    print(json.dumps(sun.gpu_last_run_stats()))
    """
    stats = _run_child(code, {"SUN_GPU_MAX_SUBMIT_SECONDS": "0.1"})
    assert stats["max_submit_seconds"] < 0.3, stats


def test_split_results_identical_to_unsplit(sun_module):
    """Splitting is scheduling only: results must not change."""
    code = """
    n2 = 256
    e = np.ascontiguousarray(elev[:n2, :n2]).ravel()
    out = sun.compute_raster_bands(elevation=e, ncols=n2, nrows=n2,
        row_lat=lat[:n2], day=355, step=0.5, linke_value=3.0,
        albedo_value=0.2, dx_m=10.0, dy_m=10.0, outputs=["glob", "insol"],
        gpu=True, row_offset=0, full_nrows=n2, quiet=True)
    ann = sun.compute_annual_bands(elevation=e, ncols=n2, nrows=n2,
        row_lat=lat[:n2], day_start=1, day_end=365, day_step=60, step=0.5,
        panel_efficiency=0.2, linke_value=3.0, albedo_value=0.2, dx_m=10.0,
        dy_m=10.0, gpu=True, row_offset=0, full_nrows=n2, quiet=True)
    print(json.dumps({"glob": np.asarray(out["glob"]).tolist(),
                      "insol": np.asarray(out["insol"]).tolist(),
                      "ann": np.asarray(ann).tolist(),
                      "subs": sun.gpu_last_run_stats()["submissions"]}))
    """
    whole = _run_child(code, {"SUN_GPU_MAX_SUBMIT_SECONDS": "1000"})
    split = _run_child(code, {"SUN_GPU_MAX_SUBMIT_SECONDS": "0.001"})
    assert split["subs"] > whole["subs"], (split["subs"], whole["subs"])
    for k in ("glob", "insol", "ann"):
        a, b = np.asarray(whole[k]), np.asarray(split[k])
        assert np.array_equal(a == UNDEFZ, b == UNDEFZ), k
        np.testing.assert_allclose(a, b, rtol=1e-6, atol=1e-6, err_msg=k)


def test_lost_gpu_raises_instead_of_aborting(sun_module):
    """A lost device (driver reset) must surface as RuntimeError, never kill
    the host process (QGIS)."""
    code = """
    try:
        sun.compute_raster_bands(elevation=flat[:64*64], ncols=64, nrows=64,
            row_lat=lat[:64], day=172, step=0.5, linke_value=3.0,
            albedo_value=0.2, dx_m=10.0, dy_m=10.0, outputs=["glob"], gpu=True,
            row_offset=0, full_nrows=64, quiet=True)
        print(json.dumps({"raised": None}))
    except RuntimeError as e:
        print(json.dumps({"raised": str(e)}))
    """
    res = _run_child(code, {"SUN_GPU_SIMULATE_LOST": "1"})
    assert res["raised"], "expected RuntimeError"
    assert "GPU" in res["raised"]
