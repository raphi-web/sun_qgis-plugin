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


def find_extension(plugin_dir, suffixes=None):
    """Return the `sun` engine binary THIS interpreter can import, or None.

    The release zip bundles one binary per platform (Linux .so, macOS .so,
    Windows .pyd). Matching against the interpreter's own extension suffixes
    (importlib.machinery.EXTENSION_SUFFIXES, most specific first) picks the
    right one; "the first sun* file" would pick macOS's on Linux.
    """
    import importlib.machinery

    plugin_dir = Path(plugin_dir)
    if suffixes is None:
        suffixes = importlib.machinery.EXTENSION_SUFFIXES
    for suffix in suffixes:
        candidate = plugin_dir / f"sun{suffix}"
        if candidate.is_file():
            return candidate
    return None


def load_sun(plugin_dir):
    """Import the bundled `sun` native extension from *plugin_dir*.

    Raises FileNotFoundError when no engine binary is present at all, and
    ImportError naming the found vs needed files when binaries exist but none
    fits this interpreter (other platform or other Python version).
    """
    import importlib.machinery
    import importlib.util

    plugin_dir = Path(plugin_dir)
    so_path = find_extension(plugin_dir)
    if so_path is None:
        present = sorted(
            p.name for p in plugin_dir.glob("sun*") if p.suffix in (".so", ".pyd")
        )
        if not present:
            raise FileNotFoundError(
                f"sun extension not found in {plugin_dir}. Reinstall the plugin "
                f"from the release zip (it bundles the engine for Linux, Windows "
                f"and macOS)."
            )
        current = sys.version_info
        raise ImportError(
            f"No sun extension in {plugin_dir} fits this QGIS "
            f"(Python {current[0]}.{current[1]}, needs "
            f"'sun{importlib.machinery.EXTENSION_SUFFIXES[0]}'). "
            f"Found: {', '.join(present)}."
        )

    # Make the binary importable as module name `sun`.
    spec = importlib.util.spec_from_file_location("sun", so_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    missing = [a for a in REQUIRED_API if not hasattr(mod, a)]
    if missing:
        raise AttributeError(f"sun extension missing API: {missing}")
    return mod
