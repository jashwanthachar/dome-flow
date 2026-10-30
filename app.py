from flask import Flask, render_template, jsonify, request
from datetime import datetime
from threading import Lock
from time import monotonic
from zoneinfo import ZoneInfo
import random

app = Flask(__name__)
lock = Lock()
INDIA_TZ = ZoneInfo("Asia/Kolkata")
MOTION_HIT_COOLDOWN_SECONDS = 3.0
motion_probe_last_hit = {}


def india_now():
    return datetime.now(INDIA_TZ)

# Global Network & Scenario State
active_scenario = "nh206"  # Default: 'nh206' (NH-206: CIT Gubbi – Tumakuru Corridor), toggleable to 'bengaluru'
network_flow = 72          # Percentage (0-100)

# S2 Impact Metrics
impact_metrics = {
    "golden_hour_sec_saved": 145,
    "fuel_litres_saved": 48.5,
    "active_green_waves": 0,
    "verified_blackspots": 1,
    "pwd_work_orders": 1
}

# Telematics Shocks / Inertial Clusters Tracker
telematics_clusters = {
    "nh206": 0,
    "bengaluru": 0
}

# Greenshields Queue-Flush Calculation Helper
def calculate_t_flush(cars: int, trucks: int, bikes: int) -> float:
    """
    Computes Greenshields queue-flush clearance time in seconds:
    t_flush = 3.5 + (cars * (4.5 + 2.0) / 6.5) + (trucks * (10.5 + 3.0) / 4.0) + (bikes * (2.0 + 1.2) / 8.0)
    """
    return round(3.5 + (cars * 6.5 / 6.5) + (trucks * 13.5 / 4.0) + (bikes * 3.2 / 8.0), 1)

# NH-206 Junctions State (CIT Gubbi to Tumakuru Corridor)
junctions = [
    {
        "id": "J1",
        "name": "CIT Campus Gate (NH-206)",
        "signal_state": "GREEN",
        "cars": 12,
        "trucks": 4,
        "bikes": 18,
        "t_flush_sec": calculate_t_flush(12, 4, 18),
        "lat": 13.3120,
        "lng": 76.9450,
        "downstream_id": "J2"
    },
    {
        "id": "J2",
        "name": "Gubbi Town Cross Junction",
        "signal_state": "RED",
        "cars": 24,
        "trucks": 8,
        "bikes": 35,
        "t_flush_sec": calculate_t_flush(24, 8, 35),
        "lat": 13.3110,
        "lng": 76.9410,
        "downstream_id": "J3"
    },
    {
        "id": "J3",
        "name": "Nittur Highway Market Bottleneck",
        "signal_state": "RED",
        "cars": 19,
        "trucks": 7,
        "bikes": 26,
        "t_flush_sec": calculate_t_flush(19, 7, 26),
        "lat": 13.3080,
        "lng": 76.9200,
        "downstream_id": "J4"
    },
    {
        "id": "J4",
        "name": "Batawadi – Tumakuru Entry Junction",
        "signal_state": "GREEN",
        "cars": 28,
        "trucks": 9,
        "bikes": 42,
        "t_flush_sec": calculate_t_flush(28, 9, 42),
        "lat": 13.3400,
        "lng": 77.1000,
        "downstream_id": None
    }
]

