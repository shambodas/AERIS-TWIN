
(function () {
  'use strict';

  const fmt = (v, d = 1) => Number.isFinite(Number(v)) ? Number(v).toFixed(d) : '--';
  const $ = id => document.getElementById(id);

  // --- Map setup ---
  let currentLat = 28.6139;
  let currentLng = 77.2090;
  const CENTER = [currentLat, currentLng];

  const map = L.map('map', {
    center: CENTER,
    zoom: 6,
    zoomControl: true,
    attributionControl: false,
  });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  let tilesLoaded = false;
  map.on('tileerror', () => {
    if (!tilesLoaded) {
      tilesLoaded = true;
    }
  });

  // Flight path trail
  const pathPoints = [CENTER];
  const flightTrail = L.polyline(pathPoints, {
    color: '#3b8beb',
    weight: 2,
    opacity: 0.6,
  }).addTo(map);
  const routeLine = L.polyline([], { color: '#e8a83e', weight: 2, dashArray: '6 8', opacity: 0.8 }).addTo(map);
  const waypointMarkers = [];

  // UAV marker — top-down symmetrical drone silhouette (orientation-independent)
  const uavSvg = `<svg viewBox="0 0 40 40" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" aria-label="Top-down UAV drone">
    <g fill="none" stroke="#3b8beb" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="11" y1="11" x2="29" y2="29"/>
      <line x1="29" y1="11" x2="11" y2="29"/>
      <circle cx="9" cy="9" r="6" fill="rgba(59, 139, 235, 0.25)" stroke="#6eb2ff" stroke-width="1.6"/>
      <circle cx="31" cy="9" r="6" fill="rgba(59, 139, 235, 0.25)" stroke="#6eb2ff" stroke-width="1.6"/>
      <circle cx="9" cy="31" r="6" fill="rgba(59, 139, 235, 0.25)" stroke="#6eb2ff" stroke-width="1.6"/>
      <circle cx="31" cy="31" r="6" fill="rgba(59, 139, 235, 0.25)" stroke="#6eb2ff" stroke-width="1.6"/>
      <circle cx="20" cy="20" r="5.5" fill="#0d1b2a" stroke="#6eb2ff" stroke-width="2"/>
      <circle cx="20" cy="20" r="2.2" fill="#00d2ff"/>
    </g>
  </svg>`;

  const uavIcon = L.divIcon({
    className: 'uav-marker',
    html: uavSvg,
    iconSize: [36, 36],
    iconAnchor: [18, 18],
  });

  const uavMarker = L.marker(CENTER, { icon: uavIcon, zIndexOffset: 1000 }).addTo(map);
  map.on('click', event => {
    const currentPoints = (window.lastRouteWaypoints || []).map(p => ({ lat: p.lat, lng: p.lng }));
    if (currentPoints.length >= 4) return;
    currentPoints.push({
      lat: Number(event.latlng.lat.toFixed(4)),
      lng: Number(event.latlng.lng.toFixed(4))
    });
    pathPoints.length = 0;
    flightTrail.setLatLngs([]);
    command('set_waypoints', { waypoints: currentPoints }).then(result => {
      if (result && result.state) render(result.state);
    });
  });

  // --- API ---
  function command(cmd, params = {}) {
    return fetch('/api/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmd, parameters: params }),
    }).then(r => r.json()).then(result => {
      if (result && result.state) render(result.state);
      return result;
    }).catch(() => null);
  }

  // --- State ---
  let selectedFault = '';
  let flightStarted = false;
  let uavHeading = 45;
  let lastRouteKey = '';

  // Fault buttons
  document.querySelectorAll('[data-fault]').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('[data-fault]').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      selectedFault = btn.dataset.fault;
      $('faultName').textContent = btn.textContent;
      $('injectBtn').disabled = false;
    };
  });

  // --- Route Planning ---
  function buildMissionRoute() {
    const start = $('missionStart').value || 'Delhi';
    const stop = $('missionStop').value || 'Jaipur';
    const intermediate = $('missionIntermediate') ? $('missionIntermediate').value : '';
    const route = [start];
    if (intermediate && intermediate !== start && intermediate !== stop) route.push(intermediate);
    if (stop && stop !== start) route.push(stop);
    const unique = [];
    route.forEach(item => { if (item && !unique.includes(item)) unique.push(item); });
    return unique;
  }

  window.planMission = function () {
    const route = buildMissionRoute();
    if (route.length < 2) return;
    pathPoints.length = 0;
    flightTrail.setLatLngs([]);
    command('set_mission_route', { route }).then(result => {
      if (result && result.state) render(result.state);
    });
  };

  window.returnToBase = function () {
    command('return_to_base', {}).then(result => {
      if (result && result.state) render(result.state);
    });
  };

  function refreshMissionUI() {
    const s = window.latestState || {};
    const uav = s.uav || {};
    const route = (window.latestMission && window.latestMission.route) || [];
    const status = (window.latestMission && window.latestMission.status) || 'READY';
    const risk = (window.latestMission && window.latestMission.risk_level) || 'CLEAR';
    const riskMessage = (window.latestMission && window.latestMission.risk_message) || 'MISSION STABLE';
    const returnRecommended = Boolean(window.latestMission && window.latestMission.return_recommended);

    const routeLabel = $('missionRouteLabel');
    const statusLabel = $('missionStatusLabel');
    const nextLabel = $('missionNextLabel');
    const riskBox = $('missionRiskBox');
    const returnBtn = $('returnBtn');
    const missionEvents = $('missionEvents');

    if (routeLabel) routeLabel.textContent = route.length ? route.join(' -> ') : 'NONE (Select above)';
    if (statusLabel) statusLabel.textContent = status;

    // --- Route progress bar ---
    const fullRoute = window.lastRouteWaypoints || [];
    const progressWrap = $('routeProgressWrap');
    const progressBar = $('routeProgressBar');
    const progressPct = $('routeProgressPct');
    if (progressWrap && fullRoute.length >= 2) {
      progressWrap.style.display = 'block';
      const totalLegs = fullRoute.length - 1;
      const completedLegs = Math.max(0, fullRoute.length - route.length);
      let pct = 0;
      if (totalLegs > 0) {
        const distKm = (uav.distance_to_next_km != null) ? uav.distance_to_next_km : 0;
        let legLenKm = 0;
        if (route.length >= 2) {
          const fp = (s.flight_path && s.flight_path.route) || [];
          const idx = fullRoute.length - route.length;
          if (idx >= 0 && idx + 1 < fp.length) {
            const a = fp[idx], b = fp[idx + 1];
            if (a && b) {
              const dLat = (b.lat - a.lat) * 111.111;
              const dLng = (b.lng - a.lng) * 111.111 * Math.cos(a.lat * Math.PI / 180);
              legLenKm = Math.hypot(dLat, dLng);
            }
          }
        }
        const legProgress = legLenKm > 0.5 ? Math.min(1, Math.max(0, 1 - distKm / legLenKm)) : 0;
        pct = ((completedLegs + legProgress) / totalLegs) * 100;
      }
      if (progressBar) progressBar.style.width = Math.min(100, pct).toFixed(1) + '%';
      if (progressPct) progressPct.textContent = Math.min(100, Math.round(pct)) + '%';
    } else if (progressWrap) {
      progressWrap.style.display = 'none';
    }

    // --- Leg info ---
    if (nextLabel) {
      if (route.length > 1) {
        const distKm = (uav.distance_to_next_km != null) ? fmt(uav.distance_to_next_km, 1) + ' km' : '';
        nextLabel.innerHTML =
          '<div style="margin-bottom:2px">LEG: ' + route[0] + ' &rarr; ' + route[1] + '</div>' +
          '<div>NEXT: <b>' + route[1] + '</b>' + (distKm ? ' <i style="color:var(--text-muted)">(' + distKm + ')</i>' : '') + '</div>';
      } else if (route.length === 1) {
        nextLabel.innerHTML = '<div style="color:var(--green)">DESTINATION REACHED</div>';
      } else {
        nextLabel.textContent = 'NO TARGET -- Select route above';
      }
    }

    // --- Live UAV coordinates ---
    const coordsEl = $('uavCoordsLabel');
    if (coordsEl && uav.position) {
      const lat = Number(uav.position.lat).toFixed(5);
      const lng = Number(uav.position.lng).toFixed(5);
      coordsEl.textContent = 'LAT ' + lat + '  LNG ' + lng;
    }

    if (riskBox) {
      riskBox.textContent = riskMessage;
      riskBox.className = 'mission-status-risk ' + (risk === 'AT_RISK' || risk === 'RETURNING' ? 'critical' : '');
    }
    if (returnBtn) {
      const canReturn = ['FLYING', 'STOPPED', 'PAUSED'].includes(uav.status) && status !== 'RETURNING';
      returnBtn.disabled = !canReturn;
      returnBtn.style.opacity = canReturn ? '1' : '0.55';
    }
    if (missionEvents) {
      const events = (window.latestMission && window.latestMission.events) || [];
      missionEvents.innerHTML = events.slice(0, 5).map(event => {
        const kind = event.kind === 'warning' ? 'warning' : event.kind === 'mission' ? 'success' : '';
        return '<div class="mission-event ' + kind + '">' + (event.message || '') + '</div>';
      }).join('');
    }
  }

  // --- Commands ---
  window.startFlight = function () {
    if (flightStarted) {
      command('stop_uav');
    } else {
      command('start_uav', {
        altitude: Number($('altSlider').value),
        speed: Number($('speedSlider').value),
        heading: Number($('headingSlider').value),
      });
    }
  };
  window.toggleUavFlight = window.startFlight;

  window.setAltitude = function (value) {
    $('altValue').textContent = Math.round(value) + ' m';
    clearTimeout(window._altTimer);
    window._altTimer = setTimeout(() => command('set_altitude', { value: Number(value) }), 200);
  };

  window.setSpeed = function (value) {
    $('speedValue').textContent = Math.round(value) + ' m/s';
    clearTimeout(window._speedTimer);
    window._speedTimer = setTimeout(() => command('set_speed', { value: Number(value) }), 200);
  };

  window.setHeading = function (value) {
    $('headingValue').textContent = String(Math.round(value)).padStart(3, '0') + '°';
    clearTimeout(window._headTimer);
    window._headTimer = setTimeout(() => command('set_heading', { value: Number(value) }), 200);
  };

  window.injectFault = async function () {
    if (!selectedFault) return;
    const result = await command('inject_fault', { fault: selectedFault, severity: 0.85 });
    $('faultPopover').classList.remove('open');
    return result;
  };

  window.clearFault = async function () {
    const result = await command('clear_fault');
    selectedFault = '';
    document.querySelectorAll('[data-fault]').forEach(b => b.classList.remove('selected'));
    $('faultName').textContent = 'No fault selected';
    $('injectBtn').disabled = true;
    $('faultPopover').classList.remove('open');
    return result;
  };

  window.toggleFaultPanel = function () {
    $('faultPopover').classList.toggle('open');
  };

  window.clearPath = function () {
    pathPoints.length = 0;
    flightTrail.setLatLngs([]);
    lastRouteKey = '';
    command('clear_path').then(result => {
      if (result && result.state) render(result.state);
    });
  };

  window.toggleMap = function () {
    const expanded = document.querySelector('.gcs-layout').classList.toggle('map-expanded');
    $('mapExpandBtn').textContent = expanded ? 'COLLAPSE MAP' : 'EXPAND MAP';
    setTimeout(() => map.invalidateSize(), 50);
  };

  function refreshPath(s) {
    const path = (s && s.flight_path) || { waypoints: [], route: [] };
    const routeWaypoints = (path.route && path.route.length) ? path.route : (path.waypoints || []);
    window.lastRouteWaypoints = routeWaypoints;

    const routeKey = JSON.stringify(routeWaypoints);
    if (routeKey !== lastRouteKey) {
      lastRouteKey = routeKey;
      waypointMarkers.forEach(marker => map.removeLayer(marker));
      waypointMarkers.length = 0;
      routeWaypoints.forEach((point, index) => {
        const marker = L.circleMarker([point.lat, point.lng], {
          radius: 6,
          color: '#e8a83e',
          fillColor: '#e8a83e',
          fillOpacity: 1,
          weight: 2
        }).addTo(map);
        marker.bindTooltip(String(index + 1), {
          permanent: true,
          direction: 'top',
          className: 'waypoint-label'
        });
        waypointMarkers.push(marker);
      });
      const routeLatLngs = routeWaypoints.map(point => [point.lat, point.lng]);
      routeLine.setLatLngs(routeLatLngs);
    }
    const count = routeWaypoints.length;
    $('pathName').textContent = count > 0
      ? count + ' waypoint' + (count === 1 ? '' : 's') + (path.following ? ' / IN FLIGHT' : ' / PLANNED')
      : 'Select route or click map';
  }

  // --- Render ---
  function render(s) {
    if (!s) return;

    window.latestState = s;
    const uav = s.uav || {};
    const e = s.engine || {};
    const mission = s.mission || {};
    window.latestMission = {
      route: Array.isArray(mission.route) ? mission.route : [],
      status: mission.status || 'READY',
      risk_level: mission.risk_level || 'CLEAR',
      risk_message: mission.risk_message || 'MISSION STABLE',
      return_recommended: Boolean(mission.return_recommended),
      events: Array.isArray(s.events) ? s.events : [],
    };
    refreshMissionUI();

    // Connection
    const telemetryStatus = s.telemetry_status || 'READY';
    const frozen = uav.status === 'STOPPED' || telemetryStatus === 'STOPPED';
    $('statusText').textContent = frozen ? 'TELEMETRY FROZEN' : 'TELEMETRY ' + telemetryStatus;
    $('statusDot').className = 'status-dot ' + (frozen ? 'red' : telemetryStatus === 'LIVE' ? 'green' : telemetryStatus === 'PAUSED' ? 'amber' : telemetryStatus === 'READY' ? 'blue' : 'red');

    // Flight state
    const flying = uav.status === 'FLYING';
    if (flying) {
      flightStarted = true;
      $('startBtn').textContent = 'STOP UAV';
      $('startBtn').className = 'btn-danger start-flight-btn';
      $('flightState').textContent = 'FLIGHT ACTIVE';
      $('flightState').style.color = 'var(--green)';
    } else if (frozen) {
      flightStarted = false;
      $('startBtn').textContent = 'START UAV';
      $('startBtn').className = 'btn-primary start-flight-btn';
      $('flightState').textContent = 'FLIGHT STOPPED';
      $('flightState').style.color = 'var(--red)';
    } else {
      flightStarted = false;
      $('startBtn').textContent = 'START UAV';
      $('startBtn').className = 'btn-primary start-flight-btn';
      $('flightState').textContent = uav.status || 'READY';
      $('flightState').style.color = '';
    }

    // Update simulation variables from backend
    if (Number.isFinite(uav.heading)) uavHeading = uav.heading;
    if (uav.position) {
      const newLatLng = [uav.position.lat, uav.position.lng];
      uavMarker.setLatLng(newLatLng);
      if (flying) {
        pathPoints.push(newLatLng);
        if (pathPoints.length > 500) pathPoints.shift();
        flightTrail.setLatLngs(pathPoints);
      } else {
        pathPoints.length = 0;
        pathPoints.push(newLatLng);
        flightTrail.setLatLngs([]);
      }
    }
    const markerElement = uavMarker.getElement();
    if (markerElement) {
      markerElement.style.filter = frozen ? 'grayscale(0.25) brightness(0.8)' : 'drop-shadow(0 0 6px rgba(59, 139, 235, 0.6))';
    }
    refreshPath(s);

    // Flight readouts
    $('infoAlt').textContent = fmt(uav.altitude_m, 0) + ' m';
    $('infoSpeed').textContent = fmt(uav.speed_mps, 1) + ' m/s';
    $('infoHeading').textContent = String(Math.round(uavHeading)).padStart(3, '0') + '°';
    $('infoFlight').textContent = frozen ? 'STOPPED' : uav.status;
    $('infoFlight').style.color = frozen ? 'var(--red)' : flying ? 'var(--green)' : uav.status === 'PAUSED' ? 'var(--amber)' : '';
    $('altCurrent').textContent = fmt(uav.altitude_m, 0) + ' m';
    $('speedCurrent').textContent = fmt(uav.speed_mps, 1) + ' m/s';
    $('headingCurrent').textContent = String(Math.round(uavHeading)).padStart(3, '0') + '°';

    // Engine status
    const preflight = s.telemetry_status === 'READY' && uav.status === 'READY';
    const engineStatus = preflight ? 'STANDBY' : (e.status || 'MONITORING');
    $('infoEngine').textContent = engineStatus;
    $('infoEngine').style.color = engineStatus === 'HEALTHY' ? 'var(--green)' : engineStatus === 'WARNING' ? 'var(--amber)' : engineStatus === 'CRITICAL' ? 'var(--red)' : '';
    
    const thermalStatus = preflight ? 'STANDBY' : ((s.intelligence && s.intelligence.thermal_condition) || 'NORMAL');
    $('infoThermal').textContent = thermalStatus;
    $('infoThermal').style.color = thermalStatus === 'NORMAL' ? 'var(--green)' : thermalStatus === 'CRITICAL' ? 'var(--red)' : thermalStatus === 'STANDBY' ? '' : 'var(--amber)';

    const faultType = (s.digital_twin && (s.digital_twin.active_fault_name || s.digital_twin.fault) || '').toUpperCase();
    const faultClass = {
      COOLING_DEGRADATION: 'fault-overheat',
      OVERHEATING: 'fault-overheat',
      COOLING: 'fault-overheat',
      LOW_OIL_PRESSURE: 'fault-oil',
      OIL_PRESSURE: 'fault-oil',
      LUBRICATION: 'fault-oil',
      MISFIRE: 'fault-misfire',
      COMBUSTION_INSTABILITY: 'fault-vibration',
      EXCESSIVE_VIBRATION: 'fault-vibration',
      SENSOR_DRIFT: 'fault-sensor',
    }[faultType] || '';
    const meaningfulFault = Boolean(s.digital_twin && s.digital_twin.active_fault_name);
    if (markerElement) {
      markerElement.classList.toggle('fault-active', meaningfulFault);
      markerElement.classList.remove('fault-overheat', 'fault-oil', 'fault-vibration', 'fault-sensor', 'fault-misfire');
      if (meaningfulFault && faultClass) markerElement.classList.add(faultClass);
    }
    const alert = $('operatorAlert');
    const diagnosis = s.intelligence && s.intelligence.diagnosis;
    const intelligenceSeverity = s.digital_twin && s.digital_twin.ai_severity;
    const missionRisk = mission && mission.risk_level;
    const returnRecommended = Boolean(mission && mission.return_recommended);
    const meaningfulWarning = engineStatus === 'WARNING' || engineStatus === 'CRITICAL' || intelligenceSeverity === 'WARNING' || intelligenceSeverity === 'CRITICAL' || intelligenceSeverity === 'SEVERE';
    if (missionRisk === 'AT_RISK' || returnRecommended) {
      alert.textContent = 'MISSION AT RISK: RETURN TO BASE RECOMMENDED';
      alert.className = 'operator-alert visible critical';
    } else if (meaningfulWarning && diagnosis) {
      alert.textContent = (engineStatus === 'CRITICAL' ? 'ACTION REQUIRED: ' : 'ENGINE WARNING: ') + (diagnosis.recommended_action || diagnosis.interpretation || 'Inspect engine condition.');
      alert.className = 'operator-alert visible' + (engineStatus === 'CRITICAL' ? ' critical' : '');
    } else {
      alert.textContent = '';
      alert.className = 'operator-alert';
    }
  }

  // --- SSE ---
  fetch('/api/state').then(r => r.json()).then(render).catch(() => {});

  const stream = new EventSource('/api/stream');
  stream.onmessage = e => render(JSON.parse(e.data));
  stream.onerror = () => {
    $('statusText').textContent = 'RECONNECTING';
    $('statusDot').className = 'status-dot amber';
  };

})();
