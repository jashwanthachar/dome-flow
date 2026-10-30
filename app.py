from flask import Flask, render_template, jsonify, request
from datetime import datetime
from datetime import timezone
from threading import Lock, Timer
from time import monotonic
from zoneinfo import ZoneInfo
import random
import math
import base64
import hashlib
import hmac
import json
import os
import re
from collections import deque
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

app = Flask(__name__)
lock = Lock()
INDIA_TZ = ZoneInfo("Asia/Kolkata")
MOTION_HIT_COOLDOWN_SECONDS = 3.0
motion_probe_last_hit = {}
preemption_release_sequences = {}
PREEMPT_RELEASE_AMBER_SECONDS = 3.0
PREEMPT_RELEASE_ALL_RED_SECONDS = 1.0

# Security and plausibility thresholds are demo assumptions; validate before field deployment.
AUTH_CONFIG = {
    "TOKEN_MAX_AGE_S": 10,  # ASSUMPTION: signed report freshness window.
    "MAX_PLAUSIBLE_KMH": 150,  # ASSUMPTION: maximum reported and implied vehicle speed.
    "REPORT_RATE_WINDOW_S": 1,  # ASSUMPTION: rate-limit window per vehicle.
    "MAX_REPORTS_PER_WINDOW": 5,  # ASSUMPTION: allowed signed reports per vehicle per window.
    "NONCE_WINDOW_S": 10,  # ASSUMPTION: retain replay nonces for at least token lifetime.
    "MAX_STORED_NONCES": 10000,  # ASSUMPTION: in-memory replay cache capacity.
    "MAX_VEHICLES": 500,  # ASSUMPTION: in-memory demo registry capacity.
    "MAX_PUBLIC_KEY_B64_LENGTH": 1024,  # ASSUMPTION: enough room for DER encoded P-256 public key plus base64.
    "ARM_DISTANCE_M": 500,  # ASSUMPTION: network token early-warning radius.
    "SIREN_SPL_REF_DB": 115,  # ASSUMPTION: same nominal siren level used by the browser range estimate.
    "REF_DIST_M": 3,  # ASSUMPTION: reference distance for the free-field range calculation.
    "TRAFFIC_NOISE_DB": 78,  # ASSUMPTION: nominal road noise for the server-side mic gate.
    "MIN_SNR_DB": 6,  # ASSUMPTION: minimum nominal signal-to-noise margin for the mic gate.
    "APPROACH_CONF_MIN": 0.65,  # ASSUMPTION: minimum browser RMS trend R-squared.
    "HEADING_TOLERANCE_DEG": 30,  # ASSUMPTION: maximum difference from configured arm bearing.
    "JUNCTION_BEARING_TOLERANCE_DEG": 60,  # ASSUMPTION: heading must point generally toward junction.
    "LATITUDE_LIMIT_DEG": 90,  # ASSUMPTION: valid geographic latitude bound.
    "LONGITUDE_LIMIT_DEG": 180,  # ASSUMPTION: valid geographic longitude bound.
    "MAX_VEHICLE_ID_LENGTH": 80,  # ASSUMPTION: identifier length limit.
    "MIN_NONCE_LENGTH": 16,  # ASSUMPTION: minimum nonce entropy encoding length.
    "MAX_NONCE_LENGTH": 128  # ASSUMPTION: nonce length limit.
}

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

JUNCTION_ARM_BEARINGS = {
    "J1": {"N": 0, "E": 90, "S": 180, "W": 270},
    "J2": {"N": 10, "E": 95, "S": 190, "W": 275},
    "J3": {"N": 350, "E": 85, "S": 170, "W": 265},
    "J4": {"N": 5, "E": 100, "S": 185, "W": 280}
}

vehicle_registry = {}
seen_nonces = {}
audit_entries = []
audit_head_hash = "0" * 64


def india_now():
    return datetime.now(INDIA_TZ)


