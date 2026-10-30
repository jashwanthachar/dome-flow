// Range and network warning assumptions; validate every value with field recordings.
const RANGE_CONFIG = {
  SIREN_SPL_REF_DB: 115, // ASSUMPTION: siren SPL at REF_DIST_M; validate with recordings.
  REF_DIST_M: 3, // ASSUMPTION: reference measurement distance in metres; validate in field.
  TRAFFIC_NOISE_DB: 78, // ASSUMPTION: representative traffic noise; measure by time/location.
  MIN_SNR_DB: 6, // ASSUMPTION: minimum usable siren-to-noise margin; validate in field.
  ARM_DISTANCE_M: 500 // ASSUMPTION: network warning radius; validate with deployment coverage.
};

// Direction thresholds and reference values; all are assumptions to tune with field recordings.
const DIRECTION_CONFIG = Object.freeze({
  APPROACH_SLOPE_DB_S: 1.5, // ASSUMPTION: minimum rising/falling level trend in dB/s.
  APPROACH_MIN_CONF: 0.65, // ASSUMPTION: minimum R-squared for a usable loudness trend.
  WINDOW_MS: 3000, // ASSUMPTION: loudness and Doppler trend window in milliseconds.
  SAMPLE_INTERVAL_MS: 100, // ASSUMPTION: RMS direction sample interval in milliseconds.
  MIN_TREND_POINTS: 8, // ASSUMPTION: samples needed before direction can be classified.
  DOPPLER_SHIFT_HZ: 18, // ASSUMPTION: minimum shift to display supporting Doppler evidence.
  DOPPLER_TEST_SHIFT_CENTS: 40, // ASSUMPTION: synthetic Doppler shift for simulator signals.
  STEREO_MAX_LAG_SAMPLES: 32, // ASSUMPTION: stereo delay search limit; tune for device sample rates.
  RECEDE_RELEASE_MS: 2000, // ASSUMPTION: continuous receding time before safe release begins.
  RELEASE_AMBER_MS: 3000, // ASSUMPTION: demo amber clearance interval.
  RELEASE_ALL_RED_MS: 1000, // ASSUMPTION: demo all-red clearance interval.
  ARM_TOLERANCE_DEG: 30, // ASSUMPTION: maximum heading difference for arm matching.
  DOPPLER_REFERENCE_RANGES: {
    wail: { minHz: 720, maxHz: 1580 }, // ASSUMPTION: typical wail sweep range; tune with recordings.
    yelp: { minHz: 700, maxHz: 1500 }, // ASSUMPTION: typical yelp sweep range; tune with recordings.
    "hi-lo": { minHz: 700, maxHz: 1500 } // ASSUMPTION: hi-lo range; used only for supporting evidence.
  }
});

// Queue-discharge model assumptions mirror app.py; verify each against field observations.
const QUEUE_CONFIG = Object.freeze({
  T_REACT_S: 3.5, // ASSUMPTION: driver reaction delay.
  T_STARTUP_S: 2.0, // ASSUMPTION: start-up lost time.
  H_S_PER_PCU: 2.0, // ASSUMPTION: nominal saturation headway, about 1800 PCU/hr/lane.
  H_LOW_S_PER_PCU: 1.7, // ASSUMPTION: low headway estimate.
  H_HIGH_S_PER_PCU: 2.6, // ASSUMPTION: high headway estimate.
  PCU_UNCERTAINTY: 0.15, // ASSUMPTION: +/- PCU uncertainty.
  GREEN_START_EARLY_BUFFER_S: 1.0, // ASSUMPTION: conservative early-start allowance.
  // ASSUMPTION: Verify against IRC:106 table before presenting. Replace if different.
  PCU_FACTORS: Object.freeze({ car: 1.0, two_wheeler: 0.5, heavy_vehicle: 2.2, auto_rickshaw: 1.2 }),
  // ASSUMPTION: effective lanes for each junction approach arm; replace after field survey.
  LANES_PER_JUNCTION_ARM: Object.freeze(Object.fromEntries(["J1", "J2", "J3", "J4"].map(id =>
    [id, Object.freeze({ N: 2, E: 2, S: 2, W: 2 })]
  )))
});

function calculateQueueDischarge(cars, trucks, bikes, autoRickshaws = 0, effectiveLanes = 2) {
  const counts = { car: Math.max(0, Math.trunc(Number(cars) || 0)), two_wheeler: Math.max(0, Math.trunc(Number(bikes) || 0)),
    heavy_vehicle: Math.max(0, Math.trunc(Number(trucks) || 0)), auto_rickshaw: Math.max(0, Math.trunc(Number(autoRickshaws) || 0)) };
  const lanes = Math.max(Number(effectiveLanes) || 2, 1);
  const pcuTotal = Object.entries(counts).reduce((sum, [kind, count]) => sum + count * QUEUE_CONFIG.PCU_FACTORS[kind], 0);
  const fixedDelay = QUEUE_CONFIG.T_REACT_S + QUEUE_CONFIG.T_STARTUP_S;
  const uncertainty = QUEUE_CONFIG.PCU_UNCERTAINTY;
  const nominal = fixedDelay + pcuTotal * QUEUE_CONFIG.H_S_PER_PCU / lanes;
  const low = fixedDelay + pcuTotal * (1 - uncertainty) * QUEUE_CONFIG.H_LOW_S_PER_PCU / lanes;
  const high = fixedDelay + pcuTotal * (1 + uncertainty) * QUEUE_CONFIG.H_HIGH_S_PER_PCU / lanes;
  const contributions = Object.fromEntries(Object.entries(counts).map(([kind, count]) =>
    [kind, count * QUEUE_CONFIG.PCU_FACTORS[kind] * QUEUE_CONFIG.H_S_PER_PCU / lanes]
  ));
  return { nominal_sec: nominal, low_sec: low, high_sec: high, pcu_total: pcuTotal, effective_lanes: lanes,
    pcu_uncertainty: uncertainty, reaction_sec: QUEUE_CONFIG.T_REACT_S, startup_sec: QUEUE_CONFIG.T_STARTUP_S,
    class_contributions_sec: contributions };
}

function runQueueModelSelfCheck() {
  const cases = [
    { name: "empty queue", args: [0, 0, 0, 0, 2], expected: 5.5 },
    { name: "10 cars, 2 lanes", args: [10, 0, 0, 0, 2], expected: 15.5 },
    { name: "mixed queue", args: [10, 2, 4, 1, 2], expected: 23.1 }
  ];
  console.group("Queue discharge model self-check");
  let allPassed = true;
  for (const test of cases) {
    const actual = calculateQueueDischarge(...test.args);
    const pass = Math.abs(actual.nominal_sec - test.expected) < 0.001;
    allPassed = allPassed && pass;
    console[pass ? "log" : "error"](`${pass ? "PASS" : "FAIL"} ${test.name}: expected ${test.expected.toFixed(3)}s, actual ${actual.nominal_sec.toFixed(3)}s`);
    const ordered = actual.low_sec <= actual.nominal_sec && actual.nominal_sec <= actual.high_sec;
    allPassed = allPassed && ordered;
    console[ordered ? "log" : "error"](`${ordered ? "PASS" : "FAIL"} ${test.name} bounds: expected LOW <= nominal <= HIGH, actual ${actual.low_sec.toFixed(3)} <= ${actual.nominal_sec.toFixed(3)} <= ${actual.high_sec.toFixed(3)}`);
  }
  const label = document.querySelector("#tflush-math-box .math-title")?.textContent || "";
  const labelPassed = label.includes("QUEUE DISCHARGE (saturation flow)");
  allPassed = allPassed && labelPassed;
  console[labelPassed ? "log" : "error"](`${labelPassed ? "PASS" : "FAIL"} renamed UI label: expected QUEUE DISCHARGE (saturation flow), actual ${label || "missing"}`);
  console.groupEnd();
  return allPassed;
}

window.runQueueModelSelfCheck = runQueueModelSelfCheck;

async function runHarmSelfCheck() {
  console.group("Minimum-harm / preemption safety self-check");
  try {
    const response = await api("/api/dev/harm-self-check");
    let passedAll = true;
    for (const item of response.results || []) {
      passedAll = passedAll && item.passed;
      console[item.passed ? "log" : "error"](`${item.passed ? "PASS" : "FAIL"} ${item.name}: expected ${JSON.stringify(item.expected)}, actual ${JSON.stringify(item.actual)}`);
    }
    console.log(passedAll ? "All harm self-checks passed" : "One or more harm self-checks failed");
    if ($("#dual-key-status")) $("#dual-key-status").textContent = passedAll
      ? "Minimum-harm self-check passed. See console."
      : "Minimum-harm self-check failed. See console.";
    await load();
    return passedAll;
  } catch (error) {
    console.error("FAIL minimum-harm self-check", error);
    if ($("#dual-key-status")) $("#dual-key-status").textContent = "Minimum-harm self-check could not run: " + error.message;
    return false;
  } finally {
    console.groupEnd();
  }
}
window.runHarmSelfCheck = runHarmSelfCheck;

