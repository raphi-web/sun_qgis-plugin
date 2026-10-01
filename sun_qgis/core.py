"""Core logic for the sun_qgis plugin — no qgis imports at module level.

Kept import-safe headless: QGIS-dependent glue lives in plugin.py / task.py.
"""

import os
import re
import select
import sys
import threading
from pathlib import Path

_PROGRESS_RE = re.compile(r"Progress:\s*(\d+)%")


def parse_progress_line(line):
    """Extract a 0-100 float from a native progress line, else None.

    The Rust engine prints e.g. 'CPU annual  Progress: 12%' (CPU paths) and
    unstructured info lines on the GPU paths ('GPU  Tile N: …' → None).
    """
    m = _PROGRESS_RE.search(line)
    return float(m.group(1)) if m else None


def run_capturing_stderr(work, on_progress, echo=None, poll_interval=0.1):
    """Run *work()* (blocking native call) while capturing C-level stderr.

    The native extension writes progress to fd 2 (Rust eprint!), which
    Python's sys.stderr swap cannot see — so fd 2 is redirected into a pipe,
    work runs on a worker thread, and this thread parses the pipe stream:

    * lines containing 'Progress: NN%' → on_progress(NN.0)
    * anything else → echo(bytes); defaults to the original stderr fd

    fd 2 is restored in a finally block even when *work* raises; the
    exception propagates. Returns work()'s result.
    """
    saved_err = os.dup(2)
    read_fd, write_fd = os.pipe()
    os.dup2(write_fd, 2)
    os.close(write_fd)

    def _emit(raw_bytes):
        if echo is not None:
            echo(raw_bytes)
        else:
            os.write(saved_err, raw_bytes)

    result_box = {}

    def _worker():
        try:
            result_box["value"] = work()
        except BaseException as e:  # re-raised on this thread after cleanup
            result_box["error"] = e

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    buf = b""
    try:
        while True:
            alive = thread.is_alive()
            ready, _, _ = select.select([read_fd], [], [], poll_interval)
            if ready:
                chunk = os.read(read_fd, 65536)
                if not chunk and not alive:
                    break
                buf += chunk
                # \r and \n both delimit progress reports (eprint! uses \r).
                while True:
                    idx_n = buf.find(b"\n")
                    idx_r = buf.find(b"\r")
                    cands = [i for i in (idx_n, idx_r) if i >= 0]
                    if not cands:
                        break
                    idx = min(cands)
                    segment, buf = buf[:idx], buf[idx + 1:]
                    text = segment.decode("utf-8", errors="replace")
                    pct = parse_progress_line(text)
                    if pct is not None:
                        on_progress(pct)
                    elif segment:
                        _emit(segment + b"\n")
            elif not alive:
                break
        if buf:
            text = buf.decode("utf-8", errors="replace")
            pct = parse_progress_line(text)
            if pct is not None:
                on_progress(pct)
            else:
                _emit(buf)
        thread.join()
    finally:
        os.dup2(saved_err, 2)
        os.close(saved_err)
        os.close(read_fd)

    if "error" in result_box:
        raise result_box["error"]
    return result_box.get("value")


REQUIRED_API = ("compute_raster", "compute_annual_potential", "create_dummy")

# (form key for the checkbox, compute_raster kwarg name, output filename suffix)
DAILY_OUTPUTS = (
    ("want_glob", "glob_rad", "glob"),
    ("want_beam", "beam_rad", "beam"),
    ("want_diff", "diff_rad", "diff"),
    ("want_refl", "refl_rad", "refl"),
    ("want_insol", "insol_time", "insol"),
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
        if not any(form.get(w) for w, _, _ in DAILY_OUTPUTS):
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


def build_daily_kwargs(form):
    """Translate a dialog form dict into ``sun.compute_raster`` kwargs.

    *form* keys: elevation, day, step, linke_value, albedo_value, output_dir,
    output_prefix, want_glob/want_beam/want_diff/want_refl/want_insol, gpu,
    plus optional raster paths (slope, aspect, linke, albedo, mask).
    Raises ValueError when no output band is selected.
    """
    out_dir = str(form["output_dir"])
    prefix = str(form["output_prefix"])

    kwargs = {
        "elevation": str(form["elevation"]),
        "day": int(form["day"]),
        "step": float(form["step"]),
        "linke_value": float(form["linke_value"]),
        "albedo_value": float(form["albedo_value"]),
        "gpu": bool(form["gpu"]),
        "quiet": True,
    }
    for name in OPTIONAL_RASTERS:
        path = form.get(name)
        kwargs[name] = str(path) if path else None

    any_selected = False
    for want_key, kwarg, suffix in DAILY_OUTPUTS:
        if form.get(want_key):
            any_selected = True
            kwargs[kwarg] = str(Path(out_dir) / f"{prefix}_{suffix}.tif")
        else:
            kwargs[kwarg] = None
    if not any_selected:
        raise ValueError("Select at least one output raster to compute.")
    return kwargs


def build_annual_kwargs(form):
    """Translate a dialog form dict into ``sun.compute_annual_potential`` kwargs.

    *form* keys: elevation, day_start, day_end, day_step, step,
    panel_efficiency, linke_value, albedo_value, output_dir, output_prefix,
    gpu, use_horizon, horizon_n_az, plus optional raster paths.
    Raises ValueError on an inverted DOY range.
    """
    day_start = int(form["day_start"])
    day_end = int(form["day_end"])
    if day_start > day_end:
        raise ValueError(
            f"day_start ({day_start}) must be <= day_end ({day_end})."
        )

    kwargs = {
        "elevation": str(form["elevation"]),
        "out_path": str(
            Path(str(form["output_dir"])) / f"{form['output_prefix']}_potential.tif"
        ),
        "day_start": day_start,
        "day_end": day_end,
        "day_step": int(form["day_step"]),
        "step": float(form["step"]),
        "panel_efficiency": float(form["panel_efficiency"]),
        "linke_value": float(form["linke_value"]),
        "albedo_value": float(form["albedo_value"]),
        "gpu": bool(form["gpu"]),
        "use_horizon": bool(form["use_horizon"]),
        "horizon_n_az": int(form["horizon_n_az"]),
        "quiet": True,
    }
    for name in OPTIONAL_RASTERS:
        path = form.get(name)
        kwargs[name] = str(path) if path else None
    return kwargs


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
