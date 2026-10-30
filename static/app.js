// Tunable siren detector and synthetic signal settings.
const SIREN_CONFIG = Object.freeze({
  FFT_SIZE: 4096,                         // Finer frequency resolution for the siren band.
  SAMPLE_INTERVAL_MS: 50,                 // Analyze 20 audio frames per second.
  WINDOW_MS: 4000,                        // Rolling pattern analysis window.
  SEARCH_MIN_HZ: 500,                     // Lower edge of dominant-peak search band.
  SEARCH_MAX_HZ: 1800,                    // Upper edge of dominant-peak search band.
  MIN_PEAK_DB: -58,                       // Reject near-silent frames.
  MIN_PEAK_PROMINENCE: 3.0,               // Peak must exceed band mean by this ratio.
  MAX_SPECTRAL_FLATNESS: 0.48,             // Reject noise-like spectra above this value.
  MIN_VALID_FRAMES: 20,                   // Minimum usable frames in a pattern window.
  MIN_VALID_RATIO: 0.65,                  // Required share of usable frames.
  MAX_FRAME_GAP_MS: 180,                  // Reject patterns with large missing-frame gaps.
  MIN_SWEEP_HZ: 250,                      // Minimum wail/yelp peak-to-peak movement.
  MIN_TONE_GAP_HZ: 300,                   // Minimum separation for alternating hi-lo tones.
  MIN_REVERSAL_HZ: 140,                   // Minimum movement before accepting a sweep reversal.
  MAX_PEAK_INTERPOLATION_BINS: 0.5,       // Bound parabolic peak interpolation to adjacent bins.
  MIN_WAVE_CANDIDATE_REVERSALS: 2,        // Minimum reversals before a sweep candidate is considered.
  MIN_WAVE_REVERSALS: 3,                  // At least this many consistent sweep turns.
  MIN_HILO_CANDIDATE_TOGGLES: 2,          // Minimum switches before a hi-lo candidate is considered.
  MIN_HILO_TOGGLES: 4,                    // Minimum low/high switches for hi-lo detection.
  HILO_TONE_TOLERANCE_HZ: 120,             // Maximum spread around each hi-lo tone.
  HILO_MIN_SEGMENT_MS: 120,               // Ignore very short tone assignments.
  MIN_FULL_CYCLES: 2,                     // Normal confirmation requirement.
  MIN_PATTERN_DURATION_MS: 1500,          // Alternative confirmation duration for consistent patterns.
  WAIL_PERIOD_MIN_MS: 900,                // Full up/down cycle range for wail.
  WAIL_PERIOD_MAX_MS: 2800,
  YELP_PERIOD_MIN_MS: 250,                // Full up/down cycle range for yelp.
  YELP_PERIOD_MAX_MS: 850,
  HILO_PERIOD_MIN_MS: 300,                // Full low/high cycle range for hi-lo.
  HILO_PERIOD_MAX_MS: 1800,
  MAX_PERIOD_CV: 0.42,                    // Maximum relative variation in cycle timing.
  MIN_CONFIRM_CONFIDENCE: 0.68,           // Minimum pattern score to confirm.
  STATE_DROP_MS: 1000,                    // Confirmed state grace period after pattern loss.
  RETRIGGER_COOLDOWN_MS: 8000,            // Prevent repeated preemptions from one long siren.
  TEST_SIGNAL_DURATION_MS: 5000,          // Duration used by the self-check for each signal.
  TEST_OUTPUT_GAIN: 0.035,                // Quiet output level for generated test sounds.
  TEST_SIGNALS: {
    wail:  { expected: "wail",  baseHz: 1150, deviationHz: 430, periodSeconds: 1.8, waveform: "sine" },
    yelp:  { expected: "yelp",  baseHz: 1100, deviationHz: 400, periodSeconds: 0.58, waveform: "triangle" },
    hiLo:  { expected: "hi-lo", baseHz: 1100, deviationHz: 390, periodSeconds: 0.72, waveform: "square" },
    horn:  { expected: null, frequencyHz: 1000, waveform: "sine" },
    noise: { expected: null },
    chord: { expected: null, frequenciesHz: [720, 1220], waveform: "sine" }
  }
});

let allIncidents = [], currentSummary = null, activeFilter = "All";
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

async function api(url, options = {}) {
  const r = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!r.ok) throw new Error("Request failed: " + r.statusText);
  return r.json();
}

function statusClass(s) {
  return s.toLowerCase().replace(" ", "-");
}

function sevClass(s) {
  return s.toLowerCase();
}

function incidentById(id) {
  return allIncidents.find(i => i.id === id);
}

function markerMarkup(i, index) {
  let c = i.severity === "High" ? "" : i.severity === "Medium" ? "amber" : "green";
  return `<g class="map-marker ${c}" data-id="${i.id}" transform="translate(${i.x * 7.45},${i.y * 4.05})"><circle class="outer" r="17"/><circle class="inner" r="10"/><text y=".5">${index + 1}</text></g>`;
}

function renderMap() {
  const mapEl = $("#mapMarkers");
  if (!mapEl) return;
  mapEl.innerHTML = allIncidents.map(markerMarkup).join("");
  document.querySelectorAll(".map-marker").forEach(m => m.addEventListener("click", () => openIncident(m.dataset.id)));
}

function priorityHTML(i) {
  return `<div class="priority-item" data-id="${i.id}"><span class="severity-bar ${sevClass(i.severity)}"></span><div class="priority-copy"><b>${esc(i.title)}</b><small>${esc(i.area)} · ${esc(i.status)}</small></div><span class="priority-time">${esc(i.reported)}</span></div>`;
}

function issueHTML(i) {
  return `<div class="issue-row" data-id="${i.id}"><span class="severity-bar ${sevClass(i.severity)}"></span><div class="issue-main"><b>${esc(i.title)}</b><small>${esc(i.road)} · ${esc(i.reported)}</small></div><span class="type-tag">${esc(i.type)}</span><span class="status-tag ${statusClass(i.status)}">${esc(i.status)}</span></div>`;
}

function managementHTML(i) {
  return `<div class="management-row"><span class="severity-bar ${sevClass(i.severity)}"></span><div class="issue-main"><b>${esc(i.id)} · ${esc(i.title)}</b><small>${esc(i.road)} · ${esc(i.severity)} severity · Reported ${esc(i.reported)}</small></div><select aria-label="Update status for ${esc(i.id)}" data-id="${i.id}"><option ${i.status === "Reported" ? "selected" : ""}>Reported</option><option ${i.status === "In progress" ? "selected" : ""}>In progress</option><option ${i.status === "Resolved" ? "selected" : ""}>Resolved</option></select></div>`;
}

function attachIncidentClicks(root) {
  if (!root) return;
  root.querySelectorAll("[data-id]").forEach(el => {
    if (el.tagName !== "SELECT") el.addEventListener("click", () => openIncident(el.dataset.id));
  });
}

