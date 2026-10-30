# DOME Flow

DOME Flow is a Flask-based traffic management demonstration for the NH-206 Gubbi–Tumakuru corridor, with a Bengaluru scenario for comparison. It provides a responsive dashboard for traffic incidents and analytics, plus two feature demonstrations:

- **Emergency preemption demo:** a simulated network warning arms queue-clear preparation, then close-range browser microphone pattern confirmation can request a simulated green wave. The acoustic range is an estimate, not a measured capability.
- **Road shock reporting:** phone motion input or a manual simulator, with a three-hit counter that creates a demo blackspot incident and work order.

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


## Run locally on Windows

From PowerShell in the project folder:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000> on the laptop. Keep the terminal running.

To open the same local server on a phone, connect both devices to the same Wi-Fi network, find the laptop's Wi-Fi IPv4 address with `ipconfig`, then open `http://LAPTOP-IP:5000` on the phone. Allow Python through Windows Firewall on the private network if prompted. Some phone browsers restrict motion sensors on plain HTTP; use the HTTPS Render deployment for sensor testing.

## Deploy to Render

The included `render.yaml` defines a Python web service. Push the project to GitHub, then in Render choose **New → Blueprint** and connect the repository. Render reads the blueprint, installs `requirements.txt`, and starts the Flask app with Gunicorn. Open the resulting HTTPS `onrender.com` URL on both devices.

The service is configured with one Gunicorn worker so requests share the same in-memory demo state. A service restart or redeploy resets that state. Microphone and motion sensor access still require browser permission; motion sensor availability varies by device and browser.

## Suggested feature demo

1. In **S2 Edge AI & Preemption**, inspect the free-field range estimate and edit its sound/noise assumptions. The starting assumptions have not been validated with field recordings; the estimate excludes buildings and reflections.
2. Open the page with `?dev=1` and run **Ambulance approach simulator**. At the network warning distance, the simulated warning changes the state to ARMED and begins queue-clear preparation; no green is granted. A close-range siren must be confirmed, its RMS loudness must show an approaching trend with sufficient R-squared, and the simulated heading must match a configured junction arm before green is requested.
3. Use the **Synthetic approach**, **Synthetic recede**, and **Constant level** buttons to inspect loudness slope, R-squared, Doppler supporting evidence, arm match, and gate reason. **Direction self-check** prints PASS/FAIL for approaching with the correct arm, receding, constant level, and approaching from an unmatched heading. These checks exercise the browser-side gate; they do not authenticate a real ambulance.
4. If a preemption is active and the trend remains receding for two seconds, the demo releases through amber and all-red clearance before restoring the prior junction states. The siren detector searches 500–1800 Hz for repeated wail, yelp, or hi-lo patterns; it is not a validated emergency-vehicle classifier.
5. For live microphone testing, review and accept the microphone consent dialog, then play a siren recording near the device. Test audio stays in the browser; no raw audio is sent to Flask. Use **Withdraw mic consent / stop** to stop capture and block further acoustic-event requests. Stereo left/right hints are shown only when the input exposes two channels. The deployment has no real ambulance network feed, so heading and approach messages are simulated.
6. On the phone, enable the accelerometer and shake the phone firmly to submit qualifying motion events. For a predictable presentation, use **Simulate Commuter Pothole Shock** three times instead. The third qualifying request creates a demo incident and work order.
7. Show the resulting changes in Overview, Road Management, and Analytics.

## Queue discharge model

The earlier Greenshields calculation was removed because Greenshields describes speed-density behaviour for moving traffic, not the discharge of a stopped queue at a signal. The replacement uses the saturation-flow estimate:

`T_flush = t_react + t_startup + (sum(count_i × PCU_i)) × h / effective_lanes`

