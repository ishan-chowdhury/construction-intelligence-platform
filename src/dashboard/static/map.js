let map;
let markersLayer;
let currentSiteId = null;

function initMap() {
    map = L.map('map', {
        zoomControl: false // Custom placement later if needed
    }).setView([22.95, 72.50], 11); // Center on Ahmedabad default
    
    // Tactical Dark Map
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: 'CARTO',
        subdomains: 'abcd',
        maxZoom: 20
    }).addTo(map);
    
    // High-res satellite
    const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Esri'
    });
    
    L.control.layers({
        "TACTICAL GRID": map.options.layers[0],
        "SATELLITE INTEL": satellite
    }, {}, {position: 'bottomleft'}).addTo(map);

    markersLayer = L.featureGroup().addTo(map);
}

async function loadCities() {
    try {
        const res = await fetch('/api/cities');
        const cities = await res.json();
        const select = document.getElementById('city-select');
        
        // Reset count
        let totalActive = 0;
        
        cities.forEach(city => {
            totalActive += city.site_count;
            const option = document.createElement('option');
            option.value = city.id;
            option.textContent = `[${city.id.toUpperCase()}] ${city.name} (${city.site_count} ANOMALIES)`;
            select.appendChild(option);
        });
        
        document.getElementById('top-sectors-count').textContent = cities.length;
        
        // Auto-select Ahmedabad if present
        if (cities.find(c => c.id === 'ahmedabad')) {
            select.value = 'ahmedabad';
        }
    } catch (e) {
        console.error("Failed to load cities", e);
    }
}

async function loadSites() {
    const cityId = document.getElementById('city-select').value;
    const minConf = document.getElementById('conf-slider').value;
    
    let url = `/api/sites?min_confidence=${minConf}`;
    if (cityId) url += `&city=${cityId}`;
    
    try {
        const res = await fetch(url);
        const sites = await res.json();
        
        document.getElementById('stat-sites').textContent = sites.length;
        const totalArea = sites.reduce((sum, s) => sum + s.area_ha, 0);
        document.getElementById('stat-area').textContent = totalArea.toFixed(1);
        
        markersLayer.clearLayers();
        const list = document.getElementById('site-list');
        list.innerHTML = '';
        
        if (sites.length === 0) {
            list.innerHTML = '<div style="color: gray; font-size: 0.8em; padding: 10px;">NO ACTIVE ANOMALIES FOUND IN THIS SECTOR WITH CURRENT FILTERS.</div>';
            return;
        }
        
        sites.forEach(site => {
            // Add to side list
            const div = document.createElement('div');
            div.className = 'site-item';
            div.innerHTML = `
                <span class="id">[Z-${site.id}]</span>
                <span class="conf">CF: ${(site.confidence * 100).toFixed(0)}%</span>
            `;
            div.onclick = () => showSiteDetail(site);
            list.appendChild(div);
            
            // Map marker
            let color = '#ffb020'; // Amber default
            if (site.confidence >= 0.8) color = '#ff3333'; // Red high priority
            if (site.confidence < 0.4) color = '#6b8e23'; // Olive low priority
            
            const marker = L.circleMarker([site.lat, site.lon], {
                radius: Math.max(4, Math.min(12, site.area_ha * 2)),
                fillColor: color,
                color: color,
                weight: 1,
                fillOpacity: 0.8,
                className: site.confidence > 0.7 ? 'marker-pulse' : ''
            });
            
            marker.on('click', () => showSiteDetail(site));
            markersLayer.addLayer(marker);
        });
        
        if (cityId) {
            map.fitBounds(markersLayer.getBounds(), {padding: [50, 50]});
        }
    } catch (e) {
        console.error("Failed to load sites", e);
    }
}

function showSiteDetail(site) {
    currentSiteId = site.id;
    document.getElementById('site-detail').style.display = 'block';
    document.getElementById('detail-id').textContent = `Z-${site.id}`;
    document.getElementById('detail-coords').textContent = `${site.lat.toFixed(4)}, ${site.lon.toFixed(4)}`;
    document.getElementById('detail-area').textContent = site.area_ha.toFixed(2);
    document.getElementById('detail-conf').textContent = `${(site.confidence * 100).toFixed(0)}%`;
    document.getElementById('detail-ndvi').textContent = site.ndvi_drop.toFixed(2);
    document.getElementById('detail-bsi').textContent = site.bsi_rise.toFixed(2);
    
    document.getElementById('label-status').style.display = 'none';
    
    map.flyTo([site.lat, site.lon], 16, {
        animate: true,
        duration: 1.0
    });
}

async function labelSite(label) {
    if (!currentSiteId) return;
    
    try {
        const res = await fetch(`/api/sites/${currentSiteId}/label`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ label })
        });
        
        if (res.ok) {
            document.getElementById('label-status').style.display = 'block';
            setTimeout(() => {
                document.getElementById('site-detail').style.display = 'none';
                loadSites(); // Refresh map to remove/update
            }, 1000);
        }
    } catch (e) {
        console.error("Failed to label site", e);
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    initMap();
    await loadCities();
    await loadSites();
    
    const confSlider = document.getElementById('conf-slider');
    const confVal = document.getElementById('conf-val');
    
    confSlider.oninput = () => { confVal.textContent = parseFloat(confSlider.value).toFixed(1); };
    
    document.getElementById('refresh-btn').onclick = loadSites;
    document.getElementById('city-select').onchange = loadSites;
    document.getElementById('close-detail').onclick = () => {
        document.getElementById('site-detail').style.display = 'none';
    };
});