async function runControllerSelfCheck() {
  console.group("Controller adapter and safety interlock self-check");
  try {
    const response = await api("/api/dev/controller-self-check");
    let allPassed = true;
    for (const item of response.results || []) {
      allPassed = allPassed && item.passed;
      console[item.passed ? "log" : "error"](`${item.passed ? "PASS" : "FAIL"} ${item.name}: expected ${JSON.stringify(item.expected)}, actual ${JSON.stringify(item.actual)}`);
    }
    console.log(allPassed ? "All controller safety checks passed" : "Controller safety checks failed");
    if ($("#dual-key-status")) $("#dual-key-status").textContent = allPassed
      ? "Controller safety self-check passed. See console."
      : "Controller safety self-check failed. See console.";
    return allPassed;
  } catch (error) {
    console.error("FAIL controller self-check", error);
    return false;
  } finally {
    console.groupEnd();
  }
}
window.runControllerSelfCheck = runControllerSelfCheck;

let latestVerifiedVehicleReports = {};

// Approach bearings are provisional compass headings toward each junction; field-check each arm.
const JUNCTION_ARMS = Object.freeze({
  J1: [{ id: "N", bearing: 0 }, { id: "E", bearing: 90 }, { id: "S", bearing: 180 }, { id: "W", bearing: 270 }],
  J2: [{ id: "N", bearing: 10 }, { id: "E", bearing: 95 }, { id: "S", bearing: 190 }, { id: "W", bearing: 275 }],
  J3: [{ id: "N", bearing: 350 }, { id: "E", bearing: 85 }, { id: "S", bearing: 170 }, { id: "W", bearing: 265 }],
  J4: [{ id: "N", bearing: 5 }, { id: "E", bearing: 100 }, { id: "S", bearing: 185 }, { id: "W", bearing: 280 }]
});

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
  const data = await r.json();
  if (!r.ok) {
    const error = new Error(data.reason || data.error || "Request failed: " + r.statusText);
    error.data = data;
    throw error;
  }
  return data;
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

  const controllerStatus = data.controller_status || {};
  const modes = [...new Set((data.junctions || []).map(j => j.controller_mode || "ADVISORY"))];
  if ($("#controller-mode-status")) $("#controller-mode-status").textContent = modes.join(" / ") + " · decision/act boundary";
  if ($("#controller-failsafe-badge")) {
    const failSafe = !!controllerStatus.fail_safe_active;
    $("#controller-failsafe-badge").textContent = failSafe ? "FAIL-SAFE ACTIVE" : "HEARTBEATS HEALTHY";
    $("#controller-failsafe-badge").classList.toggle("active", failSafe);
  }
  if ($("#controller-failsafe-reason")) $("#controller-failsafe-reason").textContent = controllerStatus.fail_safe_reason || "Heartbeat status unavailable";
  if ($("#controller-interlock-status")) {
    const blocked = (data.junctions || []).find(j => (j.interlock_status || "").startsWith("Blocked"));
    $("#controller-interlock-status").textContent = blocked
      ? `${blocked.id}: ${blocked.interlock_status}`
      : `Interlock: ${(data.junctions || []).map(j => `${j.id} ${j.interlock_status || "ready"}`).join(" · ")}`;
  }
  if ($("#controller-simulation-banner")) $("#controller-simulation-banner").textContent = controllerStatus.banner || "SIMULATION, NOT CONNECTED TO REAL SIGNALS";
  const recommendation = (data.junctions || []).map(j => j.recommendation && ({ ...j.recommendation, mode: j.controller_mode })).find(Boolean);
  if ($("#controller-recommendation")) {
    $("#controller-recommendation").hidden = !recommendation;
    if (recommendation) {
      $("#controller-recommendation-title").textContent = recommendation.reason;
      $("#controller-recommendation-details").textContent = `${recommendation.junction_id} · arm ${recommendation.arm} · ETA ${recommendation.eta_s}s · queue HIGH ${recommendation.t_flush_high_s}s · saved ${Number(recommendation.harm.delay_saved_s).toFixed(1)}s · cross traffic ${Number(recommendation.harm.cross_delay_added_vehicle_s).toFixed(1)} vehicle-s · benefit ${Number(recommendation.harm.benefit_vehicle_s).toFixed(1)} vs harm ${Number(recommendation.harm.required_benefit_vehicle_s).toFixed(1)} · expires in ${Math.max(0, Math.ceil(recommendation.expires_in_s))}s. Confirm only records operator review; it does not change a phase.`;
      $("#controller-recommendation").dataset.recommendationId = recommendation.id;
    }
  }

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
      const displaySignalState = j.display_status || j.signal_state;
      const harm = j.harm_status || {};
      const benefit = Number(harm.benefit_vehicle_s || 0);
      const harmCost = Number(harm.required_benefit_vehicle_s || 0);
      const balanceWidth = benefit + harmCost > 0 ? Math.round(benefit / (benefit + harmCost) * 100) : 0;
      const queueText = (harm.queued_requests || []).length
        ? harm.queued_requests.map(item => `${esc(item.vehicle_id)} (${Number(item.eta_s).toFixed(1)}s)`).join(" → ")
        : "None";
      let sigClass = "red";
      if (displaySignalState === "PREEMPT_GREEN") sigClass = "preempt-green";
      else if (displaySignalState === "GREEN_WAVE_STANDBY") sigClass = "standby";
      else if (displaySignalState === "GREEN") sigClass = "green";
      else if (displaySignalState === "AMBER_CLEARANCE") sigClass = "amber-clearance";

      return `
        <div class="junction-card glass" data-junction="${esc(j.id)}">
          <div class="junction-header">
            <div class="j-info"><b class="j-id">${esc(j.id)}</b> · <span class="j-name">${esc(j.name)}</span></div>
            <span class="signal-badge ${sigClass}">${esc(displaySignalState)}</span>
          </div>
          <span class="controller-mode-badge">${esc(j.controller_mode || "ADVISORY")}</span>
          <label class="controller-mode-control">Controller mode <select data-controller-mode data-junction="${esc(j.id)}">
            <option value="ADVISORY" ${j.controller_mode !== "DEMO_AUTO" ? "selected" : ""}>ADVISORY</option>
            <option value="DEMO_AUTO" ${j.controller_mode === "DEMO_AUTO" ? "selected" : ""}>DEMO_AUTO</option>
          </select></label>
          <small class="junction-interlock">${esc(j.interlock_status || "Interlock ready")}</small>
          <div class="junction-queues">
            <span title="Queued Cars">🚗 <b class="q-cars">${j.cars}</b></span>
            <span title="Queued Trucks">🚚 <b class="q-trucks">${j.trucks}</b></span>
            <span title="Queued Bikes">🛵 <b class="q-bikes">${j.bikes}</b></span>
          </div>
          <div class="junction-flush"><small>QUEUE DISCHARGE (saturation flow)</small> T_flush: <strong class="q-flush">${j.t_flush_sec}s</strong> <small class="q-flush-range">${j.t_flush_low_sec}–${j.t_flush_high_sec}s</small></div>
          <div class="harm-readout">
            <div><span>Ambulance delay saved</span><b>${Number(harm.delay_saved_s || 0).toFixed(1)}s</b></div>
            <div><span>Cross-traffic delay added</span><b>${Number(harm.cross_delay_added_vehicle_s || 0).toFixed(1)} vehicle-s</b></div>
            <div class="harm-balance-label"><span>Benefit ${benefit.toFixed(1)} vs harm ${harmCost.toFixed(1)}</span><span>${balanceWidth}%</span></div>
            <div class="harm-balance"><i style="width:${balanceWidth}%"></i></div>
            <small>Hold <b class="harm-countdown" data-seconds="${Number(harm.hold_remaining_s || 0)}">${Math.ceil(Number(harm.hold_remaining_s || 0))}s</b> / ${Number(harm.max_hold_s || 40)}s · Cooldown <b class="harm-countdown" data-seconds="${Number(harm.cooldown_remaining_s || 0)}">${Math.ceil(Number(harm.cooldown_remaining_s || 0))}s</b> · Recovery <b class="harm-countdown" data-seconds="${Number(harm.recovery_remaining_s || 0)}">${Math.ceil(Number(harm.recovery_remaining_s || 0))}s</b></small>
            <small>Decision: ${esc(harm.reason || "No preemption decision yet")}</small>
            <small>ETA priority queue: ${queueText}</small>
          </div>
        </div>
      `;
    }).join("");
  }

  // 4. SVG Green Wave Corridor Pulse
  const hasPreempt = (data.junctions || []).some(j => j.signal_state === "PREEMPT_GREEN") || ((m.active_green_waves || 0) > 0);
  preemptionActive = (data.junctions || []).some(j => j.signal_state === "PREEMPT_GREEN");
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

async function controllerHeartbeat(source) {
  try {
    await api("/api/controller/heartbeat", { method: "POST", body: JSON.stringify({ source }) });
  } catch (error) {
    console.warn(`Controller ${source} heartbeat failed:`, error.message);
  }
}