function renderAll() {
  renderMap();
  const active = allIncidents.filter(i => i.status !== "Resolved");
  if ($("#activeCount")) $("#activeCount").textContent = active.length;
  if ($("#highCount")) $("#highCount").textContent = active.filter(i => i.severity === "High").length;

  if ($("#priorityList")) {
    $("#priorityList").innerHTML = active.length
      ? active.slice(0, 3).map(priorityHTML).join("")
      : '<div class="empty-state"><b>All clear</b>No active priority incidents.</div>';
    attachIncidentClicks($("#priorityList"));
  }

  const filtered = allIncidents.filter(i => activeFilter === "All" || i.type === activeFilter);
  if ($("#filterCount")) $("#filterCount").textContent = `${filtered.length} record${filtered.length === 1 ? "" : "s"}`;

  if ($("#issueList")) {
    $("#issueList").innerHTML = filtered.length
      ? filtered.map(issueHTML).join("")
      : '<div class="empty-state"><b>No matching issues</b>Try another filter to see road activity.</div>';
    attachIncidentClicks($("#issueList"));
  }

  if ($("#managementList")) {
    $("#managementList").innerHTML = allIncidents.map(managementHTML).join("");
    $("#managementList").querySelectorAll("select").forEach(sel =>
      sel.addEventListener("change", () => updateStatus(sel.dataset.id, sel.value))
    );
  }

  if ($("#miniMap")) {
    $("#miniMap").innerHTML = filtered
      .map((i, n) => `<button class="mini-pin ${sevClass(i.severity)}" style="left:${i.x}%;top:${i.y}%" data-id="${i.id}" title="${esc(i.title)}">${n + 1}</button>`)
      .join("");
    attachIncidentClicks($("#miniMap"));
  }
}

function renderSummary(data) {
  if (!data) return;

  // 1. Corridor Breadcrumb & Map Caption
  const isNH206 = data.active_scenario === "nh206";
  if ($("#corridor-breadcrumb")) {
    $("#corridor-breadcrumb").textContent = isNH206
      ? "SMART MOBILITY / NH-206: CIT GUBBI – TUMAKURU CORRIDOR (S2)"
      : "CITY MOBILITY / BENGALURU METROPOLITAN CORRIDOR";
  }
  if ($("#svg-map-caption")) {
    $("#svg-map-caption").textContent = isNH206
      ? "NH-206 CORRIDOR · 4-JUNCTION DIGITAL TWIN"
      : "BENGALURU ROAD NETWORK · ILLUSTRATIVE SCHEMATIC";
  }

  // 2. S2 Live Impact Strip
  const m = data.impact_metrics || {};
  if ($("#kpi-golden-hour")) $("#kpi-golden-hour").textContent = `${m.golden_hour_sec_saved || 0}s`;
  if ($("#kpi-fuel-saved")) $("#kpi-fuel-saved").textContent = `${m.fuel_litres_saved || 0} L`;
  if ($("#kpi-green-waves")) $("#kpi-green-waves").textContent = m.active_green_waves || 0;
  if ($("#kpi-blackspots")) $("#kpi-blackspots").textContent = m.verified_blackspots || 0;
  if ($("#kpi-pwd-orders")) $("#kpi-pwd-orders").textContent = m.pwd_work_orders || 0;

  // 3. 4-Junction Grid Rendering
  if ($("#junctions-grid") && data.junctions) {
    $("#junctions-grid").innerHTML = data.junctions.map(j => {
      let sigClass = "red";
      if (j.signal_state === "PREEMPT_GREEN") sigClass = "preempt-green";
      else if (j.signal_state === "GREEN_WAVE_STANDBY") sigClass = "standby";
      else if (j.signal_state === "GREEN") sigClass = "green";

      return `
        <div class="junction-card glass" data-junction="${esc(j.id)}">
          <div class="junction-header">
            <div class="j-info"><b class="j-id">${esc(j.id)}</b> · <span class="j-name">${esc(j.name)}</span></div>
            <span class="signal-badge ${sigClass}">${esc(j.signal_state)}</span>
          </div>
          <div class="junction-queues">
            <span title="Queued Cars">🚗 <b class="q-cars">${j.cars}</b></span>
            <span title="Queued Trucks">🚚 <b class="q-trucks">${j.trucks}</b></span>
            <span title="Queued Bikes">🛵 <b class="q-bikes">${j.bikes}</b></span>
          </div>
          <div class="junction-flush"><small>GREENSHIELDS QUEUE-FLUSH</small> T_flush: <strong class="q-flush">${j.t_flush_sec}s</strong></div>
        </div>
      `;
    }).join("");
  }

  // 4. SVG Green Wave Corridor Pulse
  const hasPreempt = (data.junctions || []).some(j => j.signal_state === "PREEMPT_GREEN") || ((m.active_green_waves || 0) > 0);
  const gwEl = $("#svg-green-wave-corridor");
  if (gwEl) gwEl.classList.toggle("active", hasPreempt);

  // 5. Analytics Congestion Hotspots Dynamic Swap
  if ($("#hotspots-container")) {
    if (isNH206 && data.junctions) {
      $("#hotspots-container").innerHTML = data.junctions.map(j => {
        const load = Math.min(96, Math.max(28, Math.round(((j.cars * 1.0 + j.trucks * 2.5 + j.bikes * 0.4) / 45) * 100)));
        return `<div><span>${esc(j.name.split('(')[0].trim())}</span><b>${load}%</b><i><em style="width:${load}%"></em></i></div>`;
      }).join("");
    } else {
      $("#hotspots-container").innerHTML = `
        <div><span>Outer Ring Road</span><b>82%</b><i><em style="width:82%"></em></i></div>
        <div><span>Old Airport Road</span><b>67%</b><i><em style="width:67%"></em></i></div>
        <div><span>100 Feet Road</span><b>54%</b><i><em style="width:54%"></em></i></div>
        <div><span>MG Road</span><b>29%</b><i><em style="width:29%"></em></i></div>
      `;
    }
  }

  // Sync corridor dropdown in Module B if present
  if ($("#shock-corridor")) {
    const desired = isNH206 ? "nh206" : "bengaluru";
    if ($("#shock-corridor").querySelector(`option[value="${desired}"]`)) {
      $("#shock-corridor").value = desired;
    }
  }
}

async function load() {
  try {
    const [incRes, sumRes] = await Promise.all([
      api("/api/incidents"),
      api("/api/summary")
    ]);
    allIncidents = incRes.incidents || [];
    currentSummary = sumRes;
    renderAll();
    renderSummary(sumRes);
  } catch (e) {
    console.error("Load error:", e);
    toast("Could not load demo data. Is the Flask server running?");
  }
}

