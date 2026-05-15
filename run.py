import argparse
import yaml
import os
import json
from datetime import datetime

from src.data.database import DB
from src.pipeline.fetch import fetch_best_scene, fetch_bands
from src.pipeline.detect import detect_changes
from src.pipeline.filter import filter_by_roads
from src.pipeline.classify import score_sites
from src.pipeline.geocode import geocode_sites

def load_cities():
    config_path = os.path.join(os.path.dirname(__file__), "config", "cities.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)["cities"]

def sync_cities_to_db():
    db = DB()
    cities = load_cities()
    for city_id, info in cities.items():
        db.add_or_update_city(
            city_id, info["name"], info["bbox"], info["priority"], info.get("enabled", True)
        )
    print("Database cities synced.")

def run_pipeline(city_id, before_dates, after_dates):
    db = DB()
    cities = load_cities()
    if city_id not in cities:
        print(f"Error: City {city_id} not found in config.")
        return

    city = cities[city_id]
    bbox = city["bbox"]
    print(f"\n--- Running pipeline for {city['name']} ---")
    
    print("Fetching scenes...")
    item_before = fetch_best_scene(bbox, before_dates)
    item_after = fetch_best_scene(bbox, after_dates)
    
    print(f"Before scene: {item_before.id} ({item_before.properties['eo:cloud_cover']:.1f}% cloud)")
    print(f"After scene:  {item_after.id} ({item_after.properties['eo:cloud_cover']:.1f}% cloud)")
    
    print("Downloading/loading bands...")
    bands_before = fetch_bands(item_before, bbox)
    bands_after = fetch_bands(item_after, bbox)
    
    print("Detecting changes...")
    sites = detect_changes(bands_before, bands_after, bbox, min_pixels=10)
    print(f"Found {len(sites)} raw sites.")
    
    if not sites:
        return
        
    print("Filtering by road proximity (OSMnx)...")
    sites_with_dist = filter_by_roads(sites, bbox)
    
    print("Scoring sites...")
    scored_sites = score_sites(sites_with_dist)
    
    print("Geocoding high-confidence sites...")
    scored_sites = geocode_sites(scored_sites, min_confidence=0.4)
    
    total_area = sum(s["site"].area_ha for s in scored_sites)
    
    # Save to DB
    run_date = datetime.now().isoformat()
    run_id = db.add_run(city_id, run_date, item_before.id, item_after.id, len(sites), total_area)
    
    for s in scored_sites:
        site = s["site"]
        db.add_site(
            run_id, city_id, 
            (site.geo_bbox[0] + site.geo_bbox[2]) / 2, 
            (site.geo_bbox[1] + site.geo_bbox[3]) / 2,
            site.area_ha, s["confidence"], site.ndvi_drop, site.bsi_rise,
            s["location_name"]
        )
        
    print(f"Done. Saved {len(sites)} sites to database.")

def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    
    # Detect command
    detect_parser = subparsers.add_parser("detect")
    detect_parser.add_argument("--city", help="City ID to run")
    detect_parser.add_argument("--all", action="store_true", help="Run for all enabled cities")
    detect_parser.add_argument("--before", default="2024-03-01,2024-05-31", help="Before date range (start,end)")
    detect_parser.add_argument("--after", default="2025-03-01,2025-05-31", help="After date range (start,end)")
    
    # Dashboard command
    dash_parser = subparsers.add_parser("dashboard")
    dash_parser.add_argument("--port", type=int, default=5000, help="Port to run dashboard on")
    
    args = parser.parse_args()
    
    sync_cities_to_db()
    
    if args.command == "detect":
        before_dates = tuple(args.before.split(","))
        after_dates = tuple(args.after.split(","))
        
        if args.all:
            db = DB()
            enabled = db.get_enabled_cities()
            for c in enabled:
                run_pipeline(c["id"], before_dates, after_dates)
        elif args.city:
            run_pipeline(args.city, before_dates, after_dates)
        else:
            print("Please specify --city or --all")
            
    elif args.command == "dashboard":
        import uvicorn
        print(f"Starting FastAPI backend on port {args.port}...")
        uvicorn.run("src.dashboard.app:app", host="127.0.0.1", port=args.port, reload=True)

if __name__ == "__main__":
    main()
