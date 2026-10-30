# DOME Flow

DOME Flow is a Flask-based traffic management demonstration for the NH-206 Gubbi–Tumakuru corridor, with a Bengaluru scenario for comparison. It provides a responsive dashboard for traffic incidents and analytics, plus two feature demonstrations:

- **Emergency preemption demo:** a simulated network warning arms queue-clear preparation, then close-range browser microphone pattern confirmation can request a simulated green wave. The acoustic range is an estimate, not a measured capability.
- **B2B Partner Fleet Pothole Intelligence:** on-device derived feature ingestion from commercial fleet apps (ride-hailing, buses, logistics) with spatial snapping to NH-206, speed-breaker learning, co-moving deduplication, and PWD repair verification.

This is a simulation. It does not connect to real traffic signals or municipal work-order systems. The backend stores demo state in memory, so state resets when the server process restarts.

## Corridor Scope: Tumakuru – Gubbi – Nittur (NH-206)

This system is built around one real-world highway corridor in Karnataka, India: **NH-206 (BH Road / NH-73)** spanning **28.52 km** from the Tumakuru urban junction through Gubbi town to Nittur:
- **Chainage 0.0 km:** Tumakuru Entry (Batawadi NH-48 / NH-206 Cross)
- **Chainage 18.97 km:** CIT Campus Gate (NH-206)
- **Chainage 19.51 km:** Gubbi Town Cross (NH-206 / Chandrashekar Circle)
- **Chainage 28.52 km:** Nittur Highway Market Bottleneck (NH-206)