Current assumptions are reaction delay 3.5 s, start-up lost time 2.0 s, nominal headway 2.0 s per PCU (about 1800 PCU/hr/lane), and 2 effective lanes per approach arm. PCU factors are car 1.0, two-wheeler 0.5, heavy truck/bus 2.2, and auto-rickshaw 1.2. The displayed LOW estimate uses h=1.7 s/PCU and PCU total reduced by 15%; HIGH uses h=2.6 s/PCU and PCU total increased by 15%. The HIGH value is used for the timing check: `green_start_in = verified_ETA - T_flush_high`. If negative, the request is denied with **TOO LATE: queue will not clear in time**; if positive, the browser waits until the calculated start window and the server rechecks the verified report before allowing green. The one-second early-start buffer is also an assumption.

All these inputs are assumptions pending field calibration. In particular, verify the PCU factors against the IRC:106 table before presenting; replace them if the applicable table or field observations differ. The estimate is not a guarantee of queue clearance. Use **Run queue model self-check** on the dashboard and inspect the browser console for PASS/FAIL values.

The three-hit demonstration counts qualifying requests; it does not validate that hits came from three separate phones or a real-world spatial cluster.

## Project files

- `tools/fetch_corridor.py` — Offline OpenStreetMap data fetcher (Python stdlib only, queries Nominatim/Overpass/OSRM).
- `data/corridor.geojson` — Ordered 28.52 km polyline with chainages in metres and junction/signal points.
- `data/junctions.json` — Server-loaded junction configuration with road-derived arm bearings.
- `app.py` — Flask routes, corridor loader, queue-clearance calculation, and REST API.
- `templates/index.html` — dashboard markup with Leaflet Corridor Map and chainage ruler.
- `static/app.js` — dashboard interactions, Leaflet map initialization, microphone analysis, and API requests.
- `static/style.css` — dashboard styling, dark Leaflet popups, and responsive layout.
- `requirements.txt` — Flask and Gunicorn dependencies.
- `render.yaml` — Render deployment configuration.

## Siren detector self-check

Open the app with `?dev=1` appended to its URL, go to **S2 Edge AI & Preemption**, and select **Run self-check**. Open the browser developer console to see PASS/FAIL results for the six generated signals. Stop the live microphone first. Test audio is generated and analyzed in the browser; no audio is sent to Flask.

## Security model

The junction hardware assumption is one microphone plus a small edge device. This is a low-cost design target, not a measured bill of materials or a quote. The dual-key gate uses two independent signed sources: an approved ambulance signs its position report, and a separately enrolled junction unit signs the acoustic detector event. Flask verifies each signature, freshness, replay nonce, rate, and assignment; it derives distance, ETA, and arm from verified vehicle reports. An unsigned or untrusted siren claim is WATCH only. Events must be fresh and time-aligned with the vehicle position. The browser never uploads raw microphone audio to Flask, and every decision is recorded in the hash-chained audit log.

For local demo use, set an `ADMIN_TOKEN` environment variable before starting Flask. On Windows PowerShell: `$env:ADMIN_TOKEN = "choose-a-demo-token"`; then run `python app.py`. On Render, add `ADMIN_TOKEN` under the service environment variables. Open `/?dev=1`, enter the same token in the developer panel, enroll and approve the selected junction unit, and approve an enrolled vehicle. The demo unit's non-extractable key is stored in this browser's IndexedDB. Open `/ambulance` to enroll and start signed position reports.

A stolen phone with an approved key can still sign valid reports. A compromised junction unit can also lie about what its microphone detected. Physical tamper protection, prompt revocation, rate limits, and the audit log are the prototype mitigations. A production junction unit needs a hardware secure element; the ambulance identity would also need a managed enrollment authority, and the controller must perform its own safety checks. This project demonstrates the protocol; it is not a production traffic-signal security system.

The acoustic detector runs locally at the junction unit. Flask accepts its result only when the event is signed by that unit's enrolled P-256 key, approved for the same junction, fresh, not replayed, and consistent with a verified vehicle report. The demo stores its registries and audit chain in memory, so they reset when the service restarts; a production deployment needs persistent protected storage and a hardware secure element.

## Privacy