# Combined Master Incidents List (Both Bengaluru and NH-206 Scenarios)
incidents = [
    # NH-206 Corridor Incidents
    {
        "id": "NH-204",
        "type": "Accident",
        "title": "Sugarcane Tractor Breakdown",
        "road": "NH-206 · Gubbi Town Cross Junction",
        "area": "Gubbi Cross",
        "lat": 13.311,
        "x": 69,
        "y": 43,
        "severity": "High",
        "reported": "08:42 AM",
        "status": "Reported",
        "delay": 16,
        "detail": "Overturned agricultural tractor obstructing Tumakuru-bound carriage. Emergency green wave corridor on standby.",
        "detour": "Divert via Gubbi bypass rural link road.",
        "impact": "High",
        "corridor": "nh206"
    },
    {
        "id": "NH-203",
        "type": "Roadworks",
        "title": "Culvert Structural Repair",
        "road": "NH-206 · Nittur Highway Market Bottleneck",
        "area": "Nittur Market",
        "lat": 13.308,
        "x": 43,
        "y": 27,
        "severity": "Medium",
        "reported": "08:18 AM",
        "status": "In progress",
        "delay": 10,
        "detail": "PWD culvert reinforcement reduces highway transit to single staggered lane.",
        "detour": "Alternate bypass via Chelur feeder link.",
        "impact": "Medium",
        "corridor": "nh206"
    },
    {
        "id": "NH-202",
        "type": "Congestion",
        "title": "Peak Freight & Bus Transit Surge",
        "road": "NH-206 · CIT Campus Gate",
        "area": "CIT Gubbi",
        "lat": 13.312,
        "x": 35,
        "y": 65,
        "severity": "Medium",
        "reported": "07:56 AM",
        "status": "In progress",
        "delay": 12,
        "detail": "High volume of academic transport and heavy multi-axle freight entering NH-206.",
        "detour": "Utilize CIT campus south service perimeter lane.",
        "impact": "Medium",
        "corridor": "nh206"
    },
    {
        "id": "NH-201",
        "type": "Road closure",
        "title": "Toll Weighbridge Inspection",
        "road": "NH-206 · Batawadi Entry Junction",
        "area": "Batawadi Tumakuru",
        "lat": 13.340,
        "x": 55,
        "y": 51,
        "severity": "Low",
        "reported": "07:30 AM",
        "status": "Resolved",
        "delay": 3,
        "detail": "Weigh-in-motion sensor calibration completed; all highway lanes reopened.",
        "detour": "No detour currently required.",
        "impact": "Low",
        "corridor": "nh206"
    },

    # Bengaluru Corridor Incidents (Preserved from Step 1)
    {
        "id": "DF-104",
        "type": "Accident",
        "title": "Multi-vehicle collision",
        "road": "Outer Ring Road · Marathahalli Bridge",
        "area": "Marathahalli",
        "lat": 30,
        "x": 69,
        "y": 43,
        "severity": "High",
        "reported": "08:42 AM",
        "status": "Reported",
        "delay": 18,
        "detail": "Two vehicles blocking the left lane. Emergency access should be kept clear.",
        "detour": "Use Kundalahalli Gate → AECS Layout → Marathahalli service road.",
        "impact": "High",
        "corridor": "bengaluru"
    },
    {
        "id": "DF-103",
        "type": "Roadworks",
        "title": "Utility maintenance",
        "road": "100 Feet Road · Indiranagar",
        "area": "Indiranagar",
        "lat": 30,
        "x": 43,
        "y": 27,
        "severity": "Medium",
        "reported": "08:18 AM",
        "status": "In progress",
        "delay": 9,
        "detail": "Scheduled utility work has reduced the road to one lane.",
        "detour": "Divert via 12th Main and CMH Road.",
        "impact": "Medium",
        "corridor": "bengaluru"
    },
    {
        "id": "DF-102",
        "type": "Congestion",
        "title": "Heavy peak-hour traffic",
        "road": "Old Airport Road · Domlur",
        "area": "Domlur",
        "lat": 30,
        "x": 35,
        "y": 65,
        "severity": "Medium",
        "reported": "07:56 AM",
        "status": "In progress",
        "delay": 12,
        "detail": "Traffic is moving slowly near the flyover approach.",
        "detour": "Try Intermediate Ring Road via Ejipura.",
        "impact": "Medium",
        "corridor": "bengaluru"
    },
    {
        "id": "DF-101",
        "type": "Road closure",
        "title": "Temporary lane closure",
        "road": "MG Road · Trinity Junction",
        "area": "Central Bengaluru",
        "lat": 30,
        "x": 55,
        "y": 51,
        "severity": "Low",
        "reported": "07:30 AM",
        "status": "Resolved",
        "delay": 4,
        "detail": "A short-term closure has been cleared and lanes are reopening.",
        "detour": "No detour currently required.",
        "impact": "Low",
        "corridor": "bengaluru"
    }
]