async function updateStatus(id, status) {
  try {
    await api(`/api/incidents/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status })
    });
    await load();
    toast(`${id} updated to ${status}`);
  } catch (e) {
    toast("Could not update incident");
  }
}

function openIncident(id) {
  const i = incidentById(id);
  if (!i) return;
  $("#modalContent").innerHTML = `
    <div class="section-kicker">${esc(i.id)} · ${esc(i.type.toUpperCase())}</div>
    <h2>${esc(i.title)}</h2>
    <p>${esc(i.detail)}</p>
    <div class="modal-meta">
      <div><small>LOCATION</small><b>${esc(i.road)}</b></div>
      <div><small>SEVERITY</small><b class="${i.severity === "High" ? "amber-text" : ""}">${esc(i.severity)}</b></div>
      <div><small>REPORTED</small><b>${esc(i.reported)}</b></div>
      <div><small>CURRENT STATUS</small><b>${esc(i.status)}</b></div>
    </div>
    <div class="detour-box"><b>↗ SUGGESTED DETOUR</b><p>${esc(i.detour)}</p></div>
    <div class="modal-actions">
      <button class="primary-btn" id="modalManage">Manage status</button>
      <button class="secondary-btn" id="modalClose2">Close</button>
    </div>
  `;
  $("#incidentModal").classList.add("show");
  $("#modalManage").onclick = () => {
    closeModal();
    switchView("manage");
  };
  $("#modalClose2").onclick = closeModal;
}

function closeModal() {
  $("#incidentModal").classList.remove("show");
}

function toast(msg) {
  const t = $("#toast");
  if (!t) return;
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2600);
}

function switchView(id) {
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === id));
  document.querySelectorAll("[data-view]").forEach(b => b.classList.toggle("active", b.dataset.view === id));
  const titles = {
    overview: "Good morning, operator",
    traffic: "Traffic & incidents",
    manage: "Road management",
    analytics: "Mobility analytics",
    "s2-command": "S2 Edge AI & Preemption Core"
  };
  $("#pageTitle").innerHTML = `${titles[id] || "DOME Flow"} <span>✦</span>`;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ==========================================
// 2. TOPBAR CONTROLS & S2 MODAL WIRING
// ==========================================

async function switchCorridorScenario() {
  try {
    const res = await api("/api/corridor/switch", { method: "POST" });
    if (res.ok) {
      await load();
      const name = res.active_scenario === "nh206" ? "NH-206 (CIT Gubbi – Tumakuru)" : "Bengaluru Metropolitan";
      toast(`Active Corridor: ${name}`);
    }
  } catch (err) {
    console.error("Switch corridor error:", err);
    toast("Could not switch corridor scenario");
  }
}

async function triggerSimTick() {
  try {
    const res = await api("/api/simulate/tick", { method: "POST" });
    if (res.ok) {
      await load();
      toast("⚡ Highway traffic queues & flow updated");
      const currentJunction = $("#preempt-junction")?.value;
      if (currentJunction && res.junctions) {
        const j = res.junctions.find(x => x.id === currentJunction);
        if (j) {
          if ($("#preempt-cars")) $("#preempt-cars").value = j.cars;
          if ($("#preempt-trucks")) $("#preempt-trucks").value = j.trucks;
          if ($("#preempt-bikes")) $("#preempt-bikes").value = j.bikes;
          updateLiveMath();
        }
      }
    }
  } catch (err) {
    console.error("Sim tick error:", err);
    toast("Could not trigger simulation tick");
  }
}

function initTopbarAndModals() {
  if ($("#btn-switch-corridor")) $("#btn-switch-corridor").onclick = switchCorridorScenario;
  if ($("#btn-sim-tick")) $("#btn-sim-tick").onclick = triggerSimTick;

  // S2 Info Modal
  if ($("#btn-s2-info")) {
    $("#btn-s2-info").onclick = () => {
      const modal = $("#modal-s2-info");
      if (modal) modal.classList.add("show");
    };
  }
  if ($("#close-s2-info-modal")) {
    $("#close-s2-info-modal").onclick = () => {
      const modal = $("#modal-s2-info");
      if (modal) modal.classList.remove("show");
    };
  }
  if ($("#modal-s2-info")) {
    $("#modal-s2-info").addEventListener("click", e => {
      if (e.target.id === "modal-s2-info") $("#modal-s2-info").classList.remove("show");
    });
  }
}

// ==========================================
// 3. MODULE A: GREENSHIELDS MATH & ACOUSTIC FFT
// ==========================================

function updateLiveMath() {
  const cars = parseFloat($("#preempt-cars")?.value || 0);
  const trucks = parseFloat($("#preempt-trucks")?.value || 0);
  const bikes = parseFloat($("#preempt-bikes")?.value || 0);
  const dist = parseFloat($("#preempt-dist")?.value || 0);
  const speed = parseFloat($("#preempt-speed")?.value || 0);

  const t_flush = (3.5 + (cars * 6.5 / 6.5) + (trucks * 13.5 / 4.0) + (bikes * 3.2 / 8.0)).toFixed(1);
  const speedMps = Math.max(speed / 3.6, 1);
  const eta = (dist / speedMps).toFixed(1);

  if ($("#calc-tflush")) $("#calc-tflush").textContent = `${t_flush}s`;
  if ($("#calc-eta")) $("#calc-eta").textContent = `${eta}s`;

  const marginEl = $("#calc-margin");
  if (marginEl) {
    const diff = parseFloat(eta) - parseFloat(t_flush);
    if (diff >= 0) {
      marginEl.className = "margin-status safe";
      marginEl.textContent = `Margin: +${diff.toFixed(1)}s (Clear Before Arrival)`;
    } else {
      marginEl.className = "margin-status danger";
      marginEl.textContent = `Margin: ${diff.toFixed(1)}s (Immediate Preempt Critical)`;
    }
  }
}

async function triggerPreemptionOverride(sirenEvent) {
  const junction_id = $("#preempt-junction")?.value || "J1";
  const cars = parseInt($("#preempt-cars")?.value || 14);
  const trucks = parseInt($("#preempt-trucks")?.value || 3);
  const bikes = parseInt($("#preempt-bikes")?.value || 22);
  const ambulance_dist_m = parseFloat($("#preempt-dist")?.value || 450);
  const ambulance_speed_kmh = parseFloat($("#preempt-speed")?.value || 65);
  const event = sirenEvent || { confirmed: false, label: "none", confidence: 0 };
  const siren_confidence = Math.max(0, Math.min(1, Number(event.confidence) || 0));

  try {
    const res = await api("/api/preempt/trigger", {
      method: "POST",
      body: JSON.stringify({
        junction_id,
        cars,
        trucks,
        bikes,
        ambulance_dist_m,
        ambulance_speed_kmh,
        siren_confidence,
        siren_confirmed: !!event.confirmed,
        siren_label: event.label || "none"
      })
    });

    if (res.ok) {
      await load();
      const gwEl = $("#svg-green-wave-corridor");
      if (gwEl) gwEl.classList.add("active");
      toast(`🚑 Emergency Green Wave Active! Queue Flush T=${res.t_flush_sec}s`);
    }
  } catch (err) {
    console.error("Preempt error:", err);
    toast("Could not trigger emergency preemption");
  }
}

// Browser-side siren detector. The analyser and all audio stay in this page.
let audioCtx = null;
let analyser = null;
let micStream = null;
let micSource = null;
let isMicActive = false;
let micPermissionFailed = false;
let sirenAudioMode = "idle";
let sirenTestMode = false;
let activeSignalNodes = [];
let activeSignalStopTimer = null;
let lastSirenSampleAt = 0;
let lastSirenTriggerTime = -Infinity;
let sirenConfidence = 0;
let sirenLabel = "none";
let sirenHistory = [];
let sirenFloatData = null;
let sirenByteData = null;

const sirenDetector = {
  state: "IDLE",
  label: "none",
  confidence: 0,
  lastPatternAt: 0,
  candidateLabel: "none",
  candidateSince: 0
};

function ensureSirenAnalyser() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (!analyser) {
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = SIREN_CONFIG.FFT_SIZE;
    analyser.smoothingTimeConstant = 0;
    sirenFloatData = new Float32Array(analyser.frequencyBinCount);
    sirenByteData = new Uint8Array(analyser.frequencyBinCount);
    const silentSink = audioCtx.createGain();
    silentSink.gain.value = 0;
    analyser.connect(silentSink);
    silentSink.connect(audioCtx.destination);
  }
  return analyser;
}

function resetSirenDetector() {
  sirenHistory = [];
  sirenDetector.state = "IDLE";
  sirenDetector.label = "none";
  sirenDetector.confidence = 0;
  sirenDetector.lastPatternAt = 0;
  sirenDetector.candidateLabel = "none";
  sirenDetector.candidateSince = 0;
  sirenConfidence = 0;
  sirenLabel = "none";
  renderSirenReadout(null);
}

function renderSirenReadout(frame) {
  const confidence = Math.max(0, Math.min(1, sirenDetector.confidence || 0));
  sirenConfidence = confidence;
  sirenLabel = sirenDetector.label || "none";
  if ($("#siren-confidence")) $("#siren-confidence").textContent = Math.round(confidence * 100) + "%";
  if ($("#siren-frequency")) $("#siren-frequency").textContent = frame && frame.valid ? Math.round(frame.frequencyHz) + " Hz" : "—";
  if ($("#siren-prominence")) $("#siren-prominence").textContent = frame ? frame.prominence.toFixed(1) + "×" : "—";
  if ($("#siren-flatness")) $("#siren-flatness").textContent = frame ? frame.flatness.toFixed(2) : "—";
  if ($("#siren-detector-state")) $("#siren-detector-state").textContent = sirenDetector.state;
  if ($("#siren-detector-label")) $("#siren-detector-label").textContent = sirenLabel;
  if ($("#siren-detector-confidence")) $("#siren-detector-confidence").textContent = confidence.toFixed(2);
  const badge = $("#siren-status-badge");
  if (badge) {
    badge.textContent = sirenAudioMode === "idle" ? "Acoustic Standby" :
      sirenAudioMode === "mic" ? (sirenDetector.state === "CONFIRMED" ? "Siren Confirmed" : "Listening (Live Mic)") :
      sirenAudioMode === "synthetic" ? (sirenDetector.state === "CONFIRMED" ? "Synthetic Siren Confirmed" : "Synthetic Siren Active") :
      "Test Signal: " + (sirenLabel === "none" ? "Analyzing" : sirenLabel);
    badge.className = "status-tag " + (sirenDetector.state === "CONFIRMED" ? "resolved" : "in-progress");
  }
}

function extractSirenFeatures(now) {
  if (!analyser || !audioCtx) return { time: now, valid: false, frequencyHz: 0, prominence: 0, flatness: 1 };
  analyser.getFloatFrequencyData(sirenFloatData);
  const binHz = audioCtx.sampleRate / analyser.fftSize;
  const first = Math.max(1, Math.ceil(SIREN_CONFIG.SEARCH_MIN_HZ / binHz));
  const last = Math.min(sirenFloatData.length - 2, Math.floor(SIREN_CONFIG.SEARCH_MAX_HZ / binHz));
  let peakIndex = first;
  let peakDb = -Infinity;
  let sumMagnitude = 0;
  let sumLogMagnitude = 0;
  let bandCount = 0;

  for (let i = first; i <= last; i++) {
    const db = sirenFloatData[i];
    const magnitude = Number.isFinite(db) ? Math.pow(10, db / 20) : 0;
    sumMagnitude += magnitude;
    sumLogMagnitude += Math.log(Math.max(magnitude, 1e-12));
    bandCount++;
    if (db > peakDb) {
      peakDb = db;
      peakIndex = i;
    }
  }

  const meanMagnitude = bandCount ? sumMagnitude / bandCount : 0;
  const geometricMean = bandCount ? Math.exp(sumLogMagnitude / bandCount) : 0;
  const flatness = meanMagnitude > 0 ? geometricMean / meanMagnitude : 1;
  const prominence = meanMagnitude > 0 ? Math.pow(10, peakDb / 20) / meanMagnitude : 0;

  const y0 = sirenFloatData[peakIndex - 1];
  const y1 = sirenFloatData[peakIndex];
  const y2 = sirenFloatData[peakIndex + 1];
  const denominator = 2 * (y0 - 2 * y1 + y2);
  let offset = Number.isFinite(denominator) && denominator !== 0 ? (y0 - y2) / denominator : 0;
  offset = Math.max(-SIREN_CONFIG.MAX_PEAK_INTERPOLATION_BINS,
    Math.min(SIREN_CONFIG.MAX_PEAK_INTERPOLATION_BINS, offset));
  const frequencyHz = (peakIndex + offset) * binHz;
  const valid = peakDb >= SIREN_CONFIG.MIN_PEAK_DB &&
    prominence >= SIREN_CONFIG.MIN_PEAK_PROMINENCE &&
    flatness <= SIREN_CONFIG.MAX_SPECTRAL_FLATNESS;

  return { time: now, valid, frequencyHz, prominence, flatness, peakDb };
}

function average(values) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

function median(values) {
  if (!values.length) return 0;
  const sorted = values.slice().sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function intervalStats(times) {
  const intervals = [];
  for (let i = 1; i < times.length; i++) intervals.push(times[i] - times[i - 1]);
  const mean = average(intervals);
  const deviation = Math.sqrt(average(intervals.map(value => Math.pow(value - mean, 2))));
  return { mean, cv: mean > 0 ? deviation / mean : Infinity };
}

function analyzeHiLo(points, common) {
  if (points.length < SIREN_CONFIG.MIN_VALID_FRAMES) return null;
  const split = median(points.map(point => point.frequencyHz));
  const lower = points.filter(point => point.frequencyHz <= split).map(point => point.frequencyHz);
  const upper = points.filter(point => point.frequencyHz > split).map(point => point.frequencyHz);
  if (!lower.length || !upper.length) return null;
  const lowHz = median(lower);
  const highHz = median(upper);
  const gapHz = highHz - lowHz;
  if (gapHz < SIREN_CONFIG.MIN_TONE_GAP_HZ) return null;

  const states = points.map(point => Math.abs(point.frequencyHz - lowHz) <= Math.abs(point.frequencyHz - highHz) ? "L" : "H");
  const runs = [];
  let runStart = points[0].time;
  let runState = states[0];
  for (let i = 1; i < states.length; i++) {
    if (states[i] !== runState) {
      if (points[i].time - runStart >= SIREN_CONFIG.HILO_MIN_SEGMENT_MS) runs.push({ state: runState, time: runStart });
      runStart = points[i].time;
      runState = states[i];
    }
  }
  if (points[points.length - 1].time - runStart >= SIREN_CONFIG.HILO_MIN_SEGMENT_MS) runs.push({ state: runState, time: runStart });
  const toggles = Math.max(0, runs.length - 1);
  if (toggles < SIREN_CONFIG.MIN_HILO_CANDIDATE_TOGGLES) return null;

  const lowSpread = Math.max(...lower) - Math.min(...lower);
  const highSpread = Math.max(...upper) - Math.min(...upper);
  if (lowSpread > SIREN_CONFIG.HILO_TONE_TOLERANCE_HZ || highSpread > SIREN_CONFIG.HILO_TONE_TOLERANCE_HZ) return null;
  const timing = intervalStats(runs.slice(1).map(run => run.time));
  const periodMs = timing.mean * 2;
  if (periodMs < SIREN_CONFIG.HILO_PERIOD_MIN_MS || periodMs > SIREN_CONFIG.HILO_PERIOD_MAX_MS ||
      timing.cv > SIREN_CONFIG.MAX_PERIOD_CV) return null;

  const durationMs = points[points.length - 1].time - points[0].time;
  const cycles = toggles / 2;
  const ready = cycles >= SIREN_CONFIG.MIN_FULL_CYCLES ||
    (durationMs >= SIREN_CONFIG.MIN_PATTERN_DURATION_MS && toggles >= SIREN_CONFIG.MIN_HILO_TOGGLES - 1);
  const gapScore = Math.min(1, gapHz / (SIREN_CONFIG.MIN_TONE_GAP_HZ * 2));
  const stabilityScore = Math.max(0, 1 - Math.max(lowSpread, highSpread) / SIREN_CONFIG.HILO_TONE_TOLERANCE_HZ);
  const timingScore = Math.max(0, 1 - timing.cv / SIREN_CONFIG.MAX_PERIOD_CV);
  return {
    label: "hi-lo", confidence: Math.min(1, 0.3 * gapScore + 0.3 * stabilityScore + 0.25 * timingScore + 0.15 * common.quality),
    ready, durationMs, cycles, toggles
  };
}

function analyzeSweep(points, common) {
  if (points.length < SIREN_CONFIG.MIN_VALID_FRAMES) return null;
  const frequencies = points.map(point => point.frequencyHz);
  const rangeHz = Math.max(...frequencies) - Math.min(...frequencies);
  if (rangeHz < SIREN_CONFIG.MIN_SWEEP_HZ) return null;

  let direction = 0;
  let extreme = points[0];
  const turns = [];
  for (let i = 1; i < points.length; i++) {
    const point = points[i];
    if (direction === 0) {
      const delta = point.frequencyHz - extreme.frequencyHz;
      if (Math.abs(delta) >= SIREN_CONFIG.MIN_REVERSAL_HZ) {
        direction = Math.sign(delta);
        extreme = point;
      }
    } else if (direction > 0) {
      if (point.frequencyHz >= extreme.frequencyHz) extreme = point;
      else if (extreme.frequencyHz - point.frequencyHz >= SIREN_CONFIG.MIN_REVERSAL_HZ) {
        turns.push(extreme);
        direction = -1;
        extreme = point;
      }
    } else {
      if (point.frequencyHz <= extreme.frequencyHz) extreme = point;
      else if (point.frequencyHz - extreme.frequencyHz >= SIREN_CONFIG.MIN_REVERSAL_HZ) {
        turns.push(extreme);
        direction = 1;
        extreme = point;
      }
    }
  }
  if (turns.length < 2) return null;

  const timing = intervalStats(turns.map(turn => turn.time));
  const periodMs = timing.mean * 2;
  const reversals = Math.max(0, turns.length - 1);
  if (reversals < SIREN_CONFIG.MIN_WAVE_CANDIDATE_REVERSALS ||
      timing.cv > SIREN_CONFIG.MAX_PERIOD_CV) return null;
  let label = "none";
  if (periodMs >= SIREN_CONFIG.YELP_PERIOD_MIN_MS && periodMs <= SIREN_CONFIG.YELP_PERIOD_MAX_MS) label = "yelp";
  else if (periodMs >= SIREN_CONFIG.WAIL_PERIOD_MIN_MS && periodMs <= SIREN_CONFIG.WAIL_PERIOD_MAX_MS) label = "wail";
  if (label === "none") return null;

  const durationMs = points[points.length - 1].time - points[0].time;
  const cycles = reversals / 2;
  const ready = cycles >= SIREN_CONFIG.MIN_FULL_CYCLES ||
    (durationMs >= SIREN_CONFIG.MIN_PATTERN_DURATION_MS && reversals >= SIREN_CONFIG.MIN_WAVE_REVERSALS);
  const rangeScore = Math.min(1, rangeHz / (SIREN_CONFIG.MIN_SWEEP_HZ * 2));
  const timingScore = Math.max(0, 1 - timing.cv / SIREN_CONFIG.MAX_PERIOD_CV);
  return {
    label, confidence: Math.min(1, 0.35 * rangeScore + 0.35 * timingScore + 0.3 * common.quality),
    ready, durationMs, cycles, reversals, periodMs
  };
}

function classifySirenWindow(now) {
  const frames = sirenHistory.filter(frame => now - frame.time <= SIREN_CONFIG.WINDOW_MS);
  const points = frames.filter(frame => frame.valid);
  const validRatio = frames.length ? points.length / frames.length : 0;
  if (points.length < SIREN_CONFIG.MIN_VALID_FRAMES || validRatio < SIREN_CONFIG.MIN_VALID_RATIO) return null;
  let maxGap = 0;
  for (let i = 1; i < points.length; i++) maxGap = Math.max(maxGap, points[i].time - points[i - 1].time);
  if (maxGap > SIREN_CONFIG.MAX_FRAME_GAP_MS) return null;

  const durationMs = points[points.length - 1].time - points[0].time;
  const meanProminence = average(points.map(point => point.prominence));
  const meanFlatness = average(points.map(point => point.flatness));
  const quality = Math.min(1, validRatio) *
    Math.max(0, Math.min(1, meanProminence / (SIREN_CONFIG.MIN_PEAK_PROMINENCE * 2))) *
    Math.max(0, 1 - meanFlatness / SIREN_CONFIG.MAX_SPECTRAL_FLATNESS);
  const common = { validRatio, quality };

  // Test hi-lo first so regular square-wave alternation is not mistaken for a sweep.
  const hiLo = analyzeHiLo(points, common);
  if (hiLo) return Object.assign(hiLo, { durationMs: Math.max(durationMs, hiLo.durationMs) });
  return analyzeSweep(points, common);
}

function setSirenState(pattern, now) {
  const previousState = sirenDetector.state;
  const previousLabel = sirenDetector.label;
  if (pattern) {
    sirenDetector.lastPatternAt = now;
    if (sirenDetector.state === "CONFIRMED" && sirenDetector.label !== pattern.label) {
      sirenDetector.state = "CANDIDATE";
      sirenDetector.candidateLabel = pattern.label;
      sirenDetector.candidateSince = now;
    } else if (sirenDetector.state === "IDLE" || sirenDetector.candidateLabel !== pattern.label) {
      sirenDetector.state = "CANDIDATE";
      sirenDetector.candidateLabel = pattern.label;
      sirenDetector.candidateSince = now;
    }
    sirenDetector.confidence = pattern.confidence;
    if (pattern.ready && pattern.confidence >= SIREN_CONFIG.MIN_CONFIRM_CONFIDENCE) {
      sirenDetector.state = "CONFIRMED";
      sirenDetector.label = pattern.label;
      if (previousState !== "CONFIRMED" || previousLabel !== pattern.label) {
        const triggerAllowed = !sirenTestMode && (sirenAudioMode === "mic" || sirenAudioMode === "synthetic") &&
          now - lastSirenTriggerTime >= SIREN_CONFIG.RETRIGGER_COOLDOWN_MS;
        if (triggerAllowed) {
          lastSirenTriggerTime = now;
          toast("Siren pattern confirmed (" + pattern.label + ") — starting simulated preemption.");
          triggerPreemptionOverride({ confirmed: true, label: pattern.label, confidence: pattern.confidence });
        }
      }
    }
  } else if (sirenDetector.state !== "IDLE" && now - sirenDetector.lastPatternAt > SIREN_CONFIG.STATE_DROP_MS) {
    sirenDetector.state = "IDLE";
    sirenDetector.label = "none";
    sirenDetector.confidence = 0;
    sirenDetector.candidateLabel = "none";
  } else if (sirenDetector.state === "CONFIRMED") {
    sirenDetector.confidence *= 0.96;
  }
  renderSirenReadout(null);
}

function processSirenFrame(now) {
  const frame = extractSirenFeatures(now);
  sirenHistory.push(frame);
  sirenHistory = sirenHistory.filter(item => now - item.time <= SIREN_CONFIG.WINDOW_MS);
  setSirenState(classifySirenWindow(now), now);
  renderSirenReadout(frame);
  return frame;
}

function initFFTCanvas() {
  const canvas = $("#siren-fft-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;

  function draw() {
    requestAnimationFrame(draw);
    const now = performance.now();
    if (isMicActive && analyser && now - lastSirenSampleAt >= SIREN_CONFIG.SAMPLE_INTERVAL_MS) {
      lastSirenSampleAt = now;
      processSirenFrame(now);
    }

    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = "rgba(56, 189, 248, 0.08)";
    for (let x = 0; x < width; x += 35) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
    }
    if (analyser && isMicActive) {
      analyser.getByteFrequencyData(sirenByteData);
      const binHz = audioCtx.sampleRate / analyser.fftSize;
      const first = Math.ceil(SIREN_CONFIG.SEARCH_MIN_HZ / binHz);
      const last = Math.min(sirenByteData.length - 1, Math.floor(SIREN_CONFIG.SEARCH_MAX_HZ / binHz));
      const barWidth = width / Math.max(1, last - first + 1);
      for (let i = first; i <= last; i++) {
        const barHeight = (sirenByteData[i] / 255) * (height - 12);
        ctx.fillStyle = "#10b981";
        ctx.fillRect((i - first) * barWidth, height - barHeight, Math.max(1, barWidth - 1), barHeight);
      }
    }
    ctx.fillStyle = "rgba(16, 185, 129, 0.75)";
    ctx.font = "8px monospace";
    ctx.fillText("SEARCH 500–1800 Hz", 6, 11);
  }
  draw();
}

function stopGeneratedSignal() {
  if (activeSignalStopTimer) clearTimeout(activeSignalStopTimer);
  activeSignalStopTimer = null;
  activeSignalNodes.forEach(node => {
    try { if (typeof node.stop === "function") node.stop(); } catch (error) {}
    try { node.disconnect(); } catch (error) {}
  });
  activeSignalNodes = [];
  if (sirenAudioMode === "test" || sirenAudioMode === "synthetic") {
    isMicActive = false;
    sirenAudioMode = "idle";
    setTimeout(() => {
      if (sirenAudioMode === "idle") resetSirenDetector();
    }, SIREN_CONFIG.STATE_DROP_MS);
  }
}

function startSirenSignal(name, options) {
  const settings = options || {};
  if (micStream && sirenAudioMode === "mic") {
    toast("Stop the live microphone before playing a test signal.");
    return false;
  }
  stopGeneratedSignal();
  ensureSirenAnalyser();
  if (audioCtx.state === "suspended") audioCtx.resume();
  resetSirenDetector();
  const spec = SIREN_CONFIG.TEST_SIGNALS[name];
  if (!spec) return false;
  sirenTestMode = !!settings.testMode;
  sirenAudioMode = settings.testMode ? "test" : "synthetic";
  isMicActive = true;

  const output = audioCtx.createGain();
  output.gain.value = SIREN_CONFIG.TEST_OUTPUT_GAIN;
  output.connect(audioCtx.destination);
  activeSignalNodes.push(output);

  function connectTone(frequency, waveform) {
    const oscillator = audioCtx.createOscillator();
    oscillator.type = waveform || "sine";
    oscillator.frequency.value = frequency;
    oscillator.connect(analyser);
    oscillator.connect(output);
    activeSignalNodes.push(oscillator);
    oscillator.start();
    return oscillator;
  }

  if (name === "noise") {
    const length = audioCtx.sampleRate * 2;
    const buffer = audioCtx.createBuffer(1, length, audioCtx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i++) data[i] = Math.random() * 2 - 1;
    const source = audioCtx.createBufferSource();
    source.buffer = buffer;
    source.loop = true;
    source.connect(analyser);
    source.connect(output);
    source.start();
    activeSignalNodes.push(source);
  } else if (name === "chord") {
    spec.frequenciesHz.forEach(frequency => connectTone(frequency, spec.waveform));
  } else if (name === "horn") {
    connectTone(spec.frequencyHz, spec.waveform);
  } else {
    const carrier = connectTone(spec.baseHz, "sine");
    const lfo = audioCtx.createOscillator();
    const depth = audioCtx.createGain();
    lfo.type = spec.waveform;
    lfo.frequency.value = 1 / spec.periodSeconds;
    depth.gain.value = spec.deviationHz;
    lfo.connect(depth);
    depth.connect(carrier.frequency);
    lfo.start();
    activeSignalNodes.push(lfo, depth);
  }

  renderSirenReadout(null);
  if (!settings.selfCheck) {
    const status = $("#siren-test-playing");
    if (status) status.textContent = (settings.testMode ? "Playing test signal: " : "Running synthetic fallback: ") +
      name + " locally; no audio is uploaded.";
    if (settings.testMode) {
      activeSignalStopTimer = setTimeout(stopGeneratedSignal, SIREN_CONFIG.TEST_SIGNAL_DURATION_MS);
    }
  }
  return true;
}

function startSyntheticSiren() {
  if (startSirenSignal("wail", { testMode: false })) {
    sirenTestMode = false;
    sirenAudioMode = "synthetic";
    if ($("#btn-mic-toggle")) $("#btn-mic-toggle").textContent = "Stop Synthetic Siren";
    toast("Microphone unavailable — running a local synthetic wail.");
  }
}

async function toggleMic() {
  if (isMicActive) {
    stopMic();
    return;
  }
  try {
    ensureSirenAnalyser();
    if (audioCtx.state === "suspended") await audioCtx.resume();
    if (!micPermissionFailed && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        micSource = audioCtx.createMediaStreamSource(micStream);
        micSource.connect(analyser);
        sirenAudioMode = "mic";
        sirenTestMode = false;
        isMicActive = true;
        resetSirenDetector();
        if ($("#btn-mic-toggle")) $("#btn-mic-toggle").textContent = "Stop Live Mic";
        toast("Live microphone analysis active. Audio stays in this browser.");
        return;
      } catch (error) {
        micPermissionFailed = true;
      }
    }
    startSyntheticSiren();
  } catch (error) {
    console.warn("Could not start siren audio input:", error);
    startSyntheticSiren();
  }
}

function stopMic() {
  stopGeneratedSignal();
  if (micSource) {
    try { micSource.disconnect(); } catch (error) {}
    micSource = null;
  }
  if (micStream) {
    micStream.getTracks().forEach(track => track.stop());
    micStream = null;
  }
  isMicActive = false;
  sirenAudioMode = "idle";
  sirenTestMode = false;
  resetSirenDetector();
  if ($("#btn-mic-toggle")) $("#btn-mic-toggle").textContent = "🎙️ Start Live Siren Mic (FFT)";
  renderSirenReadout(null);
}

function initSirenTestPanel() {
  const panel = $("#siren-test-panel");
  if (!panel) return;
  const enabled = new URLSearchParams(window.location.search).get("dev") === "1";
  panel.hidden = !enabled;
  panel.querySelectorAll("[data-siren-test]").forEach(button => {
    button.addEventListener("click", () => startSirenSignal(button.dataset.sirenTest, { testMode: true }));
  });
  const selfCheckButton = $("#siren-self-check");
  if (selfCheckButton) selfCheckButton.addEventListener("click", runSirenSelfCheck);
}

function waitForSirenTest(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function runSirenSelfCheck() {
  if (micStream) {
    console.warn("Siren self-check: stop the live microphone first.");
    return;
  }
  const cases = [
    { name: "wail", expected: "wail" },
    { name: "yelp", expected: "yelp" },
    { name: "hiLo", expected: "hi-lo" },
    { name: "horn", expected: null },
    { name: "noise", expected: null },
    { name: "chord", expected: null }
  ];
  const results = [];
  console.group("DOME Flow siren detector self-check");
  for (const testCase of cases) {
    resetSirenDetector();
    startSirenSignal(testCase.name, { testMode: true, selfCheck: true });
    await waitForSirenTest(SIREN_CONFIG.TEST_SIGNAL_DURATION_MS);
    const confirmed = sirenDetector.state === "CONFIRMED";
    const passed = testCase.expected
      ? confirmed && sirenDetector.label === testCase.expected
      : !confirmed;
    const result = {
      signal: testCase.name,
      expected: testCase.expected || "never confirmed",
      actual: confirmed ? sirenDetector.label : sirenDetector.state,
      confidence: Number(sirenDetector.confidence.toFixed(2)),
      result: passed ? "PASS" : "FAIL"
    };
    results.push(result);
    console.log(result.result + " — " + result.signal, result);
    stopGeneratedSignal();
    resetSirenDetector();
    await waitForSirenTest(SIREN_CONFIG.SAMPLE_INTERVAL_MS * 2);
  }
  console.table(results);
  console.groupEnd();
  const status = $("#siren-test-playing");
  if (status) status.textContent = "Self-check finished. See the browser console for PASS/FAIL.";
}

window.runSirenSelfCheck = runSirenSelfCheck;


function initModuleA() {
  const inputs = ["#preempt-cars", "#preempt-trucks", "#preempt-bikes", "#preempt-dist", "#preempt-speed"];
  inputs.forEach(sel => {
    const el = $(sel);
    if (el) {
      el.addEventListener("input", updateLiveMath);
      el.addEventListener("change", updateLiveMath);
    }
  });

  if ($("#preempt-junction")) {
    $("#preempt-junction").addEventListener("change", () => {
      const jId = $("#preempt-junction").value;
      if (currentSummary && currentSummary.junctions) {
        const j = currentSummary.junctions.find(x => x.id === jId);
        if (j) {
          if ($("#preempt-cars")) $("#preempt-cars").value = j.cars;
          if ($("#preempt-trucks")) $("#preempt-trucks").value = j.trucks;
          if ($("#preempt-bikes")) $("#preempt-bikes").value = j.bikes;
        }
      }
      updateLiveMath();
    });
  }

  if ($("#btn-trigger-preempt")) $("#btn-trigger-preempt").onclick = triggerPreemptionOverride;
  if ($("#btn-mic-toggle")) $("#btn-mic-toggle").onclick = toggleMic;

  initFFTCanvas();
  initSirenTestPanel();
  updateLiveMath();
}

// ==========================================
// 4. MODULE B: CROWD-TELEMATICS PROBE WIRING
// ==========================================

async function triggerSimShock(source = "simulator") {
  const corridor = $("#shock-corridor")?.value || (currentSummary?.active_scenario || "nh206");
  const z_jerk = parseFloat($("#shock-jerk")?.value || 24.5);
  const speed_kmh = parseFloat($("#shock-speed")?.value || 48);

  try {
    const res = await api("/api/telematics/shock", {
      method: "POST",
      body: JSON.stringify({
        corridor,
        jerk_mps3: z_jerk,
        speed_kmh,
        source,
        probe_id: source === "motion" ? motionProbeId : undefined
      })
    });

    if (res.status === "filtered_noise") {
      toast("⚠️ Ignored by Spatial Filter: Speed < 15 km/h or Jerk < 15 m/s³");
    } else if (res.status === "clustering") {
      const pct = Math.round((res.hits / 3) * 100);
      if ($("#cluster-progress-bar")) $("#cluster-progress-bar").style.width = `${pct}%`;
      if ($("#cluster-status-text")) $("#cluster-status-text").textContent = `${res.hits} / 3 Hits — Shock count accumulating`;
      toast(`💥 Shock Registered (${res.hits}/3) — Shock count accumulating`);
    } else if (res.status === "verified_blackspot") {
      if ($("#cluster-progress-bar")) $("#cluster-progress-bar").style.width = "100%";
      if ($("#cluster-status-text")) $("#cluster-status-text").textContent = "3 / 3 Verified! PWD Work Order Dispatched";
      await load();
      toast("💥 Verified Pothole Blackspot Created & PWD Work Order Dispatched!");
    }
  } catch (err) {
    console.error("Shock probe error:", err);
    toast("Could not submit telematics shock probe");
  }
}

let isMotionActive = false;
let lastAcc = null;
let lastMotionTime = Date.now();
let motionHitArmed = true;
let motionLowSince = 0;
let lastMotionHitTime = 0;
const motionProbeId = (() => {
  const key = "dome-flow-motion-probe-id";
  let id = sessionStorage.getItem(key);
  if (!id) {
    id = Date.now() + "-" + Math.random().toString(36).slice(2);
    sessionStorage.setItem(key, id);
  }
  return id;
})();

function handleMotion(e) {
  const directAcc = e.acceleration;
  const gravityAcc = e.accelerationIncludingGravity;
  const directHasValues = directAcc && [directAcc.x, directAcc.y, directAcc.z].some(Number.isFinite);
  const acc = directHasValues ? directAcc : gravityAcc;
  if (!acc) return;
  const now = Date.now();
  const dt = (now - lastMotionTime) / 1000;
  if (dt < 0.08) return;

  const currentAcc = {
    x: Number.isFinite(acc.x) ? acc.x : 0,
    y: Number.isFinite(acc.y) ? acc.y : 0,
    z: Number.isFinite(acc.z) ? acc.z : 0
  };
  if (!lastAcc) {
    lastAcc = currentAcc;
    lastMotionTime = now;
    return;
  }
  const jerk = Math.hypot(
    currentAcc.x - lastAcc.x,
    currentAcc.y - lastAcc.y,
    currentAcc.z - lastAcc.z
  ) / Math.max(dt, 0.05);
  lastAcc = currentAcc;
  lastMotionTime = now;

  const jerkVal = Math.min(50, Math.round(jerk * 10) / 10);
  if ($("#shock-jerk")) $("#shock-jerk").value = jerkVal;
  if ($("#jerk-val")) $("#jerk-val").textContent = `${jerkVal} m/s³`;
  if ($("#live-jerk-readout")) $("#live-jerk-readout").innerHTML = `${jerkVal} <small>m/s³</small>`;

  if (jerkVal <= 8) {
    if (!motionLowSince) motionLowSince = now;
    if (now - motionLowSince >= 900) motionHitArmed = true;
  } else {
    motionLowSince = 0;
  }

  if (jerkVal >= 16 && motionHitArmed) {
    motionHitArmed = false;
    if (now - lastMotionHitTime >= 3000) {
      lastMotionHitTime = now;
      triggerSimShock("motion");
    } else {
      toast("Wait 3 seconds between phone shock hits");
    }
  }
}

function bindMotion() {
  if (isMotionActive) {
    window.removeEventListener("devicemotion", handleMotion);
    isMotionActive = false;
    if ($("#btn-motion-sensor")) $("#btn-motion-sensor").innerHTML = "📱 Enable Live Phone Accelerometer";
    toast("Motion sensor disabled");
  } else {
    lastAcc = null;
    lastMotionTime = Date.now();
    motionHitArmed = true;
    motionLowSince = 0;
    window.addEventListener("devicemotion", handleMotion);
    isMotionActive = true;
    if ($("#btn-motion-sensor")) $("#btn-motion-sensor").innerHTML = "📱 Motion Sensor Active (Shake to Shock)";
    toast("📱 Phone Accelerometer Active — Shake device to register shock");
  }
}

function toggleMotionSensor() {
  if (!window.DeviceMotionEvent) {
    toast("📱 DeviceMotionEvent not supported on this browser. Use Simulate (+1 Hit) button.");
    return;
  }
  if (typeof DeviceMotionEvent.requestPermission === "function") {
    DeviceMotionEvent.requestPermission()
      .then(res => {
        if (res === "granted") bindMotion();
        else toast("Device motion permission denied");
      })
      .catch(() => toast("Motion sensor permission error"));
  } else {
    bindMotion();
  }
}

function initModuleB() {
  if ($("#shock-jerk")) {
    $("#shock-jerk").addEventListener("input", e => {
      const val = e.target.value;
      if ($("#jerk-val")) $("#jerk-val").textContent = `${val} m/s³`;
      if ($("#live-jerk-readout")) $("#live-jerk-readout").innerHTML = `${val} <small>m/s³</small>`;
    });
  }

  if ($("#shock-speed")) {
    $("#shock-speed").addEventListener("input", e => {
      const val = e.target.value;
      if ($("#speed-val")) $("#speed-val").textContent = `${val} km/h`;
      if ($("#live-speed-readout")) $("#live-speed-readout").innerHTML = `${val} <small>km/h</small>`;
    });
  }

  if ($("#btn-sim-shock")) $("#btn-sim-shock").onclick = triggerSimShock;
  if ($("#btn-motion-sensor")) $("#btn-motion-sensor").onclick = toggleMotionSensor;
}

// ==========================================
// 5. EVENT LISTENERS & INITIALIZATION
// ==========================================

document.querySelectorAll("[data-view]").forEach(b =>
  b.addEventListener("click", () => switchView(b.dataset.view))
);

document.querySelectorAll("[data-goto]").forEach(b =>
  b.addEventListener("click", () => switchView(b.dataset.goto))
);

document.querySelectorAll(".filter").forEach(b =>
  b.addEventListener("click", () => {
    activeFilter = b.dataset.filter;
    document.querySelectorAll(".filter").forEach(x => x.classList.toggle("active", x === b));
    renderAll();
  })
);

if ($("#closeModal")) $("#closeModal").onclick = closeModal;
if ($("#incidentModal")) {
  $("#incidentModal").addEventListener("click", e => {
    if (e.target.id === "incidentModal") closeModal();
  });
}

if ($("#refreshBtn")) {
  $("#refreshBtn").onclick = () => {
    load();
    toast("Demo data refreshed");
  };
}

document.addEventListener("click", e => {
  const b = e.target.closest("[data-incident]");
  if (b) openIncident(b.dataset.incident);
});

function drawChart() {
  const vals = [34, 32, 36, 30, 29, 31, 28],
    days = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"];
  const chartEl = $("#travelChart");
  if (!chartEl) return;
  chartEl.innerHTML = vals
    .map((v, i) => `<div class="bar-group"><div class="bar" style="height:${(v / 40) * 100}%" data-value="${v}"></div><small>${days[i]}</small></div>`)
    .join("");
}

function updateHeaderClock() {
  const now = new Date();
  const dateEl = $("#header-date");
  const timeEl = $("#header-time");
  if (dateEl) {
    dateEl.textContent = new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata", weekday: "short", day: "2-digit", month: "short"
    }).format(now).toUpperCase();
  }
  if (timeEl) {
    timeEl.textContent = new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true
    }).format(now);
  }
}

// Bootstrap all modules
initTopbarAndModals();
initModuleA();
initModuleB();
load();
drawChart();
updateHeaderClock();
setInterval(updateHeaderClock, 1000);
