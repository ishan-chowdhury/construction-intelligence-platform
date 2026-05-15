import requests
import time

def reverse_geocode(lat, lon):
    """
    Use OpenStreetMap Nominatim to reverse geocode lat/lon.
    Note: Nominatim requires a 1 second delay between requests.
    """
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=14&addressdetails=1"
    headers = {
        'User-Agent': 'ConstructionIntelPlatform/1.0 (prototype)'
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            # Try to build a sensible short name
            addr = data.get('address', {})
            road = addr.get('road')
            suburb = addr.get('suburb') or addr.get('neighborhood') or addr.get('village')
            city = addr.get('city') or addr.get('town') or addr.get('county')
            
            parts = []
            if road: parts.append(road)
            if suburb: parts.append(suburb)
            elif city and not road: parts.append(city)
            
            if parts:
                return ", ".join(parts)
            return data.get('display_name', '').split(',')[0] # Fallback to first part
    except Exception as e:
        print(f"Geocoding failed for {lat}, {lon}: {e}")
        
    return "Unknown Location"

def geocode_sites(scored_sites, min_confidence=0.4):
    """
    Geocode sites, skipping low confidence ones to save API limits.
    """
    for s in scored_sites:
        if s["confidence"] >= min_confidence:
            lat = (s["site"].geo_bbox[0] + s["site"].geo_bbox[2]) / 2
            lon = (s["site"].geo_bbox[1] + s["site"].geo_bbox[3]) / 2
            s["location_name"] = reverse_geocode(lat, lon)
            time.sleep(1.1) # Respect OSM 1 req/sec limit
        else:
            s["location_name"] = "Low Probability Area"
    return scored_sites