def get_summary_dict() -> dict:
    """Builds the comprehensive summary payload preserving all legacy keys and adding Step 2 extensions."""
    corridor_incidents = [
        i for i in incidents
        if i.get("corridor") == active_scenario or i.get("corridor") == "both"
    ]
    active = [i for i in corridor_incidents if i["status"] != "Resolved"]
    high = sum(i["severity"] == "High" and i["status"] != "Resolved" for i in corridor_incidents)
    resolved = sum(i["status"] == "Resolved" for i in corridor_incidents)
    avg_delay = round(sum(i.get("delay", 0) for i in active) / max(len(active), 1)) if active else 0

    return {
        # Preserved Legacy Keys
        "active": len(active),
        "high": high,
        "resolved": resolved,
        "avg_delay": avg_delay or 11,
        "response": "6 min",
        "flow": network_flow,
        "demo": True,
        # S2 Architecture Extended Keys
        "active_scenario": active_scenario,
        "junctions": [dict(j) for j in junctions],
        "impact_metrics": dict(impact_metrics),
        "telematics_clusters": dict(telematics_clusters)
    }

# ==========================================
# 1. CORE & LEGACY REST ENDPOINTS
# ==========================================

@app.route("/")
def home():
    return render_template("index.html")

@app.get("/api/incidents")
def get_incidents():
    """Returns incidents filtered by type and optionally corridor/scenario, preserving legacy JSON structure."""
    kind = request.args.get("type", "All")
    corridor = request.args.get("corridor") or request.args.get("scenario")
    with lock:
        target_corridor = corridor if corridor else active_scenario
        if target_corridor == "all":
            data = [dict(i) for i in incidents if kind == "All" or i["type"] == kind]
        else:
            data = [
                dict(i) for i in incidents
                if (kind == "All" or i["type"] == kind) and
                   (i.get("corridor") == target_corridor or i.get("corridor") == "both")
            ]
    return jsonify({
        "demo": True,
        "updated": india_now().strftime("%H:%M:%S"),
        "incidents": data,
        "active_scenario": active_scenario
    })

@app.patch("/api/incidents/<incident_id>")
def update_incident(incident_id):
    """Updates the status of an incident across all corridor lists."""
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if status not in ("Reported", "In progress", "Resolved"):
        return jsonify({"error": "Unsupported status"}), 400
    with lock:
        item = next((i for i in incidents if i["id"] == incident_id), None)
        if not item:
            return jsonify({"error": "Incident not found"}), 404
        item["status"] = status
    return jsonify({"ok": True, "incident": item, "demo": True})

@app.get("/api/summary")
def summary():
    """Returns the extended summary containing all original keys plus Step 2 additions."""
    with lock:
        data = get_summary_dict()
    return jsonify(data)

# ==========================================
# 2. STEP 2: S2 REST ENDPOINTS
# ==========================================

@app.post("/api/corridor/switch")
def switch_corridor():
    """Switches active_scenario between 'nh206' and 'bengaluru', returning updated summary and incidents."""
    global active_scenario
    payload = request.get_json(silent=True) or {}
    target = payload.get("scenario") or payload.get("corridor")
    with lock:
        if target in ("nh206", "bengaluru"):
            active_scenario = target
        else:
            active_scenario = "bengaluru" if active_scenario == "nh206" else "nh206"

        current_incidents = [
            dict(i) for i in incidents
            if i.get("corridor") == active_scenario or i.get("corridor") == "both"
        ]
        summary_data = get_summary_dict()

    return jsonify({
        "ok": True,
        "active_scenario": active_scenario,
        "summary": summary_data,
        "incidents": current_incidents
    })