### Data Source & Licence
- **Map & Highway Geometry:** &copy; [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.
- **Licence:** Open Database License ([ODbL](https://opendatacommons.org/licenses/odbl/)).
- **Cartography & Leaflet Tiles:** Standard OpenStreetMap tile service with mandatory attribution: `© OpenStreetMap contributors`.

### Real vs. Proposed Junction Signals
Per strict deployment guidelines, the system does not invent traffic signals that OpenStreetMap does not verify:
- **J1 · Batawadi – Tumakuru Entry Junction (`signalised: true`):** A real, physically existing traffic signal at the major NH-48 / NH-206 interchange in Tumakuru.
- **J2 · CIT Campus Gate (`signalised: proposed`):** Proposed intelligent preemption node protecting academic and transit vehicles entering the national highway.
- **J3 · Gubbi Town Cross (`signalised: proposed`):** Proposed smart ITS intersection for the congested town centre bottleneck.
- **J4 · Nittur Highway Market Bottleneck (`signalised: proposed`):** Proposed smart preemption bottleneck for highway queue clearance.

### How to Regenerate Corridor Data
An offline tool (`tools/fetch_corridor.py`, Python standard library only) is provided to look up the towns via Nominatim, query OpenStreetMap highway geometry, compute chainage in metres, derive approach arm bearings, and export clean GeoJSON and configuration files:

```powershell
python tools/fetch_corridor.py
```
Outputs:
- `data/corridor.geojson`: Single continuous ordered polyline with chainages from Tumakuru and junction points.
- `data/junctions.json`: Server-loaded junction configuration with road-derived approach bearings (`arm_bearings: {"W": ..., "E": ..., "N": ..., "S": ...}`).



---

## Attack Lab: Naive System vs. AURA Engine

The **Attack Lab** (located at the top of the **S2 Edge AI & Preemption** dashboard) is a live adversarial testbed. It feeds identical physical inputs (real phone hand shakes, loudspeaker siren sounds) simultaneously to two engines:

| Attack Scenario | Typical / Naive Approach | AURA Verified Engine |
| :--- | :--- | :--- |
| **Indoor Phone Shake** (Sit in chair, shake phone 3 times) | **FOOLED:** Naive threshold (>12 m/s²) immediately issues an unverified PWD pothole repair ticket. | **REJECTED:** Speed is 0 km/h (< 15 km/h filter) → classified as NOISE. Single device → requires ≥ 2 independent commercial fleet groups. Zero tickets issued. |
| **Loudspeaker Siren Spoof** (Play siren YouTube/MP3 near microphone) | **FOOLED:** Naive acoustic detector hears wail/yelp frequency pattern and blindly grants GREEN signal. | **BLOCKED:** Acoustic match without a cryptographically signed ECDSA token triggers WATCH ONLY status. Signal remains safe; preemption denied. |
| **Genuine Pothole Evidence** (Two commercial fleet vehicles passing at 40 km/h) | Same unverified complaint format. | **VERIFIED:** On-device jerk & z-shock peaks + pre-braking curve + multi-fleet spatial clustering → verified PWD work-order ticket. |
| **Authorized Emergency Preemption** (Approaching ambulance with siren + valid ECDSA key) | Indistinguishable from spoofed audio. | **PREEMPTION GRANTED:** Both acoustic proximity match AND ECDSA digital signature verified → safe green corridor cleared. |

### How to Run the Attack Lab Live with Phones

1. Open the **S2 Edge AI & Preemption** dashboard on your laptop. Note the 4-digit **Lab Session Code** (e.g. `1024`).
2. On your phone (connected to the same Wi-Fi), navigate to `http://<LAPTOP-IP>:5000/lab/phone?code=1024` (or click **Copy** / **Open Phone Tool**).
3. **Attack 1 (Pothole Complaint Spoof):**
   - Tap **"Start hit sensor"** on the phone.
   - Shake the phone firmly 3 times while sitting indoors.
   - Look at the dashboard:
     - The **Naive System** increments its hit counter and generates an unverified municipal complaint ticket at Km 5.4.
     - The **AURA Engine** flags the hits as `NOISE (speed < 15 km/h)` and `REJECTED (single source group)`, creating zero tickets.
4. **Attack 2 (Acoustic Siren Preemption Spoof):**
   - On the phone, tap **"Play fake siren"** (or play any emergency siren sound on YouTube).
   - The laptop microphone detects the acoustic wail pattern.
   - The **Naive System** flips immediately to `GREEN GRANTED`.
   - The **AURA Engine** places the junction in `WATCH ONLY (Spoof Blocked - Missing Digital Signature)`.
5. **Legitimate Verification Proof:**
   - Click **"Add genuine evidence"** to demonstrate multi-fleet speed-correlated consensus.
   - Click **"Genuine ambulance"** to demonstrate cryptographic ECDSA preemption verification.
6. **Automated Self-Check:**
   - Click **"Run Lab Self-Check"** (or execute `POST /api/dev/lab_self_check`) to run all 4 adversarial unit tests in memory.

## Run locally on Windows

From PowerShell in the project folder:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000> on the laptop. Keep the terminal running.

To open the same local server on a phone, connect both devices to the same Wi-Fi network, find the laptop's Wi-Fi IPv4 address with `ipconfig`, then open `http://LAPTOP-IP:5000` on the phone. Allow Python through Windows Firewall on the private network if prompted.

## Deploy to Render

The included `render.yaml` defines a Python web service. Push the project to GitHub, then in Render choose **New → Blueprint** and connect the repository. Render reads the blueprint, installs `requirements.txt`, and starts the Flask app with Gunicorn. Open the resulting HTTPS `onrender.com` URL on both devices.

The service is configured with one Gunicorn worker so requests share the same in-memory demo state. A service restart or redeploy resets that state.

## Suggested feature demo

1. In **S2 Edge AI & Preemption**, inspect the free-field range estimate and edit its sound/noise assumptions.
2. Open the page with `?dev=1` and run **Ambulance approach simulator**.
3. In **Module B (Partner Fleet Pothole Intelligence)**, authenticate with the PWD role token (`demo-pwd-token`) or Police token (`demo-police-token`).
4. Inspect the **B2B Partner Telematics** panel. Click **"Run 8-Test Suite"** to verify:
   - Clean pass over 3 real potholes at 5.4 km, 14.2 km, 22.8 km.
   - Speed-breaker automatic learning and ticket suppression at 18.2 km.
   - Bus-shake deduplication (10 co-moving devices grouped into 1 source group).
   - Swerve-avoidance voting without physical shocks.
   - Low-speed noise filtering (<15 km/h).
   - Partner write-only enforcement (HTTP 403 on raw record queries).
   - Repair claim followed by 3 smooth passes leading to `VERIFIED_REPAIRED`.
   - Repair-failed pass triggering ticket reopening.
5. Open the **Partner App Demo** at `/partner-demo` in a separate tab to see the fake "QuickCabs Driver" app running the embeddable `aura-sdk.js` in 5 lines with zero UI changes.
6. Toggle **"Partner-Blind View"** on the main dashboard to verify that partner keys can only query upcoming severity bands (`/api/partner/alerts`) and are blocked with HTTP 403 on internal ticket records.

---

## Partner SDK Model (B2B Fleet Intelligence)

The road anomaly detection subsystem is structured strictly as a **B2B plugin for commercial fleets** (ride-hailing, buses, logistics operators). It is not a public commuter crowdsourcing application.

### What the SDK Collects
- **Derived events only:** On-device feature extraction computes peak vertical acceleration ($z$-axis), jerk, duration, pre-braking speed drop, gyro yaw swerve rate, vehicle speed, and timestamp.
- **NO raw sensor streams:** High-frequency raw accelerometer and gyroscope streams never leave the mobile device.
- **NEVER the microphone:** The SDK requests only motion and GPS permissions; audio capture is strictly prohibited.
- **Resettable pseudonyms:** Each vehicle or driver installation generates a random pseudo-anonymous identifier that can be reset at any time.

### Partner-Blind by Design and Contract
- Fleet partners (e.g. QuickCabs, Urban Transit) transmit derived road shocks into the ingestion pipeline using write-only partner keys.
- Partners **cannot read** pothole tickets, municipal work orders, exact GPS incident coordinates, or telemetry from other fleets.
- A partner application may only call `GET /api/partner/alerts?chainage_m=...` to receive coarse hazard severity bands ahead within 2 km (e.g. "HIGH severity hazard ahead at +450 m"). Any attempt by a partner key to read `/api/potholes/dashboard` or internal records returns **HTTP 403 Forbidden**.
- *Security boundary:* Because partner applications run on hardware outside municipal control, confidentiality is enforced through write-only API keys, TLS encrypted transport, and commercial data contracts.

### Data Minimisation
- Geographic coordinates (`lat`, `lon`) are evaluated against the NH-206 corridor polyline using `snap_to_road`.
- If lateral distance > 30 metres, the event is rejected as off-corridor.
- **Raw coordinates are immediately discarded.** The server stores only the 1D chainage distance (metres from Tumakuru start) and a 25-metre segment bin index.

### Role-Based Access Control
- **Partner Key (`X-Partner-Key`):** Write-only access to `/api/sdk/ingest` and read access only to own ingest stats (`/api/partner/me`) and coarse ahead hazard alerts (`/api/partner/alerts`).
- **PWD Token (`PWD_TOKEN`):** Full read access to pothole tickets, speed-breaker registers, ticket acknowledgment (`/api/pwd/tickets/<id>/acknowledge`), and repair claims (`/api/pwd/tickets/<id>/claim_repair`).
- **Police Token (`POLICE_TOKEN`):** Situational awareness read access for traffic enforcement and hazardous bottleneck planning.
- **Admin Token (`ADMIN_TOKEN`):** Partner onboarding, controller mode configuration, and cryptographic credential issuance.

### Honest Operational Limitations
- **Foreground browser SDK:** The JavaScript SDK (`aura-sdk.js`) operates while the web tab is active. An embeddable Android background service SDK is on the technical roadmap for production fleet telematics.
- **Provisional thresholds:** Peak acceleration and jerk thresholds in `POTHOLE_CONFIG` are engineering assumptions that must be calibrated through dedicated test drives with instrumented fleet vehicles along NH-206.
- **Simulation scope:** Current commercial partner integrations are simulated for prototype verification.

---

## Queue discharge model

The saturation-flow queue discharge calculation is:

`T_flush = t_react + t_startup + (sum(count_i × PCU_i)) × h / effective_lanes`

Current assumptions are reaction delay 3.5 s, start-up lost time 2.0 s, nominal headway 2.0 s per PCU (about 1800 PCU/hr/lane), and 2 effective lanes per approach arm. PCU factors are car 1.0, two-wheeler 0.5, heavy truck/bus 2.2, and auto-rickshaw 1.2.

## Project files

- `tools/fetch_corridor.py` — Offline OpenStreetMap data fetcher (Python stdlib only).
- `data/corridor.geojson` — Ordered 28.52 km polyline with chainages in metres and junction/signal points.
- `data/junctions.json` — Server-loaded junction configuration with road-derived arm bearings.
- `static/aura-sdk.js` — B2B Partner Telematics SDK with on-device derived feature extraction.
- `templates/partner_demo.html` — Mock QuickCabs ride-hailing driver app proving zero UI change.
- `app.py` — Flask backend, corridor snapping, queue discharge, B2B partner ingestion, speed-breaker learning, and PWD ticket lifecycle.
- `templates/index.html` — Dashboard markup with Leaflet Corridor Map, chainage ruler, and Partner Fleet Telematics panel.
- `static/app.js` — Dashboard interactions, Leaflet maps, preemption logic, and PWD ticket management.
- `static/style.css` — Modern dashboard styles and responsive layout.
- `requirements.txt` — Python dependencies (Flask, Gunicorn, Cryptography).
- `render.yaml` — Render deployment configuration.
