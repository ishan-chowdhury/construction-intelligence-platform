"use client";
import React, { useState, useEffect } from 'react';
import Map, { Source, Layer } from 'react-map-gl/maplibre';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import axios from 'axios';

const API_URL = "http://127.0.0.1:5002/api";

export default function Dashboard() {
  const [cities, setCities] = useState([]);
  const [selectedCity, setSelectedCity] = useState('');
  const [minConf, setMinConf] = useState(0.5);
  const [sites, setSites] = useState([]);
  const [selectedSite, setSelectedSite] = useState(null);
  
  const [viewState, setViewState] = useState({
    longitude: 72.50,
    latitude: 22.95,
    zoom: 10,
    pitch: 0,
    bearing: 0
  });

  useEffect(() => {
    axios.get(`${API_URL}/cities`).then(res => {
      setCities(res.data);
      if(res.data.find(c => c.id === 'ahmedabad')) setSelectedCity('ahmedabad');
    }).catch(err => console.error("API Error: ", err));
  }, []);

  const loadSites = () => {
    let url = `${API_URL}/sites?min_confidence=${minConf}`;
    if (selectedCity) url += `&city=${selectedCity}`;
    axios.get(url).then(res => {
      setSites(res.data);
    });
  };

  useEffect(() => {
    loadSites();
  }, [selectedCity, minConf]);

  // GeoJSON features for MapLibre
  const geojson = {
    type: 'FeatureCollection',
    features: sites.map(s => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [s.lon, s.lat] },
      properties: { ...s }
    }))
  };

  // Custom Map Style with Satellite + Labels
  const mapStyle = {
    version: 8,
    sources: {
      satellite: {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256
      },
      labels: {
        type: 'raster',
        tiles: ['https://a.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png'],
        tileSize: 256
      }
    },
    layers: [
      { id: 'satellite-layer', type: 'raster', source: 'satellite' },
      { id: 'labels-layer', type: 'raster', source: 'labels' }
    ]
  };

  const handleMapClick = (e) => {
    const feature = e.features && e.features[0];
    if (feature && feature.properties.id) {
      setSelectedSite(feature.properties);
      setViewState({ ...viewState, longitude: feature.properties.lon, latitude: feature.properties.lat, zoom: 14, transitionDuration: 1000 });
    }
  };

  const labelSite = (label) => {
    if(!selectedSite) return;
    axios.post(`${API_URL}/sites/${selectedSite.id}/label`, { label }).then(() => {
      alert("Intelligence Logged!");
      setSelectedSite(null);
      loadSites();
    });
  };

  return (
    <div className="layout">
      {/* Top Bar */}
      <div className="top-bar">
        <div className="brand">CONSTRUCTION INTELLIGENCE COMMAND CENTER [v3.0 NEXT.JS]</div>
        <div className="status-bar">
            <span>SYSTEM STATUS: <span className="status-ok">ONLINE</span></span>
            <span>ACTIVE SECTORS: <span>{cities.length}</span></span>
        </div>
      </div>

      <div className="main-container">
        {/* Left Panel */}
        <div className="sidebar left-panel">
            <h2>MISSION FILTERS</h2>
            <div className="filters">
                <label>SECTOR SELECTION</label>
                <select value={selectedCity} onChange={(e) => setSelectedCity(e.target.value)}>
                    <option value="">ALL MONITORED ZONES</option>
                    {cities.map(c => <option key={c.id} value={c.id}>[{c.id.toUpperCase()}] {c.name}</option>)}
                </select>

                <label>THREAT/ACTIVITY LEVEL: <span>{minConf.toFixed(1)}</span></label>
                <input type="range" min="0" max="1" step="0.1" value={minConf} onChange={(e) => setMinConf(parseFloat(e.target.value))} />
            </div>
            
            <div className="stats-panel">
                <div className="stat-box">
                    <h3 className="pulse-text">{sites.length}</h3>
                    <p>ACTIVE ZONES</p>
                </div>
                <div className="stat-box">
                    <h3>{sites.reduce((a, b) => a + b.area_ha, 0).toFixed(1)}</h3>
                    <p>TOTAL AREA (HA)</p>
                </div>
            </div>
            
            <h3 className="panel-subtitle">ANOMALY CLUSTERS</h3>
            <div className="site-list">
              {sites.map(s => (
                <div key={s.id} className="site-item" onClick={() => {
                  setSelectedSite(s);
                  setViewState({ ...viewState, longitude: s.lon, latitude: s.lat, zoom: 14, transitionDuration: 1000 });
                }}>
                  <span className="id">[Z-{s.id}]</span>
                  <span className="conf" style={{color: s.confidence >= 0.8 ? '#ff3333' : '#ffb020'}}>CF: {(s.confidence * 100).toFixed(0)}%</span>
                  <div className="location-subtext">{s.location_name || "Unmapped Zone (Geocoding Pending)"}</div>
                </div>
              ))}
            </div>
        </div>

        {/* Map */}
        <div className="map-container">
          <Map
            {...viewState}
            onMove={evt => setViewState(evt.viewState)}
            mapStyle={mapStyle}
            mapLib={maplibregl}
            interactiveLayerIds={['clusters']}
            onClick={handleMapClick}
          >
            <Source id="sites" type="geojson" data={geojson}>
              <Layer
                id="clusters"
                type="circle"
                paint={{
                  'circle-color': [
                    'step',
                    ['get', 'confidence'],
                    '#6b8e23', // < 0.4
                    0.4, '#ffb020', // 0.4 - 0.8
                    0.8, '#ff3333'  // >= 0.8
                  ],
                  'circle-radius': ['+', 4, ['*', ['get', 'area_ha'], 2]],
                  'circle-opacity': 0.8,
                  'circle-stroke-width': 1,
                  'circle-stroke-color': '#000'
                }}
              />
            </Source>
          </Map>

          {/* Right Panel: Target Intel */}
          {selectedSite && (
            <div className="site-detail-panel">
              <div className="panel-header">
                  <h3>TARGET INTELLIGENCE</h3>
                  <button className="close-btn" onClick={() => setSelectedSite(null)}>✖</button>
              </div>
              
              <div className="intel-body">
                  <div className="data-row"><span className="label">ZONE ID</span> <span className="value">Z-{selectedSite.id}</span></div>
                  <div className="data-row"><span className="label">LOCATION</span> <span className="value" style={{maxWidth: '180px', textAlign: 'right'}}>{selectedSite.location_name || "Unmapped Zone"}</span></div>
                  <div className="data-row"><span className="label">COORDINATES</span> <span className="value">{selectedSite.lat.toFixed(4)}, {selectedSite.lon.toFixed(4)}</span></div>
                  <div className="data-row"><span className="label">AREA</span> <span className="value">{selectedSite.area_ha.toFixed(2)} HA</span></div>
                  <div className="data-row"><span className="label">CONFIDENCE</span> <span className="value highlight">{(selectedSite.confidence * 100).toFixed(0)}%</span></div>
                  
                  <div className="notes-section">
                      <h4>ANALYST NOTES</h4>
                      <p className="auto-note">Detected via multispectral anomaly (NDVI: {selectedSite.ndvi_drop.toFixed(2)}, BSI: {selectedSite.bsi_rise.toFixed(2)}). Strong probability of surface excavation.</p>
                  </div>
              </div>
              
              <div className="actions">
                  <button className="btn btn-verify" onClick={() => labelSite('construction')}>[ VERIFY ACTIVITY ]</button>
                  <button className="btn btn-dismiss" onClick={() => labelSite('agriculture')}>[ DISMISS - AGRICULTURE ]</button>
                  <button className="btn btn-dismiss" onClick={() => labelSite('false_positive')}>[ DISMISS - FALSE POSITIVE ]</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
