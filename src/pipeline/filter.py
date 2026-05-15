import osmnx as ox
import geopandas as gpd
from shapely.geometry import Point, box
import warnings

def filter_by_roads(sites, bbox, max_distance_meters=500):
    """
    Check if sites are near roads to reduce agricultural false positives.
    Returns a list of tuples: (site, distance_to_road_meters)
    """
    warnings.filterwarnings("ignore", category=FutureWarning)
    
    # Define polygon for the bbox
    west, south, east, north = bbox
    polygon = box(west, south, east, north)
    
    try:
        # Fetch road network for the bbox
        G = ox.graph_from_polygon(polygon, network_type='drive')
        # Convert to GeoDataFrame
        nodes, edges = ox.graph_to_gdfs(G)
        
        # Project to local UTM to measure distance in meters accurately
        # Simplification: use Web Mercator or just local UTM zone
        edges_proj = edges.to_crs(epsg=3857) 
        
        filtered_sites = []
        for site in sites:
            center_lat = (site.geo_bbox[0] + site.geo_bbox[2]) / 2
            center_lon = (site.geo_bbox[1] + site.geo_bbox[3]) / 2
            
            point = gpd.GeoSeries([Point(center_lon, center_lat)], crs="EPSG:4326").to_crs(epsg=3857).iloc[0]
            
            # Find nearest edge distance
            distance = edges_proj.distance(point).min()
            
            filtered_sites.append((site, float(distance)))
            
        return filtered_sites
    except Exception as e:
        print(f"Warning: Road filtering failed ({e}). Returning all sites with distance=0.")
        return [(site, 0.0) for site in sites]
