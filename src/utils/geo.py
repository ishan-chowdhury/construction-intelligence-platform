import numpy as np

def pixels_to_latlon(pixel_bbox, grid_shape, geo_bbox):
    """Convert pixel row/col bounding box to lat/lon coordinates."""
    h, w = grid_shape
    rmin, cmin, rmax, cmax = pixel_bbox
    west, south, east, north = geo_bbox

    lat_max = north - (rmin / h) * (north - south)
    lat_min = north - (rmax / h) * (north - south)
    lon_min = west  + (cmin / w) * (east  - west)
    lon_max = west  + (cmax / w) * (east  - west)

    return lat_min, lon_min, lat_max, lon_max

def compute_ndvi(red, nir):
    """NDVI = (NIR - Red) / (NIR + Red)"""
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where((nir + red) == 0, 0, (nir - red) / (nir + red))
    return ndvi.astype(np.float32)

def compute_bsi(red, nir, swir, blue):
    """Bare Soil Index = ((SWIR + Red) - (NIR + Blue)) / ((SWIR + Red) + (NIR + Blue))"""
    num = (swir + red) - (nir + blue)
    den = (swir + red) + (nir + blue)
    with np.errstate(divide="ignore", invalid="ignore"):
        bsi = np.where(den == 0, 0, num / den)
    return bsi.astype(np.float32)
