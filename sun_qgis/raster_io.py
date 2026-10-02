"""GDAL-based raster I/O for the sun_qgis plugin (Python side).

The native extension no longer opens files: Python reads rasters (optionally
tiled for huge DEMs), passes flat f32 lists to Rust, and writes the returned
band arrays into GeoTIFFs. Nodata handling mirrors the Rust convention:
declared nodata and NaN are both normalized to UNDEFZ (-9999).

All functions here are plain path-in/array-out so they run headless in tests
against real GDAL.
"""

import numpy as np
from osgeo import gdal, osr

UNDEFZ = -9999.0

# Default number of rows per band when tiling reads/writes. Chosen so a band
# of a 20k-wide f32 raster stays around 160 MB.
DEFAULT_BAND_ROWS = 2048


def raster_meta(path):
    """Return dict with ncols, nrows, gt (6-tuple), wkt, nodata for band 1."""
    ds = gdal.Open(path)
    if ds is None:
        raise FileNotFoundError(f"Could not open raster: {path}")
    try:
        band = ds.GetRasterBand(1)
        meta = {
            "ncols": ds.RasterXSize,
            "nrows": ds.RasterYSize,
            "gt": ds.GetGeoTransform(),
            "wkt": ds.GetProjection(),
            "nodata": band.GetNoDataValue(),
            "path": path,
        }
        return meta
    finally:
        ds = None


def _normalize(arr, nodata):
    """Map declared nodata and NaN to UNDEFZ (float32, C-contiguous)."""
    out = np.asarray(arr, dtype=np.float32)
    mask = np.isnan(out)
    if nodata is not None:
        mask |= out == np.float32(nodata)
    out[mask] = UNDEFZ
    return np.ascontiguousarray(out)


def read_full(path):
    """Read band 1 of *path* fully; returns (nrows, ncols) float32 array
    with nodata/NaN normalized to UNDEFZ."""
    meta = raster_meta(path)
    ds = gdal.Open(path)
    try:
        band = ds.GetRasterBand(1)
        arr = band.ReadAsArray()
    finally:
        ds = band = None
    return _normalize(arr, meta["nodata"])


def read_band(path, row_off, row_end):
    """Read rows [row_off, row_end) of band 1, clipped to the raster.

    Returns (h, ncols) float32 array with nodata/NaN normalized to UNDEFZ.
    Half-open interval matches band_plan()'s (start, end) contract. Used for
    tiled reading of optional inputs (slope/aspect/linke/albedo/mask) so a
    huge DEM never has to be duplicated for those layers.
    """
    meta = raster_meta(path)
    total = meta["nrows"]
    row_off = max(0, min(row_off, total))
    row_end = max(row_off, min(row_end, total))
    nrows = row_end - row_off
    if nrows == 0:
        return np.zeros((0, meta["ncols"]), dtype=np.float32)
    ds = gdal.Open(path)
    try:
        band = ds.GetRasterBand(1)
        arr = band.ReadAsArray(0, row_off, meta["ncols"], nrows)
    finally:
        ds = band = None
    return _normalize(arr, meta["nodata"])


def band_plan(nrows, band_rows=DEFAULT_BAND_ROWS):
    """Split *nrows* into contiguous (start, end) row bands of ≤ band_rows.

    Covers every row exactly once, last band may be shorter.
    """
    plan = []
    start = 0
    while start < nrows:
        end = min(start + band_rows, nrows)
        plan.append((start, end))
        start = end
    return plan


def row_latitudes(meta, ncols, nrows):
    """Per-row pixel-centre latitude in WGS84 degrees.

    Geographic CRS: straight from the geotransform. Projected CRS: sample the
    column-centre x at each row-centre y and transform to EPSG:4326 (same
    approach as the old Rust implementation — latitude varies primarily
    along Y).
    """
    gt = meta["gt"]
    srs = osr.SpatialReference()
    srs.ImportFromWkt(meta["wkt"])
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    col_centre = ncols / 2.0
    if srs.IsGeographic():
        return [
            float(gt[3] + col_centre * gt[4] + (row + 0.5) * gt[5])
            for row in range(nrows)
        ]

    tgt = osr.SpatialReference()
    tgt.ImportFromEPSG(4326)
    tgt.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tr = osr.CoordinateTransformation(srs, tgt)

    xs = [gt[0] + col_centre * gt[1] + 0.5 * gt[2]] * nrows
    ys = [gt[3] + col_centre * gt[4] + (row + 0.5) * gt[5] for row in range(nrows)]
    lats = []
    for x, y in zip(xs, ys):
        lon, lat, _ = tr.TransformPoint(x, y)
        lats.append(float(lat))
    return lats


def create_output(path, meta, nodata=UNDEFZ):
    """Create an output GeoTIFF cloning *meta*'s geometry. Returns the open
    dataset — caller writes bands then sets it to None to flush/close."""
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(
        path, meta["ncols"], meta["nrows"], 1, gdal.GDT_Float32,
        options=["TILED=YES", "COMPRESS=DEFLATE"],
    )
    if ds is None:
        raise IOError(f"Could not create output raster: {path}")
    ds.SetGeoTransform(meta["gt"])
    ds.SetProjection(meta["wkt"])
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(nodata)
    return ds


def write_band(ds, arr, row_off):
    """Write a (h, ncols) array into the open dataset at *row_off*."""
    band = ds.GetRasterBand(1)
    band.WriteArray(np.asarray(arr, dtype=np.float32), 0, row_off)