@app.post("/api/preempt/trigger")
def trigger_preempt():
    """
    Executes Greenshields Queue-Flush emergency vehicle preemption algorithm:
    - Calculates clearance time t_flush and ambulance ETA
    - Preempts target junction to PREEMPT_GREEN and downstream to GREEN_WAVE_STANDBY
    - Logs high-priority green wave incident and increments saved life & fuel metrics
    """
    payload = request.get_json(silent=True) or {}
    junction_id = payload.get("junction_id", "J1")

    with lock:
        target_j = next((j for j in junctions if j["id"] == junction_id), junctions[0])

        cars = int(payload.get("cars", target_j["cars"]))
        trucks = int(payload.get("trucks", target_j["trucks"]))
        bikes = int(payload.get("bikes", target_j["bikes"]))
        ambulance_dist_m = float(payload.get("ambulance_dist_m", 800.0))
        ambulance_speed_kmh = float(payload.get("ambulance_speed_kmh", 55.0))
        siren_confidence = float(payload.get("siren_confidence", 0.94))

        # Greenshields Queue-Flush time
        t_flush = 3.5 + (cars * (4.5 + 2.0) / 6.5) + (trucks * (10.5 + 3.0) / 4.0) + (bikes * (2.0 + 1.2) / 8.0)

        # Ambulance ETA
        speed_mps = max((ambulance_speed_kmh * 1000.0 / 3600.0), 1.0)
        eta_sec = ambulance_dist_m / speed_mps

        # Update target junction
        target_j["cars"] = cars
        target_j["trucks"] = trucks
        target_j["bikes"] = bikes
        target_j["signal_state"] = "PREEMPT_GREEN"
        target_j["t_flush_sec"] = round(t_flush, 1)

        # Update downstream junction
        idx = junctions.index(target_j)
        downstream_j = junctions[idx + 1] if idx + 1 < len(junctions) else None
        if downstream_j:
            downstream_j["signal_state"] = "GREEN_WAVE_STANDBY"

        # Update S2 Impact Metrics
        sec_saved = round(t_flush + 42)
        fuel_saved = round((cars * 0.08 + trucks * 0.25), 2)
        impact_metrics["golden_hour_sec_saved"] += sec_saved
        impact_metrics["fuel_litres_saved"] = round(impact_metrics["fuel_litres_saved"] + fuel_saved, 2)
        impact_metrics["active_green_waves"] += 1

        # Insert high-priority incident log
        gw_incident = {
            "id": f"GW-{len(incidents) + 101}",
            "type": "Accident",
            "title": f"Emergency Green Wave Active — Queue Flush T={round(t_flush, 1)}s",
            "road": f"NH-206 · {target_j['name']}",
            "area": target_j['name'].split("(")[0].strip(),
            "lat": target_j.get("lat", 13.312),
            "x": 48,
            "y": 32,
            "severity": "High",
            "reported": india_now().strftime("%I:%M:%S %p"),
            "status": "In progress",
            "delay": 0,
            "detail": f"Emergency preemption corridor engaged. ETA: {round(eta_sec, 1)}s ({round(ambulance_dist_m)}m @ {round(ambulance_speed_kmh)} km/h). Siren confidence: {int(siren_confidence * 100)}%.",
            "detour": "Clear emergency priority corridor. All conflicting approaches held on RED.",
            "impact": "High",
            "corridor": "nh206"
        }
        incidents.insert(0, gw_incident)

    return jsonify({
        "ok": True,
        "junction_id": target_j["id"],
        "junction_name": target_j["name"],
        "t_flush_sec": round(t_flush, 2),
        "eta_sec": round(eta_sec, 2),
        "speed_mps": round(speed_mps, 2),
        "ambulance_dist_m": ambulance_dist_m,
        "ambulance_speed_kmh": ambulance_speed_kmh,
        "siren_confidence": siren_confidence,
        "formula": "3.5 + (cars * (4.5 + 2.0) / 6.5) + (trucks * (10.5 + 3.0) / 4.0) + (bikes * (2.0 + 1.2) / 8.0)",
        "queue_breakdown": {
            "cars": cars,
            "trucks": trucks,
            "bikes": bikes,
            "startup_lost_time_sec": 3.5,
            "car_flush_sec": round(cars * 6.5 / 6.5, 2),
            "truck_flush_sec": round(trucks * 13.5 / 4.0, 2),
            "bike_flush_sec": round(bikes * 3.2 / 8.0, 2)
        },
        "target_signal_state": "PREEMPT_GREEN",
        "downstream_junction_id": downstream_j["id"] if downstream_j else None,
        "downstream_signal_state": "GREEN_WAVE_STANDBY" if downstream_j else None,
        "impact_increment": {
            "golden_hour_sec_saved": sec_saved,
            "fuel_litres_saved": fuel_saved
        },
        "impact_metrics": dict(impact_metrics),
        "incident": gw_incident
    })

