"""Core logic for the sun_qgis plugin — no qgis imports at module level.

Kept import-safe headless: QGIS-dependent glue lives in plugin.py / task.py.
"""

import sys
from pathlib import Path

REQUIRED_API = ("compute_raster", "compute_annual_potential", "create_dummy")


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
