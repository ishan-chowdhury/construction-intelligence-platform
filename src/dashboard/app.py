from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from typing import Optional, List
from src.data.database import DB_PATH

app = FastAPI(title="Construction Intelligence API")

# Allow CORS for the Next.js frontend (default port 3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/cities")
def get_cities():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT c.*, 
               (SELECT COUNT(*) FROM sites s WHERE s.city_id = c.id) as site_count,
               (SELECT SUM(area_ha) FROM sites s WHERE s.city_id = c.id) as total_area
        FROM cities c
        WHERE enabled = 1
    """)
    return [dict(row) for row in c.fetchall()]

@app.get("/api/sites")
def get_sites(city: Optional[str] = None, min_confidence: float = Query(0.0)):
    conn = get_db()
    c = conn.cursor()
    
    query = "SELECT * FROM sites WHERE confidence >= ?"
    params = [min_confidence]
    
    if city:
        query += " AND city_id = ?"
        params.append(city)
        
    query += " ORDER BY area_ha DESC"
    
    c.execute(query, params)
    return [dict(row) for row in c.fetchall()]

class LabelRequest(BaseModel):
    label: str

@app.post("/api/sites/{site_id}/label")
def label_site(site_id: int, request: LabelRequest):
    if request.label not in ['construction', 'agriculture', 'false_positive']:
        raise HTTPException(status_code=400, detail="Invalid label")
        
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE sites SET label = ? WHERE id = ?", (request.label, site_id))
    conn.commit()
    return {"success": True}
