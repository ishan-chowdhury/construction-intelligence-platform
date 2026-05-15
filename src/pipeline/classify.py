import os
import joblib
import numpy as np

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "output", "model.joblib")

def score_sites(sites_with_distance):
    """
    Score sites using a heuristic if no model exists.
    Returns list of dicts with 'site', 'distance', and 'confidence'.
    """
    scored_sites = []
    
    # Try to load a trained model (for future use once we have labels)
    model = None
    if os.path.exists(MODEL_PATH):
        try:
            model = joblib.load(MODEL_PATH)
        except:
            pass

    for site, distance in sites_with_distance:
        if model:
            # Prepare features: area, ndvi_drop, bsi_rise, distance
            features = np.array([[site.area_ha, site.ndvi_drop, site.bsi_rise, distance]])
            confidence = float(model.predict_proba(features)[0][1]) # Probability of class 1 (construction)
        else:
            # Heuristic scoring
            # High confidence if:
            # 1. Close to road (< 300m)
            # 2. Significant NDVI drop and BSI rise
            # 3. Reasonable size (not too small, not massive like a whole farm)
            
            score = 0.5
            
            # STRICT Distance factor: focus on highways and corridors
            if distance < 50:
                score += 0.4
            elif distance < 100:
                score += 0.3
            elif distance < 200:
                score += 0.1
            else:
                score -= 0.6  # Heavy penalty for being far from roads (likely agriculture)
                
            # Signal strength
            if site.ndvi_drop > 0.15:
                score += 0.15
            if site.bsi_rise > 0.10:
                score += 0.15
                
            # Size factor: exclude massive agricultural tracts
            if 0.2 <= site.area_ha <= 4.0:
                score += 0.1
            elif site.area_ha > 8.0:
                score -= 0.5 # Extremely likely to be farm clearing
                
            confidence = max(0.0, min(1.0, score))
            
        scored_sites.append({
            "site": site,
            "distance_to_road": distance,
            "confidence": confidence
        })
        
    return scored_sites