This prototype minimizes collection for demonstration; these controls are not a legal compliance determination. The [Digital Personal Data Protection Act, 2023 (official Gazette text)](https://www.meity.gov.in/static/uploads/2024/02/Digital-Personal-Data-Protection-Act-2023.pdf) describes consent and certain legitimate uses as grounds for processing. The operator and legal team must determine which lawful basis applies to a real deployment and provide the required notices and rights process.

| Data | Purpose | Retention in this prototype | Proposed basis to review |
| --- | --- | --- | --- |
| Raw microphone samples | Local siren analysis only | Volatile browser audio buffers while mic is active; never transmitted or recorded | Explicit local microphone consent; withdraw to stop capture |
| Derived acoustic event: unit_id, junction_id, timestamp, nonce, label, confidence, approach, slope, r_squared, signature | Confirm a nearby siren and verify junction-unit origin | Up to 7 days in the running Flask process | Local microphone consent plus approved emergency-system purpose; authority/legal review required |
| Ambulance report: vehicle_id, lat, lon, heading_deg, speed_kmh, timestamp, nonce, signature | Verify an approved vehicle's approach and calculate distance/ETA | Latest exact position trace up to 24 hours; reports are sent only while an enrolled, approved vehicle is on duty | Driver authorization and a lawful emergency-operation basis to be determined by the deploying authority |
| Preemption decision fields and audit metadata | Apply the advisory/simulator gates and support accountability | Audit entries kept for the life of the in-memory process; process restart clears them. No coordinates are written to audit entries. | Documented public-safety purpose and authority policy; review required |
| Junction queue baseline | Queue-discharge estimate | Junction-level aggregate values only; no per-device queue history | Operational aggregate, subject to authority review |
| Random per-install ID | Link a device's enrolled/report records to the delete-data control | In-memory association while the service runs; reset or delete from the Privacy panel | User control for data access and deletion; no name, email, or phone is collected by this ID |

The Privacy panel shows the current payload body and the field names sent by the driver and junction demo clients. `X-Privacy-Install-ID` is a random 128-bit value stored locally and can be reset. Exact latitude/longitude is restricted to the approved on-duty vehicle report; no non-emergency request in this project sends a location. A 50 m grid-rounding helper and self-check are included for any future non-emergency location use. The server purges position traces after 24 hours and signed acoustic events after 7 days on incoming requests. Queue data stays aggregated. Audit entries are kept without coordinates; if a future audit entry includes a position, it is rounded to about 50 m after 24 hours. After deletion or redaction the server recomputes the SHA-256 chain over the redacted entries, so the chain remains verifiable while the old exact value is no longer retained.

**This is a prototype, not legal advice. A production system needs a proper data-protection review, a documented lawful basis, retention policy, notice, and operational deletion process before deployment.**

The in-memory vehicle and junction-unit registries, replay cache, and hash-chained audit log reset when the service restarts. The dev attack panel (`/?dev=1`) exercises unsigned siren claims, vehicle and acoustic replay, tampering, revoked and unknown identities, wrong-junction assignment, teleporting, and a valid dual-signature request. These tests exercise the demo protocol and do not substitute for field or security testing.

## Risk & Misuse

- **Recorded siren near a junction:** an unsigned claim is WATCH only. A grant also requires a fresh event signed by the approved junction unit plus a fresh signed vehicle token. A compromised unit can still sign a false acoustic event; physical tamper protection, revocation, and the audit log are mitigations, not guarantees.
- **Replayed token or report:** the server verifies the signature, rejects reports older than 10 seconds or from the future, and rejects a nonce reused within the replay window. The nonce cache is in memory, so a service restart clears it.
- **Stolen approved device:** whoever controls the device can use its approved key to sign reports until the administrator revokes it. Per-vehicle rate limits and the audit log help detect or limit abuse; they do not prevent use before revocation.
- **Cross-traffic harm:** the prototype now estimates ambulance delay saved against conflicting traffic delay added, applies a weighted minimum-harm gate, enforces a maximum hold, recovery service, cooldown, and arm-starvation limit. These estimates are not a validated controller interlock; signal timing, per-arm queues, and arrival rates need field measurement and traffic authority approval.

## Cross-traffic harm

The preemption decision reuses the existing conservative queue discharge estimate `T_flush_high`. The estimated ambulance wait without preemption is `remaining red + T_flush_high`; with preemption it is `T_flush_high`. Their difference is the estimated seconds saved for the ambulance. Cross-traffic cost is estimated per conflicting arm as `(queued PCU * extra red seconds) + (arrival rate PCU/s * extra red seconds^2 / 2)`. Both the queue and arrival terms are estimates, because this demo has no live per-arm detector counts or calibrated arrival rates.

The gate computes `benefit = delay_saved_s * AMBULANCE_WEIGHT` and compares it with `cross_delay_added_vehicle_s * HARM_MARGIN`. The current weight is **20 vehicle-seconds per ambulance-second saved**, an assumption expressing emergency priority. The traffic authority, not the project team, must select and approve that policy weight and margin before any real deployment. The displayed remaining-red time, queue allocation, arrival rates, and all PCU inputs are provisional assumptions requiring field calibration.

Preemption is capped at **40 seconds**. At the cap, the system starts the existing amber and all-red clearances, which remain mandatory and unchanged. After release, each of the three conflicting arms is assigned a sequential **15-second recovery green** before another request can begin. A **60-second junction cooldown** follows a preemption; an exception permits a different verified approaching vehicle with at least **30 seconds of estimated delay saved**. New preemptions are denied if any other arm has been red for more than **90 seconds**, until that arm is served. When verified ambulances compete, the request with the smaller verified ETA is first in the queue; the system never permits conflicting preemption greens.

These safeguards are demo policy logic, not a safety-certified traffic controller. The actual normal phase schedule is represented only by simplified junction state in this project, so the recovery green schedule and red-age tracking must be integrated with a controller's authoritative phase plan and validated by the road authority.

## Controller integration

DOME Flow is **advisory-first**. In `ADVISORY` mode (the default), it evaluates the verified ambulance, siren, queue, and harm gates, then displays a timed recommendation with its inputs. An operator can confirm or dismiss it; confirming records that the advice was reviewed and does not change any phase. Recommendations expire and are audit-logged. The dashboard's controller card identifies whether each junction is in `ADVISORY` or `DEMO_AUTO`.

`ControllerAdapter` separates the decision engine from signal actions. `SimulatedController` runs an in-memory demonstration through `SafetyInterlock`; it is the only implementation selected by this project. The `ModelSignalController` is a documentation stub and opens no network or serial connection. The interlock gates each simulator phase transition on minimum green, amber, all-red, and the configured junction conflict matrix. Failed transitions are explained in the dashboard and written to the hash-chained audit log. `DEMO_AUTO` means the simulator only and always displays **SIMULATION, NOT CONNECTED TO REAL SIGNALS**.

The browser sends decision and input heartbeats. If either is stale beyond the configured five-second assumption, the fail-safe cancels pending advice and asks the simulated adapter to release through the same interlocked minimum-green, amber, and all-red sequence before returning to its fixed-time demo plan. The operator's manual override also uses that adapter and interlock. Missing the microphone/input heartbeat keeps the fail-safe badge active; a verified signed vehicle report is another input heartbeat source.

Connecting to any real signal requires authorization from the traffic police or signal authority, a vendor-provided controller interface, and safety checks enforced inside the signal controller itself. The authority must provide the actual phase timings and conflict matrix. This repository claims compatibility with no particular controller standard; the current code does not connect to real hardware.

## Optional future upgrade (not required)

The low-cost hardware estimate assumes only a microphone and small edge device; cameras or radar are not required and are not used for ambulance verification. They could be evaluated only as optional future sensing. Verification remains the signed ambulance token plus confirmed approaching siren, with the audit log providing accountability.