def _append_audit_locked(decision, reason, vehicle_id=None, junction_id=None):
    global audit_head_hash
    content = {
        "sequence": len(audit_entries) + 1,
        "decision": decision,
        "reason": str(reason),
        "vehicle_id": vehicle_id,
        "junction": junction_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    previous_hash = audit_head_hash
    serialized = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    entry_hash = hashlib.sha256((previous_hash + serialized).encode("utf-8")).hexdigest()
    entry = dict(content, previous_hash=previous_hash, hash=entry_hash)
    audit_entries.append(entry)
    audit_head_hash = entry_hash
    return entry


def _audit(decision, reason, vehicle_id=None, junction_id=None):
    with lock:
        return _append_audit_locked(decision, reason, vehicle_id, junction_id)


def _canonical_report(payload):
    required = ("vehicle_id", "lat", "lon", "heading_deg", "speed_kmh", "timestamp", "nonce")
    if any(key not in payload for key in required):
        raise ValueError("Missing signed report fields")
    vehicle_id = payload["vehicle_id"]
    nonce = payload["nonce"]
    if (not isinstance(vehicle_id, str) or len(vehicle_id) > AUTH_CONFIG["MAX_VEHICLE_ID_LENGTH"] or
            not re.fullmatch(r"[A-Za-z0-9_-]+", vehicle_id)):
        raise ValueError("Invalid vehicle_id")
    if (not isinstance(nonce, str) or not AUTH_CONFIG["MIN_NONCE_LENGTH"] <= len(nonce) <= AUTH_CONFIG["MAX_NONCE_LENGTH"] or
            not re.fullmatch(r"[A-Za-z0-9_-]+", nonce)):
        raise ValueError("Invalid nonce")
    try:
        lat = float(payload["lat"])
        lon = float(payload["lon"])
        heading = float(payload["heading_deg"])
        speed = float(payload["speed_kmh"])
        timestamp = int(payload["timestamp"])
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Invalid signed report numbers")
    if (isinstance(payload["timestamp"], bool) or timestamp != payload["timestamp"] or
            not all(math.isfinite(value) for value in (lat, lon, heading, speed))):
        raise ValueError("Invalid signed report numbers")
    if not -AUTH_CONFIG["LATITUDE_LIMIT_DEG"] <= lat <= AUTH_CONFIG["LATITUDE_LIMIT_DEG"]:
        raise ValueError("Latitude out of bounds")
    if not -AUTH_CONFIG["LONGITUDE_LIMIT_DEG"] <= lon <= AUTH_CONFIG["LONGITUDE_LIMIT_DEG"]:
        raise ValueError("Longitude out of bounds")
    if not 0 <= heading < 360:
        raise ValueError("Heading must be from 0 to 359.99 degrees")
    if not 0 <= speed <= AUTH_CONFIG["MAX_PLAUSIBLE_KMH"]:
        raise ValueError("Reported speed exceeds the plausible limit")

    # Fixed decimal strings make canonical JSON identical in Web Crypto and Python.
    canonical = {
        "vehicle_id": vehicle_id,
        "lat": f"{lat:.7f}",
        "lon": f"{lon:.7f}",
        "heading_deg": f"{heading:.2f}",
        "speed_kmh": f"{speed:.2f}",
        "timestamp": timestamp,
        "nonce": nonce
    }
    for key in ("lat", "lon", "heading_deg", "speed_kmh"):
        if not isinstance(payload[key], str) or payload[key] != canonical[key]:
            raise ValueError(f"{key} must use its canonical fixed-decimal string")
    return canonical


def _distance_m(lat1, lon1, lat2, lon2):
    earth_radius_m = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return earth_radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def _bearing_deg(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    y = math.sin(d_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _angle_difference(a, b):
    return abs((a - b + 180) % 360 - 180)


def _mic_range_m():
    return AUTH_CONFIG["REF_DIST_M"] * 10 ** (
        (AUTH_CONFIG["SIREN_SPL_REF_DB"] - AUTH_CONFIG["TRAFFIC_NOISE_DB"] - AUTH_CONFIG["MIN_SNR_DB"]) / 20
    )


def _report_metrics(report, previous=None):
    metrics = {}
    for junction in junctions:
        junction_id = junction["id"]
        distance = _distance_m(report["lat_value"], report["lon_value"], junction["lat"], junction["lng"])
        inbound_bearing = _bearing_deg(report["lat_value"], report["lon_value"], junction["lat"], junction["lng"])
        arm_bearings = JUNCTION_ARM_BEARINGS.get(junction_id, {})
        arm_id, arm_delta = min(arm_bearings.items(), key=lambda item: _angle_difference(report["heading_value"], item[1]))
        toward_delta = _angle_difference(report["heading_value"], inbound_bearing)
        prior_distance = previous.get("distances", {}).get(junction_id) if previous else None
        metrics[junction_id] = {
            "distance_m": distance,
            "eta_s": distance / max(report["speed_value"] / 3.6, 1.0),
            "arm": arm_id if arm_delta <= AUTH_CONFIG["HEADING_TOLERANCE_DEG"] else None,
            "approaching": bool(prior_distance is not None and distance < prior_distance and
                                 toward_delta <= AUTH_CONFIG["JUNCTION_BEARING_TOLERANCE_DEG"]),
            "bearing_to_junction_deg": inbound_bearing
        }
    return metrics

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

# Queue discharge assumptions; verify PCU factors against IRC:106 before presenting.
QUEUE_CONFIG = {
    "T_REACT_S": 3.5,  # ASSUMPTION: driver reaction delay; retain current demo value.
    "T_STARTUP_S": 2.0,  # ASSUMPTION: start-up lost time.
    "H_S_PER_PCU": 2.0,  # ASSUMPTION: nominal saturation headway, about 1800 PCU/hr/lane.
    "H_LOW_S_PER_PCU": 1.7,  # ASSUMPTION: optimistic headway bound.
    "H_HIGH_S_PER_PCU": 2.6,  # ASSUMPTION: conservative headway bound.
    "PCU_UNCERTAINTY": 0.15,  # ASSUMPTION: relative uncertainty applied to total PCU.
    "GREEN_START_EARLY_BUFFER_S": 1.0,  # ASSUMPTION: start queue discharge slightly before the calculated deadline.
    # ASSUMPTION: Verify against IRC:106 table before presenting. Replace if different.
    "PCU_FACTORS": {"car": 1.0, "two_wheeler": 0.5, "heavy_vehicle": 2.2, "auto_rickshaw": 1.2},
    # ASSUMPTION: effective discharge lanes for each approach arm; replace with field survey.
    "LANES_PER_JUNCTION_ARM": {
        junction_id: {arm: 2 for arm in ("N", "E", "S", "W")}
        for junction_id in ("J1", "J2", "J3", "J4")
    }
}


def calculate_queue_discharge(cars, trucks, bikes, auto_rickshaws=0, effective_lanes=2):
    """Pure saturation-flow estimate returning nominal and uncertainty bounds in seconds."""
    counts = {
        "car": max(0, int(cars)),
        "two_wheeler": max(0, int(bikes)),
        "heavy_vehicle": max(0, int(trucks)),
        "auto_rickshaw": max(0, int(auto_rickshaws))
    }
    lanes = max(float(effective_lanes), 1.0)
    factors = QUEUE_CONFIG["PCU_FACTORS"]
    pcu_total = sum(counts[name] * factors[name] for name in counts)
    fixed_delay = QUEUE_CONFIG["T_REACT_S"] + QUEUE_CONFIG["T_STARTUP_S"]
    uncertainty = QUEUE_CONFIG["PCU_UNCERTAINTY"]
    nominal = fixed_delay + pcu_total * QUEUE_CONFIG["H_S_PER_PCU"] / lanes
    low = fixed_delay + pcu_total * (1 - uncertainty) * QUEUE_CONFIG["H_LOW_S_PER_PCU"] / lanes
    high = fixed_delay + pcu_total * (1 + uncertainty) * QUEUE_CONFIG["H_HIGH_S_PER_PCU"] / lanes
    class_contributions = {
        name: counts[name] * factors[name] * QUEUE_CONFIG["H_S_PER_PCU"] / lanes
        for name in counts
    }
    return {
        "nominal_sec": nominal,
        "low_sec": low,
        "high_sec": high,
        "pcu_total": pcu_total,
        "pcu_uncertainty": uncertainty,
        "effective_lanes": lanes,
        "reaction_sec": QUEUE_CONFIG["T_REACT_S"],
        "startup_sec": QUEUE_CONFIG["T_STARTUP_S"],
        "class_contributions_sec": class_contributions
    }


def update_junction_queue_estimate(junction, arm="N"):
    lanes = QUEUE_CONFIG["LANES_PER_JUNCTION_ARM"].get(junction["id"], {}).get(arm, 2)
    estimate = calculate_queue_discharge(
        junction["cars"], junction["trucks"], junction["bikes"],
        junction.get("auto_rickshaws", 0), lanes
    )
    junction["queue_estimate"] = estimate
    junction["t_flush_sec"] = round(estimate["nominal_sec"], 1)
    junction["t_flush_low_sec"] = round(estimate["low_sec"], 1)
    junction["t_flush_high_sec"] = round(estimate["high_sec"], 1)

# NH-206 Junctions State (CIT Gubbi to Tumakuru Corridor)
junctions = [
    {
        "id": "J1",
        "name": "CIT Campus Gate (NH-206)",
        "signal_state": "GREEN",
        "cars": 12,
        "trucks": 4,
        "bikes": 18,
        "auto_rickshaws": 0,
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
        "auto_rickshaws": 0,
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
        "auto_rickshaws": 0,
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
        "auto_rickshaws": 0,
        "lat": 13.3400,
        "lng": 77.1000,
        "downstream_id": None
    }
]

for junction in junctions:
    update_junction_queue_estimate(junction)

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


@app.get("/ambulance")
def ambulance_app():
    return render_template("ambulance.html")


@app.post("/api/vehicle/enroll")
def enroll_vehicle():
    payload = request.get_json(silent=True) or {}
    vehicle_id = payload.get("vehicle_id")
    public_key_b64 = payload.get("public_key")
    if (not isinstance(vehicle_id, str) or len(vehicle_id) > AUTH_CONFIG["MAX_VEHICLE_ID_LENGTH"] or
            not re.fullmatch(r"[A-Za-z0-9_-]+", vehicle_id or "")):
        return jsonify({"ok": False, "reason": "Invalid vehicle_id"}), 400
    if not isinstance(public_key_b64, str) or len(public_key_b64) > AUTH_CONFIG["MAX_PUBLIC_KEY_B64_LENGTH"]:
        return jsonify({"ok": False, "reason": "Public key is missing or too large"}), 400
    try:
        public_key_der = base64.b64decode(public_key_b64, validate=True)
        public_key = serialization.load_der_public_key(public_key_der)
    except (TypeError, ValueError, base64.binascii.Error):
        return jsonify({"ok": False, "reason": "Invalid public key encoding"}), 400
    if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(public_key.curve, ec.SECP256R1):
        return jsonify({"ok": False, "reason": "Only ECDSA P-256 public keys are accepted"}), 400

    with lock:
        existing = vehicle_registry.get(vehicle_id)
        if existing:
            if existing["public_key_b64"] != public_key_b64:
                return jsonify({"ok": False, "reason": "Vehicle ID is already enrolled with another key"}), 409
            return jsonify({"ok": True, "vehicle_id": vehicle_id, "status": existing["status"]})
        if len(vehicle_registry) >= AUTH_CONFIG["MAX_VEHICLES"]:
            return jsonify({"ok": False, "reason": "Vehicle registry is full"}), 507
        vehicle_registry[vehicle_id] = {
            "status": "pending",
            "public_key_b64": public_key_b64,
            "public_key": public_key,
            "enrolled_at": datetime.now(timezone.utc).isoformat(),
            "latest_report": None,
            "report_times": deque()
        }
        _append_audit_locked("enrolled", "Vehicle key awaiting admin approval", vehicle_id)
    return jsonify({"ok": True, "vehicle_id": vehicle_id, "status": "pending"}), 201


@app.get("/api/vehicles")
def list_vehicles():
    with lock:
        results = []
        for vehicle_id, vehicle in vehicle_registry.items():
            latest = vehicle.get("latest_report")
            results.append({
                "vehicle_id": vehicle_id,
                "status": vehicle["status"],
                "enrolled_at": vehicle["enrolled_at"],
                "last_report_at": latest["received_at"] if latest else None,
                "junctions": latest["junctions"] if latest else None
            })
    return jsonify({"vehicles": results})


@app.get("/api/vehicle/status")
def vehicle_status():
    vehicle_id = request.args.get("vehicle_id", "")
    with lock:
        vehicle = vehicle_registry.get(vehicle_id)
        if not vehicle:
            return jsonify({"ok": False, "status": "not_enrolled"}), 404
        latest = vehicle.get("latest_report")
        return jsonify({"ok": True, "vehicle_id": vehicle_id, "status": vehicle["status"],
                        "report": latest})


@app.post("/api/dev/vehicle/<vehicle_id>/status")
def set_vehicle_status(vehicle_id):
    if not ADMIN_TOKEN or not hmac.compare_digest(request.headers.get("X-Admin-Token", ""), ADMIN_TOKEN):
        return jsonify({"ok": False, "reason": "Admin approval requires the configured ADMIN_TOKEN"}), 401
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if status not in ("approved", "revoked"):
        return jsonify({"ok": False, "reason": "Status must be approved or revoked"}), 400
    with lock:
        vehicle = vehicle_registry.get(vehicle_id)
        if not vehicle:
            return jsonify({"ok": False, "reason": "Vehicle not found"}), 404
        vehicle["status"] = status
        if status == "revoked":
            vehicle["latest_report"] = None
        _append_audit_locked(status, f"Admin set vehicle status to {status}", vehicle_id)
    return jsonify({"ok": True, "vehicle_id": vehicle_id, "status": status})


@app.post("/api/vehicle/report")
def vehicle_report():
    payload = request.get_json(silent=True) or {}
    signature_b64 = payload.get("signature")
    try:
        canonical = _canonical_report(payload)
    except ValueError as error:
        vehicle_id = payload.get("vehicle_id") if isinstance(payload.get("vehicle_id"), str) else None
        _audit("denied", f"Report rejected: {error}", vehicle_id)
        return jsonify({"ok": False, "reason": str(error)}), 400

    vehicle_id = canonical["vehicle_id"]
    now = datetime.now(timezone.utc).timestamp()
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (TypeError, ValueError, base64.binascii.Error):
        _audit("denied", "Report signature encoding is invalid", vehicle_id)
        return jsonify({"ok": False, "reason": "Invalid signature encoding"}), 400
    if len(signature) != 64:
        _audit("denied", "Web Crypto signature must be raw 64-byte r||s", vehicle_id)
        return jsonify({"ok": False, "reason": "Invalid ECDSA signature length"}), 400

    canonical_bytes = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    r_value = int.from_bytes(signature[:32], "big")
    s_value = int.from_bytes(signature[32:], "big")
    der_signature = encode_dss_signature(r_value, s_value)
    with lock:
        vehicle = vehicle_registry.get(vehicle_id)
        if not vehicle:
            _append_audit_locked("denied", "Vehicle is not enrolled", vehicle_id)
            return jsonify({"ok": False, "reason": "Vehicle is not enrolled"}), 403
        if vehicle["status"] != "approved":
            reason = f"Vehicle is {vehicle['status']}; admin approval is required"
            _append_audit_locked("denied", reason, vehicle_id)
            return jsonify({"ok": False, "reason": reason}), 403

        timestamp = canonical["timestamp"]
        age_s = now - timestamp
        if age_s < 0:
            _append_audit_locked("denied", "Signed report timestamp is in the future", vehicle_id)
            return jsonify({"ok": False, "reason": "Report timestamp is in the future"}), 400
        if age_s > AUTH_CONFIG["TOKEN_MAX_AGE_S"]:
            _append_audit_locked("denied", "Signed report is stale", vehicle_id)
            return jsonify({"ok": False, "reason": "Report is stale"}), 401

        nonce_key = vehicle_id + ":" + canonical["nonce"]
        expired = [key for key, seen_at in seen_nonces.items() if now - seen_at > AUTH_CONFIG["NONCE_WINDOW_S"]]
        for key in expired:
            seen_nonces.pop(key, None)
        if nonce_key in seen_nonces:
            _append_audit_locked("denied", "Nonce replay detected", vehicle_id)
            return jsonify({"ok": False, "reason": "Nonce replay detected"}), 409

        try:
            vehicle["public_key"].verify(der_signature, canonical_bytes, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature:
            _append_audit_locked("denied", "Signature verification failed", vehicle_id)
            return jsonify({"ok": False, "reason": "Signature verification failed"}), 401

        report_times = vehicle["report_times"]
        while report_times and now - report_times[0] > AUTH_CONFIG["REPORT_RATE_WINDOW_S"]:
            report_times.popleft()
        if len(report_times) >= AUTH_CONFIG["MAX_REPORTS_PER_WINDOW"]:
            _append_audit_locked("denied", "Vehicle report rate limit exceeded", vehicle_id)
            return jsonify({"ok": False, "reason": "Rate limit exceeded; wait before sending another report"}), 429
        report_times.append(now)

        previous = vehicle.get("latest_report")
        lat_value, lon_value = float(canonical["lat"]), float(canonical["lon"])
        heading_value, speed_value = float(canonical["heading_deg"]), float(canonical["speed_kmh"])
        if previous:
            elapsed_s = timestamp - previous["timestamp"]
            if elapsed_s <= 0:
                _append_audit_locked("denied", "Report timestamp did not advance", vehicle_id)
                return jsonify({"ok": False, "reason": "Report timestamp must advance"}), 409
            moved_m = _distance_m(previous["lat_value"], previous["lon_value"], lat_value, lon_value)
            implied_kmh = moved_m / elapsed_s * 3.6
            if implied_kmh >= AUTH_CONFIG["MAX_PLAUSIBLE_KMH"]:
                _append_audit_locked("denied", "Implausible position jump / teleport detected", vehicle_id)
                return jsonify({"ok": False, "reason": "Teleport rejected: implied speed exceeds the plausible limit"}), 400

        seen_nonces[nonce_key] = now
        if len(seen_nonces) > AUTH_CONFIG["MAX_STORED_NONCES"]:
            oldest = sorted(seen_nonces.items(), key=lambda item: item[1])[:len(seen_nonces) - AUTH_CONFIG["MAX_STORED_NONCES"]]
            for key, _seen_at in oldest:
                seen_nonces.pop(key, None)

        report = {
            "vehicle_id": vehicle_id,
            "lat_value": lat_value,
            "lon_value": lon_value,
            "heading_value": heading_value,
            "speed_value": speed_value,
            "timestamp": timestamp,
            "nonce": canonical["nonce"],
            "received_at": datetime.now(timezone.utc).isoformat()
        }
        report["junctions"] = _report_metrics(report, previous)
        vehicle["latest_report"] = report
        _append_audit_locked("report_verified", "Signed vehicle position accepted", vehicle_id)

        selected = report["junctions"].get(request.args.get("junction_id", "J2"), {})
        response = {
            "ok": True,
            "vehicle_id": vehicle_id,
            "status": "approved",
            "distance_m": selected.get("distance_m"),
            "eta_s": selected.get("eta_s"),
            "arm": selected.get("arm"),
            "approaching": selected.get("approaching"),
            "junctions": report["junctions"]
        }
    return jsonify(response)


@app.get("/api/audit")
def get_audit_log():
    with lock:
        previous = "0" * 64
        valid = True
        for entry in audit_entries:
            content = {key: entry[key] for key in ("sequence", "decision", "reason", "vehicle_id", "junction", "timestamp")}
            serialized = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            expected = hashlib.sha256((previous + serialized).encode("utf-8")).hexdigest()
            if entry.get("previous_hash") != previous or entry.get("hash") != expected:
                valid = False
                break
            previous = expected
    return jsonify({"chain_valid": valid, "entries": audit_entries[-100:]})

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
    Applies saturation-flow queue-discharge timing before granting preemption:
    - Calculates saturation-flow queue-discharge time and verified ambulance ETA
    - Preempts target junction to PREEMPT_GREEN and downstream to GREEN_WAVE_STANDBY
    - Logs high-priority green wave incident and increments saved life & fuel metrics
    """
    payload = request.get_json(silent=True) or {}
    junction_id = payload.get("junction_id", "J1")
    vehicle_id = payload.get("vehicle_id") if isinstance(payload.get("vehicle_id"), str) else None
    stage = payload.get("stage")
    siren_confirmed = payload.get("siren_confirmed") is True
    with lock:
        target_j = next((j for j in junctions if j["id"] == junction_id), None)
        if target_j is None:
            reason = "Unknown target junction"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 400

        vehicle = vehicle_registry.get(vehicle_id) if vehicle_id else None
        if not vehicle or vehicle["status"] != "approved" or not vehicle.get("latest_report"):
            if siren_confirmed and not vehicle_id:
                reason = "WATCH: siren heard without an approved signed vehicle token; no green granted"
                _append_audit_locked("watch", reason, None, junction_id)
                return jsonify({"ok": False, "decision": "WATCH", "reason": reason}), 200
            reason = "No current approved vehicle token; unauthenticated network message denied"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 403

        report = vehicle["latest_report"]
        age_s = datetime.now(timezone.utc).timestamp() - report["timestamp"]
        if age_s < 0 or age_s > AUTH_CONFIG["TOKEN_MAX_AGE_S"]:
            reason = "Approved vehicle token is stale or future-dated"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 401
        metrics = report["junctions"].get(junction_id, {})
        distance_m = metrics.get("distance_m", float("inf"))
        if distance_m > AUTH_CONFIG["ARM_DISTANCE_M"]:
            reason = "Verified ambulance is outside the network warning radius"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 403

        eta_s = metrics.get("eta_s")
        ambulance_speed_kmh = report["speed_value"]
        arm = metrics.get("arm")
        approaching = metrics.get("approaching", False)
        try:
            approach_conf = float(payload.get("approach_conf", 0))
        except (TypeError, ValueError):
            approach_conf = 0.0
        approach = payload.get("approach")

        # A fresh signed location alone only arms the junction; it can never grant green.
        if stage == "armed" or not siren_confirmed:
            reason = "ARMED: verified vehicle is in warning range; waiting for local siren confirmation"
            _append_audit_locked("armed", reason, vehicle_id, junction_id)
            return jsonify({"ok": True, "decision": "ARMED", "reason": reason,
                            "distance_m": round(distance_m, 1), "eta_s": round(eta_s, 1) if eta_s is not None else None}), 200
        if stage != "confirmed":
            reason = "Invalid preemption stage"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 400
        if distance_m > _mic_range_m():
            reason = f"MISMATCH: microphone reports a siren, but signed vehicle position is {round(distance_m)} m away"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "MISMATCH", "reason": reason,
                            "distance_m": round(distance_m, 1)}), 403
        if not approaching:
            reason = "Verified position is not approaching the selected junction"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 403
        if arm is None:
            reason = "Verified heading does not match a known arm of this junction"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 403
        if approach != "approaching" or not math.isfinite(approach_conf) or approach_conf < AUTH_CONFIG["APPROACH_CONF_MIN"]:
            reason = "Siren loudness trend is not confidently approaching"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 403

        # Ignore client distance, ETA, speed, and arm; use the signed report-derived values.
        payload["distance_m"] = distance_m
        payload["eta_s"] = eta_s
        payload["ambulance_speed_kmh"] = ambulance_speed_kmh
        payload["arm"] = arm

        cars = int(payload.get("cars", target_j["cars"]))
        trucks = int(payload.get("trucks", target_j["trucks"]))
        bikes = int(payload.get("bikes", target_j["bikes"]))
        ambulance_dist_m = distance_m
        pending_release = preemption_release_sequences.pop(target_j["id"], None)
        previous_target_state = pending_release["previous_target_state"] if pending_release else target_j["signal_state"]
        previous_downstream_state = pending_release["previous_downstream_state"] if pending_release else None
        siren_confidence = max(0.0, min(1.0, float(payload.get("siren_confidence", 0.0))))
        siren_label = payload.get("siren_label", "none")
        if siren_label not in ("wail", "yelp", "hi-lo", "none"):
            siren_label = "none"

        lanes = QUEUE_CONFIG["LANES_PER_JUNCTION_ARM"].get(target_j["id"], {}).get(arm, 2)
        queue_estimate = calculate_queue_discharge(cars, trucks, bikes, target_j.get("auto_rickshaws", 0), lanes)
        t_flush = queue_estimate["nominal_sec"]
        t_flush_high = queue_estimate["high_sec"]

        # Ambulance ETA
        speed_mps = max((ambulance_speed_kmh * 1000.0 / 3600.0), 1.0)
        eta_sec = ambulance_dist_m / speed_mps
        green_start_in = eta_sec - t_flush_high
        if green_start_in < 0:
            reason = (f"TOO LATE: queue will not clear in time; ETA {eta_sec:.1f}s is below "
                      f"the conservative queue-discharge estimate {t_flush_high:.1f}s")
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "TOO_LATE", "reason": reason,
                            "eta_s": round(eta_sec, 1), "t_flush_sec": round(t_flush, 1),
                            "t_flush_low_sec": round(queue_estimate["low_sec"], 1),
                            "t_flush_high_sec": round(t_flush_high, 1),
                            "green_start_in": round(green_start_in, 1)}), 409
        if green_start_in > QUEUE_CONFIG["GREEN_START_EARLY_BUFFER_S"]:
            reason = (f"Queue-discharge start in {green_start_in:.1f}s; the conservative clearance "
                      "estimate will be rechecked before green")
            _append_audit_locked("timing_wait", reason, vehicle_id, junction_id)
            return jsonify({"ok": True, "decision": "WAIT", "reason": reason,
                            "eta_s": round(eta_sec, 1), "t_flush_sec": round(t_flush, 1),
                            "t_flush_low_sec": round(queue_estimate["low_sec"], 1),
                            "t_flush_high_sec": round(t_flush_high, 1),
                            "green_start_in": round(green_start_in, 1)}), 200

        # Update target junction
        target_j["cars"] = cars
        target_j["trucks"] = trucks
        target_j["bikes"] = bikes
        target_j["queue_estimate"] = queue_estimate
        target_j["signal_state"] = "PREEMPT_GREEN"
        target_j["t_flush_sec"] = round(t_flush, 1)
        target_j["t_flush_low_sec"] = round(queue_estimate["low_sec"], 1)
        target_j["t_flush_high_sec"] = round(t_flush_high, 1)

        # Update downstream junction
        idx = junctions.index(target_j)
        downstream_j = junctions[idx + 1] if idx + 1 < len(junctions) else None
        if downstream_j:
            if previous_downstream_state is None:
                previous_downstream_state = downstream_j["signal_state"]
            downstream_j["signal_state"] = "GREEN_WAVE_STANDBY"
        preemption_release_sequences[target_j["id"]] = {
            "previous_target_state": previous_target_state,
            "downstream_id": downstream_j["id"] if downstream_j else None,
            "previous_downstream_state": previous_downstream_state
        }

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
            "title": f"Emergency Green Wave Active — Queue Discharge T={round(t_flush, 1)}s",
            "road": f"NH-206 · {target_j['name']}",
            "area": target_j['name'].split("(")[0].strip(),
            "lat": target_j.get("lat", 13.312),
            "x": 48,
            "y": 32,
            "severity": "High",
            "reported": india_now().strftime("%I:%M:%S %p"),
            "status": "In progress",
            "delay": 0,
            "detail": f"Emergency preemption corridor engaged. ETA: {round(eta_sec, 1)}s ({round(ambulance_dist_m)}m @ {round(ambulance_speed_kmh)} km/h). Siren event: {siren_label} ({'confirmed' if siren_confirmed else 'manual'}), confidence: {round(siren_confidence * 100)}%.",
            "detour": "Clear emergency priority corridor. All conflicting approaches held on RED.",
            "impact": "High",
            "corridor": "nh206"
        }
        incidents.insert(0, gw_incident)
        _append_audit_locked("granted", "Approved vehicle token and local confirmed approaching siren agree", vehicle_id, junction_id)

    return jsonify({
        "ok": True,
        "decision": "GRANTED",
        "reason": "Approved signed vehicle, verified approaching position, arm, and close-range siren agree",
        "vehicle_id": vehicle_id,
        "junction_id": target_j["id"],
        "junction_name": target_j["name"],
        "t_flush_sec": round(t_flush, 2),
        "t_flush_low_sec": round(queue_estimate["low_sec"], 2),
        "t_flush_high_sec": round(t_flush_high, 2),
        "pcu_total": round(queue_estimate["pcu_total"], 2),
        "effective_lanes": lanes,
        "green_start_in": round(green_start_in, 2),
        "eta_sec": round(eta_sec, 2),
        "speed_mps": round(speed_mps, 2),
        "ambulance_dist_m": ambulance_dist_m,
        "ambulance_speed_kmh": ambulance_speed_kmh,
        "siren_confidence": siren_confidence,
        "siren_confirmed": siren_confirmed,
        "siren_label": siren_label,
        "approach": approach,
        "approach_conf": approach_conf,
        "arm": arm,
        "stage": stage,
        "distance_m": distance_m,
        "eta_s": eta_s,
        "formula": "t_react + t_startup + (cars*PCU_car + trucks*PCU_heavy + bikes*PCU_two_wheeler + auto_rickshaws*PCU_auto) * h / effective_lanes",
        "queue_breakdown": queue_estimate,
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

@app.post("/api/preempt/release")
def release_preempt():
    """Demo release sequence: amber, all-red, then restore the saved normal states."""
    payload = request.get_json(silent=True) or {}
    junction_id = payload.get("junction_id", "J1")
    with lock:
        target = next((j for j in junctions if j["id"] == junction_id), None)
        if target is None:
            return jsonify({"ok": False, "error": "Unknown junction"}), 404
        if target["signal_state"] != "PREEMPT_GREEN":
            return jsonify({"ok": False, "error": "No active preemption to release"}), 409
        context = preemption_release_sequences.get(junction_id, {})
        token = object()
        context["token"] = token
        preemption_release_sequences[junction_id] = context
        target["signal_state"] = "AMBER_CLEARANCE"
        downstream = next((j for j in junctions if j["id"] == context.get("downstream_id")), None)
        if downstream and downstream["signal_state"] == "GREEN_WAVE_STANDBY":
            downstream["signal_state"] = "AMBER_CLEARANCE"

    def enter_all_red():
        with lock:
            if preemption_release_sequences.get(junction_id, {}).get("token") is not token:
                return
            target["signal_state"] = "ALL_RED_CLEARANCE"
            if downstream:
                downstream["signal_state"] = "ALL_RED_CLEARANCE"
        finish_timer = Timer(PREEMPT_RELEASE_ALL_RED_SECONDS, restore_normal_states)
        finish_timer.daemon = True
        finish_timer.start()

    def restore_normal_states():
        with lock:
            release = preemption_release_sequences.get(junction_id)
            if not release or release.get("token") is not token:
                return
            target["signal_state"] = release.get("previous_target_state", "RED")
            if downstream:
                downstream["signal_state"] = release.get("previous_downstream_state", "RED")
            preemption_release_sequences.pop(junction_id, None)
            impact_metrics["active_green_waves"] = max(0, impact_metrics["active_green_waves"] - 1)

    amber_timer = Timer(PREEMPT_RELEASE_AMBER_SECONDS, enter_all_red)
    amber_timer.daemon = True
    amber_timer.start()
    return jsonify({
        "ok": True,
        "stage": "amber_clearance",
        "next_stage": "all_red_clearance",
        "amber_seconds": PREEMPT_RELEASE_AMBER_SECONDS,
        "all_red_seconds": PREEMPT_RELEASE_ALL_RED_SECONDS,
        "message": "Amber then all-red clearance will complete before the saved normal states resume."
    })


@app.post("/api/telematics/shock")
def telematics_shock():
    """
    Ingests inertial probe telemetry for motion jerk / road surface quality:
    - Filters low-speed / low-intensity noise (<15 km/h or <15 m/s³)
    - Aggregates cluster counts per corridor
    - On 3x hits, automatically generates a verified pothole blackspot and PWD work order
    """
    payload = request.get_json(silent=True) or {}
    corridor = payload.get("corridor") or active_scenario
    source = payload.get("source", "simulator")
    probe_id = str(payload.get("probe_id", ""))
    jerk_mps3 = float(payload.get("jerk_mps3", payload.get("z_jerk", 0.0)))
    speed_kmh = float(payload.get("speed_kmh", 0.0))
    lat = float(payload.get("lat", 13.3120))
    lng = float(payload.get("lng", 76.9450))

    # Noise filter: ignore if speed < 15 km/h or phone jerk < 15 m/s³
    if speed_kmh < 15.0 or jerk_mps3 < 15.0:
        return jsonify({
            "status": "filtered_noise",
            "reason": "Speed or motion jerk threshold not met (< 15 km/h or < 15 m/s³)",
            "speed_kmh": speed_kmh,
            "jerk_mps3": jerk_mps3
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
            "title": "Verified Phone Shock Blackspot (3 qualifying hits)",
            "road": f"NH-206 · Gubbi-Nittur Highway Segment" if corridor == "nh206" else "Outer Ring Road Telematics Sector",
            "area": "Gubbi-Nittur Km 18.2" if corridor == "nh206" else "Marathahalli East",
            "lat": lat,
            "x": 52,
            "y": 48,
            "severity": "High",
            "reported": india_now().strftime("%I:%M:%S %p"),
            "status": "Reported",
            "delay": 14,
            "detail": f"Phone motion jerk: {round(jerk_mps3, 1)} m/s³ at {round(speed_kmh, 1)} km/h; three qualifying hits verified this demo incident.",
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
    - Fluctuates queue counts (cars, trucks, bikes) and recalculates discharge estimates
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
            update_junction_queue_estimate(j)

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
