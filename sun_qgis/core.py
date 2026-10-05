"""Core logic for the sun_qgis plugin — no qgis imports at module level.

Kept import-safe headless: QGIS-dependent glue lives in plugin.py / task.py,
raster I/O in raster_io.py, and the tiled computation loop in pipeline.py.
"""

# The computation engine is the pip package sun-solar-radiation (import name
# `sun`). The plugin ships no binaries; load_sun() imports the installed one.
ENGINE_DIST = "sun-solar-radiation"
# 0.1.1 fixed never-sunlit slopes (nodata) and east aspect computed as north.
# 0.1.2 keeps every GPU submission short so the driver never resets the GPU
# (large DEMs took QGIS down) and reports GPU failures as errors.
MIN_ENGINE_VERSION = (0, 1, 2)

# The engine is GDAL-free: it exposes only the array API (band-in /
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


def engine_version():
    """Installed version of the sun-solar-radiation package, or None."""
    from importlib import metadata

    try:
        return metadata.version(ENGINE_DIST)
    except metadata.PackageNotFoundError:
        return None


def _release_tuple(version):
    """'0.1.2.dev3' -> (0, 1, 2): leading numeric release components only."""
    parts = []
    for piece in version.split("."):
        digits = ""
        for ch in piece:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
        if len(digits) != len(piece):
            break
    return tuple(parts)


def load_sun():
    """Import the computation engine (pip package sun-solar-radiation).

    Raises ImportError with the pip command to run when the engine is
    missing, older than MIN_ENGINE_VERSION, or when some other package
    named `sun` shadows it.
    """
    try:
        import sun
    except ImportError as e:
        raise ImportError(
            f"The computation engine is not installed ({e}). Install it into "
            f"QGIS's Python with: pip install {ENGINE_DIST}"
        ) from e

    missing = [a for a in REQUIRED_API if not hasattr(sun, a)]
    if missing:
        where = getattr(sun, "__file__", None) or "<unknown location>"
        raise ImportError(
            f"The Python module 'sun' at {where} is not the {ENGINE_DIST} "
            f"engine (missing {', '.join(missing)}). If it is an older engine "
            f"build, run: pip install --upgrade {ENGINE_DIST}. If another "
            f"package named 'sun' is installed, remove it first with: "
            f"pip uninstall sun"
        )

    installed = engine_version()
    if installed is not None and _release_tuple(installed) < MIN_ENGINE_VERSION:
        need = ".".join(map(str, MIN_ENGINE_VERSION))
        raise ImportError(
            f"{ENGINE_DIST} {installed} is too old (this plugin needs {need} "
            f"or newer). Run: pip install --upgrade {ENGINE_DIST}"
        )
    return sun
