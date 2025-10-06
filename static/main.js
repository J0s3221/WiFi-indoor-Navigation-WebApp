// main.js
let map, imageOverlay;
let imgMeta = null;
let pixelsPerMeter = 1;
let realWidthMeters = 50;
let routers = {}; // {ssid: {x,y, marker}}
let estimates = [];
const SQUARE_SIZE = 1.0;

async function init() {
  // get image metadata
  imgMeta = await fetch('/api/image-metadata').then(r => r.json());
  // default UI: set map once user clicks Set Map
  document.getElementById('setMap').onclick = setupMap;
  document.getElementById('inputRouters').onclick = promptRouters;
  document.getElementById('clearEst').onclick = clearEstimates;
}

function setupMap() {
  realWidthMeters = parseFloat(document.getElementById('realWidth').value) || 50;
  // compute pixelsPerMeter
  pixelsPerMeter = imgMeta.width_px / realWidthMeters;
  // compute real height in meters:
  const realHeightMeters = imgMeta.height_px / pixelsPerMeter;

  // initialize Leaflet map using CRS.Simple
  if (map) map.remove();
  map = L.map('map', {
    crs: L.CRS.Simple,
    minZoom: -5
  });

  // image bounds: [[0,0], [height_m, width_m]]
  const bounds = [[0,0], [realHeightMeters, realWidthMeters]];
  imageOverlay = L.imageOverlay(imgMeta.path, bounds).addTo(map);
  map.fitBounds(bounds);

  // draw grid (simple: draw rectangles of 1m)
  drawGrid(realWidthMeters, realHeightMeters);

  // click handler: convert latlng to meters (lat=Y, lng=X in our CRS)
  map.on('click', async function(e) {
    const x = e.latlng.lng; // meters from left
    const y_top = e.latlng.lat; // meters from top
    // convert to our coordinate system (y from bottom)
    const y = realHeightMeters - y_top;
    // open scan workflow
    await runScanAt(x, y);
  });

  // load state (routers/progress)
  loadState();
}

function drawGrid(realWidth, realHeight) {
  // remove existing grid layer if any
  if (window.gridLayer) {
    map.removeLayer(window.gridLayer);
  }
  const lines = [];
  for (let gx=0; gx<=Math.ceil(realWidth); gx++) {
    lines.push(L.polyline([[0,gx],[realHeight,gx]], {color:'#888', weight:1, interactive:false}));
  }
  for (let gy=0; gy<=Math.ceil(realHeight); gy++) {
    lines.push(L.polyline([[gy,0],[gy,realWidth]], {color:'#888', weight:1, interactive:false}));
  }
  window.gridLayer = L.layerGroup(lines).addTo(map);
}

async function promptRouters() {
  // ask for routers in the same format as before: SSID, x, y ; ...
  const txt = prompt("Enter routers as: SSID, x_m, y_m ; SSID2, x2, y2 ; ... (x from left, y from bottom in meters)");
  if (!txt) return;
  const parts = txt.split(';').map(s => s.trim()).filter(Boolean);
  const list = [];
  routers = {};
  for (const p of parts) {
    const cols = p.split(',').map(s => s.trim());
    if (cols.length >= 3) {
      const ssid = cols[0];
      const x = parseFloat(cols[1]);
      const y = parseFloat(cols[2]);
      routers[ssid] = {x,y, marker: null};
      list.push({ssid, x, y});
    }
  }
  // send routers to backend
  await fetch('/api/routers', {
    method:'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({routers: list})
  });
  drawRouters();
}

function drawRouters() {
  // remove old markers
  for (const ssid in routers) {
    if (routers[ssid].marker) {
      map.removeLayer(routers[ssid].marker);
      routers[ssid].marker = null;
    }
    const x = routers[ssid].x;
    const y_m_from_bottom = routers[ssid].y;
    // convert to Leaflet latlng coords (lat = top-based)
    const realHeightMeters = imgMeta.height_px / pixelsPerMeter;
    const y_top = realHeightMeters - y_m_from_bottom;
    const latlng = L.latLng(y_top, x);
    const m = L.circleMarker(latlng, {radius:6, color:'red', fillColor:'red'}).addTo(map);
    m.bindTooltip(ssid, {permanent:true, direction:'right'});
    routers[ssid].marker = m;
  }
}

async function runScanAt(x, y) {
  // get SSIDs to scan: use the configured routers' SSIDs
  const ssids = Object.keys(routers);
  if (ssids.length === 0) {
    alert("No routers configured. Click 'Input Routers' first.");
    return;
  }
  // call backend to scan
  const resp = await fetch('/api/scan', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ssids})
  });
  const rssi = await resp.json(); // {ssid: rssi}
  // show results and ask to save
  let summary = "Scan results:\n";
  for (const s of ssids) summary += `${s}: ${rssi[s]} dBm\n`;
  if (!confirm(summary + "\nSave this fingerprint at this position?")) return;
  // save
  const saveResp = await fetch('/api/save', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({x, y, rssi})
  });
  const saveJson = await saveResp.json();
  if (saveJson.ok) {
    alert('Saved!');
    if (saveJson.est) {
      drawEstimate(saveJson.est[0], saveJson.est[1]);
    }
  } else {
    alert('Save failed');
  }
}

function drawEstimate(x,y) {
  const realHeightMeters = imgMeta.height_px / pixelsPerMeter;
  const y_top = realHeightMeters - y;
  const latlng = L.latLng(y_top, x);
  const marker = L.circleMarker(latlng, {radius:6, color:'blue', fillColor:'blue'}).addTo(map);
  marker.bindTooltip(`Est: ${x.toFixed(2)}, ${y.toFixed(2)}`, {permanent:true, direction:'right'});
  estimates.push(marker);
}

function clearEstimates() {
  estimates.forEach(m => map.removeLayer(m));
  estimates = [];
}

async function loadState() {
  const st = await fetch('/api/state').then(r=>r.json());
  // restore routers if any
  for (const ssid in st.routers) {
    const [x,y] = st.routers[ssid];
    routers[ssid] = {x: parseFloat(x), y: parseFloat(y), marker: null};
  }
  if (map) drawRouters();
}

init();
