"""
Construction Intelligence Platform — Ahmedabad Prototype
Detects potential construction sites using Sentinel-2 change detection.
"""

import os
import warnings
import numpy as np
import folium
import json
from datetime import datetime, timedelta
from scipy import ndimage
import requests
warnings.filterwarnings("ignore")

# ─── CONFIG ────────────────────────────────────────────────────────────────────

# Ahmedabad bounding box (W, S, E, N)
BBOX = [72.45, 22.95, 72.75, 23.15]

# Time windows
DATE_BEFORE = ("2024-03-01", "2024-05-31")
DATE_AFTER  = ("2025-03-01", "2025-05-31")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# ─── HELPERS ───────────────────────────────────────────────────────────────────

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


def fetch_sentinel2_bands(bbox, date_range, label=""):
    """
    Fetch Sentinel-2 L2A bands via Microsoft Planetary Computer STAC API.
    Returns dict of normalised float32 arrays for B02, B04, B08, B11.
    """
    import pystac_client
    import planetary_computer as pc
    import rioxarray

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
        max_items=5,
    )

    items = list(search.items())
    if not items:
        raise RuntimeError(f"No Sentinel-2 scenes found for {label} with <20% cloud cover.")

    item = items[0]
    print(f"  [{label}] Using scene: {item.id}  cloud={item.properties['eo:cloud_cover']:.1f}%")

    # Read bands at 20m resolution
    bands = {}
    # B02/B04 native 10m → overview_level=1 gives ~20m
    # B08 native 10m → overview_level=1 gives ~20m
    # B11 native 20m → overview_level=0 gives ~20m (no overview needed)
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

    return bands, item


def detect_construction_sites(bands_before, bands_after, min_pixels=10):
    """
    Change detection: find pixels where vegetation dropped and bare soil increased.
    Returns a binary mask and list of site bounding boxes in pixel coords.
    """
    # Align both periods to the same grid before computing indices
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

    # Debug stats
    print(f"  NDVI drop  — mean: {ndvi_drop.mean():.3f}  max: {ndvi_drop.max():.3f}")
    print(f"  BSI rise   — mean: {bsi_rise.mean():.3f}   max: {bsi_rise.max():.3f}")
    print(f"  Pixels with NDVI drop >0.10: {(ndvi_drop>0.10).sum()}")
    print(f"  Pixels with BSI  rise >0.05: {(bsi_rise>0.05).sum()}")

    # Construction signal: vegetation lost AND bare soil gained
    # Use looser thresholds for first prototype pass
    change_mask = (ndvi_drop > 0.08) & (bsi_rise > 0.04)

    # Light morphological cleanup to remove single-pixel noise
    change_mask = ndimage.binary_opening(change_mask, iterations=1)
    change_mask = ndimage.binary_closing(change_mask, iterations=1)

    # Label connected regions
    labeled, n_features = ndimage.label(change_mask)
    print(f"  Raw clusters found: {n_features}")

    sites = []
    for i in range(1, n_features + 1):
        component = labeled == i
        pixel_count = np.sum(component)
        if pixel_count < min_pixels:
            continue
        rows, cols = np.where(component)
        sites.append({
            "pixel_bbox": (rows.min(), cols.min(), rows.max(), cols.max()),
            "pixel_count": int(pixel_count),
            "area_m2": int(pixel_count * 20 * 20),  # ~20m resolution
        })

    return change_mask, sites, (h, w)


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


