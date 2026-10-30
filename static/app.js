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

async function triggerPreemptionOverride() {
  const junction_id = $("#preempt-junction")?.value || "J1";
  const cars = parseInt($("#preempt-cars")?.value || 14);
  const trucks = parseInt($("#preempt-trucks")?.value || 3);
  const bikes = parseInt($("#preempt-bikes")?.value || 22);
  const ambulance_dist_m = parseFloat($("#preempt-dist")?.value || 450);
  const ambulance_speed_kmh = parseFloat($("#preempt-speed")?.value || 65);
  const siren_confidence = Math.max(sirenConfidence / 100, 0.94);

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
        siren_confidence
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

// Web Audio API Siren FFT Engine
let audioCtx = null, analyser = null, micStream = null, isMicActive = false;
let sirenConfidence = 0, sirenLockStartTime = 0, lastSirenTriggerTime = 0;
let synthOsc = null, synthGain = null, synthLfo = null, micPermissionFailed = false;

function checkSirenTrigger() {
  const threshold = parseInt($("#siren-threshold")?.value || 65);
  const now = Date.now();

  if (sirenConfidence >= threshold) {
    if (!sirenLockStartTime) {
      sirenLockStartTime = now;
    } else if (now - sirenLockStartTime >= 1200) {
      if (now - lastSirenTriggerTime >= 8000) {
        lastSirenTriggerTime = now;
        sirenLockStartTime = 0;
        toast("🎙️ Acoustic Siren Locked (650-1450Hz) — Auto-Preempting Junction!");
        triggerPreemptionOverride();
      }
    }
  } else {
    sirenLockStartTime = 0;
  }
}

function initFFTCanvas() {
  const canvas = $("#siren-fft-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;

  function draw() {
    requestAnimationFrame(draw);
    ctx.clearRect(0, 0, W, H);

    // Subtle background grid
    ctx.strokeStyle = "rgba(56, 189, 248, 0.08)";
    ctx.lineWidth = 1;
    for (let x = 0; x < W; x += 35) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
    }
    for (let y = 0; y < H; y += 22) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }

    if (analyser && isMicActive) {
      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      analyser.getByteFrequencyData(dataArray);

      const barWidth = (W / bufferLength) * 2.3;
      let inBandEnergy = 0, totalEnergy = 0, inBandCount = 0;
      const nyquist = (audioCtx.sampleRate || 48000) / 2;

      for (let i = 0; i < bufferLength; i++) {
        const val = dataArray[i];
        totalEnergy += val;
        const freq = (i / bufferLength) * nyquist;
        const isInBand = freq >= 650 && freq <= 1450;

        if (isInBand) {
          inBandEnergy += val;
          inBandCount++;
        }

        const barHeight = (val / 255) * (H - 14);
        const x = i * barWidth;
        const y = H - barHeight;

        if (isInBand) {
          ctx.fillStyle = val > 150 ? "#ff707d" : "#10b981";
          ctx.shadowColor = val > 150 ? "#ff707d" : "#10b981";
          ctx.shadowBlur = 8;
        } else {
          ctx.fillStyle = "rgba(56, 189, 248, 0.35)";
          ctx.shadowBlur = 0;
        }
        ctx.fillRect(x, y, Math.max(1, barWidth - 1.5), barHeight);
      }
      ctx.shadowBlur = 0;

      const avgInBand = inBandCount > 0 ? (inBandEnergy / inBandCount) : 0;
      const avgTotal = bufferLength > 0 ? (totalEnergy / bufferLength) : 0;
      const ratio = avgTotal > 5 ? (avgInBand / Math.max(avgTotal, 1)) : 0;

      let conf = 0;
      if (avgInBand > 45) {
        conf = Math.min(100, Math.round(Math.min(ratio * 48, 100) * (avgInBand / 190)));
      }
      sirenConfidence = conf;
    } else {
      // Idle ambient baseline spectrum
      const time = Date.now() * 0.003;
      const bars = 48;
      const barWidth = W / bars;
      for (let i = 0; i < bars; i++) {
        const freqRatio = i / bars;
        const isSirenBand = freqRatio >= 0.18 && freqRatio <= 0.42;
        const baseHeight = 10 + Math.sin(time + i * 0.3) * 8 + Math.cos(time * 0.7 + i * 0.15) * 5;
        const barHeight = Math.max(4, baseHeight);
        const x = i * barWidth;
        const y = H - barHeight;

        ctx.fillStyle = isSirenBand ? "rgba(16, 185, 129, 0.42)" : "rgba(56, 189, 248, 0.2)";
        ctx.fillRect(x, y, barWidth - 2, barHeight);
      }
      sirenConfidence = 0;
    }

    // Siren Band 650Hz–1450Hz Highlighted Overlay
    const bandStart = W * 0.18;
    const bandWidth = W * 0.24;
    ctx.fillStyle = "rgba(16, 185, 129, 0.07)";
    ctx.fillRect(bandStart, 0, bandWidth, H);
    ctx.strokeStyle = "rgba(16, 185, 129, 0.35)";
    ctx.lineWidth = 1;
    ctx.strokeRect(bandStart, 0, bandWidth, H);

    ctx.fillStyle = "#34d399";
    ctx.font = "8px 'JetBrains Mono', monospace";
    ctx.fillText("SIREN BAND 650Hz–1450Hz", bandStart + 4, 12);

    // Update confidence badge
    if ($("#siren-confidence")) {
      $("#siren-confidence").textContent = `${sirenConfidence}%`;
      $("#siren-confidence").style.color = sirenConfidence >= 65 ? "#34d399" : (sirenConfidence >= 35 ? "#fbbf24" : "#94a3b8");
    }

    checkSirenTrigger();
  }
  draw();
}