async function updateControllerMode(junctionId, mode) {
  try {
    const result = await api("/api/controller/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": $("#admin-token")?.value || "" },
      body: JSON.stringify({ junction_id: junctionId, mode })
    });
    if ($("#dual-key-status")) $("#dual-key-status").textContent = `${junctionId} mode set to ${result.mode}.`;
  } catch (error) {
    if ($("#dual-key-status")) $("#dual-key-status").textContent = `Mode change rejected: ${error.message}`;
  }
  await load();
}

async function handleRecommendation(action) {
  const panel = $("#controller-recommendation");
  const id = panel?.dataset.recommendationId;
  if (!id) return;
  try {
    const result = await api(`/api/controller/recommendation/${encodeURIComponent(id)}/${action}`, {
      method: "POST", body: JSON.stringify({})
    });
    if ($("#dual-key-status")) $("#dual-key-status").textContent = result.reason || `Recommendation ${action}ed; no phase changed.`;
  } catch (error) {
    if ($("#dual-key-status")) $("#dual-key-status").textContent = `Recommendation ${action} failed: ${error.message}`;
  }
  await load();
}

async function requestManualOverride() {
  const junctionId = $("#preempt-junction")?.value || "J1";
  try {
    const result = await api("/api/controller/override", {
      method: "POST", body: JSON.stringify({ junction_id: junctionId })
    });
    if ($("#dual-key-status")) $("#dual-key-status").textContent = result.reason;
  } catch (error) {
    if ($("#dual-key-status")) $("#dual-key-status").textContent = `Manual override blocked: ${error.message}`;
  }
  await load();
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
// 3. MODULE A: QUEUE DISCHARGE MATH & ACOUSTIC FFT
// ==========================================

function updateLiveMath() {
  const cars = parseFloat($("#preempt-cars")?.value || 0);
  const trucks = parseFloat($("#preempt-trucks")?.value || 0);
  const bikes = parseFloat($("#preempt-bikes")?.value || 0);
  const junctionId = $("#preempt-junction")?.value || "J2";
  const selectedVehicle = $("#verified-vehicle")?.value || "";
  const verifiedMetrics = latestVerifiedVehicleReports[selectedVehicle]?.[junctionId];
  const manualEta = Number($("#preempt-dist")?.value || 0) / Math.max(Number($("#preempt-speed")?.value || 0) / 3.6, 1);
  const eta = Number.isFinite(verifiedMetrics?.eta_s) ? verifiedMetrics.eta_s : manualEta;
  const chosenArm = verifiedMetrics?.arm || identifyJunctionArm(junctionId, Number($("#ambulance-sim-heading")?.value || 0)) || "N";
  const lanes = QUEUE_CONFIG.LANES_PER_JUNCTION_ARM[junctionId]?.[chosenArm] || 2;
  const estimate = calculateQueueDischarge(cars, trucks, bikes, 0, lanes);
  const tFlushHigh = estimate.high_sec;
  const greenStartIn = eta - tFlushHigh;
  const formula = `${QUEUE_CONFIG.T_REACT_S.toFixed(1)} + ${QUEUE_CONFIG.T_STARTUP_S.toFixed(1)} + (${cars}*${QUEUE_CONFIG.PCU_FACTORS.car.toFixed(1)} + ${trucks}*${QUEUE_CONFIG.PCU_FACTORS.heavy_vehicle.toFixed(1)} + ${bikes}*${QUEUE_CONFIG.PCU_FACTORS.two_wheeler.toFixed(1)} + 0*${QUEUE_CONFIG.PCU_FACTORS.auto_rickshaw.toFixed(1)}) * ${QUEUE_CONFIG.H_S_PER_PCU.toFixed(1)} / ${lanes} = ${estimate.nominal_sec.toFixed(1)} s`;

  if ($("#queue-formula")) $("#queue-formula").textContent = formula;
  if ($("#calc-tflush")) $("#calc-tflush").textContent = `${estimate.nominal_sec.toFixed(1)}s`;
  if ($("#calc-tflush-range")) $("#calc-tflush-range").textContent = `${estimate.low_sec.toFixed(1)}–${estimate.high_sec.toFixed(1)}s`;
  if ($("#calc-eta")) $("#calc-eta").textContent = `${eta.toFixed(1)}s`;
  if ($("#calc-eta-source")) $("#calc-eta-source").textContent = Number.isFinite(verifiedMetrics?.eta_s) ? "verified position" : "manual estimate";
  if ($("#queue-breakdown")) {
    const parts = estimate.class_contributions_sec;
    $("#queue-breakdown").textContent = `Reaction ${estimate.reaction_sec.toFixed(1)}s · start-up ${estimate.startup_sec.toFixed(1)}s · cars ${parts.car.toFixed(1)}s · heavy vehicles ${parts.heavy_vehicle.toFixed(1)}s · two-wheelers ${parts.two_wheeler.toFixed(1)}s · auto-rickshaws ${parts.auto_rickshaw.toFixed(1)}s · ${lanes} lanes · PCU ±${Math.round(estimate.pcu_uncertainty * 100)}%`;
  }

  const marginEl = $("#calc-margin");
  if (marginEl) {
    if (greenStartIn < 0) {
      marginEl.className = "margin-status danger";
      marginEl.textContent = "TOO LATE: queue will not clear in time";
    } else {
      marginEl.className = "margin-status safe";
      marginEl.textContent = `Green start in ${greenStartIn.toFixed(1)}s using high estimate`;
    }
  }
}

function currentRangeConfig() {
  return {
    SIREN_SPL_REF_DB: Number($("#range-spl")?.value ?? RANGE_CONFIG.SIREN_SPL_REF_DB),
    REF_DIST_M: Number($("#range-ref-dist")?.value ?? RANGE_CONFIG.REF_DIST_M),
    TRAFFIC_NOISE_DB: Number($("#range-noise")?.value ?? RANGE_CONFIG.TRAFFIC_NOISE_DB),
    MIN_SNR_DB: Number($("#range-min-snr")?.value ?? RANGE_CONFIG.MIN_SNR_DB),
    ARM_DISTANCE_M: RANGE_CONFIG.ARM_DISTANCE_M
  };
}

function maxMicRangeM(config = currentRangeConfig()) {
  return config.REF_DIST_M * Math.pow(10,
    (config.SIREN_SPL_REF_DB - config.TRAFFIC_NOISE_DB - config.MIN_SNR_DB) / 20);
}

function renderRangeEstimate() {
  const config = currentRangeConfig();
  const valid = config.REF_DIST_M > 0 && [config.SIREN_SPL_REF_DB, config.TRAFFIC_NOISE_DB, config.MIN_SNR_DB].every(Number.isFinite);
  const range = valid ? maxMicRangeM(config) : 0;
  if ($("#mic-range-result")) $("#mic-range-result").textContent = valid ? `${Math.round(range)} m` : "Invalid inputs";
  const body = $("#range-table-body");
  if (body) body.innerHTML = [50, 100, 150, 250, 400].map(distance => {
    const spl = config.SIREN_SPL_REF_DB - 20 * Math.log10(distance / config.REF_DIST_M);
    const snr = spl - config.TRAFFIC_NOISE_DB;
    return `<tr><td>${distance} m</td><td>${spl.toFixed(1)} dB</td><td>${snr.toFixed(1)} dB</td><td>${snr >= config.MIN_SNR_DB ? "Yes" : "No"}</td></tr>`;
  }).join("");
  renderApproachSimulator();
}

let approachDistanceM = 600;
let approachTimer = null;
let approachSimulationActive = false;
let directionSelfCheckRunning = false;
let preemptionActive = false;
let preemptionRequestPending = false;
let preemptionScheduled = false;
let preemptionReleasePending = false;
let recedingSince = 0;
let lastDirectionSampleAt = 0;
let rmsTrendPoints = [];
let sirenTimeData = null;
let directionAnalysis = { slopeDbS: 0, rSquared: 0, state: "UNKNOWN", dopplerHint: "—", dopplerOffsetHz: 0 };
let leftChannelAnalyser = null;
let rightChannelAnalyser = null;
let leftChannelData = null;
let rightChannelData = null;
let channelSplitter = null;
let stereoHint = "—";

function identifyJunctionArm(junctionId, headingDeg) {
  const arms = JUNCTION_ARMS[junctionId] || [];
  const heading = ((Number(headingDeg) % 360) + 360) % 360;
  let nearest = null;
  arms.forEach(arm => {
    const difference = Math.abs(((heading - arm.bearing + 540) % 360) - 180);
    if (!nearest || difference < nearest.difference) nearest = { id: arm.id, difference };
  });
  return nearest && nearest.difference <= DIRECTION_CONFIG.ARM_TOLERANCE_DEG ? nearest.id : null;
}

function calculateRmsDb() {
  if (!analyser || !sirenTimeData) return null;
  analyser.getFloatTimeDomainData(sirenTimeData);
  let sumSquares = 0;
  for (const sample of sirenTimeData) sumSquares += sample * sample;
  const rms = Math.sqrt(sumSquares / sirenTimeData.length);
  return 20 * Math.log10(Math.max(rms, 1e-8));
}

function fitRmsTrend() {
  const points = rmsTrendPoints;
  if (points.length < DIRECTION_CONFIG.MIN_TREND_POINTS) {
    return { slopeDbS: 0, rSquared: 0, state: "UNKNOWN" };
  }
  const origin = points[0].time;
  const xs = points.map(point => (point.time - origin) / 1000);
  const ys = points.map(point => point.db);
  const meanX = xs.reduce((sum, value) => sum + value, 0) / xs.length;
  const meanY = ys.reduce((sum, value) => sum + value, 0) / ys.length;
  let covariance = 0, varianceX = 0, varianceY = 0;
  for (let i = 0; i < xs.length; i++) {
    covariance += (xs[i] - meanX) * (ys[i] - meanY);
    varianceX += (xs[i] - meanX) ** 2;
    varianceY += (ys[i] - meanY) ** 2;
  }
  const slopeDbS = varianceX ? covariance / varianceX : 0;
  const rSquared = varianceY ? Math.max(0, Math.min(1, (covariance * covariance) / (varianceX * varianceY))) : 0;
  const state = slopeDbS > DIRECTION_CONFIG.APPROACH_SLOPE_DB_S ? "APPROACHING" :
    slopeDbS < -DIRECTION_CONFIG.APPROACH_SLOPE_DB_S ? "RECEDING" : "UNKNOWN";
  return { slopeDbS, rSquared, state };
}

function getDopplerHint() {
  const label = sirenDetector.label !== "none" ? sirenDetector.label : sirenDetector.candidateLabel;
  const reference = DIRECTION_CONFIG.DOPPLER_REFERENCE_RANGES[label];
  const points = sirenHistory.filter(point => point.valid && performance.now() - point.time <= DIRECTION_CONFIG.WINDOW_MS);
  if (!reference || points.length < DIRECTION_CONFIG.MIN_TREND_POINTS) return { dopplerHint: "—", dopplerOffsetHz: 0 };
  const low = Math.min(...points.map(point => point.frequencyHz));
  const high = Math.max(...points.map(point => point.frequencyHz));
  const observedMidpoint = (low + high) / 2;
  const referenceMidpoint = (reference.minHz + reference.maxHz) / 2;
  const offsetHz = observedMidpoint - referenceMidpoint;
  const hint = offsetHz > DIRECTION_CONFIG.DOPPLER_SHIFT_HZ ? "Approach-like (supporting evidence)" :
    offsetHz < -DIRECTION_CONFIG.DOPPLER_SHIFT_HZ ? "Recede-like (supporting evidence)" : "No clear shift (supporting evidence)";
  return { dopplerHint: hint, dopplerOffsetHz: offsetHz };
}

function evaluateDirectionGate(stage = sirenDetector.state === "CONFIRMED" ? "confirmed" : "armed", checkDistance = true) {
  const junctionId = $("#preempt-junction")?.value || "J1";
  const headingValue = $("#ambulance-sim-heading")?.value;
  const heading = headingValue === "" || headingValue === undefined ? NaN : Number(headingValue);
  const arm = Number.isFinite(heading) ? identifyJunctionArm(junctionId, heading) : null;
  let reason = "Green gate ready";
  if (directionAnalysis.state === "RECEDING") reason = "Ambulance moving away";
  else if (directionAnalysis.state !== "APPROACHING" || directionAnalysis.rSquared < DIRECTION_CONFIG.APPROACH_MIN_CONF) reason = "Trend uncertain";
  else if (!arm) reason = "Not on a known arm";
  else if (stage !== "confirmed") reason = "Siren not confirmed";
  else if (checkDistance && getActiveApproachDistance() > maxMicRangeM()) reason = "Outside microphone range";
  return { allowed: reason === "Green gate ready", reason, arm, approach: directionAnalysis.state.toLowerCase(), confidence: directionAnalysis.rSquared };
}

function renderDirectionReadout() {
  const gate = evaluateDirectionGate();
  if (typeof directionAnalysis.slopeDbS === "number" && $("#direction-slope")) $("#direction-slope").textContent = `${directionAnalysis.slopeDbS.toFixed(2)} dB/s`;
  if ($("#direction-r2")) $("#direction-r2").textContent = directionAnalysis.rSquared.toFixed(2);
  if ($("#direction-state")) $("#direction-state").textContent = directionAnalysis.state;
  if ($("#direction-doppler")) $("#direction-doppler").textContent = directionAnalysis.dopplerHint;
  if ($("#direction-arm")) $("#direction-arm").textContent = gate.arm || "Unknown";
  if ($("#direction-stereo")) $("#direction-stereo").textContent = stereoHint;
  if ($("#direction-gate")) $("#direction-gate").textContent = gate.allowed ? `Granted · ${gate.arm}` : `Denied · ${gate.reason}`;
}

function updateDirectionAnalysis(now) {
  if (sirenDetector.state === "CANDIDATE" || sirenDetector.state === "CONFIRMED") {
    if (now - lastDirectionSampleAt >= DIRECTION_CONFIG.SAMPLE_INTERVAL_MS) {
      lastDirectionSampleAt = now;
      const db = calculateRmsDb();
      if (db !== null && Number.isFinite(db)) rmsTrendPoints.push({ time: now, db });
      updateStereoHint();
    }
    rmsTrendPoints = rmsTrendPoints.filter(point => now - point.time <= DIRECTION_CONFIG.WINDOW_MS);
    directionAnalysis = Object.assign(fitRmsTrend(), getDopplerHint());
  } else {
    rmsTrendPoints = [];
    directionAnalysis = { slopeDbS: 0, rSquared: 0, state: "UNKNOWN", dopplerHint: "—", dopplerOffsetHz: 0 };
  }
  renderDirectionReadout();

  const liveDirectionEvidence = !sirenTestMode && (sirenAudioMode === "mic" || sirenAudioMode === "synthetic");
  if (preemptionActive && (liveDirectionEvidence || (approachSimulationActive && !directionSelfCheckRunning))) {
    if (directionAnalysis.state === "RECEDING") {
      if (!recedingSince) recedingSince = now;
      if (!preemptionReleasePending && now - recedingSince >= DIRECTION_CONFIG.RECEDE_RELEASE_MS) {
        releasePreemptionEarly();
      }
    } else recedingSince = 0;
  } else {
    recedingSince = 0;
    const liveAudio = !sirenTestMode && (sirenAudioMode === "mic" || sirenAudioMode === "synthetic");
    if (sirenDetector.state === "CONFIRMED" && (liveAudio || (approachSimulationActive && !directionSelfCheckRunning)) &&
        !preemptionRequestPending && !preemptionScheduled && now - lastSirenTriggerTime >= SIREN_CONFIG.RETRIGGER_COOLDOWN_MS) {
      const vehicleId = $("#verified-vehicle")?.value || "";
      const directionReady = directionAnalysis.state === "APPROACHING" && directionAnalysis.rSquared >= DIRECTION_CONFIG.APPROACH_MIN_CONF;
      if (!vehicleId || directionReady) {
        const gate = evaluateDirectionGate("confirmed", false);
        lastSirenTriggerTime = now;
        triggerPreemptionOverride({ confirmed: true, label: sirenDetector.label,
          confidence: sirenDetector.confidence, stage: "confirmed", arm: gate.arm,
          approach: directionAnalysis.state.toLowerCase(), approach_conf: directionAnalysis.rSquared });
      }
    }
  }
}

function createStereoChannelAnalyser() {
  const channelAnalyser = audioCtx.createAnalyser();
  channelAnalyser.fftSize = SIREN_CONFIG.FFT_SIZE;
  channelAnalyser.smoothingTimeConstant = 0;
  return channelAnalyser;
}

function configureStereoMicHints(stream) {
  const settings = stream.getAudioTracks()[0]?.getSettings?.() || {};
  if (!Number.isFinite(Number(settings.channelCount)) || Number(settings.channelCount) < 2) return; // Mono/unknown devices skip silently.
  channelSplitter = audioCtx.createChannelSplitter(2);
  leftChannelAnalyser = createStereoChannelAnalyser();
  rightChannelAnalyser = createStereoChannelAnalyser();
  leftChannelData = new Float32Array(leftChannelAnalyser.fftSize);
  rightChannelData = new Float32Array(rightChannelAnalyser.fftSize);
  micSource.connect(channelSplitter);
  channelSplitter.connect(leftChannelAnalyser, 0);
  channelSplitter.connect(rightChannelAnalyser, 1);
}

function updateStereoHint() {
  if (!leftChannelAnalyser || !rightChannelAnalyser || !leftChannelData || !rightChannelData) return;
  leftChannelAnalyser.getFloatTimeDomainData(leftChannelData);
  rightChannelAnalyser.getFloatTimeDomainData(rightChannelData);
  let leftSquares = 0, rightSquares = 0;
  for (let i = 0; i < leftChannelData.length; i++) {
    leftSquares += leftChannelData[i] ** 2;
    rightSquares += rightChannelData[i] ** 2;
  }
  const levelDifferenceDb = 10 * Math.log10(Math.max(leftSquares, 1e-12) / Math.max(rightSquares, 1e-12));
  let bestLag = 0, bestCorrelation = -Infinity;
  const stride = 4;
  const maxLag = DIRECTION_CONFIG.STEREO_MAX_LAG_SAMPLES;
  for (let lag = -maxLag; lag <= maxLag; lag++) {
    let cross = 0, leftPower = 0, rightPower = 0;
    for (let i = maxLag; i < leftChannelData.length - maxLag; i += stride) {
      const j = i + lag;
      const left = leftChannelData[i], right = rightChannelData[j];
      cross += left * right;
      leftPower += left * left;
      rightPower += right * right;
    }
    const correlation = cross / Math.sqrt(Math.max(leftPower * rightPower, 1e-20));
    if (correlation > bestCorrelation) { bestCorrelation = correlation; bestLag = lag; }
  }
  const levelHint = Math.abs(levelDifferenceDb) < 1.5 ? "Balanced" : levelDifferenceDb > 0 ? "Left louder" : "Right louder";
  const delayMs = bestLag / audioCtx.sampleRate * 1000;
  stereoHint = `${levelHint}; lag ${delayMs.toFixed(2)} ms (supporting evidence)`;
}

function getActiveApproachDistance() {
  return approachSimulationActive || directionSelfCheckRunning
    ? Number($("#ambulance-sim-distance")?.value ?? approachDistanceM)
    : Number($("#preempt-dist")?.value || 0);
}

async function releasePreemptionEarly() {
  preemptionReleasePending = true;
  const junction_id = $("#preempt-junction")?.value || "J1";
  try {
    const result = await api("/api/preempt/release", { method: "POST", body: JSON.stringify({ junction_id }) });
    preemptionActive = false;
    toast("Ambulance moving away; starting amber and all-red clearance before normal cycle resumes.");
    await load();
    setTimeout(load, result.amber_seconds * 1000 + 100);
    setTimeout(load, (result.amber_seconds + result.all_red_seconds) * 1000 + 200);
  } catch (error) {
    console.error("Could not begin safe preemption release:", error);
  } finally {
    preemptionReleasePending = false;
    recedingSince = 0;
  }
}

function renderApproachSimulator() {
  const distance = Number($("#ambulance-sim-distance")?.value ?? approachDistanceM);
  const speed = Number($("#ambulance-sim-speed")?.value ?? $("#preempt-speed")?.value ?? 65);
  approachDistanceM = distance;
  const micRange = maxMicRangeM();
  const armed = distance <= RANGE_CONFIG.ARM_DISTANCE_M;
  const confirmed = distance <= micRange && sirenDetector.state === "CONFIRMED";
  const eta = speed > 0 ? distance / (speed / 3.6) : 0;
  const queue = calculateQueueDischarge(Number($("#preempt-cars")?.value || 14), Number($("#preempt-trucks")?.value || 3),
    Number($("#preempt-bikes")?.value || 22), 0, 2);
  const greenStartIn = eta - queue.high_sec;
  if ($("#ambulance-sim-distance-value")) $("#ambulance-sim-distance-value").textContent = `${Math.round(distance)} m`;
  if ($("#ambulance-sim-eta")) $("#ambulance-sim-eta").textContent = `${eta.toFixed(1)} s`;
  if ($("#approach-state")) $("#approach-state").textContent = confirmed ? "CONFIRMED" : armed ? "ARMED" : "IDLE";
  if ($("#approach-armed-at")) $("#approach-armed-at").textContent = `${RANGE_CONFIG.ARM_DISTANCE_M} m`;
  if ($("#approach-confirmed-at")) $("#approach-confirmed-at").textContent = `${Math.round(micRange)} m + siren`;
  if ($("#approach-queue-countdown")) $("#approach-queue-countdown").textContent = !armed
    ? "Waiting for network warning."
    : greenStartIn < 0
      ? "TOO LATE: queue will not clear in time."
      : `Green start countdown: ${greenStartIn.toFixed(1)}s using the HIGH queue estimate; green held.`;
  renderDirectionReadout();
}

async function triggerPreemptionOverride(sirenEvent) {
  const junction_id = $("#preempt-junction")?.value || "J1";
  const cars = parseInt($("#preempt-cars")?.value || 14);
  const trucks = parseInt($("#preempt-trucks")?.value || 3);
  const bikes = parseInt($("#preempt-bikes")?.value || 22);
  const vehicle_id = $("#verified-vehicle")?.value || "";
  const event = sirenEvent || { confirmed: false, label: "none", confidence: 0 };
  if (event.stage !== "confirmed" || !event.confirmed) return;
  const siren_confidence = Math.max(0, Math.min(1, Number(event.confidence) || 0));

  preemptionRequestPending = true;
  try {
    const unit_event_id = await postSignedAcousticEvent(event, junction_id);
    const res = await api("/api/preempt/trigger", {
      method: "POST",
      body: JSON.stringify({
        junction_id,
        cars,
        trucks,
        bikes,
        ...(vehicle_id ? { vehicle_id } : {}),
        siren_confidence,
        siren_confirmed: !!event.confirmed,
        unit_event_id,
        siren_label: event.label || "none",
        stage: event.stage,
        approach: event.approach,
        approach_conf: event.approach_conf,
      })
    });

    if (res.decision === "WAIT" || res.decision === "QUEUED") {
      preemptionScheduled = true;
      const scheduledVehicle = vehicle_id;
      const delayMs = res.decision === "WAIT"
        ? Math.max(250, (res.green_start_in - QUEUE_CONFIG.GREEN_START_EARLY_BUFFER_S) * 1000)
        : Math.max(1000, Number(res.retry_after_s || 2) * 1000);
      if ($("#dual-key-status")) $("#dual-key-status").textContent = res.decision === "QUEUED"
        ? "Ambulance queued by verified ETA: " + res.reason
        : "Queue discharge timing: " + res.reason;
      if (res.decision === "QUEUED") await load();
      setTimeout(() => {
        preemptionScheduled = false;
        const detectorStillConfirmed = sirenDetector.state === "CONFIRMED" && directionAnalysis.state === "APPROACHING" &&
          directionAnalysis.rSquared >= DIRECTION_CONFIG.APPROACH_MIN_CONF && $("#verified-vehicle")?.value === scheduledVehicle;
        if (detectorStillConfirmed) triggerPreemptionOverride(event);
        else if ($("#dual-key-status")) $("#dual-key-status").textContent = "Queue-discharge wait cancelled because the siren, direction, or selected vehicle is no longer confirmed.";
      }, delayMs);
    } else if (res.decision === "GRANTED") {
      preemptionScheduled = false;
      preemptionActive = true;
      await load();
      const gwEl = $("#svg-green-wave-corridor");
      if (gwEl) gwEl.classList.add("active");
      toast(`🚑 Emergency Green Wave Active! Queue Discharge T=${res.t_flush_sec}s (high ${res.t_flush_high_sec}s)`);
    } else if (res.decision === "RECOMMENDED") {
      if ($("#dual-key-status")) $("#dual-key-status").textContent = `${res.reason}. Advisory only; no phase changed.`;
      await load();
      toast("Advisory recommendation created. No signal phase changed.");
    } else if (res.decision === "APPLYING") {
      preemptionScheduled = false;
      if ($("#dual-key-status")) $("#dual-key-status").textContent = res.reason;
      await load();
      toast("Simulator is applying the interlocked phase sequence; no real controller is connected.");
    } else {
      if ($("#dual-key-status")) $("#dual-key-status").textContent = `${res.decision}: ${res.reason}`;
      toast(`${res.decision}: ${res.reason}`);
    }
  } catch (err) {
    console.error("Preempt error:", err);
    if ($("#dual-key-status")) $("#dual-key-status").textContent = `${err.data?.decision || "DENIED"}: ${err.message}`;
    toast(err.message || "Could not trigger emergency preemption");
  } finally {
    preemptionRequestPending = false;
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
    sirenTimeData = new Float32Array(analyser.fftSize);
    const silentSink = audioCtx.createGain();
    silentSink.gain.value = 0;
    analyser.connect(silentSink);
    silentSink.connect(audioCtx.destination);
  }
  return analyser;
}

function resetSirenDetector() {
  sirenHistory = [];
  rmsTrendPoints = [];
  directionAnalysis = { slopeDbS: 0, rSquared: 0, state: "UNKNOWN", dopplerHint: "—", dopplerOffsetHz: 0 };
  lastDirectionSampleAt = 0;
  sirenDetector.state = "IDLE";
  sirenDetector.label = "none";
  sirenDetector.confidence = 0;
  sirenDetector.lastPatternAt = 0;
  sirenDetector.candidateLabel = "none";
  sirenDetector.candidateSince = 0;
  sirenConfidence = 0;
  sirenLabel = "none";
  renderSirenReadout(null);
  renderDirectionReadout();
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
  updateDirectionAnalysis(now);
  renderSirenReadout(frame);
  renderApproachSimulator();
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

  // The analysis-side gain creates controlled level trends for direction tests.
  const analysisGain = audioCtx.createGain();
  const motion = settings.directionTest || "constant";
  const startedAt = audioCtx.currentTime;
  const duration = SIREN_CONFIG.TEST_SIGNAL_DURATION_MS / 1000;
  if (motion === "approach") {
    analysisGain.gain.setValueAtTime(0.08, startedAt);
    analysisGain.gain.linearRampToValueAtTime(0.9, startedAt + duration);
  } else if (motion === "recede") {
    analysisGain.gain.setValueAtTime(0.9, startedAt);
    analysisGain.gain.linearRampToValueAtTime(0.08, startedAt + duration);
  } else {
    analysisGain.gain.value = 0.4;
  }
  analysisGain.connect(analyser);
  activeSignalNodes.push(analysisGain);

  function connectTone(frequency, waveform) {
    const oscillator = audioCtx.createOscillator();
    oscillator.type = waveform || "sine";
    oscillator.frequency.value = frequency;
    if (settings.dopplerDirection === "approach") oscillator.detune.value = DIRECTION_CONFIG.DOPPLER_TEST_SHIFT_CENTS;
    if (settings.dopplerDirection === "recede") oscillator.detune.value = -DIRECTION_CONFIG.DOPPLER_TEST_SHIFT_CENTS;
    oscillator.connect(analysisGain);
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
    source.connect(analysisGain);
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
        micStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: { ideal: 2 } }, video: false });
        micSource = audioCtx.createMediaStreamSource(micStream);
        micSource.connect(analyser);
        configureStereoMicHints(micStream);
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
  if (channelSplitter) { try { channelSplitter.disconnect(); } catch (error) {} }
  [leftChannelAnalyser, rightChannelAnalyser].forEach(node => { if (node) { try { node.disconnect(); } catch (error) {} } });
  channelSplitter = leftChannelAnalyser = rightChannelAnalyser = null;
  leftChannelData = rightChannelData = null;
  stereoHint = "—";
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

