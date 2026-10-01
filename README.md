# sun_qgis-plugin

QGIS plugin wrapping [`sun`](../../Rust/sun) — a Rust/WebGPU port of the GRASS
`r.sun` clear-sky solar irradiation model.

## What it does

- **Daily mode** — beam / diffuse / reflected / global irradiation
  [Wh/m²/day] and sunshine duration [h/day] for one day of year.
- **Annual mode** — photovoltaic potential [kWh/m²/yr] integrated over a DOY
  range with a panel-efficiency factor.
- **CPU or GPU** — rayon-parallel CPU or a wgpu compute shader; both give
  equivalent results (verified by `tests/test_end_to_end.py -m gpu`).
- Optional slope / aspect / Linke / albedo / mask rasters; slope and aspect
  are derived from the DEM (Horn 3×3) when not given.

## Layout

```
sun_qgis/          the plugin package (deployed into QGIS profiles)
  core.py          testable pure logic: load_sun, validate_form, build_*_kwargs
  task.py          run_sun_task core + QgsTask wrapper (background thread)
  sun_dialog.py    form_from_dialog core + Qt dialog glue
  plugin.py        toolbar action + layer loading (thin glue)
  ui/sun_dialog.ui
  metadata.txt, icon.png
  sun.cpython-312-*.so   the compiled Rust extension (bundled binary)
tests/             headless pytest: mocked qgis/PyQt, REAL gdal + REAL .so
scripts/
  build_extension.sh   maturin build against /usr/bin/python3 (QGIS's 3.12)
  deploy.sh            copy into every QGIS profile, verify byte-identical
```

## Build & deploy

```bash
scripts/build_extension.sh [path-to-rust-repo]   # rebuild the .so
/usr/bin/python3 -m pytest tests/ -q             # 34 tests
scripts/deploy.sh                                # install into QGIS profiles
```

Then restart QGIS (or Plugin Reloader) and enable **Solar Radiation (sun)**
under Plugins → Manage. A sun icon appears in the toolbar.

### Build notes

- QGIS 3.34 runs **Python 3.12** (`/usr/bin/python3`) — maturin must build
  with `-i /usr/bin/python3`, not the default venv/python.
- `--skip-auditwheel` keeps the `.so` linked against the system
  `libgdal.so.34` that QGIS already loads (~4 MB instead of ~56 MB with a
  vendored GDAL). Verify with `ldd` — a stale vendored-linked `.so` fails
  with `libgdal-<hash>.so.34: cannot open shared object file`.
- Tests: run with `env -i` + system python3 per the qgis-plugin-development
  workflow; GPU test needs `XDG_RUNTIME_DIR` set for the Vulkan loader.

## Requirements

- QGIS ≥ 3.34 (Python 3.12)
- Linux x86_64 with system GDAL 3.8 (`libgdal.so.34`)
- GPU mode: any wgpu-supported backend (Vulkan/Metal/DX12 or lavapipe fallback)