def build_map(sites_geo, bbox, output_path):
    """Build a folium interactive map with site markers."""
    center_lat = (bbox[1] + bbox[3]) / 2
    center_lon = (bbox[0] + bbox[2]) / 2

    m = folium.Map(location=[center_lat, center_lon], zoom_start=12,
                   tiles="CartoDB dark_matter")

    # Add satellite tile layer option
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satellite",
        overlay=False,
        control=True,
    ).add_to(m)

    folium.TileLayer("CartoDB dark_matter", name="Dark Map").add_to(m)

    # Study area boundary
    folium.Rectangle(
        bounds=[[bbox[1], bbox[0]], [bbox[3], bbox[2]]],
        color="#00d4ff", weight=2, fill=False,
        tooltip="Study Area: Ahmedabad"
    ).add_to(m)

    # Site markers
    for i, site in enumerate(sites_geo, 1):
        lat_min, lon_min, lat_max, lon_max = site["geo_bbox"]
        center = [(lat_min + lat_max) / 2, (lon_min + lon_max) / 2]
        area_ha = site["area_m2"] / 10000

        popup_html = f"""
        <div style="font-family:sans-serif;min-width:180px">
          <b style="color:#ff4444">🏗 Potential Construction Site #{i}</b><br>
          <hr style="margin:4px 0">
          <b>Area:</b> {area_ha:.2f} ha<br>
          <b>Confidence:</b> {"High" if area_ha > 1 else "Medium"}<br>
          <b>Coords:</b> {center[0]:.4f}°N, {center[1]:.4f}°E<br>
          <b>Detection:</b> NDVI drop + BSI rise<br>
          <b>Period:</b> Mar–May 2024 → Mar–May 2025
        </div>
        """

        # Rectangle for larger sites
        if area_ha > 0.2:
            folium.Rectangle(
                bounds=[[lat_min, lon_min], [lat_max, lon_max]],
                color="#ff4444", weight=2, fill=True, fill_opacity=0.25,
                popup=folium.Popup(popup_html, max_width=250),
                tooltip=f"Site #{i} | {area_ha:.2f} ha"
            ).add_to(m)

        folium.CircleMarker(
            location=center,
            radius=8,
            color="#ff4444",
            fill=True,
            fill_color="#ff8800",
            fill_opacity=0.9,
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"🏗 Site #{i} | {area_ha:.2f} ha"
        ).add_to(m)

    folium.LayerControl().add_to(m)

    # Legend
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
         background:rgba(0,0,0,0.8);color:white;padding:12px 16px;
         border-radius:8px;font-family:sans-serif;font-size:13px">
      <b>🛰 Construction Intelligence — Ahmedabad</b><br>
      <span style="color:#00d4ff">■</span> Study Area<br>
      <span style="color:#ff4444">■</span> Potential Construction Site<br>
      <hr style="border-color:#444;margin:6px 0">
      Change Period: 2024 → 2025<br>
      Method: NDVI drop + BSI rise
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    m.save(output_path)
    print(f"\n✅ Map saved → {output_path}")


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("  Construction Intelligence Platform — Ahmedabad Prototype")
    print("=" * 60)

    print("\n📡 Fetching Sentinel-2 imagery...")
    print("  Fetching BEFORE period (Mar–May 2024)...")
    bands_before, item_before = fetch_sentinel2_bands(BBOX, DATE_BEFORE, "BEFORE")

    print("  Fetching AFTER period (Mar–May 2025)...")
    bands_after, item_after = fetch_sentinel2_bands(BBOX, DATE_AFTER, "AFTER")

    print("\n🔍 Running change detection...")
    change_mask, sites, grid_shape = detect_construction_sites(bands_before, bands_after)
    print(f"  Sites after size filter: {len(sites)}")

    # Convert pixel coords → lat/lon
    sites_geo = []
    for site in sites:
        geo_bbox = pixels_to_latlon(site["pixel_bbox"], grid_shape, BBOX)
        sites_geo.append({**site, "geo_bbox": geo_bbox})

    # Sort by area descending
    sites_geo.sort(key=lambda s: s["area_m2"], reverse=True)

    # Print summary
    print(f"\n📊 Detection Summary")
    print(f"  Total sites detected: {len(sites_geo)}")
    total_area = sum(s["area_m2"] for s in sites_geo) / 10000
    print(f"  Total flagged area:   {total_area:.1f} ha")
    print(f"\n  Top 10 sites by area:")
    for i, s in enumerate(sites_geo[:10], 1):
        lat, lon = (s["geo_bbox"][0]+s["geo_bbox"][2])/2, (s["geo_bbox"][1]+s["geo_bbox"][3])/2
        print(f"    #{i:02d}  {s['area_m2']/10000:6.2f} ha   {lat:.4f}°N  {lon:.4f}°E")

    # Save GeoJSON
    geojson_path = os.path.join(OUTPUT_DIR, "sites.geojson")
    features = []
    for i, s in enumerate(sites_geo, 1):
        lat_min, lon_min, lat_max, lon_max = s["geo_bbox"]
        features.append({
            "type": "Feature",
            "properties": {"id": i, "area_m2": s["area_m2"], "area_ha": round(s["area_m2"]/10000, 3)},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[lon_min, lat_min],[lon_max, lat_min],
                                  [lon_max, lat_max],[lon_min, lat_max],[lon_min, lat_min]]]
            }
        })
    with open(geojson_path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, indent=2)
    print(f"  GeoJSON saved → {geojson_path}")

    # Build map
    print("\n🗺  Building interactive map...")
    map_path = os.path.join(OUTPUT_DIR, "construction_sites_map.html")
    build_map(sites_geo, BBOX, map_path)

    print("\n🎉 Done! Open output/construction_sites_map.html in your browser.")
    print("=" * 60)


if __name__ == "__main__":
    main()