function bytesToBase64(bytes) {
  let binary = "";
  new Uint8Array(bytes).forEach(byte => { binary += String.fromCharCode(byte); });
  return btoa(binary);
}

const unitDbName = "dome-flow-junction-unit-keys";
let junctionUnitDb;
function openJunctionUnitDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(unitDbName, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("units", { keyPath: "junction_id" });
    request.onsuccess = () => { junctionUnitDb = request.result; resolve(request.result); };
    request.onerror = () => reject(request.error);
  });
}
function readJunctionKey(junctionId) {
  return new Promise((resolve, reject) => {
    const request = junctionUnitDb.transaction("units").objectStore("units").get(junctionId);
    request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
  });
}
function saveJunctionKey(record) {
  return new Promise((resolve, reject) => {
    const tx = junctionUnitDb.transaction("units", "readwrite"); tx.objectStore("units").put(record);
    tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
  });
}
const canonicalSignedJson = data => JSON.stringify(Object.fromEntries(Object.keys(data).sort().map(key => [key, data[key]])));
const randomNonce = () => bytesToBase64(crypto.getRandomValues(new Uint8Array(18))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function enrollJunctionUnit(junctionId) {
  if (!junctionUnitDb) await openJunctionUnitDb();
  let keyRecord = await readJunctionKey(junctionId);
  if (!keyRecord) {
    const pair = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, false, ["sign", "verify"]);
    keyRecord = { junction_id: junctionId, unit_id: `demo-unit-${junctionId}`, privateKey: pair.privateKey, publicKey: pair.publicKey };
    await saveJunctionKey(keyRecord);
  }
  const publicKey = bytesToBase64(await crypto.subtle.exportKey("spki", keyRecord.publicKey));
  const enrollment = await api("/api/unit/enroll", { method: "POST", body: JSON.stringify({ unit_id: keyRecord.unit_id, junction_id: junctionId, public_key: publicKey }) });
  if ($("#junction-unit-status")) $("#junction-unit-status").textContent = `${keyRecord.unit_id}: ${enrollment.status}. Admin approval is required.`;
  await refreshDualKeyData();
  return keyRecord;
}

