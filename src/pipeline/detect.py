import numpy as np
from scipy import ndimage
from dataclasses import dataclass
from src.utils.geo import compute_ndvi, compute_bsi, pixels_to_latlon

@dataclass
class Site:
    pixel_bbox: tuple
    geo_bbox: tuple
    area_ha: float
    ndvi_drop: float
    bsi_rise: float
    pixel_count: int

def detect_changes(bands_before, bands_after, bbox, min_pixels=10):
    """
    Detect change between two time periods.
    Returns a list of Site objects.
    """
    # Align both periods to the same grid
    h = min(bands_before["red"].shape[0], bands_after["red"].shape[0])
    w = min(bands_before["red"].shape[1], bands_after["red"].shape[1])
    for k in bands_before:  bands_before[k] = bands_before[k][:h, :w]
    for k in bands_after:   bands_after[k]  = bands_after[k][:h, :w]

    ndvi_before = compute_ndvi(bands_before["red"], bands_before["nir"])
    ndvi_after  = compute_ndvi(bands_after["red"],  bands_after["nir"])

    bsi_before = compute_bsi(bands_before["red"], bands_before["nir"],
                              bands_before["swir"], bands_before["blue"])
    bsi_after  = compute_bsi(bands_after["red"],  bands_after["nir"],
                              bands_after["swir"],  bands_after["blue"])

    ndvi_drop = ndvi_before - ndvi_after   # positive = vegetation lost
    bsi_rise  = bsi_after  - bsi_before   # positive = bare soil gained

    change_mask = (ndvi_drop > 0.08) & (bsi_rise > 0.04)

    # Light morphological cleanup
    change_mask = ndimage.binary_opening(change_mask, iterations=1)
    change_mask = ndimage.binary_closing(change_mask, iterations=1)

    labeled, n_features = ndimage.label(change_mask)
    
    sites = []
    for i in range(1, n_features + 1):
        component = labeled == i
        pixel_count = np.sum(component)
        if pixel_count < min_pixels:
            continue
            
        rows, cols = np.where(component)
        pixel_bbox = (rows.min(), cols.min(), rows.max(), cols.max())
        
        # Calculate mean change metrics for the site
        site_ndvi_drop = float(np.mean(ndvi_drop[component]))
        site_bsi_rise = float(np.mean(bsi_rise[component]))
        
        geo_bbox = pixels_to_latlon(pixel_bbox, (h, w), bbox)
        area_ha = (pixel_count * 20 * 20) / 10000.0  # ~20m res
        
        sites.append(Site(
            pixel_bbox=pixel_bbox,
            geo_bbox=geo_bbox,
            area_ha=area_ha,
            ndvi_drop=site_ndvi_drop,
            bsi_rise=site_bsi_rise,
            pixel_count=int(pixel_count)
        ))

    return sites
