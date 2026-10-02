# Solar Radiation for QGIS

Compute clear-sky solar irradiation and photovoltaic potential directly inside QGIS from any digital elevation model (DEM). Built for speed: large rasters are processed in memory-bounded tiles, and a GPU compute path makes annual, whole-year simulations practical on a laptop.

## What This Plugin Does

The plugin calculates solar radiation maps from elevation data using the validated clear-sky model behind GRASS GIS `r.sun`. You can generate:

- **Single-day irradiation maps**: beam, diffuse, reflected, and global radiation (Wh/m²/day) plus sunshine duration (hours)
- **Annual PV potential maps**: yearly photovoltaic energy yield (kWh/m²/year) with custom panel efficiency

The model accounts for solar geometry, terrain shadowing (cast shadows from ridges and buildings), slope and aspect effects, atmospheric attenuation, and ground reflection.

## Installation

### Requirements

- QGIS 3.34 or later (ships with Python 3.12)
- For GPU mode: a graphics card with Vulkan support (most GPUs from 2015+). Without one, the plugin silently falls back to the CPU — everything still works, just slower.

### Install Steps

1. Download the plugin zip (`sun_qgis_plugin-<version>.zip`)
2. In QGIS: **Plugins → Manage and Install Plugins → Install from ZIP**, select the zip
   (or copy the extracted `sun_qgis` folder into your profile's `python/plugins/` directory:
   **Linux** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/` ·
   **Windows** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\` ·
   **macOS** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`)
3. Enable the plugin: **Plugins → Manage and Install Plugins → Installed → Solar Radiation**

A sun icon appears in the toolbar; the tool is also under **Raster → Solar Radiation**.

## Usage

### Basic Workflow

1. **Load your DEM** into QGIS (GeoTIFF or any GDAL-supported raster, elevation in metres)
2. **Open the dialog** via the sun toolbar icon or **Raster → Solar Radiation**
3. **Configure inputs**:
   - Elevation DEM (required — pick a raster layer from the dropdown)
   - Optionally: slope, aspect, Linke turbidity, albedo, mask rasters
4. **Choose the mode**:
   - **Daily**: single-day irradiation for one day of year
   - **Annual**: yearly PV potential sampled over the year
5. **Set outputs**: directory, filename prefix, and which rasters to generate
6. Click **Run**. The progress bar updates while the computation runs; finished rasters are added to your project automatically (if that option is checked).

### Input Parameters

**Required:**
- **Elevation DEM** — digital elevation model in metres, any projection

**Optional rasters (refine the model; omitted = derived or constant):**
- **Slope** — terrain slope in degrees. Omit to derive automatically from the DEM (Horn 3×3)
- **Aspect** — terrain aspect in degrees, **GRASS convention: 0° = East, counter-clockwise (90° = North, 180° = West, 270° = South)**. This differs from the common compass convention — supplying a compass-convention aspect raster will bias results. Omit to derive from the DEM automatically
- **Linke turbidity** — atmospheric clarity (dimensionless, typically 2–5; 3 ≈ clear mid-European air). Provide a raster for spatially varying turbidity, or just set the constant value field. Default constant: 3.0
- **Albedo** — ground reflectivity (0–1; 0.2 ≈ vegetation, 0.8 ≈ fresh snow). Raster or constant. Default constant: 0.2
- **Mask** — binary raster; pixels with value 0 are skipped (output nodata), everything else is computed

### Daily Mode Parameters

- **Day of year** — 1–365 (172 ≈ June 21, 355 ≈ December 21 in the Northern Hemisphere)
- **Time step** — integration interval in hours (default 0.5; smaller = more accurate, slower)
- **Outputs** (any combination):
  - **Beam** — direct radiation (Wh/m²/day)
  - **Diffuse** — scattered sky radiation (Wh/m²/day)
  - **Reflected** — ground-reflected radiation (Wh/m²/day)
  - **Global** — total = beam + diffuse + reflected (Wh/m²/day)
  - **Sunshine duration** — hours of unshadowed direct sun (h/day)

### Annual Mode Parameters

- **Day range / sampling stride** — the year is sampled every *stride* days (default 10 → 37 samples) and integrated; smaller strides are more accurate but slower
- **Time step** — sub-daily integration interval (default 0.5 h)
- **Panel efficiency** — PV conversion factor 0–1 (e.g. 0.21 for 21 % panels)
- **Precompute horizon** — replaces per-step cast-shadow ray-marching with a precomputed horizon map (faster for many sample days on large DEMs); azimuth bins control its resolution
- **Output** — single raster: annual PV potential (kWh/m²/year)

### GPU Acceleration

The plugin uses the GPU when one is available and the checkbox is on (it is by default). If no compatible GPU/driver is found at run time, computation silently falls back to the CPU — same results contract, no error dialogs.

## Examples

### Example 1: Summer solstice irradiation map

Goal: global radiation for June 21 (day 172) over a mountainous area.