async function postSignedAcousticEvent(event, junctionId) {
  const keyRecord = await enrollJunctionUnit(junctionId);
  const payload = {
    unit_id: keyRecord.unit_id, junction_id: junctionId,
    timestamp: Math.floor(Date.now() / 1000), nonce: randomNonce(),
    label: event.label, confidence: Number(event.confidence) || 0,
    approach: directionAnalysis.state.toLowerCase(),
    slope: Number(directionAnalysis.slopeDbS.toFixed(2)),
    r_squared: Number(directionAnalysis.rSquared.toFixed(4))
  };
  const signature = bytesToBase64(await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, keyRecord.privateKey,
    new TextEncoder().encode(canonicalSignedJson(payload))));
  const result = await api("/api/unit/event", { method: "POST", body: JSON.stringify({ ...payload, signature }) });
  return result.event_id;
}

function pointAtDistance(distanceM, headingDeg) {
  const radius = 6371000, lat1 = 13.3110 * Math.PI / 180, lon1 = 76.9410 * Math.PI / 180;
  const bearing = ((headingDeg + 180) % 360) * Math.PI / 180, delta = distanceM / radius;
  const lat2 = Math.asin(Math.sin(lat1) * Math.cos(delta) + Math.cos(lat1) * Math.sin(delta) * Math.cos(bearing));
  const lon2 = lon1 + Math.atan2(Math.sin(bearing) * Math.sin(delta) * Math.cos(lat1), Math.cos(delta) - Math.sin(lat1) * Math.sin(lat2));
  return [lat2 * 180 / Math.PI, lon2 * 180 / Math.PI];
}