function startSyntheticSiren() {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();

    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;

    synthOsc = audioCtx.createOscillator();
    synthGain = audioCtx.createGain();
    synthOsc.type = "sawtooth";
    synthGain.gain.value = 0.08;

    synthLfo = audioCtx.createOscillator();
    const lfoGain = audioCtx.createGain();
    synthLfo.frequency.value = 0.8;
    lfoGain.gain.value = 350;

    synthOsc.frequency.value = 1050;
    synthLfo.connect(lfoGain);
    lfoGain.connect(synthOsc.frequency);
    synthLfo.start();

    synthOsc.connect(analyser);
    analyser.connect(synthGain);
    synthGain.connect(audioCtx.destination);
    synthOsc.start();

    isMicActive = true;
    if ($("#btn-mic-toggle")) $("#btn-mic-toggle").innerHTML = "⏹️ Stop Siren (Synthetic)";
    if ($("#siren-status-badge")) {
      $("#siren-status-badge").className = "status-tag in-progress";
      $("#siren-status-badge").textContent = "Synthetic Siren Active";
    }
    toast("🎙️ Live Mic unavailable — Running Synthetic Doppler Siren demo");
  } catch (err) {
    console.error("Synthetic siren error:", err);
  }
}

async function toggleMic() {
  if (isMicActive) {
    stopMic();
    return;
  }

  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") await audioCtx.resume();

    if (!micPermissionFailed && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        const source = audioCtx.createMediaStreamSource(micStream);
        source.connect(analyser);
        isMicActive = true;
        if ($("#btn-mic-toggle")) $("#btn-mic-toggle").innerHTML = "⏹️ Stop Live Mic";
        if ($("#siren-status-badge")) {
          $("#siren-status-badge").className = "status-tag resolved";
          $("#siren-status-badge").textContent = "Listening (Live Mic)";
        }
        toast("🎙️ Live Microphone FFT Spectrum Active");
        return;
      } catch (micErr) {
        console.warn("Microphone access failed/denied, activating synthetic Doppler siren backup:", micErr);
        micPermissionFailed = true;
      }
    }
    startSyntheticSiren();
  } catch (e) {
    console.warn("AudioContext error, activating synthetic siren backup:", e);
    startSyntheticSiren();
  }
}