1. Load `alps_dem.tif`, open the plugin, select it as elevation
2. **Daily** mode, day = 172, time step = 0.5 h
3. Check **Global**, click **Run**
4. Result: `<prefix>_glob.tif` in Wh/m²/day, added to your project

### Example 2: Annual PV potential for rooftop planning

Goal: yearly yield estimate for 20 % panels on a LiDAR building/terrain model.

1. Load the DSM, select it as elevation
2. **Annual** mode, day range 1–365, stride 10, time step 0.5 h
3. Panel efficiency = 0.20, click **Run**
4. Result: `<prefix>_potential.tif` in kWh/m²/year — symbolize with a sequential colormap to spot the best roofs

### Example 3: Custom atmospheric conditions

Goal: winter-solstice radiation under hazy air over snow.

1. Select your DEM; set **Linke** constant = 4.5 and **Albedo** constant = 0.8
2. **Daily** mode, day = 355; check **Beam** and **Diffuse**
3. Click **Run**

## Performance

Measured on a laptop with AMD Ryzen 5 PRO 8540U (12 threads) and integrated Radeon 740M graphics, day 172, 0.5 h time step, global-irradiation output:

| DEM size    | Mode                      | CPU     | GPU    | Speedup |
|-------------|---------------------------|---------|--------|---------|
| 500×500     | Daily                     | 0.7 s   | 0.13 s | 5.6×    |
| 500×500     | Annual (37 sampled days)  | 24 s    | 1.4 s  | 17×     |
| 1000×1000   | Daily                     | 2.9 s   | 0.34 s | 8.8×    |
| 1000×1000   | Annual (37 sampled days)  | 99 s    | 6.3 s  | 16×     |
| 2000×2000   | Daily                     | 12.3 s  | 1.4 s  | 8.9×    |

Notes:

- Larger DEMs benefit more — the per-run setup cost amortizes.
- Memory stays bounded: the DEM is held once, while inputs and outputs stream through in row bands (default 2048 rows), so rasters far larger than free RAM are processable.
- CPU timings use all cores. A discrete GPU will beat the integrated one above by a further factor.

## Troubleshooting

### Plugin doesn't appear in QGIS

- **QGIS version**: requires 3.34+ (older versions ship Python < 3.12, which the bundled extension can't load)
- **Enabled?**: check **Plugins → Manage and Install Plugins → Installed**

### "sun extension not found" / "Failed to load" error

The plugin bundles a self-contained native computation library (no external dependencies — it does not use QGIS's GDAL at all).

- Make sure the zip was installed completely: the plugin folder must contain a file named like `sun.cpython-312-*.so` (Linux/macOS) or `.pyd` (Windows)
- The error message names the Python version the bundled file was built for — it must be 3.12 (QGIS 3.34+). If you run an older QGIS, upgrade QGIS
- Reinstalling the zip overwrites stale files from previous versions

### GPU mode doesn't seem to engage

- The plugin probes for a usable GPU at run time and silently falls back to the CPU when none is found — results are still correct
- On Linux, `vulkaninfo --summary` should list your GPU; if it lists only `llvmpipe`, install your vendor's Vulkan driver (e.g. `mesa-vulkan-drivers` / `vulkan-radeon`, `nvidia-driver`)
- Virtual machines and remote sessions often expose no GPU; the CPU path handles those

### Results look wrong

- **DEM units**: elevation must be metres (convert feet first)
- **CRS**: any projected or geographic CRS works, but the layer must have one assigned
- **Aspect convention**: supplied aspect rasters must be GRASS convention (0° = East, CCW), not compass (0° = North, CW)
- **Linke vs albedo mix-up**: Linke is ~2–5, albedo is 0–1
- **Southern Hemisphere**: seasons are reversed — day 172 is winter there

### Progress bar doesn't move for a while

Large DEMs spend the first seconds reading the raster and deriving slope/aspect. Progress updates follow per processed band; the dialog stays responsive throughout and the run can be cancelled.

## Technical Details

The model is the GRASS GIS `r.sun` clear-sky solar radiation model (Hofierka & Suri, 2002), ported to a native compiled engine with an optional GPU compute path:

- Solar geometry and day-length per pixel latitude
- Cast-shadow ray-marching against the full DEM (shadows cross tile boundaries correctly)
- ESRA clear-sky beam/diffuse transmittance (Linke turbidity)
- Ground reflection (albedo), slope/aspect incidence

Raster I/O is handled by QGIS/GDAL in Python; the computation engine receives plain arrays and has no file-format or GDAL dependency.

Source and issue tracker: [github.com/raphi-web/sun-solar-radiation](https://github.com/raphi-web/sun-solar-radiation)

## License

MIT License — see LICENSE file.

## Credits

- Solar radiation model: GRASS GIS `r.sun` (Hofierka & Suri, 2002)
- Computation engine: native compiled code with WebGPU compute-shader acceleration
- Plugin architecture follows QGIS Python plugin best practices
