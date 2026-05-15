import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "output", "platform.db")

class DB:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        c = self.conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS cities (
                id TEXT PRIMARY KEY,
                name TEXT,
                bbox_json TEXT,
                priority TEXT,
                enabled BOOLEAN
            );
            
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city_id TEXT,
                run_date TEXT,
                before_scene TEXT,
                after_scene TEXT,
                n_sites INTEGER,
                total_area_ha REAL,
                FOREIGN KEY(city_id) REFERENCES cities(id)
            );
            
            CREATE TABLE IF NOT EXISTS sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                city_id TEXT,
                lat REAL,
                lon REAL,
                area_ha REAL,
                confidence REAL,
                ndvi_drop REAL,
                bsi_rise REAL,
                location_name TEXT,
                label TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(run_id) REFERENCES runs(id),
                FOREIGN KEY(city_id) REFERENCES cities(id)
            );
        """)
        self.conn.commit()

    def add_or_update_city(self, city_id, name, bbox, priority, enabled):
        c = self.conn.cursor()
        c.execute("""
            INSERT INTO cities (id, name, bbox_json, priority, enabled)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                bbox_json=excluded.bbox_json,
                priority=excluded.priority,
                enabled=excluded.enabled
        """, (city_id, name, json.dumps(bbox), priority, enabled))
        self.conn.commit()

    def add_run(self, city_id, run_date, before_scene, after_scene, n_sites, total_area_ha):
        c = self.conn.cursor()
        c.execute("""
            INSERT INTO runs (city_id, run_date, before_scene, after_scene, n_sites, total_area_ha)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (city_id, run_date, before_scene, after_scene, n_sites, total_area_ha))
        self.conn.commit()
        return c.lastrowid

    def add_site(self, run_id, city_id, lat, lon, area_ha, confidence, ndvi_drop, bsi_rise, location_name=None):
        c = self.conn.cursor()
        c.execute("""
            INSERT INTO sites (run_id, city_id, lat, lon, area_ha, confidence, ndvi_drop, bsi_rise, location_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_id, city_id, lat, lon, area_ha, confidence, ndvi_drop, bsi_rise, location_name))
        self.conn.commit()
        return c.lastrowid

    def get_enabled_cities(self):
        c = self.conn.cursor()
        c.execute("SELECT * FROM cities WHERE enabled=1")
        return [dict(row) for row in c.fetchall()]

    def get_all_sites(self, city_id=None, min_confidence=None):
        c = self.conn.cursor()
        query = "SELECT * FROM sites WHERE 1=1"
        params = []
        if city_id:
            query += " AND city_id=?"
            params.append(city_id)
        if min_confidence is not None:
            query += " AND confidence>=?"
            params.append(min_confidence)
        c.execute(query, params)
        return [dict(row) for row in c.fetchall()]

    def get_site(self, site_id):
        c = self.conn.cursor()
        c.execute("SELECT * FROM sites WHERE id=?", (site_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def update_site_label(self, site_id, label):
        c = self.conn.cursor()
        c.execute("UPDATE sites SET label=? WHERE id=?", (label, site_id))
        self.conn.commit()
        
    def get_labeled_sites(self):
        c = self.conn.cursor()
        c.execute("SELECT * FROM sites WHERE label IS NOT NULL")
        return [dict(row) for row in c.fetchall()]