function stopMic() {
  if (micStream) {
    micStream.getTracks().forEach(t => t.stop());
    micStream = null;
  }
  if (synthOsc) {
    try {
      synthOsc.stop();
      synthOsc.disconnect();
      if (synthLfo) { synthLfo.stop(); synthLfo.disconnect(); }
    } catch (e) {}
    synthOsc = null;
    synthLfo = null;
  }
  isMicActive = false;
  sirenConfidence = 0;
  if ($("#btn-mic-toggle")) $("#btn-mic-toggle").innerHTML = "🎙️ Start Live Siren Mic (FFT)";
  if ($("#siren-status-badge")) {
    $("#siren-status-badge").className = "status-tag in-progress";
    $("#siren-status-badge").textContent = "Acoustic Standby";
  }
  if ($("#siren-confidence")) $("#siren-confidence").textContent = "0%";
  toast("Mic stopped");
}

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

  if ($("#siren-threshold")) {
    $("#siren-threshold").addEventListener("input", e => {
      if ($("#thresh-val")) $("#thresh-val").textContent = `${e.target.value}%`;
    });
  }

  initFFTCanvas();
  updateLiveMath();
}

// ==========================================
// 4. MODULE B: CROWD-TELEMATICS PROBE WIRING
// ==========================================

async function triggerSimShock() {
  const corridor = $("#shock-corridor")?.value || (currentSummary?.active_scenario || "nh206");
  const z_jerk = parseFloat($("#shock-jerk")?.value || 24.5);
  const speed_kmh = parseFloat($("#shock-speed")?.value || 48);

  try {
    const res = await api("/api/telematics/shock", {
      method: "POST",
      body: JSON.stringify({ corridor, z_jerk, speed_kmh })
    });

    if (res.status === "filtered_noise") {
      toast("⚠️ Ignored by Spatial Filter: Speed < 15 km/h or Jerk < 15 m/s³");
    } else if (res.status === "clustering") {
      const pct = Math.round((res.hits / 3) * 100);
      if ($("#cluster-progress-bar")) $("#cluster-progress-bar").style.width = `${pct}%`;
      if ($("#cluster-status-text")) $("#cluster-status-text").textContent = `${res.hits} / 3 Hits — Spatial Cluster Accumulating`;
      toast(`💥 Shock Registered (${res.hits}/3) — Spatial Cluster Accumulating`);
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
let lastAcc = { x: 0, y: 0, z: 9.8 };
let lastMotionTime = Date.now();

function handleMotion(e) {
  const acc = e.accelerationIncludingGravity || e.acceleration;
  if (!acc) return;
  const now = Date.now();
  const dt = (now - lastMotionTime) / 1000;
  if (dt < 0.08) return;

  const z = acc.z !== null ? acc.z : 9.8;
  const jerk = Math.abs((z - lastAcc.z) / Math.max(dt, 0.05));
  lastAcc = { x: acc.x, y: acc.y, z };
  lastMotionTime = now;

  const jerkVal = Math.min(50, Math.round(jerk * 10) / 10);
  if ($("#shock-jerk")) $("#shock-jerk").value = jerkVal;
  if ($("#jerk-val")) $("#jerk-val").textContent = `${jerkVal} m/s³`;
  if ($("#live-jerk-readout")) $("#live-jerk-readout").innerHTML = `${jerkVal} <small>m/s³</small>`;

  if (jerkVal >= 16) {
    triggerSimShock();
  }
}

function bindMotion() {
  if (isMotionActive) {
    window.removeEventListener("devicemotion", handleMotion);
    isMotionActive = false;
    if ($("#btn-motion-sensor")) $("#btn-motion-sensor").innerHTML = "📱 Enable Live Phone Accelerometer";
    toast("Motion sensor disabled");
  } else {
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

// Bootstrap all modules
initTopbarAndModals();
initModuleA();
initModuleB();
load();
drawChart();
