"""
Verification Script — Generate a visual grid of top detected sites
Fetches true-colour thumbnails from Sentinel-2 for manual inspection.
"""

import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import warnings
warnings.filterwarnings("ignore")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
GEOJSON_PATH = os.path.join(OUTPUT_DIR, "sites.geojson")

BBOX = [72.45, 22.95, 72.75, 23.15]
DATE_BEFORE = ("2024-03-01", "2024-05-31")
DATE_AFTER  = ("2025-03-01", "2025-05-31")

TOP_N = 10  # Verify top N sites


def fetch_scene_item(bbox, date_range):
    import pystac_client
    import planetary_computer as pc
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
    return items[0] if items else None


def fetch_rgb_chip(item, site_bbox_geo, pad=0.005):
    """Fetch a small RGB chip around a site bbox."""
    import planetary_computer as pc
    import rioxarray

    lat_min, lon_min, lat_max, lon_max = site_bbox_geo
    chip_bbox = [lon_min - pad, lat_min - pad, lon_max + pad, lat_max + pad]

    rgb = []
    for band_id in ["B04", "B03", "B02"]:  # R, G, B
        href = pc.sign(item.assets[band_id].href)
        da = rioxarray.open_rasterio(href, overview_level=1)
        da = da.rio.clip_box(*chip_bbox, crs="EPSG:4326")
        arr = da.values.squeeze().astype(np.float32) / 10000.0
        rgb.append(np.clip(arr, 0, 1))

    img = np.stack(rgb, axis=-1)
    # Brighten for visualisation (gamma)
    img = np.clip(img * 3.5, 0, 1)
    return img


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load detected sites
    with open(GEOJSON_PATH) as f:
        fc = json.load(f)

    features = fc["features"]
    # Sort by area desc (already sorted, but let's be sure)
    features.sort(key=lambda x: x["properties"]["area_m2"], reverse=True)
    top_sites = features[:TOP_N]

    print(f"Verifying top {len(top_sites)} sites...")
    print("Fetching scene items...")

    item_before = fetch_scene_item(BBOX, DATE_BEFORE)
    item_after  = fetch_scene_item(BBOX, DATE_AFTER)

    fig, axes = plt.subplots(TOP_N, 2, figsize=(10, TOP_N * 3.2))
    fig.patch.set_facecolor("#0d0d0d")
    fig.suptitle(
        "🏗  Construction Intelligence — Ahmedabad\nTop 10 Detected Sites: Before (2024) vs After (2025)",
        color="white", fontsize=13, fontweight="bold", y=0.995
    )

    for i, feat in enumerate(top_sites):
        coords = feat["geometry"]["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        geo_bbox = (min(lats), min(lons), max(lats), max(lons))
        area_ha = feat["properties"]["area_ha"]
        site_id = feat["properties"]["id"]
        center_lat = (geo_bbox[0] + geo_bbox[2]) / 2
        center_lon = (geo_bbox[1] + geo_bbox[3]) / 2

        for j, (item, label, col) in enumerate([
            (item_before, "Before — May 2024", "#4fc3f7"),
            (item_after,  "After  — May 2025", "#ff5252"),
        ]):
            ax = axes[i][j]
            ax.set_facecolor("#111")
            try:
                chip = fetch_rgb_chip(item, geo_bbox)
                ax.imshow(chip, interpolation="bilinear")

                # Draw site boundary
                h, w = chip.shape[:2]
                rect = mpatches.Rectangle(
                    (w * 0.2, h * 0.2), w * 0.6, h * 0.6,
                    linewidth=2, edgecolor="#ff5252" if j == 1 else "#4fc3f7",
                    facecolor="none", linestyle="--"
                )
                ax.add_patch(rect)
            except Exception as e:
                ax.text(0.5, 0.5, f"No data\n{e}", color="gray",
                        ha="center", va="center", transform=ax.transAxes, fontsize=7)

            ax.set_title(
                f"Site #{site_id} | {area_ha:.2f} ha | {label}\n"
                f"{center_lat:.4f}°N  {center_lon:.4f}°E",
                color="white", fontsize=8, pad=4
            )
            ax.axis("off")

        print(f"  ✓ Site #{site_id} ({area_ha:.2f} ha) — {center_lat:.4f}°N, {center_lon:.4f}°E")

    plt.tight_layout(rect=[0, 0, 1, 0.995])
    out_path = os.path.join(OUTPUT_DIR, "top10_sites_verification.png")
    plt.savefig(out_path, dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"\n✅ Verification grid saved → {out_path}")


if __name__ == "__main__":
    main()
