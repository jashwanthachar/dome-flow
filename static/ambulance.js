(() => {
  const $ = selector => document.querySelector(selector);
  const dbName = "dome-flow-vehicle-keys";
  let db, reportTimer, keyRecord;
  const status = message => { $("#driver-status").textContent = message; };
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
      const response = await fetch("/api/vehicle/enroll", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ vehicle_id, public_key: b64(publicDer) }) });
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
    const id = $("#driver-vehicle-id").value.trim();
    const distance = Number($("#driver-distance").value), heading = Number($("#driver-heading").value), speed = Number($("#driver-speed").value);
    const [lat, lon] = destination(13.3110, 76.9410, (heading + 180) % 360, distance);
    const nonceBytes = crypto.getRandomValues(new Uint8Array(18));
    const nonce = b64(nonceBytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    const report = { vehicle_id: id, lat: lat.toFixed(7), lon: lon.toFixed(7), heading_deg: heading.toFixed(2), speed_kmh: speed.toFixed(2), timestamp: Math.floor(Date.now() / 1000), nonce };
    try {
      const signature = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, keyRecord.privateKey, new TextEncoder().encode(canonical(report)));
      const response = await fetch("/api/vehicle/report", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...report, signature: b64(signature) }) });
      const result = await response.json(); if (!response.ok) throw new Error(result.reason || "Report rejected");
      status(`Signed report accepted · ${Math.round(result.distance_m)} m · ETA ${Math.round(result.eta_s)} s · arm ${result.arm || "unknown"}`);
      // The demo vehicle advances between signed reports so the server can verify a decreasing range.
      $("#driver-distance").value = Math.max(0, distance - speed * 1.5 / 3.6).toFixed(1);
    } catch (error) { status(error.message); stop(); }
  }
  function start() { if (!keyRecord) return; $("#driver-start").disabled = true; $("#driver-stop").disabled = false; sendReport(); reportTimer = setInterval(sendReport, 1500); }
  function stop() { clearInterval(reportTimer); $("#driver-start").disabled = false; $("#driver-stop").disabled = true; }
  $("#driver-enroll").addEventListener("click", enroll);
  $("#driver-start").addEventListener("click", start);
  $("#driver-stop").addEventListener("click", stop);
  openDb().then(async value => { db = value; keyRecord = await read($("#driver-vehicle-id").value); if (keyRecord) { status("Local key found. Check enrollment status before reporting."); fetch(`/api/vehicle/status?vehicle_id=${encodeURIComponent(keyRecord.vehicle_id)}`).then(r => r.json()).then(v => { keyRecord.status = v.status; $("#driver-start").disabled = v.status !== "approved"; status(`Vehicle status: ${v.status || "not enrolled"}`); }); } }).catch(error => status(error.message));
})();