async function createAttackVehicle(vehicleId) {
  const pair = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, false, ["sign", "verify"]);
  const pub = bytesToBase64(await crypto.subtle.exportKey("spki", pair.publicKey));
  const enrolled = await fetch("/api/vehicle/enroll", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ vehicle_id: vehicleId, public_key: pub }) }).then(r => r.json());
  if (!enrolled.ok) throw Error(enrolled.reason);
  const admin = $("#admin-token")?.value || "";
  const approval = await fetch(`/api/dev/vehicle/${encodeURIComponent(vehicleId)}/status`, { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Token": admin }, body: JSON.stringify({ status: "approved" }) }).then(async r => ({ ok: r.ok, data: await r.json() }));
  if (!approval.ok) throw Error(approval.data.reason);
  return { vehicleId, privateKey: pair.privateKey };
}

async function signedAttackReport(fixture, distanceM, heading = 10, speed = 55, timestamp = Math.floor(Date.now() / 1000)) {
  const [lat, lon] = pointAtDistance(distanceM, heading);
  const nonce = bytesToBase64(crypto.getRandomValues(new Uint8Array(18))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const payload = { vehicle_id: fixture.vehicleId, lat: lat.toFixed(7), lon: lon.toFixed(7), heading_deg: heading.toFixed(2), speed_kmh: speed.toFixed(2), timestamp, nonce };
  const canonical = JSON.stringify(Object.fromEntries(Object.keys(payload).sort().map(key => [key, payload[key]])));
  const signature = bytesToBase64(await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, fixture.privateKey, new TextEncoder().encode(canonical)));
  return { ...payload, signature };
}

async function createAttackUnit(unitId, junctionId, status = "approved") {
  const pair = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, false, ["sign", "verify"]);
  const public_key = bytesToBase64(await crypto.subtle.exportKey("spki", pair.publicKey));
  const enrolled = await attackPost("/api/unit/enroll", { unit_id: unitId, junction_id: junctionId, public_key });
  if (!enrolled.ok) throw Error(enrolled.reason);
  if (status !== "pending") {
    const approval = await attackPost(`/api/dev/unit/${encodeURIComponent(unitId)}/status`, { status }, { "X-Admin-Token": $("#admin-token")?.value || "" });
    if (!approval.ok) throw Error(approval.reason);
  }
  return { unitId, junctionId, privateKey: pair.privateKey };
}

async function signedAttackAcoustic(fixture, junctionId = fixture.junctionId) {
  const payload = { unit_id: fixture.unitId, junction_id: junctionId, timestamp: Math.floor(Date.now() / 1000), nonce: randomNonce(),
    label: "wail", confidence: 0.95, approach: "approaching", slope: 2.5, r_squared: 0.95 };
  const signature = bytesToBase64(await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, fixture.privateKey,
    new TextEncoder().encode(canonicalSignedJson(payload))));
  return { ...payload, signature };
}

async function attackPost(url, body, headers = {}) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body) });
  const data = await response.json().catch(() => ({}));
  return { ok: response.ok, status: response.status, ...data };
}

