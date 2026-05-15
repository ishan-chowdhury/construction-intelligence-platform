import os
import numpy as np
import pystac_client
import planetary_computer as pc
import rioxarray

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output", "cache")

def fetch_best_scene(bbox, date_range):
    """Fetch the best cloud-free Sentinel-2 scene from MS Planetary Computer."""
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=pc.sign_inplace,
    )
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=f"{date_range[0]}/{date_range[1]}",
        query={"eo:cloud_cover": {"lt": 20}},
        sortby=[{"field": "eo:cloud_cover", "direction": "asc"}],
        max_items=1,
    )
    items = list(search.items())
    if not items:
        raise RuntimeError(f"No Sentinel-2 scenes found for date range {date_range} with <20% cloud cover.")
    return items[0]

def fetch_bands(item, bbox, use_cache=True):
    """Download, align and cache Sentinel-2 bands for a specific bbox."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    # We create a unique cache key based on scene ID and bounding box
    bbox_str = "_".join(map(lambda x: f"{x:.2f}", bbox))
    cache_path = os.path.join(CACHE_DIR, f"{item.id}_{bbox_str}.npz")
    
    if use_cache and os.path.exists(cache_path):
        print(f"    Loaded bands from cache: {cache_path}")
        data = np.load(cache_path)
        return {k: data[k] for k in data.files}

    bands = {}
    band_map = {"B02": "blue", "B04": "red", "B08": "nir", "B11": "swir"}
    ov_map   = {"B02": 1,       "B04": 1,       "B08": 1,       "B11": 0}
    
    for band_id, name in band_map.items():
        href = pc.sign(item.assets[band_id].href)
        da = rioxarray.open_rasterio(href, overview_level=ov_map[band_id])
        da = da.rio.clip_box(*bbox, crs="EPSG:4326")
        arr = da.values.squeeze().astype(np.float32) / 10000.0
        bands[name] = np.clip(arr, 0, 1)

    # Align all bands to the same shape (use smallest common grid)
    h = min(v.shape[0] for v in bands.values())
    w = min(v.shape[1] for v in bands.values())
    for k in bands:
        bands[k] = bands[k][:h, :w]

    if use_cache:
        np.savez_compressed(cache_path, **bands)
        print(f"    Saved bands to cache: {cache_path}")

    return bands
