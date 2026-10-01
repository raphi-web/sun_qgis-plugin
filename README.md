# Solar Radiation QGIS Plugin

Compute clear-sky solar irradiation and photovoltaic potential directly inside QGIS from any digital elevation model.

## What This Plugin Does

This plugin calculates solar radiation maps from elevation data using a validated clear-sky model. You can generate:

- **Single-day irradiation maps**: beam, diffuse, reflected, and global radiation (Wh/m²/day) plus sunshine duration (hours)
- **Annual PV potential maps**: yearly photovoltaic energy yield (kWh/m²/year) with custom panel efficiency

The computation uses GPU acceleration when available, making it fast enough for large DEMs — a 1600×1600 pixel run completes in seconds on modern hardware.

## Installation

### Requirements

- QGIS 3.34 or later
- Python 3.12 (ships with QGIS 3.34)
- For GPU mode: a graphics card with Vulkan support (most GPUs from 2015+)

### Install Steps

1. Download the plugin package (`sun_qgis` folder with all contents)
2. Copy it to your QGIS plugins directory:
   - **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows**: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
   - **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
3. Restart QGIS
4. Enable the plugin: **Plugins → Manage and Install Plugins → Installed → Solar Radiation**

The plugin icon (a sun) appears in the toolbar.

## Usage

### Basic Workflow

1. **Load your DEM**: Open or drag a digital elevation model (GeoTIFF, ASCII grid, or other GDAL-supported raster) into QGIS
2. **Open the plugin**: Click the sun icon in the toolbar or go to **Raster → Solar Radiation**
3. **Configure inputs**:
   - Select your DEM from the dropdown (required)
   - Optionally select slope, aspect, Linke turbidity, albedo, or mask rasters
4. **Choose computation mode**:
   - **Daily**: Single-day irradiation for a specific day of year
   - **Annual**: Yearly PV potential integrated over all days
5. **Set output options**: Choose output directory, file prefix, and which rasters to generate
6. **Run**: Click "Run" and watch the progress bar. Results are added to your QGIS project automatically.

### Input Parameters

**Required:**
- **Elevation DEM**: Digital elevation model in meters (any GDAL-supported raster format)

**Optional (refine the model):**
- **Slope**: Terrain slope in degrees. If not provided, derived automatically from the DEM using Horn's method
- **Aspect**: Terrain aspect in degrees (0° = North, 90° = East). If not provided, derived automatically from the DEM
- **Linke turbidity**: Atmospheric clarity factor (dimensionless, typical range 2–5). Can be a constant value or a spatially varying raster. Default: 3.0 (clear atmosphere)
- **Albedo**: Ground reflectivity (0–1). Can be a constant value or a raster. Default: 0.2 (typical for vegetation)
- **Mask**: Binary raster (0/1) to restrict computation to specific areas. Pixels with mask=0 are skipped

### Daily Mode Parameters

- **Day of year**: 1–365 (e.g., 172 = summer solstice in Northern Hemisphere)
- **Time step**: Integration interval in hours (default 0.5h). Smaller steps are more accurate but slower
- **Output rasters**: Choose which to generate:
  - **Beam**: Direct solar radiation (Wh/m²/day)
  - **Diffuse**: Scattered sky radiation (Wh/m²/day)
  - **Reflected**: Ground-reflected radiation (Wh/m²/day)
  - **Global**: Total radiation = beam + diffuse + reflected (Wh/m²/day)
  - **Sunshine duration**: Hours of direct sunlight (h/day)

### Annual Mode Parameters

- **Day range**: Start and end day of year (e.g., 1–365 for full year)
- **Day step**: Sampling interval for integration (default 10 days). Smaller steps are more accurate but slower
- **Time step**: Sub-daily integration interval in hours (default 0.5h)
- **Panel efficiency**: PV conversion efficiency (0–1, e.g., 0.18 for 18% efficient panels)
- **Output**: Single raster showing annual PV potential (kWh/m²/year)

### GPU Acceleration

The plugin automatically uses GPU acceleration when available, providing 10–100× speedup for large DEMs. If no compatible GPU is found, it falls back to CPU computation automatically.

To force CPU mode (e.g., for debugging), uncheck "Use GPU acceleration" in the dialog.

## Examples

### Example 1: Summer Solstice Irradiation Map

**Goal**: Generate a global radiation map for June 21st (day 172) over a mountainous area.

1. Load your DEM (e.g., `alps_dem.tif`)
2. Open Solar Radiation plugin
3. Select `alps_dem.tif` as elevation
4. Choose **Daily** mode
5. Set day = 172, time step = 0.5h
6. Check **Global** output
7. Click **Run**
8. Result: `global_rad.tif` showing Wh/m²/day, automatically styled and added to your project