async function runDualKeyAttack(name) {
  const selectedJunction = "J2"; // Attack fixtures are positioned relative to the demo ambulance page's J2 location.
  const trigger = (vehicle_id, unit_event_id = null, stage = "confirmed") => attackPost("/api/preempt/trigger", { junction_id: selectedJunction, vehicle_id, stage, siren_confirmed: true, unit_event_id, cars: 0, trucks: 0, bikes: 0 });
  let result;
  if (name === "recorded") result = await trigger(null);
  else if (name === "replay") {
    const fixture = await createAttackVehicle(`atk-replay-${Date.now()}`), signed = await signedAttackReport(fixture, 130);
    await attackPost("/api/vehicle/report", signed); result = await attackPost("/api/vehicle/report", signed);
  } else if (name === "tamper") {
    const fixture = await createAttackVehicle(`atk-tamper-${Date.now()}`), signed = await signedAttackReport(fixture, 130);
    signed.lat = pointAtDistance(5000, 10)[0].toFixed(7); result = await attackPost("/api/vehicle/report", signed);
  } else if (name === "revoked") {
    const fixture = await createAttackVehicle(`atk-revoked-${Date.now()}`);
    await attackPost(`/api/dev/vehicle/${fixture.vehicleId}/status`, { status: "revoked" }, { "X-Admin-Token": $("#admin-token")?.value || "" });
    result = await trigger(fixture.vehicleId);
  } else if (name === "teleport") {
    const fixture = await createAttackVehicle(`atk-teleport-${Date.now()}`), first = await signedAttackReport(fixture, 300);
    await attackPost("/api/vehicle/report", first);
    await new Promise(resolve => setTimeout(resolve, 1100));
    result = await attackPost("/api/vehicle/report", await signedAttackReport(fixture, 5300));
  } else if (["unknown-unit", "revoked-unit", "replay-event", "wrong-junction", "valid"].includes(name)) {
    const fixture = await createAttackVehicle(`atk-${name.replaceAll("-", "")}-${Date.now()}`);
    await attackPost("/api/vehicle/report", await signedAttackReport(fixture, 50, 10, 18));
    await new Promise(resolve => setTimeout(resolve, 1050));
    await attackPost("/api/vehicle/report", await signedAttackReport(fixture, 30, 10, 18));
    const unit = await createAttackUnit(`unit-${name.replaceAll("-", "")}-${Date.now()}`, name === "wrong-junction" ? "J1" : selectedJunction,
      name === "revoked-unit" ? "revoked" : "approved");
    let signed = await signedAttackAcoustic(unit, name === "wrong-junction" ? selectedJunction : unit.junctionId);
    if (name === "unknown-unit") {
      unit.unitId = `missing-${Date.now()}`;
      signed = await signedAttackAcoustic(unit);
      result = await attackPost("/api/unit/event", signed);
    } else if (name === "revoked-unit" || name === "wrong-junction") result = await attackPost("/api/unit/event", signed);
    else if (name === "replay-event") {
      await attackPost("/api/unit/event", signed); result = await attackPost("/api/unit/event", signed);
    } else {
      const eventResult = await attackPost("/api/unit/event", signed);
      if (!eventResult.ok) result = eventResult;
      else result = await trigger(fixture.vehicleId, eventResult.event_id);
    }
  } else {
    const fixture = await createAttackVehicle(`atk-valid-${Date.now()}`);
    await attackPost("/api/vehicle/report", await signedAttackReport(fixture, 50, 10, 18));
    await new Promise(resolve => setTimeout(resolve, 1100));
    await attackPost("/api/vehicle/report", await signedAttackReport(fixture, 30, 10, 18));
    result = await trigger(fixture.vehicleId);
  }
  const selectedMode = currentSummary?.junctions?.find(j => j.id === selectedJunction)?.controller_mode || "ADVISORY";
  const passed = name === "valid"
    ? (selectedMode === "ADVISORY" ? result.decision === "RECOMMENDED" : result.decision === "APPLYING")
    : name === "recorded" || name === "unknown-unit" || name === "revoked-unit" ? result.decision === "WATCH" || result.decision === "DENIED"
      : !result.ok;
  const line = `${passed ? "PASS" : "FAIL"} ${name}: ${result.decision || result.reason || result.status} — ${result.reason || ""}`;
  console[passed ? "log" : "error"](line);
  if ($("#dual-key-status")) $("#dual-key-status").textContent = line;
  await refreshDualKeyData();
  return passed;
}

async function refreshDualKeyData() {
  const [vehicles, units, audit] = await Promise.all([fetch("/api/vehicles").then(r => r.json()), fetch("/api/units").then(r => r.json()), fetch("/api/audit").then(r => r.json())]);
  latestVerifiedVehicleReports = Object.fromEntries(vehicles.vehicles
    .filter(vehicle => vehicle.status === "approved" && vehicle.junctions)
    .map(vehicle => [vehicle.vehicle_id, vehicle.junctions]));
  const selected = $("#verified-vehicle")?.value;
  if ($("#verified-vehicle")) $("#verified-vehicle").innerHTML = '<option value="">No vehicle selected</option>' + vehicles.vehicles.filter(v => v.status === "approved").map(v => `<option value="${v.vehicle_id}">${v.vehicle_id}</option>`).join("");
  if (selected && $("#verified-vehicle")) $("#verified-vehicle").value = selected;
  if ($("#vehicle-registry-body")) $("#vehicle-registry-body").innerHTML = vehicles.vehicles.map(v => `<tr><td>${v.vehicle_id}</td><td>${v.status}</td><td>${v.last_report_at || "—"}</td><td>${v.status === "approved" ? `<button data-admin-status="revoked" data-vehicle="${v.vehicle_id}">Revoke</button>` : `<button data-admin-status="approved" data-vehicle="${v.vehicle_id}">Approve</button>`}</td></tr>`).join("");
  $("#vehicle-registry-body")?.querySelectorAll("[data-admin-status]").forEach(button => button.addEventListener("click", async () => {
    const result = await attackPost(`/api/dev/vehicle/${encodeURIComponent(button.dataset.vehicle)}/status`, { status: button.dataset.adminStatus }, { "X-Admin-Token": $("#admin-token")?.value || "" });
    if (!result.ok) toast(result.reason); await refreshDualKeyData();
  }));
  if ($("#unit-registry-body")) $("#unit-registry-body").innerHTML = units.units.map(u => `<tr><td>${u.unit_id}</td><td>${u.junction_id}</td><td>${u.status}</td><td>${u.last_event_at || "—"}</td><td><button data-unit-status="${u.status === "approved" ? "revoked" : "approved"}" data-unit="${u.unit_id}">${u.status === "approved" ? "Revoke" : "Approve"}</button></td></tr>`).join("");
  $("#unit-registry-body")?.querySelectorAll("[data-unit-status]").forEach(button => button.addEventListener("click", async () => {
    const result = await attackPost(`/api/dev/unit/${encodeURIComponent(button.dataset.unit)}/status`, { status: button.dataset.unitStatus }, { "X-Admin-Token": $("#admin-token")?.value || "" });
    if (!result.ok) toast(result.reason); await refreshDualKeyData();
  }));
  if ($("#audit-chain-status")) $("#audit-chain-status").textContent = audit.chain_valid ? "CHAIN VALID" : "CHAIN BROKEN";
  if ($("#audit-log-body")) $("#audit-log-body").innerHTML = audit.entries.slice().reverse().map(e => `<tr><td>${e.decision}</td><td>${e.reason}</td><td>${e.vehicle_id || "—"}</td><td>${e.junction || "—"}</td><td>${e.timestamp}</td></tr>`).join("");
  updateLiveMath();
}

function initDualKeyTools(panel, enabled) {
  panel.querySelectorAll("[data-attack]").forEach(button => button.addEventListener("click", () => runDualKeyAttack(button.dataset.attack).catch(error => { console.error(error); toast(error.message); })));
  $("#vehicle-refresh")?.addEventListener("click", refreshDualKeyData);
  $("#junction-unit-enroll")?.addEventListener("click", async () => {
    try { await enrollJunctionUnit($("#preempt-junction")?.value || "J2"); }
    catch (error) { if ($("#junction-unit-status")) $("#junction-unit-status").textContent = error.message; }
  });
  $("#attack-self-check")?.addEventListener("click", async () => {
    console.group("Dual-key spoof resistance self-check");
    for (const name of ["recorded", "replay", "tamper", "revoked", "teleport", "valid", "unknown-unit", "revoked-unit", "replay-event", "wrong-junction"]) await runDualKeyAttack(name);
    console.groupEnd();
  });
  if (enabled) refreshDualKeyData().catch(console.error);
}

