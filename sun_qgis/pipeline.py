"""Tiled computation pipeline: Python GDAL I/O around the native array API.

Memory strategy for large DEMs:
  * The elevation DEM is read ONCE, whole, as f32 — the cast-shadow ray
    march spans the full grid (shadow.rs), so the whole DEM must be
    resident. Slope/aspect are likewise derived once over the full grid
    (horn_slope_aspect) to avoid band-edge seams.
  * Optional inputs (slope/aspect/linke/albedo/mask rasters) and ALL
    outputs are handled in row bands of `band_rows` rows, so peak memory
    beyond the DEM context scales with the band, not the raster.

Result identity: computing with band_rows=N must give exactly the same
rasters as a single full-grid call — enforced by tests/test_pipeline.py.
"""

import numpy as np

from . import core
from .raster_io import (
    DEFAULT_BAND_ROWS,
    UNDEFZ,
    band_plan,
    create_output,
    raster_meta,
    read_band,
    read_full,
    row_latitudes,
    write_band,
)

# daily form checkbox -> (native output key, output filename suffix)
_DAILY_MAP = {
    "want_glob": ("glob", "glob"),
    "want_beam": ("beam", "beam"),
    "want_diff": ("diff", "diff"),
    "want_refl": ("refl", "refl"),
    "want_insol": ("insol", "insol"),
}


def _flat(arr):
    return np.ascontiguousarray(arr, dtype=np.float32).ravel()


def run_tiled(sun, form, progress_cb=None, band_rows=DEFAULT_BAND_ROWS):
    """Run the sun computation for *form* with tiled I/O. Returns the list
    of written output paths.

    *sun* is the loaded computation engine module (core.load_sun). Raises
    ValueError on invalid forms; native errors propagate.
    """
    errors = core.validate_form(form)
    if errors:
        raise ValueError("\n".join(errors))

    meta = raster_meta(str(form["elevation"]))
    ncols, nrows = meta["ncols"], meta["nrows"]
    # Match the path-based engine: pixel sizes in map units (its shadow
    # ray-march and Horn derivation use |gt[1]| / |gt[5]| directly).
    dx_m = abs(meta["gt"][1])
    dy_m = abs(meta["gt"][5])

    elev_full = read_full(str(form["elevation"]))  # (nrows, ncols) f32, nodata=UNDEFZ
    lats = np.asarray(row_latitudes(meta, ncols, nrows), dtype=np.float32)

    # Derive slope/aspect once over the FULL grid when not provided, so band
    # seams don't get a spurious nodata ring (the equivalence tests pin this).
    derived_slope = derived_aspect = None
    if not form.get("slope") or not form.get("aspect"):
        slope_arr, aspect_arr = sun.horn_slope_aspect(
            _flat(elev_full), ncols, nrows, dx_m=dx_m, dy_m=dy_m
        )
        derived_slope = np.asarray(slope_arr).reshape(nrows, ncols)
        derived_aspect = np.asarray(aspect_arr).reshape(nrows, ncols)

    shadow_flat = _flat(elev_full)
    plan = band_plan(nrows, band_rows)

    # Honor the dialog's GPU checkbox, but only when an adapter actually
    # exists — silently fall back to CPU otherwise (headless servers, missing
    # Vulkan drivers). Probe once per run.
    use_gpu = bool(form.get("gpu")) and _gpu_available(sun)

    if form.get("mode") == "annual":
        paths = _run_annual_bands(sun, form, meta, plan, ncols, nrows,
                                  elev_full, lats, shadow_flat,
                                  derived_slope, derived_aspect,
                                  dx_m, dy_m, progress_cb, use_gpu)
    else:
        paths = _run_daily_bands(sun, form, meta, plan, ncols, nrows,
                                 elev_full, lats, shadow_flat,
                                 derived_slope, derived_aspect,
                                 dx_m, dy_m, progress_cb, use_gpu)
    return paths


def _gpu_available(sun):
    """Adapter probe; old extensions without gpu_available() are treated as
    CPU-only (the native call would reject gpu=True)."""
    probe = getattr(sun, "gpu_available", None)
    return bool(probe()) if probe is not None else False


def _read_optional(form, key, start, end, ncols, nrows, derived):
    """Band slice for an optional input: external raster band, derived
    full-grid array slice, or None (native constant fallback)."""
    path = form.get(key)
    if path:
        return _flat(read_band(str(path), start, end))
    if derived is not None:
        return _flat(derived[start:end])
    return None