@app.post("/api/telematics/shock")
def telematics_shock():
    """
    Ingests inertial probe telemetry for vertical jerk / road surface quality:
    - Filters low-speed / low-intensity noise (<15 km/h or <15 m/s³)
    - Aggregates cluster counts per corridor
    - On 3x hits, automatically generates a verified pothole blackspot and PWD work order
    """
    payload = request.get_json(silent=True) or {}
    corridor = payload.get("corridor") or active_scenario
    source = payload.get("source", "simulator")
    probe_id = str(payload.get("probe_id", ""))
    z_jerk = float(payload.get("z_jerk", 0.0))
    speed_kmh = float(payload.get("speed_kmh", 0.0))
    lat = float(payload.get("lat", 13.3120))
    lng = float(payload.get("lng", 76.9450))

    # Noise filter: ignore if speed < 15 km/h or z_jerk < 15 m/s³
    if speed_kmh < 15.0 or z_jerk < 15.0:
        return jsonify({
            "status": "filtered_noise",
            "reason": "Speed or vertical jerk threshold not met (< 15 km/h or < 15 m/s³)",
            "speed_kmh": speed_kmh,
            "z_jerk": z_jerk
        }), 200

    with lock:
        if source == "motion":
            probe_key = f"{corridor}:{probe_id or request.remote_addr or 'unknown'}"
            now = monotonic()
            previous_hit = motion_probe_last_hit.get(probe_key, 0.0)
            if now - previous_hit < MOTION_HIT_COOLDOWN_SECONDS:
                return jsonify({
                    "status": "motion_cooldown",
                    "retry_after_seconds": round(MOTION_HIT_COOLDOWN_SECONDS - (now - previous_hit), 1)
                }), 200
            motion_probe_last_hit[probe_key] = now

        telematics_clusters[corridor] = telematics_clusters.get(corridor, 0) + 1
        count = telematics_clusters[corridor]

        if count < 3:
            return jsonify({
                "status": "clustering",
                "hits": count,
                "needed": 3,
                "corridor": corridor
            }), 200

        # count >= 3: verified blackspot triggered
        impact_metrics["verified_blackspots"] += 1
        impact_metrics["pwd_work_orders"] += 1
        telematics_clusters[corridor] = 0  # Reset cluster accumulator for next blackspot detection

        new_incident = {
            "id": f"BS-{len(incidents) + 201}",
            "type": "Roadworks",
            "title": "Verified Pothole Blackspot (3x Inertial Cluster)",
            "road": f"NH-206 · Gubbi-Nittur Highway Segment" if corridor == "nh206" else "Outer Ring Road Telematics Sector",
            "area": "Gubbi-Nittur Km 18.2" if corridor == "nh206" else "Marathahalli East",
            "lat": lat,
            "x": 52,
            "y": 48,
            "severity": "High",
            "reported": india_now().strftime("%I:%M:%S %p"),
            "status": "Reported",
            "delay": 14,
            "detail": f"Triangulated inertial probe cluster: 3 independent probe hits registered severe vertical shock (z-jerk: {round(z_jerk, 1)} m/s³ @ {round(speed_kmh, 1)} km/h). PWD work order automatically generated.",
            "detour": "Caution advised. Highway single lane diversion marked.",
            "impact": "High",
            "corridor": corridor
        }
        incidents.insert(0, new_incident)

    return jsonify({
        "status": "verified_blackspot",
        "hits": count,
        "incident": new_incident,
        "pwd_work_orders": impact_metrics["pwd_work_orders"],
        "verified_blackspots": impact_metrics["verified_blackspots"]
    }), 201

@app.post("/api/simulate/tick")
def simulate_tick():
    """
    Simulates real-time live highway traffic dynamics on NH-206:
    - Fluctuates queue counts (cars, trucks, bikes) and recalculates t_flush
    - Fluctuates network flow percentage
    - Returns updated state
    """
    global network_flow
    with lock:
        # Fluctuates network flow gently between 60% and 88%
        network_flow = max(60, min(88, network_flow + random.choice([-2, -1, 0, 1, 2])))

        # Fluctuate junction queues
        for j in junctions:
            j["cars"] = max(4, min(50, j["cars"] + random.choice([-2, -1, 0, 1, 2])))
            j["trucks"] = max(1, min(20, j["trucks"] + random.choice([-1, 0, 1])))
            j["bikes"] = max(8, min(65, j["bikes"] + random.choice([-3, -2, -1, 0, 1, 2, 3])))
            j["t_flush_sec"] = calculate_t_flush(j["cars"], j["trucks"], j["bikes"])

        summary_data = get_summary_dict()

    return jsonify({
        "ok": True,
        "active_scenario": active_scenario,
        "flow": network_flow,
        "junctions": [dict(j) for j in junctions],
        "impact_metrics": dict(impact_metrics),
        "summary": summary_data
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