function initSirenTestPanel() {
  const panel = $("#siren-test-panel");
  if (!panel) return;
  const rangeDefaults = {
    "#range-spl": RANGE_CONFIG.SIREN_SPL_REF_DB,
    "#range-ref-dist": RANGE_CONFIG.REF_DIST_M,
    "#range-noise": RANGE_CONFIG.TRAFFIC_NOISE_DB,
    "#range-min-snr": RANGE_CONFIG.MIN_SNR_DB
  };
  Object.entries(rangeDefaults).forEach(([selector, value]) => {
    const input = $(selector);
    if (input && !input.value) input.value = value;
  });
  const enabled = new URLSearchParams(window.location.search).get("dev") === "1";
  panel.hidden = !enabled;
  initDualKeyTools(panel, enabled);
  panel.querySelectorAll("[data-siren-test]").forEach(button => {
    button.addEventListener("click", () => startSirenSignal(button.dataset.sirenTest, { testMode: true }));
  });
  const selfCheckButton = $("#siren-self-check");
  if (selfCheckButton) selfCheckButton.addEventListener("click", runSirenSelfCheck);
  const rangeInputs = ["#range-spl", "#range-ref-dist", "#range-noise", "#range-min-snr"];
  rangeInputs.forEach(selector => $(selector)?.addEventListener("input", renderRangeEstimate));
  ["#ambulance-sim-distance", "#ambulance-sim-speed"].forEach(selector =>
    $(selector)?.addEventListener("input", renderApproachSimulator));
  $("#ambulance-sim-heading")?.addEventListener("input", renderDirectionReadout);
  $("#preempt-junction")?.addEventListener("change", renderDirectionReadout);
  panel.querySelectorAll("[data-direction-test]").forEach(button => {
    button.addEventListener("click", () => {
      const motion = button.dataset.directionTest;
      const dopplerDirection = motion === "approach" ? "approach" : motion === "recede" ? "recede" : "none";
      approachSimulationActive = motion === "recede" && preemptionActive;
      startSirenSignal("wail", { testMode: true, directionTest: motion, dopplerDirection });
      if (approachSimulationActive) {
        setTimeout(() => { approachSimulationActive = false; }, SIREN_CONFIG.TEST_SIGNAL_DURATION_MS + 100);
      }
      if ($("#siren-test-playing")) $("#siren-test-playing").textContent = `Synthetic ${motion} level and Doppler test is running locally; no audio is uploaded.`;
      renderDirectionReadout();
    });
  });
  $("#direction-self-check")?.addEventListener("click", runDirectionSelfCheck);
  $("#ambulance-sim-run")?.addEventListener("click", runAmbulanceApproach);
  $("#ambulance-sim-siren")?.addEventListener("click", () => {
    simulateApproachSiren();
  });
  renderRangeEstimate();
}

function simulateApproachSiren() {
  const distance = Number($("#ambulance-sim-distance")?.value ?? approachDistanceM);
  const speed = Number($("#ambulance-sim-speed")?.value || 65);
  if (distance > maxMicRangeM()) {
    toast("Move the simulated ambulance into the estimated microphone range first.");
    return;
  }
  approachSimulationActive = true;
  if (!startSirenSignal("wail", { testMode: true, directionTest: "approach", dopplerDirection: "approach" })) {
    approachSimulationActive = false;
    return;
  }
  const deadline = performance.now() + SIREN_CONFIG.TEST_SIGNAL_DURATION_MS;
  const check = setInterval(() => {
    if (preemptionActive || preemptionRequestPending) {
      clearInterval(check);
      approachSimulationActive = false;
    } else if (performance.now() >= deadline || distance > maxMicRangeM()) {
      clearInterval(check);
      approachSimulationActive = false;
    }
  }, SIREN_CONFIG.SAMPLE_INTERVAL_MS);
}

async function runDirectionSelfCheck() {
  if (micStream) {
    console.warn("Direction self-check: stop the live microphone first.");
    return;
  }
  const junctionId = $("#preempt-junction")?.value || "J1";
  const correctArm = JUNCTION_ARMS[junctionId]?.[0];
  if (!correctArm) return;
  const cases = [
    { motion: "approach", heading: correctArm.bearing, expected: true },
    { motion: "recede", heading: correctArm.bearing, expected: false },
    { motion: "constant", heading: correctArm.bearing, expected: false },
    { motion: "approach", heading: (correctArm.bearing + DIRECTION_CONFIG.ARM_TOLERANCE_DEG + 10) % 360, expected: false }
  ];
  const previousDistance = $("#ambulance-sim-distance")?.value;
  const previousHeading = $("#ambulance-sim-heading")?.value;
  if ($("#ambulance-sim-distance")) $("#ambulance-sim-distance").value = String(Math.max(0, Math.floor(maxMicRangeM() / 2)));
  approachSimulationActive = false;
  directionSelfCheckRunning = true;
  const results = [];
  console.group("DOME Flow approach/recede and arm self-check");
  for (const testCase of cases) {
    $("#ambulance-sim-heading").value = testCase.heading;
    resetSirenDetector();
    directionAnalysis = { slopeDbS: 0, rSquared: 0, state: "UNKNOWN", dopplerHint: "—", dopplerOffsetHz: 0 };
    rmsTrendPoints = [];
    const dopplerDirection = testCase.motion === "approach" ? "approach" : testCase.motion === "recede" ? "recede" : "none";
    startSirenSignal("wail", { testMode: true, directionTest: testCase.motion, dopplerDirection });
    await waitForSirenTest(SIREN_CONFIG.TEST_SIGNAL_DURATION_MS);
    const detectorConfirmed = sirenDetector.state === "CONFIRMED";
    const gate = evaluateDirectionGate(detectorConfirmed ? "confirmed" : "armed");
    const granted = detectorConfirmed && gate.allowed;
    const passed = granted === testCase.expected;
    const result = {
      motion: testCase.motion,
      heading: testCase.heading,
      approach: directionAnalysis.state,
      slopeDbS: Number(directionAnalysis.slopeDbS.toFixed(2)),
      rSquared: Number(directionAnalysis.rSquared.toFixed(2)),
      doppler: directionAnalysis.dopplerHint,
      arm: gate.arm || "unknown",
      expected: testCase.expected ? "granted" : "denied",
      actual: granted ? "granted" : gate.reason,
      result: passed ? "PASS" : "FAIL"
    };
    results.push(result);
    console.log(result.result + " — " + result.motion, result);
    stopGeneratedSignal();
    resetSirenDetector();
    directionAnalysis = { slopeDbS: 0, rSquared: 0, state: "UNKNOWN", dopplerHint: "—", dopplerOffsetHz: 0 };
    await waitForSirenTest(DIRECTION_CONFIG.SAMPLE_INTERVAL_MS * 2);
  }
  console.table(results);
  console.groupEnd();
  directionSelfCheckRunning = false;
  if ($("#ambulance-sim-distance") && previousDistance !== undefined) $("#ambulance-sim-distance").value = previousDistance;
  if ($("#ambulance-sim-heading") && previousHeading !== undefined) $("#ambulance-sim-heading").value = previousHeading;
  renderApproachSimulator();
}

function runAmbulanceApproach() {
  clearInterval(approachTimer);
  const distanceInput = $("#ambulance-sim-distance");
  const speed = Number($("#ambulance-sim-speed")?.value || 65);
  if (!distanceInput || speed <= 0) return;
  distanceInput.value = 600;
  approachDistanceM = 600;
  approachSimulationActive = true;
  resetSirenDetector();
  let lastDistance = 600;
  approachTimer = setInterval(() => {
    const current = Math.max(0, Number(distanceInput.value) - speed / 3.6 * 0.25);
    distanceInput.value = current.toFixed(0);
    approachDistanceM = current;
    if (lastDistance > RANGE_CONFIG.ARM_DISTANCE_M && current <= RANGE_CONFIG.ARM_DISTANCE_M) {
      const eta = speed > 0 ? current / (speed / 3.6) : 0;
      api("/api/preempt/trigger", {
        method: "POST",
        body: JSON.stringify({ stage: "armed", distance_m: current, eta_s: eta })
      }).catch(error => console.warn("Approach arm notification failed:", error));
    }
    if (current <= maxMicRangeM() && !activeSignalNodes.length) {
      startSirenSignal("wail", { testMode: true, directionTest: "approach", dopplerDirection: "approach" });
    }
    renderApproachSimulator();
    lastDistance = current;
    if (preemptionActive || preemptionRequestPending || current <= 0) {
      clearInterval(approachTimer);
      approachSimulationActive = false;
    }
  }, 250);
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
  $("#verified-vehicle")?.addEventListener("change", updateLiveMath);
  $("#queue-self-check")?.addEventListener("click", runQueueModelSelfCheck);
  $("#harm-self-check")?.addEventListener("click", runHarmSelfCheck);
  $("#controller-self-check")?.addEventListener("click", runControllerSelfCheck);
  $("#junctions-grid")?.addEventListener("change", event => {
    const select = event.target.closest("[data-controller-mode]");
    if (select) updateControllerMode(select.dataset.junction, select.value);
  });
  $("#controller-recommendation")?.addEventListener("click", event => {
    const action = event.target.closest("[data-recommendation-action]")?.dataset.recommendationAction;
    if (action) handleRecommendation(action);
  });
  $("#controller-manual-override")?.addEventListener("click", requestManualOverride);

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

  if ($("#btn-trigger-preempt")) $("#btn-trigger-preempt").onclick = () => {
    toast("Manual override is gated. Use a confirmed close-range siren pattern to simulate preemption.");
  };
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
setInterval(load, 5000);
controllerHeartbeat("decision");
setInterval(() => {
  controllerHeartbeat("decision");
  if (isMicActive) controllerHeartbeat("input");
}, 1000);
function tickHarmCountdowns() {
  document.querySelectorAll(".harm-countdown[data-seconds]").forEach(el => {
    const next = Math.max(0, Number(el.dataset.seconds || 0) - 1);
    el.dataset.seconds = String(next);
    el.textContent = `${Math.ceil(next)}s`;
  });
}
setInterval(tickHarmCountdowns, 1000);
