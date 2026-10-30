(() => {
  const $ = selector => document.querySelector(selector);
  const dbName = "dome-flow-vehicle-keys";
  let db, reportTimer, keyRecord, onDuty = false;
  const status = message => { $("#driver-status").textContent = message; };
  const installKey = "dome-flow-privacy-install-id";
  function installId() {
    let id = localStorage.getItem(installKey);
    if (!/^[a-f0-9]{32}$/.test(id || "")) {
      id = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("");
      localStorage.setItem(installKey, id);
    }
    return id;
  }
  const headers = extra => ({ ...extra, "X-Privacy-Install-ID": installId() });
  function showPayload(url, method, payload) {
    const viewer = $("#driver-last-payload");
    if (viewer) viewer.textContent = JSON.stringify({ method, url, header: "X-Privacy-Install-ID", payload }, null, 2);
    const payloadText = JSON.stringify(payload);
    const hasAudioField = /raw.?audio|audio.?data|samples|waveform|spectrogram|recording|pcm|microphone.?buffer/i.test(payloadText);
    console[hasAudioField ? "error" : "log"](`${hasAudioField ? "FAIL" : "PASS"} Driver payload privacy check: ${url} contains ${hasAudioField ? "an audio-like field" : "no raw-audio fields"}`);
  }
  function openDb() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(dbName, 1);
      request.onupgradeneeded = () => request.result.createObjectStore("vehicles", { keyPath: "vehicle_id" });
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
  function store(record) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction("vehicles", "readwrite"); tx.objectStore("vehicles").put(record);
      tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
    });
  }
  function read(id) {
    return new Promise((resolve, reject) => {
      const request = db.transaction("vehicles").objectStore("vehicles").get(id);
      request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
    });
  }
  const b64 = bytes => { let binary = ""; new Uint8Array(bytes).forEach(byte => binary += String.fromCharCode(byte)); return btoa(binary); };
  const canonical = data => JSON.stringify(Object.fromEntries(Object.keys(data).sort().map(key => [key, data[key]])));
  async function enroll() {
    const vehicle_id = $("#driver-vehicle-id").value.trim();
    if (!vehicle_id) return status("Enter a vehicle ID.");
    status("Generating P-256 key and enrolling…");
    try {
      db = await openDb();
      const existing = await read(vehicle_id);
      keyRecord = existing || await (async () => {
        const pair = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, false, ["sign", "verify"]);
        return { vehicle_id, privateKey: pair.privateKey, publicKey: pair.publicKey };
      })();
      if (!existing) await store(keyRecord);
      const publicDer = await crypto.subtle.exportKey("spki", keyRecord.publicKey);
      const enrollment = { vehicle_id, public_key: b64(publicDer) };
      showPayload("/api/vehicle/enroll", "POST", enrollment);
      const response = await fetch("/api/vehicle/enroll", { method: "POST", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify(enrollment) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.reason || "Enrollment failed");
      $("#driver-start").disabled = result.status !== "approved";
      status(`Enrolled: ${result.status}. Ask the dashboard admin to approve this vehicle.`);
      keyRecord.status = result.status;
    } catch (error) { status(error.message); }
  }
  function destination(lat, lon, bearing, meters) {
    const r = 6371000, p1 = lat * Math.PI / 180, l1 = lon * Math.PI / 180, t = bearing * Math.PI / 180, d = meters / r;
    const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(t));
    const l2 = l1 + Math.atan2(Math.sin(t) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
    return [p2 * 180 / Math.PI, l2 * 180 / Math.PI];
  }
  async function sendReport() {
    if (!onDuty || !keyRecord) return;
    try {
      const statusResponse = await fetch(`/api/vehicle/status?vehicle_id=${encodeURIComponent(keyRecord.vehicle_id)}`, { headers: headers() });
      const current = await statusResponse.json();
      keyRecord.status = current.status;
      if (!statusResponse.ok || keyRecord.status !== "approved") { stop(); status("Vehicle is not approved; exact location reporting stopped."); return; }
    } catch (error) { stop(); status("Approval could not be checked; exact location reporting stopped."); return; }
    const id = $("#driver-vehicle-id").value.trim();
    const distance = Number($("#driver-distance").value), heading = Number($("#driver-heading").value), speed = Number($("#driver-speed").value);
    const [lat, lon] = destination(13.3110, 76.9410, (heading + 180) % 360, distance);
    const nonceBytes = crypto.getRandomValues(new Uint8Array(18));
    const nonce = b64(nonceBytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    const report = { vehicle_id: id, lat: lat.toFixed(7), lon: lon.toFixed(7), heading_deg: heading.toFixed(2), speed_kmh: speed.toFixed(2), timestamp: Math.floor(Date.now() / 1000), nonce };
    try {
      const signature = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, keyRecord.privateKey, new TextEncoder().encode(canonical(report)));
      const signedReport = { ...report, signature: b64(signature) };
      showPayload("/api/vehicle/report", "POST", signedReport);
      const response = await fetch("/api/vehicle/report", { method: "POST", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify(signedReport) });
      const result = await response.json(); if (!response.ok) throw new Error(result.reason || "Report rejected");
      status(`Signed report accepted · ${Math.round(result.distance_m)} m · ETA ${Math.round(result.eta_s)} s · arm ${result.arm || "unknown"}`);
      // The demo vehicle advances between signed reports so the server can verify a decreasing range.
      $("#driver-distance").value = Math.max(0, distance - speed * 1.5 / 3.6).toFixed(1);
    } catch (error) { status(error.message); stop(); }
  }
  async function start() {
    if (!keyRecord) return status("Enroll and approve this vehicle before starting duty.");
    try {
      const response = await fetch(`/api/vehicle/status?vehicle_id=${encodeURIComponent(keyRecord.vehicle_id)}`, { headers: headers() });
      const current = await response.json();
      keyRecord.status = current.status;
      if (!response.ok || keyRecord.status !== "approved") return status("Exact position is not sent: this vehicle is not currently approved.");
      onDuty = true; $("#driver-start").disabled = true; $("#driver-stop").disabled = false;
      status("On duty. Exact signed positions are sent every 1.5 s while this is active.");
      sendReport(); reportTimer = setInterval(sendReport, 1500);
    } catch (error) { status(error.message); }
  }
  function stop() { onDuty = false; clearInterval(reportTimer); $("#driver-start").disabled = keyRecord?.status !== "approved"; $("#driver-stop").disabled = true; status("Off duty. Position reporting stopped."); }
  function clearVehicleKeys() {
    return new Promise(resolve => {
      const request = indexedDB.open(dbName, 1);
      request.onupgradeneeded = () => request.result.createObjectStore("vehicles", { keyPath: "vehicle_id" });
      request.onsuccess = () => { const keyDb = request.result; const tx = keyDb.transaction("vehicles", "readwrite"); tx.objectStore("vehicles").clear(); tx.oncomplete = tx.onerror = () => { keyDb.close(); resolve(); }; };
      request.onerror = resolve;
    });
  }
  function clearUnitKeys() {
    return new Promise(resolve => {
      const request = indexedDB.open("dome-flow-junction-unit-keys", 1);
      request.onupgradeneeded = () => request.result.createObjectStore("units", { keyPath: "junction_id" });
      request.onsuccess = () => { const keyDb = request.result; const tx = keyDb.transaction("units", "readwrite"); tx.objectStore("units").clear(); tx.oncomplete = tx.onerror = () => { keyDb.close(); resolve(); }; };
      request.onerror = resolve;
    });
  }
  async function deleteData(resetId = false) {
    stop();
    showPayload("/api/privacy/delete", "POST", {});
    const response = await fetch("/api/privacy/delete", { method: "POST", headers: headers({ "Content-Type": "application/json" }), body: "{}" });
    const result = await response.json(); if (!response.ok) throw new Error(result.reason || "Delete failed");
    await Promise.all([clearVehicleKeys(), clearUnitKeys()]); keyRecord = null; $("#driver-vehicle-id").value = "";
    if (resetId) localStorage.setItem(installKey, Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join(""));
    status("Linked server records removed; audit entries remain anonymized. Local vehicle key deleted.");
    $("#driver-start").disabled = true; $("#driver-stop").disabled = true;
  }
  $("#driver-enroll").addEventListener("click", enroll);
  $("#driver-start").addEventListener("click", start);
  $("#driver-stop").addEventListener("click", stop);
  $("#driver-delete-data")?.addEventListener("click", () => { if (confirm("Delete this browser install's linked records and local vehicle key?")) deleteData().catch(error => status(error.message)); });
  $("#driver-reset-id")?.addEventListener("click", () => { if (confirm("Delete linked records and keys, then reset the random install ID?")) deleteData(true).catch(error => status(error.message)); });
  openDb().then(async value => { db = value; keyRecord = await read($("#driver-vehicle-id").value); if (keyRecord) { status("Local key found. Check enrollment status before reporting."); fetch(`/api/vehicle/status?vehicle_id=${encodeURIComponent(keyRecord.vehicle_id)}`, { headers: headers() }).then(r => r.json()).then(v => { keyRecord.status = v.status; $("#driver-start").disabled = v.status !== "approved"; status(`Vehicle status: ${v.status || "not enrolled"}`); }); } $("#driver-install-id").textContent = `${installId().slice(0, 8)}…`; }).catch(error => status(error.message));
})();