### Example 2: Annual PV Potential for Rooftop Solar

**Goal**: Estimate yearly solar energy yield for a region with 20% efficient panels.

1. Load a high-resolution DEM (e.g., LiDAR-derived 1m DSM)
2. Open Solar Radiation plugin
3. Select the DSM as elevation
4. Choose **Annual** mode
5. Set day range = 1–365, day step = 10, time step = 0.5h
6. Set panel efficiency = 0.20
7. Click **Run**
8. Result: `pv_potential.tif` showing kWh/m²/year

### Example 3: Custom Atmospheric Conditions

**Goal**: Model radiation under hazy conditions (Linke = 4.5) over snow (albedo = 0.8).

1. Load your DEM
2. Open Solar Radiation plugin
3. Select elevation DEM
4. Set **Linke turbidity** = 4.5 (constant value)
5. Set **Albedo** = 0.8 (constant value)
6. Choose daily mode, day = 355 (winter solstice)
7. Check **Beam** and **Diffuse** outputs
8. Click **Run**

## Troubleshooting

### Plugin doesn't appear in QGIS

- **Check QGIS version**: Requires QGIS 3.34 or later. Older versions use Python 3.9/3.10 which is incompatible.
- **Check plugin directory**: Verify the `sun_qgis` folder is in the correct plugins directory (see Installation)
- **Check Python version**: QGIS 3.34 ships with Python 3.12. If you have multiple QGIS versions, ensure you're using 3.34+

### "Could not load the sun extension" error

This means the compiled native library is missing or incompatible.

- **Linux**: Check that `sun.cpython-312-x86_64-linux-gnu.so` exists in the plugin directory
- **Verify GDAL linkage**: Run `ldd sun_qgis/sun.cpython-312-x86_64-linux-gnu.so | grep gdal` — should show `libgdal.so.34 => /lib/x86_64-linux-gnu/libgdal.so.34`
- **Rebuild if needed**: If you built from source, run `scripts/build_extension.sh` to rebuild against your system's GDAL

### GPU mode is slow or fails

- **Check GPU support**: The plugin needs Vulkan support. Run `vulkaninfo | grep "Device Name"` to verify your GPU is detected
- **Fallback to CPU**: Uncheck "Use GPU acceleration" — CPU mode is always available
- **Memory issues**: Very large DEMs (>8000×8000 pixels) may exceed GPU memory. The plugin automatically tiles the computation, but you can also clip the DEM to a smaller extent first

### Results look wrong

- **Check DEM units**: Elevation must be in meters. If your DEM is in feet, convert first
- **Check CRS**: The plugin works in any coordinate system, but ensure your DEM has a valid CRS assigned
- **Check Linke/Albedo ranges**: Linke should be 2–5 (not 0.2–0.5), albedo should be 0–1 (not 0–100)
- **Verify day of year**: Day 1 = January 1st, day 365 = December 31st. For Southern Hemisphere, remember seasons are reversed

### Progress bar freezes

- **Normal for large DEMs**: The first few seconds are spent loading the DEM and setting up GPU buffers. Progress updates appear after initialization
- **Check system resources**: If RAM is exhausted, the system may swap and appear frozen. Monitor with `top` or `htop`
- **Cancel and retry**: You can cancel the computation and try with a smaller DEM or coarser time step

## Performance

Typical runtimes on a modern laptop (Intel i7 + integrated GPU):

| DEM size | Mode | CPU time | GPU time |
|----------|------|----------|----------|
| 100×100 | Daily | 0.1s | 0.05s |
| 1000×1000 | Daily | 8s | 0.3s |
| 1600×1600 | Daily | 20s | 0.8s |
| 1000×1000 | Annual (365 days) | 5min | 15s |

GPU acceleration provides 10–100× speedup for large DEMs. The speedup is smaller for tiny DEMs due to GPU initialization overhead.

## Technical Details

The plugin implements the GRASS GIS `r.sun` clear-sky solar radiation model, validated against measured data and widely used in solar energy research. The model accounts for:

- Solar geometry (sun position, day length)
- Topographic shading (horizon blocking)
- Atmospheric attenuation (Linke turbidity)
- Ground reflection (albedo)
- Slope and aspect effects

For technical documentation, source code, and the underlying computation engine, see the [Rust implementation repository](https://github.com/yourusername/sun).

## License

MIT License — see LICENSE file for details.

## Credits

- Solar radiation model: GRASS GIS `r.sun` (Hofierka & Suri, 2002)
- GPU acceleration: WebGPU compute shaders
- QGIS plugin architecture: Following QGIS Python plugin best practices