def _run_daily_bands(sun, form, meta, plan, ncols, nrows, elev_full, lats,
                     shadow_flat, derived_slope, derived_aspect,
                     dx_m, dy_m, progress_cb, use_gpu):
    from pathlib import Path

    out_dir = Path(str(form["output_dir"]))
    prefix = str(form["output_prefix"])

    wanted = [(native, suffix) for box, (native, suffix) in _DAILY_MAP.items()
              if form.get(box)]
    if not wanted:
        raise ValueError("Select at least one output raster to compute.")

    datasets = {}
    paths = []
    try:
        for native_key, suffix in wanted:
            p = str(out_dir / f"{prefix}_{suffix}.tif")
            datasets[native_key] = create_output(p, meta, nodata=UNDEFZ)
            paths.append(p)

        for start, end in plan:
            result = sun.compute_raster_bands(
                elevation=_flat(elev_full[start:end]),
                ncols=ncols,
                nrows=end - start,
                row_lat=lats[start:end],
                day=int(form["day"]),
                step=float(form["step"]),
                linke_value=float(form["linke_value"]),
                albedo_value=float(form["albedo_value"]),
                dx_m=dx_m,
                dy_m=dy_m,
                slope=_read_optional(form, "slope", start, end, ncols, nrows, derived_slope),
                aspect=_read_optional(form, "aspect", start, end, ncols, nrows, derived_aspect),
                linke=_read_optional(form, "linke", start, end, ncols, nrows, None),
                albedo=_read_optional(form, "albedo", start, end, ncols, nrows, None),
                mask=_read_optional(form, "mask", start, end, ncols, nrows, None),
                shadow_context_elev=shadow_flat,
                row_offset=start,
                full_nrows=nrows,
                outputs=[k for k, _ in wanted],
                gpu=use_gpu,  # adapter-probed; CPU fallback when unavailable
                quiet=True,
            )
            for native_key, _ in wanted:
                arr = np.asarray(result[native_key]).reshape(end - start, ncols)
                write_band(datasets[native_key], arr, start)
            if progress_cb is not None:
                progress_cb(100.0 * end / nrows)
    finally:
        for ds in datasets.values():
            ds.FlushCache()
        datasets.clear()  # GDAL closes on refcount drop
    return paths


def _run_annual_bands(sun, form, meta, plan, ncols, nrows, elev_full, lats,
                      shadow_flat, derived_slope, derived_aspect,
                      dx_m, dy_m, progress_cb, use_gpu):
    from pathlib import Path

    out_dir = Path(str(form["output_dir"]))
    prefix = str(form["output_prefix"])
    path = str(out_dir / f"{prefix}_potential.tif")
    ds = create_output(path, meta, nodata=UNDEFZ)
    try:
        for start, end in plan:
            arr = sun.compute_annual_bands(
                elevation=_flat(elev_full[start:end]),
                ncols=ncols,
                nrows=end - start,
                row_lat=lats[start:end],
                day_start=int(form["day_start"]),
                day_end=int(form["day_end"]),
                day_step=int(form["day_step"]),
                step=float(form["step"]),
                solar_constant=float(form.get("solar_constant", 1367.0)),
                panel_efficiency=float(form["panel_efficiency"]),
                linke_value=float(form["linke_value"]),
                albedo_value=float(form["albedo_value"]),
                dx_m=dx_m,
                dy_m=dy_m,
                slope=_read_optional(form, "slope", start, end, ncols, nrows, derived_slope),
                aspect=_read_optional(form, "aspect", start, end, ncols, nrows, derived_aspect),
                linke=_read_optional(form, "linke", start, end, ncols, nrows, None),
                albedo=_read_optional(form, "albedo", start, end, ncols, nrows, None),
                mask=_read_optional(form, "mask", start, end, ncols, nrows, None),
                shadow_context_elev=shadow_flat,
                row_offset=start,
                full_nrows=nrows,
                gpu=use_gpu,
                use_horizon=bool(form.get("use_horizon")),
                horizon_n_az=int(form.get("horizon_n_az", 64)),
                quiet=True,
            )
            write_band(ds, np.asarray(arr).reshape(end - start, ncols), start)
            if progress_cb is not None:
                progress_cb(100.0 * end / nrows)
    finally:
        ds.FlushCache()
        ds = None
    return [path]
