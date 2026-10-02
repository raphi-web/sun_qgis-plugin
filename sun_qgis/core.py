"""Core logic for the sun_qgis plugin — no qgis imports at module level.

Kept import-safe headless: QGIS-dependent glue lives in plugin.py / task.py,
raster I/O in raster_io.py, and the tiled computation loop in pipeline.py.
"""

import sys
from pathlib import Path

# The bundled extension is GDAL-free: it exposes only the array API (band-in /
# band-out) plus the pure single-pixel helper. Raster I/O lives in Python
# (raster_io.py); if the path-based functions ever come back, they dragged
# GDAL linkage with them — see tests/test_no_gdal_dependency.py.
REQUIRED_API = (
    "compute_raster_bands",
    "compute_annual_bands",
    "horn_slope_aspect",
    "compute_pixel",
)

# Form checkboxes for the daily outputs (shared with pipeline._DAILY_MAP).
DAILY_OUTPUT_WANTS = (
    "want_glob",
    "want_beam",
    "want_diff",
    "want_refl",
    "want_insol",
)

OPTIONAL_RASTERS = ("slope", "aspect", "linke", "albedo", "mask")


def validate_form(form):
    """Validate a dialog form dict; return a list of human-readable errors.

    Empty list means the form is valid. Mode "daily" checks the single-day
    params and output checkboxes; mode "annual" checks the DOY range instead.
    """
    errors = []

    if not str(form.get("elevation", "")).strip():
        errors.append("Elevation raster is required.")
    if not str(form.get("output_dir", "")).strip():
        errors.append("Output directory is required.")
    if not str(form.get("output_prefix", "")).strip():
        errors.append("Output file name prefix is required.")

    try:
        step = float(form.get("step", 0.0))
    except (TypeError, ValueError):
        errors.append(f"Time step must be a number, got {form.get('step')!r}.")
        step = None
    if step is not None and not (0.0 < step <= 24.0):
        errors.append(f"Time step must be in (0, 24] hours, got {step}.")

    mode = form.get("mode", "daily")
    if mode == "daily":
        try:
            day = int(form.get("day", 0))
        except (TypeError, ValueError):
            errors.append(f"Day of year must be an integer, got {form.get('day')!r}.")
            day = None
        if day is not None and not (1 <= day <= 365):
            errors.append(f"Day of year must be 1-365, got {day}.")
        if not any(form.get(w) for w in DAILY_OUTPUT_WANTS):
            errors.append("Select at least one output raster to compute.")
    else:  # annual
        try:
            day_start = int(form.get("day_start", 0))
            day_end = int(form.get("day_end", 0))
        except (TypeError, ValueError):
            errors.append("Day range bounds must be integers.")
        else:
            for name, v in (("day_start", day_start), ("day_end", day_end)):
                if not (1 <= v <= 365):
                    errors.append(f"{name} must be 1-365, got {v}.")
            if day_start > day_end:
                errors.append(
                    f"Invalid day range: day_start ({day_start}) > day_end ({day_end})."
                )

    return errors


def load_sun(plugin_dir):
    """Import the bundled `sun` native extension from *plugin_dir*.

    Raises FileNotFoundError with an actionable message when the compiled
    extension is missing (e.g. plugin copied without its .so).
    """
    plugin_dir = Path(plugin_dir)
    so_files = sorted(plugin_dir.glob("sun*.so"))
    if not so_files:
        raise FileNotFoundError(
            f"sun extension not found in {plugin_dir}. Expected a compiled "
            f"'sun*.so' (build with: maturin build --release in the Rust repo, "
            f"then copy target/wheels/… .so into the plugin directory)."
        )

    # Make the .so importable as module name `sun`.
    import importlib.util

    current = sys.version_info
    so_path = so_files[0]
    spec = importlib.util.spec_from_file_location("sun", so_path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError as e:
        raise ImportError(
            f"Failed to load {so_path.name}: {e}. The extension was built for "
            f"Python {so_path.name.split('cpython-')[-1].split('.')[0] if 'cpython' in so_path.name else '?'} "
            f"but this interpreter is {current[0]}.{current[1]}."
        ) from e

    missing = [a for a in REQUIRED_API if not hasattr(mod, a)]
    if missing:
        raise AttributeError(f"sun extension missing API: {missing}")
    return mod
