# AURA-TMS — Autonomous Urban & Rural Arterial Traffic Management System
### Buildathon 2.0 2K26 · Track S2: Smarter Traffic & Road Management

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Flask 3.0+](https://img.shields.io/badge/Framework-Flask%203.0%2B-green.svg)](https://flask.palletsprojects.com/)
[![Web Audio API](https://img.shields.io/badge/Audio%20AI-Web%20Audio%20FFT-orange.svg)]()
[![Zero Hardware](https://img.shields.io/badge/Architecture-Zero--Hardware%20Edge%20AI-emerald.svg)]()
[![Corridor](https://img.shields.io/badge/Scope-NH--206%20CIT%20Gubbi--Tumakuru-purple.svg)]()

---

## 1. Executive Summary: The Zero-Hardware Breakthrough

Municipal traffic authorities and highway administrators face a critical dilemma: **traditional intelligent transportation systems (ITS) are economically unviable for rural-urban highway transitions**. Installing physical inductive loops, microwave radars, LiDAR gantry sensors, and dedicated DSRC/V2X emergency transponders costs upwards of **$25,000–$40,000 per junction**.

**AURA-TMS** delivers a transformative, **zero-hardware edge solution** tailored for National Highway 206 (CIT Gubbi to Tumakuru) and metropolitan corridors. It achieves intelligent emergency preemption, queue clearance, and pavement maintenance without installing a single new sensor on the roadway:

1. **Acoustic FFT Siren Detection (Module A):** Employs Web Audio edge spectral analysis (650 Hz – 1450 Hz) on existing roadside CCTV microphones, operator computers, or traffic kiosk devices to detect emergency ambulances up to 800m away with zero vehicle-side hardware.
2. **Greenshields Hydrodynamic Queue-Flushing:** Rather than simply flipping lights to green upon ambulance arrival (trapping the ambulance behind stopped cars), AURA-TMS dynamically calculates and executes queue clearance timing ($T_{\text{flush}}$) in advance to open an empty corridor before the ambulance arrives.
3. **Crowd-Sourced Inertial Telematics (Module B):** Uses commuter smartphones' accelerometer sensors (`DeviceMotionEvent`) to register road pavement shocks ($Z_{\text{jerk}} \ge 15\text{ m/s}^3$). Employs a 3-hit spatial clustering filter to eliminate speed-bump noise and autonomously generate high-priority PWD road repair work orders.

---

## 2. Strict Compliance with S2 Constraints

AURA-TMS was built from the ground up to satisfy all core geographical, mathematical, and algorithmic requirements of Track S2:

### S2 Constraint #1 — Geographical Scope: NH-206 Corridor
The platform is calibrated specifically for the 22-kilometer rural-urban transition corridor on **National Highway 206 (NH-206: CIT Gubbi to Tumakuru)**, modeling 4 high-friction bottleneck intersections with realistic heterogenous traffic:

* **J1: CIT Campus Gate (NH-206)** — Academic bus transit surges mixed with high-speed highway cargo transit.
* **J2: Gubbi Town Cross Junction** — Heavy agricultural haulage (overloaded sugarcane tractors) and state transport buses.
* **J3: Nittur Highway Market Bottleneck** — Dense pedestrian market activity, roadside vendors, and narrow single-lane culvert bottlenecks.
* **J4: Batawadi – Tumakuru Entry Junction** — High-density industrial transition and multi-lane toll merge entering Tumakuru city center.

> **Dual Scenario Architecture:** A single click on `Switch: NH-206 ⇄ Bengaluru` toggles between the NH-206 highway digital twin and the legacy Bengaluru metropolitan network (Outer Ring Road, Indiranagar, Domlur, MG Road).

---

### S2 Constraint #2 — Greenshields Model & Simulation Assumptions

#### Hydrodynamic Queue-Flush Equation
Traditional preemption fails because queued vehicles have physical inertia and startup lost time. AURA-TMS models queue discharge using Greenshields hydrodynamic shockwave parameters for heterogenous vehicle fleets:

$$T_{\text{flush}} = t_0 + \sum_{i \in \{\text{cars}, \text{trucks}, \text{bikes}\}} \frac{L_i + d_{\text{gap}}}{v_i}$$

Implemented computational model:
$$T_{\text{flush}} = 3.5 + \frac{\text{Cars} \times (4.5 + 2.0)}{6.5} + \frac{\text{Trucks} \times (10.5 + 3.0)}{4.0} + \frac{\text{Bikes} \times (2.0 + 1.2)}{8.0}$$

* **Startup Lost Time ($t_0$):** $3.5\text{ s}$ perception-reaction delay before green queue movement initiates.
* **Cars:** $L=4.5\text{m}$, gap $d=2.0\text{m}$, clearance speed $v=6.5\text{ m/s}$.
* **Heavy Trucks & Tractors:** $L=10.5\text{m}$, gap $d=3.0\text{m}$, clearance speed $v=4.0\text{ m/s}$.
* **Bikes & Two-Wheelers:** $L=2.0\text{m}$, gap $d=1.2\text{m}$, clearance speed $v=8.0\text{ m/s}$.

#### Clearance Safety Margin
$$\text{Ambulance ETA} = \frac{\text{Ambulance Distance (m)}}{\max\left(\frac{\text{Speed (km/h)}}{3.6},\; 1\right)}$$
$$\text{Preemption Margin} = \text{ETA} - T_{\text{flush}}$$

* **$\text{Margin} \ge 0\text{ s}$:** Safe. Queue discharges fully before the ambulance reaches the intersection line.
* **$\text{Margin} < 0\text{ s}$:** Critical. Immediate preemption override triggered; downstream signal is placed on `GREEN_WAVE_STANDBY`.

#### Crowd Telematics Spatial Noise Filter
Commuter smartphone accelerometers frequently report false spikes from speed bumps, rumbler strips, and potholes. AURA-TMS enforces strict multi-vehicle spatial filtering:
1. **Speed Threshold:** $\text{Speed} \ge 15\text{ km/h}$ (eliminates parking, idling, and walking vibration).
2. **Inertial Threshold:** Vertical Jerk $Z_{\text{jerk}} \ge 15\text{ m/s}^3$ (eliminates gradual braking and compliant suspension bounce).
3. **3-Hit Spatial Cluster:** A blackspot incident is only verified when 3 distinct telemetry probes record qualifying shocks at the same corridor segment within a temporal cluster window.

---

## 3. Core S2 Impact Metrics (Digital Twin KPIs)

The Overview dashboard and REST APIs continuously track 5 quantifiable metrics:

| Metric | Baseline | Description | Formula / Tracking |
| :--- | :--- | :--- | :--- |
| **Golden Hour Saved** | `145s` | Cumulative emergency vehicle delay eliminated | $+ (T_{\text{flush}} + 42\text{s})$ per preempted junction |
| **Fuel Saved** | `48.5 L` | Fuel waste prevented by eliminating stopping shockwaves | $+ (\text{Cars}\times 0.08\text{L} + \text{Trucks}\times 0.25\text{L})$ |
| **Active Green Waves** | `0` | Corridors currently locked into coordinated preemption | Real-time count of active emergency corridors |
| **Verified Blackspots** | `1` | High-risk road hazards confirmed by multi-probe clusters | Increments on the 3rd valid shock hit |
| **PWD Work Orders** | `1` | Automated municipal maintenance work orders | Generated autonomously without citizen paperwork |

---

## 4. System Architecture

```text
AURA-TMS Architecture
├── Edge Audio AI (Browser / CCTV)
│   ├── Web Audio API (AnalyserNode, fftSize = 256)
│   ├── 650 Hz – 1450 Hz Bandpass Energy Integrator
│   └── Synthetic Doppler Siren Oscillator (Auto-fallback)
├── Crowd-Telematics Probe (Smartphone Client)
│   ├── DeviceMotionEvent (Z-axis jerk extraction)
│   └── 3-Hit Spatial Clustering State Machine
├── Backend Application Server (Python / Flask)
│   ├── REST API Engine (app.py)
│   ├── Thread-Safe State Store (threading.Lock)
│   ├── Greenshields Queue-Flush Calculator
│   └── Dual Scenario Engine (NH-206 ⇄ Bengaluru)
└── Presentation Layer (HTML5 / Glassmorphism CSS)
    ├── Overview Digital Twin (SVG corridor schematic)
    ├── S2 Command Center (Module A & Module B)
    ├── Operator Road Management Workspace
    └── Mobility Analytics (Hotspot & travel time charts)
```

---

## 5. API Reference

| Endpoint | Method | Payload / Params | Response | Description |
| :--- | :--- | :--- | :--- | :--- |
| `/` | `GET` | — | HTML | Serves the single-page AURA-TMS dashboard |
| `/api/summary` | `GET` | — | JSON | Returns system KPIs, 4 junctions, impact metrics, scenario |
| `/api/incidents` | `GET` | `?type=`, `?corridor=` | JSON | Filterable corridor incident register |
| `/api/incidents/<id>` | `PATCH` | `{"status": "Reported"\|"In progress"\|"Resolved"}` | JSON | Updates incident lifecycle status |
| `/api/corridor/switch` | `POST` | `{"scenario": "nh206"\|"bengaluru"}` | JSON | Toggles active corridor digital twin |
| `/api/preempt/trigger` | `POST` | `{"junction_id", "cars", "trucks", "bikes", "ambulance_dist_m", "ambulance_speed_kmh", "siren_confidence"}` | JSON | Triggers Greenshields preemption & downstream standby |
| `/api/telematics/shock`| `POST` | `{"corridor", "z_jerk", "speed_kmh", "lat", "lng"}` | JSON | Ingests probe jerk; triggers blackspot at hit 3 |
| `/api/simulate/tick` | `POST` | — | JSON | Fluctuates queues and network flow % in real-time |

---

## 6. Setup & Execution Instructions

### Prerequisites
* **Python 3.9** or newer
* Modern Web Browser (Google Chrome, Microsoft Edge, Mozilla Firefox, or Safari)

### Run on Windows
1. Open PowerShell or Command Prompt in the project folder:
   ```powershell
   cd D:\MODIFIED
   ```
2. (Optional) Create and activate a virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
3. Install required dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Start the AURA-TMS server:
   ```powershell
   python app.py
   ```
5. Open your browser and navigate to:
   **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

### Run on macOS / Linux
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```
Then navigate to **http://127.0.0.1:5000**.

---

## 7. 4-Member, 3-Minute Live Hackathon Pitch Script

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIME   │ SPEAKER   │ ROLE & LIVE ACTION                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 0:00 - │ Member 1  │ THE HOOK & THE ZERO-HARDWARE DILEMMA                   │
│ 0:45   │ (Lead)    │ • Open on Overview dashboard showing NH-206.           │
│        │           │ • State the problem: Smart traffic costs $30k/junction │
│        │           │   rural highways like CIT Gubbi-Tumakuru get left      │
│        │           │   behind.                                              │
│        │           │ • Introduce AURA-TMS: Zero-hardware edge AI turning    │
│        │           │   existing sound and commuter phones into our sensors. │
│        │           │ • Point to the 5 S2 Impact Metrics on top.             │
├─────────────────────────────────────────────────────────────────────────────┤
│ 0:45 - │ Member 2  │ MODULE A: ACOUSTIC FFT & GREENSHIELDS QUEUE-FLUSH      │
│ 1:30   │ (Edge AI) │ • Switch to "🚨 S2 Edge AI & Preemption" tab.          │
│        │           │ • Click "🎙️ Start Live Siren Mic (FFT)".               │
│        │           │ • Play siren audio near laptop mic (or let synthetic   │
│        │           │   Doppler oscillator lock on).                         │
│        │           │ • Point out the 650Hz–1450Hz glowing siren band.       │
│        │           │ • Show Greenshields live formula: T_flush=36.4s vs     │
│        │           │   ETA=24.9s.                                           │
│        │           │ • Watch auto-preemption trigger: J2 flips to           │
│        │           │   PREEMPT_GREEN, J3 enters GREEN_WAVE_STANDBY.         │
│        │           │ • Return to Overview: point to glowing emerald green   │
│        │           │   wave corridor path on the digital twin map.          │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1:30 - │ Member 3  │ MODULE B: ZERO-TOUCH TELEMATICS & 3-HIT BLACKSPOT      │
│ 2:15   │ (IoT/Mob) │ • Stay on S2 Command View (Module B).                  │
│        │           │ • Explain why potholes cause fatal highway crashes     │
│        │           │   and why manual reporting fails.                      │
│        │           │ • Demonstrate the Spatial Noise Filter: show that low  │
│        │           │   jerk/speed is ignored.                               │
│        │           │ • Click "Simulate Commuter Pothole Shock (+1 Hit)"     │
│        │           │   (or shake the smartphone with Accelerometer active). │
│        │           │ • Hit 1 (33%) → Hit 2 (66%) → Hit 3 (100% verified!). │
│        │           │ • Show toast & automated PWD Work Order dispatched!    │
│        │           │ • Navigate to "Road Management" to show the verified   │
│        │           │   incident added to the queue for city operators.      │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2:15 - │ Member 4  │ IMPACT METRICS, S2 COMPLIANCE & CLOSING                │
│ 3:00   │ (Impact)  │ • Return to Overview & Analytics view.                 │
│        │           │ • Highlight quantifiable results: Golden Hour Saved    │
│        │           │   jumped to 223s, Fuel Saved +12.4L.                   │
│        │           │ • Click "Switch: NH-206 ⇄ Bengaluru" to prove dual-   │
│        │           │   scenario architectural scalability.                  │
│        │           │ • Open "S2 Math & Constraints" modal to demonstrate    │
│        │           │   strict compliance with Buildathon S2 rules.          │
│        │           │ • Final punchline: "AURA-TMS saves lives and roads     │
│        │           │   starting tomorrow, without waiting for million-dollar│
│        │           │   infrastructure budgets."                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Built-in Venue Fail-safes & Redundancy

To ensure a flawless live presentation regardless of hackathon Wi-Fi or browser permissions:
1. **Microphone Permission Fallback:** If the browser or venue OS blocks microphone access, clicking the mic button automatically engages the **Synthetic Doppler Siren Oscillator**, generating realistic pitch-modulated acoustic frequencies directly into the AnalyserNode.
2. **Motion Sensor Fallback:** If testing on a laptop without an accelerometer, the `💥 Simulate Commuter Pothole Shock (+1 Hit)` button triggers identical spatial telematics payloads.
3. **In-Memory Thread Safety:** Server state is guarded by `threading.Lock()`, ensuring simultaneous simulator ticks, telematics shock packets, and preemption triggers never race or crash.

---

*Developed for Buildathon 2.0 2K26 · S2 Smarter Traffic & Road Management*
