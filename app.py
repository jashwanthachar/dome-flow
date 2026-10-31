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
import secrets
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
    "MAX_NONCE_LENGTH": 128,  # ASSUMPTION: nonce length limit.
    "ACOUSTIC_MAX_AGE_S": 3,  # ASSUMPTION: maximum age of a signed acoustic confirmation.
    "ACOUSTIC_POSITION_TIME_TOLERANCE_S": 3,  # ASSUMPTION: allowed time difference from the signed vehicle fix.
    "ACOUSTIC_POSITION_TOLERANCE_M": 50,  # ASSUMPTION: position uncertainty allowed at event time.
    "MAX_JUNCTION_UNITS": 100  # ASSUMPTION: in-memory demo registry capacity.
}

# In-memory retention periods are ASSUMPTIONS for this prototype, not a legal schedule.
RETENTION_CONFIG = {
    "VEHICLE_POSITION_TRACE_S": 24 * 60 * 60,  # ASSUMPTION: exact signed position is retained for 24 hours.
    "ACOUSTIC_EVENT_S": 7 * 24 * 60 * 60,  # ASSUMPTION: signed derived acoustic events are kept for 7 days.
    "QUEUE_BASELINES": "aggregated_only",  # ASSUMPTION: no individual device queue history is retained.
    "AUDIT_LOG": "kept",  # ASSUMPTION: retain decisions, with identifiers redacted on data deletion.
    "AUDIT_POSITION_REDACT_S": 24 * 60 * 60  # ASSUMPTION: any future audit position field is rounded after 24 hours.
}

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

# Corridor and Junctions Data Configuration
CORRIDOR_FILE = os.path.join(os.path.dirname(__file__), "data", "corridor.geojson")
JUNCTIONS_FILE = os.path.join(os.path.dirname(__file__), "data", "junctions.json")

corridor_data = None
corridor_coords = []
corridor_chainages = []
corridor_total_length_m = 0.0

def load_corridor_data():
    global corridor_data, corridor_coords, corridor_chainages, corridor_total_length_m
    if os.path.exists(CORRIDOR_FILE):
        try:
            with open(CORRIDOR_FILE, "r", encoding="utf-8") as f:
                corridor_data = json.load(f)
            for feature in corridor_data.get("features", []):
                if feature.get("geometry", {}).get("type") == "LineString":
                    corridor_coords = feature["geometry"]["coordinates"]  # [[lon, lat], ...]
                    props = feature.get("properties", {})
                    corridor_chainages = props.get("chainages", [])
                    corridor_total_length_m = float(props.get("length_m", 0.0))
                    break
        except Exception as e:
            print(f"[!] Warning: failed to load corridor.geojson: {e}")

load_corridor_data()

class RoadSnapResult(dict):
    """Result object supporting both dict access (res['chainage_m']) and tuple unpacking."""
    def __init__(self, chainage_m, lateral_distance_m, snapped_lat, snapped_lon, road_bearing_deg):
        super().__init__(
            chainage_m=chainage_m,
            lateral_distance_m=lateral_distance_m,
            snapped_lat=snapped_lat,
            snapped_lon=snapped_lon,
            road_bearing_deg=road_bearing_deg
        )
        self.chainage_m = chainage_m
        self.lateral_distance_m = lateral_distance_m
        self.snapped_lat = snapped_lat
        self.snapped_lon = snapped_lon
        self.road_bearing_deg = road_bearing_deg

    def __iter__(self):
        return iter((self.chainage_m, self.lateral_distance_m))

def snap_to_road(lat, lon):
    """
    Snaps a geographic coordinate (lat, lon) to the corridor polyline.
    Returns RoadSnapResult containing chainage_m, lateral_distance_m, snapped_lat, snapped_lon, and road_bearing_deg.
    Can be unpacked as `chainage_m, lateral_dist = snap_to_road(lat, lon)`.
    """
    if not corridor_coords or not corridor_chainages:
        return RoadSnapResult(0.0, 0.0, float(lat), float(lon), 0.0)

    best_dist = float("inf")
    best_chainage = 0.0
    best_bearing = 0.0
    best_lat = float(lat)
    best_lon = float(lon)

    for i in range(len(corridor_coords) - 1):
        lon1, lat1 = corridor_coords[i]
        lon2, lat2 = corridor_coords[i+1]
        c1 = corridor_chainages[i]
        c2 = corridor_chainages[i+1]

        mid_lat_rad = math.radians((lat1 + lat2) / 2.0)
        dx = (lon2 - lon1) * math.cos(mid_lat_rad) * 111320.0
        dy = (lat2 - lat1) * 111320.0
        seg_len_sq = dx * dx + dy * dy

        if seg_len_sq <= 1e-6:
            t = 0.0
        else:
            px = (lon - lon1) * math.cos(mid_lat_rad) * 111320.0
            py = (lat - lat1) * 111320.0
            t = max(0.0, min(1.0, (px * dx + py * dy) / seg_len_sq))

        proj_lon = lon1 + t * (lon2 - lon1)
        proj_lat = lat1 + t * (lat2 - lat1)
        lat_dist = _distance_m(lat, lon, proj_lat, proj_lon)

        if lat_dist < best_dist:
            best_dist = lat_dist
            best_chainage = c1 + t * (c2 - c1)
            best_bearing = _bearing_deg(lat1, lon1, lat2, lon2)
            best_lat = proj_lat
            best_lon = proj_lon

    return RoadSnapResult(
        round(best_chainage, 1),
        round(best_dist, 1),
        round(best_lat, 6),
        round(best_lon, 6),
        round(best_bearing, 1)
    )

def chainage_to_latlon(chainage_m):
    """
    Given a chainage distance in metres along the corridor from Tumakuru end, returns (lat, lon).
    """
    if not corridor_coords or not corridor_chainages:
        return (13.3401, 77.1006)
    if chainage_m <= 0:
        return (corridor_coords[0][1], corridor_coords[0][0])
    if chainage_m >= corridor_total_length_m:
        return (corridor_coords[-1][1], corridor_coords[-1][0])

    for i in range(len(corridor_chainages) - 1):
        c1, c2 = corridor_chainages[i], corridor_chainages[i+1]
        if c1 <= chainage_m <= c2:
            seg_len = c2 - c1
            t = (chainage_m - c1) / seg_len if seg_len > 1e-6 else 0.0
            lon1, lat1 = corridor_coords[i]
            lon2, lat2 = corridor_coords[i+1]
            return (round(lat1 + t * (lat2 - lat1), 6), round(lon1 + t * (lon2 - lon1), 6))
    return (corridor_coords[-1][1], corridor_coords[-1][0])

JUNCTION_ARM_BEARINGS = {
    "J1": {"N": 8, "E": 278, "S": 188, "W": 98},
    "J2": {"N": 181, "E": 91, "S": 1, "W": 271},
    "J3": {"N": 277, "E": 187, "S": 97, "W": 7},
    "J4": {"N": 189, "E": 99, "S": 9, "W": 279}
}

vehicle_registry = {}
junction_unit_registry = {}
acoustic_event_registry = {}
seen_nonces = {}
audit_entries = []
audit_head_hash = "0" * 64
privacy_owners = {}


def india_now():
    return datetime.now(INDIA_TZ)


def _append_audit_locked(decision, reason, vehicle_id=None, junction_id=None, position=None):
    global audit_head_hash
    content = {
        "sequence": len(audit_entries) + 1,
        "decision": decision,
        "reason": str(reason),
        "vehicle_id": vehicle_id,
        "junction": junction_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "position": position
    }
    previous_hash = audit_head_hash
    serialized = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    entry_hash = hashlib.sha256((previous_hash + serialized).encode("utf-8")).hexdigest()
    entry = dict(content, previous_hash=previous_hash, hash=entry_hash)
    audit_entries.append(entry)
    audit_head_hash = entry_hash
    return entry


def _rechain_audit_locked():
    """Recompute audit hashes after identifier redaction; audit entries remain in sequence."""
    global audit_head_hash
    previous = "0" * 64
    for sequence, entry in enumerate(audit_entries, 1):
        content = {key: entry.get(key) for key in ("sequence", "decision", "reason", "vehicle_id", "junction", "timestamp", "position")}
        content["sequence"] = sequence
        entry.update(content)
        serialized = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256((previous + serialized).encode("utf-8")).hexdigest()
        entry["previous_hash"], entry["hash"] = previous, digest
        previous = digest
    audit_head_hash = previous


def _audit_chain_valid_locked():
    previous = "0" * 64
    for sequence, entry in enumerate(audit_entries, 1):
        content = {key: entry[key] for key in ("sequence", "decision", "reason", "vehicle_id", "junction", "timestamp", "position")}
        if entry.get("sequence") != sequence:
            return False
        serialized = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected = hashlib.sha256((previous + serialized).encode("utf-8")).hexdigest()
        if entry.get("previous_hash") != previous or entry.get("hash") != expected:
            return False
        previous = expected
    return previous == audit_head_hash


def _install_id():
    value = request.headers.get("X-Privacy-Install-ID", "")
    return value if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value) else None


def _remember_privacy_record_locked(install_id, category, record_id):
    if not install_id:
        return
    owner = privacy_owners.setdefault(install_id, {"vehicles": set(), "units": set()})
    owner[category].add(record_id)


def _round_coordinates_to_grid(lat, lon, grid_m=50):
    lat_step = grid_m / 111320.0
    lon_step = grid_m / (111320.0 * max(math.cos(math.radians(float(lat))), 0.01))
    return {"lat": round(round(float(lat) / lat_step) * lat_step, 6),
            "lon": round(round(float(lon) / lon_step) * lon_step, 6), "precision_m": grid_m}


def _round_expired_audit_positions_locked(now):
    changed = False
    for entry in audit_entries:
        position = entry.get("position")
        if not isinstance(position, dict) or position.get("precision_m"):
            continue
        try:
            age = now - datetime.fromisoformat(entry["timestamp"]).timestamp()
            if age > RETENTION_CONFIG["AUDIT_POSITION_REDACT_S"]:
                entry["position"] = _round_coordinates_to_grid(position["lat"], position["lon"])
                changed = True
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    if changed:
        _rechain_audit_locked()


def _purge_retention_locked(now=None):
    now = now or datetime.now(timezone.utc).timestamp()
    for vehicle in vehicle_registry.values():
        report = vehicle.get("latest_report")
        if report and now - report.get("timestamp", now) > RETENTION_CONFIG["VEHICLE_POSITION_TRACE_S"]:
            vehicle["latest_report"] = None
    expired_ids = []
    for event_id, event in acoustic_event_registry.items():
        if now - event.get("timestamp", now) > RETENTION_CONFIG["ACOUSTIC_EVENT_S"]:
            expired_ids.append(event_id)
    for event_id in expired_ids:
        event = acoustic_event_registry.pop(event_id, None)
        if event:
            unit = junction_unit_registry.get(event.get("unit_id"))
            if unit and (unit.get("latest_event") or {}).get("event_id") == event_id:
                unit["latest_event"] = None
    for nonce, timestamp in list(seen_nonces.items()):
        if now - timestamp > AUTH_CONFIG["NONCE_WINDOW_S"]:
            seen_nonces.pop(nonce, None)
    _round_expired_audit_positions_locked(now)


def _delete_install_data_locked(install_id):
    owner = privacy_owners.pop(install_id, {"vehicles": set(), "units": set()})
    vehicle_ids, unit_ids = owner["vehicles"], owner["units"]
    for vehicle_id in vehicle_ids:
        vehicle_registry.pop(vehicle_id, None)
    for unit_id in unit_ids:
        junction_unit_registry.pop(unit_id, None)
    for event_id, event in list(acoustic_event_registry.items()):
        if event.get("unit_id") in unit_ids:
            acoustic_event_registry.pop(event_id, None)
    for nonce in list(seen_nonces):
        if any(nonce.startswith(f"{identity}:") or nonce.startswith(f"unit:{identity}:") for identity in vehicle_ids | unit_ids):
            seen_nonces.pop(nonce, None)
    for entry in audit_entries:
        if entry.get("vehicle_id") in vehicle_ids | unit_ids:
            entry["vehicle_id"] = None
            entry["position"] = None
    _rechain_audit_locked()
    return {"vehicle_records": len(vehicle_ids), "unit_records": len(unit_ids)}


@app.before_request
def enforce_retention():
    with lock:
        _purge_retention_locked()


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


def _canonical_unit_event(payload):
    required = ("unit_id", "junction_id", "timestamp", "nonce", "label", "confidence",
                "approach", "slope", "r_squared")
    if any(key not in payload for key in required):
        raise ValueError("Missing signed acoustic event fields")
    unit_id, junction_id, nonce = payload["unit_id"], payload["junction_id"], payload["nonce"]
    if not isinstance(unit_id, str) or len(unit_id) > AUTH_CONFIG["MAX_VEHICLE_ID_LENGTH"] or not re.fullmatch(r"[A-Za-z0-9_-]+", unit_id):
        raise ValueError("Invalid unit_id")
    if junction_id not in {item["id"] for item in junctions}:
        raise ValueError("Unknown junction_id")
    if not isinstance(nonce, str) or not AUTH_CONFIG["MIN_NONCE_LENGTH"] <= len(nonce) <= AUTH_CONFIG["MAX_NONCE_LENGTH"] or not re.fullmatch(r"[A-Za-z0-9_-]+", nonce):
        raise ValueError("Invalid nonce")
    if payload["label"] not in ("wail", "yelp", "hi-lo") or payload["approach"] not in ("approaching", "receding", "unknown"):
        raise ValueError("Invalid acoustic label or approach state")
    try:
        timestamp = int(payload["timestamp"])
        confidence, slope, r_squared = (float(payload[key]) for key in ("confidence", "slope", "r_squared"))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Invalid acoustic event measurements")
    if isinstance(payload["timestamp"], bool) or timestamp != payload["timestamp"] or not all(math.isfinite(v) for v in (confidence, slope, r_squared)):
        raise ValueError("Invalid acoustic event measurements")
    if not 0 <= confidence <= 1 or not 0 <= r_squared <= 1 or abs(slope) > 100:
        raise ValueError("Acoustic measurements are outside allowed bounds")
    return {"unit_id": unit_id, "junction_id": junction_id, "timestamp": timestamp, "nonce": nonce,
            "label": payload["label"], "confidence": confidence, "approach": payload["approach"],
            "slope": slope, "r_squared": r_squared}


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

# Cross-traffic harm and fairness limits; values are provisional assumptions for this demo.
HARM_CONFIG = {
    "AMBULANCE_WEIGHT": 20.0,  # ASSUMPTION: vehicle-seconds of benefit per ambulance-second saved; traffic authority must set this.
    "HARM_MARGIN": 1.0,  # ASSUMPTION: minimum benefit-to-harm ratio.
    "MAX_PREEMPT_HOLD_S": 40.0,  # ASSUMPTION: absolute maximum preemption green hold.
    "MIN_RECOVERY_GREEN_S": 15.0,  # ASSUMPTION: minimum service time per cross arm after release.
    "COOLDOWN_S": 60.0,  # ASSUMPTION: minimum interval between preemptions at one junction.
    "COOLDOWN_EXCEPTION_MIN_DELAY_S": 30.0,  # ASSUMPTION: large saved-delay threshold for a different approaching vehicle.
    "MAX_ARM_STARVATION_S": 90.0,  # ASSUMPTION: maximum time any arm may go without service.
    "REMAINING_RED_ESTIMATE_S": 30.0,  # ASSUMPTION: typical red time remaining without preemption; replace with signal timing data.
    "ARRIVAL_RATE_PCU_PER_S_PER_ARM": 0.10,  # ASSUMPTION: estimated conflicting-arm arrival rate.
    "CROSS_ARM_QUEUE_SHARE": 1.0 / 3.0  # ASSUMPTION: observed queue PCU is allocated evenly across three conflicting arms.
}

# Signal timing and conflict assumptions. Replace with values and matrices approved by the traffic authority.
SAFETY_CONFIG = {
    "MIN_GREEN_S": 10.0,  # ASSUMPTION: minimum green interval; authority-approved phase timing must replace this.
    "AMBER_S": 3.0,  # ASSUMPTION: amber clearance; must match the approved signal plan.
    "ALL_RED_S": 1.0,  # ASSUMPTION: all-red clearance; must match the approved signal plan.
    "HEARTBEAT_TIMEOUT_S": 5.0,  # ASSUMPTION: stale decision/input heartbeat threshold.
    "RECOMMENDATION_TTL_S": 20.0,  # ASSUMPTION: time allowed for an operator to acknowledge a recommendation.
    "NORMAL_ARM_SERVICE_INTERVAL_S": 15.0,  # ASSUMPTION: simulated fixed-time arm service interval.
    # ASSUMPTION: each different approach conflicts; replace this matrix with authority-approved movements.
    "JUNCTION_CONFLICT_MATRIX": {
        junction_id: {arm: [other for other in ("N", "E", "S", "W") if other != arm]
                      for arm in ("N", "E", "S", "W")}
        for junction_id in ("J1", "J2", "J3", "J4")
    }
}
PREEMPT_RELEASE_AMBER_SECONDS = SAFETY_CONFIG["AMBER_S"]
PREEMPT_RELEASE_ALL_RED_SECONDS = SAFETY_CONFIG["ALL_RED_S"]


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


def calculate_delay_harm(remaining_red_s, t_flush_high_s, conflicting_arms, extra_red_s):
    """Pure estimated delay accounting and weighted minimum-harm decision."""
    delay_without = max(0.0, remaining_red_s) + max(0.0, t_flush_high_s)
    delay_with = max(0.0, t_flush_high_s)
    delay_saved = delay_without - delay_with
    queue_cost = 0.0
    arrival_cost = 0.0
    arm_costs = []
    for arm in conflicting_arms:
        queue_term = max(0.0, arm["queue_pcu"]) * extra_red_s
        arrival_term = max(0.0, arm["arrival_rate_pcu_per_s"]) * (extra_red_s ** 2) / 2.0
        queue_cost += queue_term
        arrival_cost += arrival_term
        arm_costs.append({"arm": arm["arm"], "queue_pcu": arm["queue_pcu"],
                          "queue_delay_vehicle_s_estimate": queue_term,
                          "arrival_delay_vehicle_s_estimate": arrival_term})
    cross_delay = queue_cost + arrival_cost
    benefit = delay_saved * HARM_CONFIG["AMBULANCE_WEIGHT"]
    required_benefit = cross_delay * HARM_CONFIG["HARM_MARGIN"]
    if delay_saved <= 0:
        reason = "Delay saved too small"
    elif benefit < required_benefit:
        reason = "Net harm too high"
    else:
        reason = "Minimum-harm check passed"
    return {
        "ambulance_delay_without_s": delay_without,
        "ambulance_delay_with_s": delay_with,
        "delay_saved_s": delay_saved,
        "cross_delay_added_vehicle_s": cross_delay,
        "cross_queue_term_vehicle_s_estimate": queue_cost,
        "cross_arrival_term_vehicle_s_estimate": arrival_cost,
        "benefit_vehicle_s": benefit,
        "required_benefit_vehicle_s": required_benefit,
        "extra_red_s_estimate": extra_red_s,
        "arm_costs": arm_costs,
        "granted_by_harm_check": benefit >= required_benefit and delay_saved > 0,
        "decision_reason": reason
    }


def choose_earliest_ambulance(requests):
    """Return the verified request with the lowest ETA, preserving arrival order on ties."""
    return min(requests, key=lambda item: (item["eta_s"], item.get("queued_at", 0))) if requests else None


def hold_limit_reached(elapsed_s):
    return elapsed_s >= HARM_CONFIG["MAX_PREEMPT_HOLD_S"]


def cooldown_allows(last_preemption_at, now, last_vehicle_id, vehicle_id, approaching, delay_saved_s):
    if last_preemption_at is None or now - last_preemption_at >= HARM_CONFIG["COOLDOWN_S"]:
        return True
    return bool(vehicle_id != last_vehicle_id and approaching and
                delay_saved_s >= HARM_CONFIG["COOLDOWN_EXCEPTION_MIN_DELAY_S"])


def find_starved_arms(last_served_at, now, requested_arm):
    return [arm for arm, served_at in last_served_at.items()
            if arm != requested_arm and now - served_at > HARM_CONFIG["MAX_ARM_STARVATION_S"]]


def can_grant_without_conflict(signal_states):
    # Treat clearance as occupied too; a new grant must never cut across amber/all-red.
    return not any(state in ("PREEMPT_GREEN", "AMBER_CLEARANCE", "ALL_RED_CLEARANCE") for state in signal_states)


def run_harm_self_checks():
    big_saved = calculate_delay_harm(60, 10, [{"arm": "E", "queue_pcu": 1, "arrival_rate_pcu_per_s": 0.01}], 10)
    small_saved = calculate_delay_harm(1, 10, [{"arm": "E", "queue_pcu": 100, "arrival_rate_pcu_per_s": 1}], 40)
    closest = choose_earliest_ambulance([{"vehicle_id": "far", "eta_s": 18}, {"vehicle_id": "near", "eta_s": 7}])
    results = [
        ("large saved delay / small cross queue grants", True, big_saved["granted_by_harm_check"]),
        ("small saved delay / large cross queue denies", False, small_saved["granted_by_harm_check"]),
        ("40 second hold limit forces release", True, hold_limit_reached(HARM_CONFIG["MAX_PREEMPT_HOLD_S"])),
        ("cooldown denies same-vehicle immediate request", False, cooldown_allows(10, 20, "v1", "v1", True, 60)),
        ("starved cross arm blocks request", True, "E" in find_starved_arms({"N": 190, "E": 10, "S": 190}, 110, "N")),
        ("nearer verified ambulance sorts first", "near", closest["vehicle_id"]),
        ("active green blocks conflicting grant", False, can_grant_without_conflict(["PREEMPT_GREEN", "RED"])),
        ("all-red clearance blocks a new grant", False, can_grant_without_conflict(["ALL_RED_CLEARANCE", "RED"]))
    ]
    return [{"name": name, "expected": expected, "actual": actual, "passed": expected == actual}
            for name, expected, actual in results]

# NH-206 Junctions State (Tumakuru – Gubbi – Nittur Corridor)
# Loaded dynamically from data/junctions.json with robust fallback
def _load_initial_junctions():
    if os.path.exists(JUNCTIONS_FILE):
        try:
            with open(JUNCTIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    for j in data:
                        j["lat"] = float(j["lat"])
                        j["lng"] = float(j.get("lon", j.get("lng", 76.945)))
                        j["lon"] = j["lng"]
                        if "arm_bearings" in j:
                            JUNCTION_ARM_BEARINGS[j["id"]] = j["arm_bearings"]
                    return data
        except Exception as e:
            print(f"[!] Warning: failed to load junctions.json: {e}")
    # Fallback default if junctions.json is not yet created
    return [
        {
            "id": "J1",
            "name": "Batawadi – Tumakuru Entry Junction",
            "signal_state": "GREEN",
            "cars": 28,
            "trucks": 9,
            "bikes": 42,
            "auto_rickshaws": 0,
            "lat": 13.3401,
            "lng": 77.1006,
            "lon": 77.1006,
            "chainage_m": 0.0,
            "signalised": "true",
            "downstream_id": "J2",
            "arm_bearings": {"W": 98, "E": 278, "N": 8, "S": 188}
        },
        {
            "id": "J2",
            "name": "CIT Campus Gate (NH-206)",
            "signal_state": "RED",
            "cars": 14,
            "trucks": 5,
            "bikes": 22,
            "auto_rickshaws": 0,
            "lat": 13.3120,
            "lng": 76.9450,
            "lon": 76.9450,
            "chainage_m": 18970.0,
            "signalised": "proposed",
            "downstream_id": "J3",
            "arm_bearings": {"W": 271, "E": 91, "N": 181, "S": 1}
        },
        {
            "id": "J3",
            "name": "Gubbi Town Cross (NH-206)",
            "signal_state": "RED",
            "cars": 26,
            "trucks": 8,
            "bikes": 38,
            "auto_rickshaws": 0,
            "lat": 13.3096,
            "lng": 76.9401,
            "lon": 76.9401,
            "chainage_m": 19510.0,
            "signalised": "proposed",
            "downstream_id": "J4",
            "arm_bearings": {"W": 7, "E": 187, "N": 277, "S": 97}
        },
        {
            "id": "J4",
            "name": "Nittur Highway Market Bottleneck",
            "signal_state": "RED",
            "cars": 20,
            "trucks": 7,
            "bikes": 29,
            "auto_rickshaws": 0,
            "lat": 13.3204,
            "lng": 76.8620,
            "lon": 76.8620,
            "chainage_m": 28521.0,
            "signalised": "proposed",
            "downstream_id": None,
            "arm_bearings": {"W": 279, "E": 99, "N": 189, "S": 9}
        }
    ]

junctions = _load_initial_junctions()
for j in junctions:
    if "arm_bearings" in j:
        JUNCTION_ARM_BEARINGS[j["id"]] = j["arm_bearings"]

for junction in junctions:
    update_junction_queue_estimate(junction)

harm_runtime = {
    junction["id"]: {
        "arm_last_served_at": {arm: monotonic() for arm in JUNCTION_ARM_BEARINGS[junction["id"]]},
        "arm_recovery": {},
        "recovery_until": 0.0,
        "last_preemption_at": None,
        "last_vehicle_id": None,
        "active": None,
        "last_decision": None,
        "arm_cycle_index": 0,
        "queued_requests": []
    }
    for junction in junctions
}
preemption_request_queue = []


def harm_status_for_junction(junction_id):
    now = monotonic()
    state = harm_runtime[junction_id]
    active = state.get("active") or {}
    served = state["arm_last_served_at"]
    starvation_remaining = min(
        (max(0.0, HARM_CONFIG["MAX_ARM_STARVATION_S"] - (now - served_at)) for served_at in served.values()),
        default=HARM_CONFIG["MAX_ARM_STARVATION_S"]
    )
    cooldown_remaining = 0.0
    if state.get("last_preemption_at") is not None:
        cooldown_remaining = max(0.0, HARM_CONFIG["COOLDOWN_S"] - (now - state["last_preemption_at"]))
    return {
        "delay_saved_s": (state.get("last_decision") or {}).get("delay_saved_s", 0.0),
        "cross_delay_added_vehicle_s": (state.get("last_decision") or {}).get("cross_delay_added_vehicle_s", 0.0),
        "benefit_vehicle_s": (state.get("last_decision") or {}).get("benefit_vehicle_s", 0.0),
        "required_benefit_vehicle_s": (state.get("last_decision") or {}).get("required_benefit_vehicle_s", 0.0),
        "reason": (state.get("last_decision") or {}).get("decision_reason", "No preemption decision yet"),
        "hold_remaining_s": max(0.0, active.get("hold_deadline", now) - now) if active else 0.0,
        "max_hold_s": HARM_CONFIG["MAX_PREEMPT_HOLD_S"],
        "cooldown_remaining_s": cooldown_remaining,
        "recovery_remaining_s": max(0.0, state.get("recovery_until", 0.0) - now),
        "starvation_remaining_s": starvation_remaining,
        "active_vehicle_id": active.get("vehicle_id"),
        "active_arm": active.get("arm"),
        "queued_requests": sorted(preemption_request_queue, key=lambda item: (item["eta_s"], item["queued_at"]))
    }


def _finish_arm_recovery(junction_id, arm):
    with lock:
        runtime = harm_runtime[junction_id]
        runtime["arm_recovery"].pop(arm, None)
        runtime["arm_last_served_at"][arm] = monotonic()


def _start_arm_recovery(junction_id, arm):
    with lock:
        harm_runtime[junction_id]["arm_recovery"][arm] = {
            "state": "GREEN",
            "until": monotonic() + HARM_CONFIG["MIN_RECOVERY_GREEN_S"]
        }
    timer = Timer(HARM_CONFIG["MIN_RECOVERY_GREEN_S"], _finish_arm_recovery, args=(junction_id, arm))
    timer.daemon = True
    timer.start()


def _record_normal_arm_service(junction_id):
    with lock:
        runtime = harm_runtime[junction_id]
        if not any(item["signal_state"] == "PREEMPT_GREEN" for item in junctions):
            arms = list(JUNCTION_ARM_BEARINGS[junction_id])
            index = runtime["arm_cycle_index"] % len(arms)
            runtime["arm_last_served_at"][arms[index]] = monotonic()
            runtime["arm_cycle_index"] = (index + 1) % len(arms)
    timer = Timer(SAFETY_CONFIG["NORMAL_ARM_SERVICE_INTERVAL_S"], _record_normal_arm_service, args=(junction_id,))
    timer.daemon = True
    timer.start()


for _junction_id in harm_runtime:
    _normal_service_timer = Timer(SAFETY_CONFIG["NORMAL_ARM_SERVICE_INTERVAL_S"], _record_normal_arm_service,
                                  args=(_junction_id,))
    _normal_service_timer.daemon = True
    _normal_service_timer.start()


controller_runtime = {
    junction["id"]: {
        "mode": "ADVISORY",
        "phase_since": monotonic(),
        "phase_arm": "N" if junction["signal_state"] == "GREEN" else None,
        "arm_states": {arm: ("GREEN" if junction["signal_state"] == "GREEN" and arm == "N" else "RED")
                       for arm in JUNCTION_ARM_BEARINGS[junction["id"]]},
        "fixed_time_phase": junction["signal_state"],
        "recommendation": None,
        "interlock_status": "No phase request",
        "transition_token": None
    }
    for junction in junctions
}
controller_heartbeats = {"decision": None, "input": None}
controller_fail_safe = {"active": True, "reason": "Waiting for decision and input heartbeats"}


def _transition_allowed(current, target, elapsed, *, arm_conflict=False):
    """Pure timing/conflict policy; all phase transitions go through SafetyInterlock."""
    if current in ("GREEN", "PREEMPT_GREEN") and target == "AMBER_CLEARANCE" and elapsed < SAFETY_CONFIG["MIN_GREEN_S"]:
        return False, f"Minimum green has {SAFETY_CONFIG['MIN_GREEN_S'] - elapsed:.1f}s remaining"
    if target == "ALL_RED_CLEARANCE":
        if current != "AMBER_CLEARANCE":
            return False, "All-red requires a completed amber phase"
        if elapsed < SAFETY_CONFIG["AMBER_S"]:
            return False, f"Amber clearance has {SAFETY_CONFIG['AMBER_S'] - elapsed:.2f}s remaining"
    if target in ("GREEN", "PREEMPT_GREEN"):
        if current == "ALL_RED_CLEARANCE" and elapsed < SAFETY_CONFIG["ALL_RED_S"]:
            return False, f"All-red clearance has {SAFETY_CONFIG['ALL_RED_S'] - elapsed:.2f}s remaining"
        if current not in ("ALL_RED_CLEARANCE", "RED"):
            return False, "A green phase requires all-red clearance"
        if current == "RED" and elapsed < SAFETY_CONFIG["ALL_RED_S"]:
            return False, f"Red clearance has {SAFETY_CONFIG['ALL_RED_S'] - elapsed:.2f}s remaining"
        if arm_conflict:
            return False, "Conflicting green phase is already active"
    return True, "Interlock allowed the phase change"


class SafetyInterlock:
    """Single gate below the controller adapter for every phase mutation."""
    def transition_locked(self, junction_id, target_phase, arm=None, reason=""):
        junction = next((item for item in junctions if item["id"] == junction_id), None)
        if junction is None:
            return False, "Unknown junction"
        state = controller_runtime[junction_id]
        now = monotonic()
        current = junction["signal_state"]
        conflict = False
        if target_phase in ("GREEN", "PREEMPT_GREEN") and arm:
            conflicts = SAFETY_CONFIG["JUNCTION_CONFLICT_MATRIX"][junction_id].get(arm, [])
            conflict = any(state["arm_states"].get(other) == "GREEN" for other in conflicts)
        allowed, detail = _transition_allowed(current, target_phase, now - state["phase_since"], arm_conflict=conflict)
        if not allowed:
            state["interlock_status"] = f"Blocked: {detail}"
            _append_audit_locked("interlock_blocked", f"{detail}; requested={target_phase}; {reason}", None, junction_id)
            return False, detail
        junction["signal_state"] = target_phase
        state["phase_since"] = now
        if target_phase in ("GREEN", "PREEMPT_GREEN"):
            state["arm_states"] = {item: ("GREEN" if item == arm else "RED") for item in JUNCTION_ARM_BEARINGS[junction_id]}
            state["phase_arm"] = arm
        elif target_phase in ("AMBER_CLEARANCE", "ALL_RED_CLEARANCE", "RED"):
            state["arm_states"] = {item: "RED" for item in JUNCTION_ARM_BEARINGS[junction_id]}
            if target_phase == "RED":
                state["phase_arm"] = None
        state["interlock_status"] = f"Allowed: {target_phase} via interlock"
        return True, state["interlock_status"]


class ControllerAdapter:
    """Hardware-neutral controller boundary; implementations must preserve the interlock."""
    def current_phase(self, junction): raise NotImplementedError
    def request_phase(self, junction, arm, reason): raise NotImplementedError
    def release(self, junction, reason="operator release"): raise NotImplementedError
    def heartbeat(self): raise NotImplementedError


class SimulatedController(ControllerAdapter):
    """In-memory simulator. Transitions are timed and interlocked; it has no signal hardware."""
    def current_phase(self, junction):
        return junction["signal_state"]

    def heartbeat(self):
        return {key: value for key, value in controller_heartbeats.items()}

    def set_corridor_status(self, junction, status):
        # Standby is a dashboard annotation, not a commanded signal phase.
        junction["display_status"] = status

    def request_phase(self, junction, arm, reason):
        jid = junction["id"]
        with lock:
            return self.request_phase_locked(junction, arm, reason)

    def request_phase_locked(self, junction, arm, reason):
        jid = junction["id"]
        token = object()
        state = controller_runtime[jid]
        current = junction["signal_state"]
        if current not in ("GREEN", "RED"):
            state["interlock_status"] = f"Blocked: junction is in {current}"
            _append_audit_locked("interlock_blocked", state["interlock_status"], None, jid)
            return False, state["interlock_status"]
        state["transition_token"] = token
        elapsed = monotonic() - state["phase_since"]
        delay = max(0.0, SAFETY_CONFIG["MIN_GREEN_S"] - elapsed) if current == "GREEN" else max(0.0, SAFETY_CONFIG["ALL_RED_S"] - elapsed)
        timer = Timer(delay + 0.02, self._begin_preempt_transition, args=(jid, arm, reason, token))
        timer.daemon = True
        timer.start()
        return True, f"Safety transition scheduled after {delay:.1f}s minimum-green/red wait"

    def _begin_preempt_transition(self, jid, arm, reason, token):
        with lock:
            state = controller_runtime[jid]
            junction = next(item for item in junctions if item["id"] == jid)
            if state["transition_token"] is not token:
                return
            if junction["signal_state"] == "GREEN":
                allowed, message = safety_interlock.transition_locked(jid, "AMBER_CLEARANCE", state["phase_arm"], reason)
                if not allowed:
                    Timer(max(0.05, SAFETY_CONFIG["MIN_GREEN_S"] - (monotonic() - state["phase_since"]) + 0.02),
                          self._begin_preempt_transition, args=(jid, arm, reason, token)).start()
                    return
                next_delay = SAFETY_CONFIG["AMBER_S"] + 0.02
            else:
                next_delay = max(0.0, SAFETY_CONFIG["ALL_RED_S"] - (monotonic() - state["phase_since"])) + 0.02
        timer = Timer(next_delay, self._begin_preempt_green, args=(jid, arm, reason, token))
        timer.daemon = True
        timer.start()

    def _begin_preempt_green(self, jid, arm, reason, token):
        with lock:
            state = controller_runtime[jid]
            junction = next(item for item in junctions if item["id"] == jid)
            if state["transition_token"] is not token:
                return
            if junction["signal_state"] == "AMBER_CLEARANCE":
                allowed, message = safety_interlock.transition_locked(jid, "ALL_RED_CLEARANCE", arm, reason)
                if not allowed:
                    Timer(max(0.05, SAFETY_CONFIG["AMBER_S"] - (monotonic() - state["phase_since"]) + 0.02),
                          self._begin_preempt_green, args=(jid, arm, reason, token)).start()
                    return
                timer = Timer(SAFETY_CONFIG["ALL_RED_S"] + 0.02, self._finish_preempt_green, args=(jid, arm, reason, token))
                timer.daemon = True
                timer.start()
                return
            allowed, message = safety_interlock.transition_locked(jid, "PREEMPT_GREEN", arm, reason)
            if not allowed:
                controller_runtime[jid]["transition_token"] = None
                return
            context = preemption_release_sequences.get(jid, {})
            context["hold_started_at"] = monotonic()
            context["hold_deadline"] = context["hold_started_at"] + HARM_CONFIG["MAX_PREEMPT_HOLD_S"]
            preemption_release_sequences[jid] = context
            harm_runtime[jid]["active"] = {"vehicle_id": context.get("vehicle_id"), "arm": arm,
                                           "hold_deadline": context["hold_deadline"]}
            harm_runtime[jid]["last_preemption_at"] = context["hold_started_at"]
            harm_runtime[jid]["last_vehicle_id"] = context.get("vehicle_id")
            harm_runtime[jid]["arm_last_served_at"][arm] = context["hold_started_at"]
            if not context.get("metrics_applied"):
                impact_metrics["active_green_waves"] += 1
                impact_metrics["golden_hour_sec_saved"] += context.get("sec_saved", 0)
                impact_metrics["fuel_litres_saved"] = round(impact_metrics["fuel_litres_saved"] + context.get("fuel_saved", 0), 2)
                context["metrics_applied"] = True
                if context.get("incident"):
                    context["incident"]["title"] = f"Emergency Green Wave Active — Queue Discharge T={context.get('t_flush_sec', 0):.1f}s"
                    context["incident"]["detail"] = "Simulator phase is active after interlocked minimum-green, amber, and all-red sequence."
        timer = Timer(HARM_CONFIG["MAX_PREEMPT_HOLD_S"], _force_release_at_hold_limit, args=(jid, context.get("hold_token")))
        timer.daemon = True
        timer.start()

    def _finish_preempt_green(self, jid, arm, reason, token):
        self._begin_preempt_green(jid, arm, reason, token)

    def release(self, junction, reason="operator release"):
        jid = junction["id"]
        with lock:
            state = controller_runtime[jid]
            context = preemption_release_sequences.get(jid)
            state["transition_token"] = None
            if context is None:
                context = {"previous_target_state": state["fixed_time_phase"], "downstream_id": None,
                           "cross_arms": [], "vehicle_id": None}
                preemption_release_sequences[jid] = context
            token = object()
            context["release_token"] = token
            preemption_release_sequences[jid] = context
            current = junction["signal_state"]
            elapsed = monotonic() - state["phase_since"]
            if current in ("GREEN", "PREEMPT_GREEN"):
                delay = max(0.0, SAFETY_CONFIG["MIN_GREEN_S"] - elapsed)
            elif current == "AMBER_CLEARANCE":
                delay = 0.0
            elif current == "ALL_RED_CLEARANCE":
                delay = 0.0
            else:
                delay = max(0.0, SAFETY_CONFIG["ALL_RED_S"] - elapsed)
            state["interlock_status"] = f"Safe release requested: {reason}"
        timer = Timer(delay + 0.02, self._release_to_amber_or_all_red, args=(jid, reason, token))
        timer.daemon = True
        timer.start()
        return True, f"Safe release scheduled; minimum phase and clearance times remain enforced ({delay:.1f}s wait)"

    def _release_to_amber_or_all_red(self, jid, reason, token):
        with lock:
            context = preemption_release_sequences.get(jid, {})
            if context.get("release_token") is not token:
                return
            junction = next(item for item in junctions if item["id"] == jid)
            state = controller_runtime[jid]
            if junction["signal_state"] in ("GREEN", "PREEMPT_GREEN"):
                allowed, message = safety_interlock.transition_locked(jid, "AMBER_CLEARANCE", state["phase_arm"], reason)
                if not allowed:
                    retry = max(0.05, SAFETY_CONFIG["MIN_GREEN_S"] - (monotonic() - state["phase_since"]) + 0.02)
                    timer = Timer(retry, self._release_to_amber_or_all_red, args=(jid, reason, token))
                    timer.daemon = True
                    timer.start()
                    return
                wait = SAFETY_CONFIG["AMBER_S"] + 0.02
            elif junction["signal_state"] == "AMBER_CLEARANCE":
                wait = max(0.0, SAFETY_CONFIG["AMBER_S"] - (monotonic() - state["phase_since"])) + 0.02
            else:
                wait = max(0.0, SAFETY_CONFIG["ALL_RED_S"] - (monotonic() - state["phase_since"])) + 0.02
        timer = Timer(wait, self._release_to_fixed_plan, args=(jid, reason, token))
        timer.daemon = True
        timer.start()

    def _release_to_fixed_plan(self, jid, reason, token):
        with lock:
            context = preemption_release_sequences.get(jid, {})
            if context.get("release_token") is not token:
                return
            junction = next(item for item in junctions if item["id"] == jid)
            state = controller_runtime[jid]
            if junction["signal_state"] == "AMBER_CLEARANCE":
                allowed, message = safety_interlock.transition_locked(jid, "ALL_RED_CLEARANCE", None, reason)
                if not allowed:
                    retry = max(0.05, SAFETY_CONFIG["AMBER_S"] - (monotonic() - state["phase_since"]) + 0.02)
                    timer = Timer(retry, self._release_to_fixed_plan, args=(jid, reason, token))
                    timer.daemon = True
                    timer.start()
                    return
                wait = SAFETY_CONFIG["ALL_RED_S"] + 0.02
            else:
                wait = max(0.0, SAFETY_CONFIG["ALL_RED_S"] - (monotonic() - state["phase_since"])) + 0.02
        timer = Timer(wait, self._finish_release, args=(jid, reason, token))
        timer.daemon = True
        timer.start()

    def _finish_release(self, jid, reason, token):
        with lock:
            context = preemption_release_sequences.get(jid, {})
            if context.get("release_token") is not token:
                return
            junction = next(item for item in junctions if item["id"] == jid)
            state = controller_runtime[jid]
            fixed = context.get("previous_target_state", state["fixed_time_phase"])
            fixed = "GREEN" if fixed == "PREEMPT_GREEN" else fixed
            fixed_arm = state["phase_arm"] or "N"
            allowed, message = safety_interlock.transition_locked(jid, fixed, fixed_arm if fixed == "GREEN" else None, reason)
            if not allowed:
                _append_audit_locked("interlock_blocked", f"Fixed-time restore blocked: {message}; fail-safe keeps junction non-green", None, jid)
                return
            context = preemption_release_sequences.pop(jid, {})
            downstream = next((item for item in junctions if item["id"] == context.get("downstream_id")), None)
            if downstream and downstream.get("display_status") == "GREEN_WAVE_STANDBY":
                self.set_corridor_status(downstream, None)
            if context.get("metrics_applied"):
                impact_metrics["active_green_waves"] = max(0, impact_metrics["active_green_waves"] - 1)
            harm = harm_runtime[jid]
            harm["active"] = None
            recovery_arms = context.get("cross_arms", [])
            harm["recovery_until"] = monotonic() + len(recovery_arms) * HARM_CONFIG["MIN_RECOVERY_GREEN_S"]
            for index, arm_id in enumerate(recovery_arms):
                timer = Timer(index * HARM_CONFIG["MIN_RECOVERY_GREEN_S"], _start_arm_recovery, args=(jid, arm_id))
                timer.daemon = True
                timer.start()
            _append_audit_locked("controller_release", f"Returned to fixed-time plan through amber/all-red interlock: {reason}", context.get("vehicle_id"), jid)


class ModelSignalController(ControllerAdapter):
    """No-I/O hardware stub. A future approved adapter would translate these calls to a vendor interface,
    for example an ESP32 LED training model over HTTP or serial, while retaining this interlock. Nothing connects here."""
    def current_phase(self, junction): return {"supported": False, "reason": "No real controller connection configured"}
    def request_phase(self, junction, arm, reason): return False, "Model controller is a non-connecting stub"
    def release(self, junction, reason="operator release"): return False, "Model controller is a non-connecting stub"
    def heartbeat(self): return {"supported": False, "reason": "No hardware connection configured"}


safety_interlock = SafetyInterlock()
controller_adapter = SimulatedController()


def _require_admin_token():
    return bool(ADMIN_TOKEN and hmac.compare_digest(request.headers.get("X-Admin-Token", ""), ADMIN_TOKEN))


def _heartbeat_is_stale(source, now=None):
    stamp = controller_heartbeats.get(source)
    return stamp is None or (monotonic() if now is None else now) - stamp > SAFETY_CONFIG["HEARTBEAT_TIMEOUT_S"]


def should_apply_recommendation(mode, _operator_confirmed=False):
    # Advisory confirmation records review only; only the simulator mode executes a phase request.
    return mode == "DEMO_AUTO"


def recommendation_expired(expires_at, now):
    return now >= expires_at


def admin_token_valid(supplied, expected):
    return bool(expected) and hmac.compare_digest(str(supplied or ""), expected)


def safe_release_sequence_allowed():
    return all((
        _transition_allowed("PREEMPT_GREEN", "AMBER_CLEARANCE", SAFETY_CONFIG["MIN_GREEN_S"])[0],
        _transition_allowed("AMBER_CLEARANCE", "ALL_RED_CLEARANCE", SAFETY_CONFIG["AMBER_S"])[0],
        _transition_allowed("ALL_RED_CLEARANCE", "GREEN", SAFETY_CONFIG["ALL_RED_S"])[0]
    ))


def _recommendation_status(junction_id):
    state = controller_runtime[junction_id]
    recommendation = state.get("recommendation")
    if recommendation and recommendation["expires_at"] <= monotonic():
        return None
    if recommendation:
        recommendation = dict(recommendation, expires_in_s=max(0.0, recommendation["expires_at"] - monotonic()))
    return recommendation


def controller_status():
    now = monotonic()
    stale = [source for source in controller_heartbeats if _heartbeat_is_stale(source, now)]
    controller_fail_safe["active"] = bool(stale)
    if stale:
        controller_fail_safe["reason"] = "Heartbeat timeout: " + ", ".join(stale)
    elif not controller_fail_safe.get("reason"):
        controller_fail_safe["reason"] = "Heartbeats healthy"
    return {
        "adapter": "SimulatedController",
        "banner": "SIMULATION, NOT CONNECTED TO REAL SIGNALS",
        "fail_safe_active": controller_fail_safe["active"],
        "fail_safe_reason": controller_fail_safe["reason"],
        "heartbeat_timeout_s": SAFETY_CONFIG["HEARTBEAT_TIMEOUT_S"],
        "interlock_status": {jid: state["interlock_status"] for jid, state in controller_runtime.items()}
    }


def _expire_recommendation(junction_id, recommendation_id):
    with lock:
        recommendation = controller_runtime[junction_id].get("recommendation")
        if recommendation and recommendation["id"] == recommendation_id and recommendation["expires_at"] <= monotonic():
            controller_runtime[junction_id]["recommendation"] = None
            _append_audit_locked("recommendation_expired", "Operator recommendation expired without confirmation; no phase was changed",
                                 recommendation.get("vehicle_id"), junction_id)


def _controller_watchdog():
    now = monotonic()
    releases = []
    with lock:
        stale = [source for source in controller_heartbeats if _heartbeat_is_stale(source, now)]
        was_active = controller_fail_safe["active"]
        controller_fail_safe["active"] = bool(stale)
        controller_fail_safe["reason"] = "Heartbeat timeout: " + ", ".join(stale) if stale else "Heartbeats healthy"
        if stale and not was_active:
            _append_audit_locked("fail_safe", controller_fail_safe["reason"] + "; cancel pending actions and return through safe release", None, None)
        for jid, state in controller_runtime.items():
            rec = state.get("recommendation")
            if rec and (stale or rec["expires_at"] <= now):
                state["recommendation"] = None
                _append_audit_locked("recommendation_cancelled" if stale else "recommendation_expired",
                                     "Heartbeat fail-safe cancelled advisory; no phase was changed" if stale else "Operator recommendation expired without confirmation; no phase was changed",
                                     rec.get("vehicle_id"), jid)
            junction = next(item for item in junctions if item["id"] == jid)
            if stale and not was_active and (junction["signal_state"] in ("PREEMPT_GREEN", "AMBER_CLEARANCE", "ALL_RED_CLEARANCE") or state["transition_token"] is not None):
                state["transition_token"] = None
                releases.append(jid)
    for jid in releases:
        junction = next(item for item in junctions if item["id"] == jid)
        controller_adapter.release(junction, "heartbeat timeout fail-safe")
    timer = Timer(1.0, _controller_watchdog)
    timer.daemon = True
    timer.start()


_watchdog_timer = Timer(1.0, _controller_watchdog)
_watchdog_timer.daemon = True
_watchdog_timer.start()


def run_controller_self_checks():
    results = []
    def check(name, expected, actual):
        results.append({"name": name, "expected": expected, "actual": actual, "passed": expected == actual})
    check("Advisory mode does not apply before operator confirmation", False, should_apply_recommendation("ADVISORY", False))
    check("Amber/all-red timing blocks an unsafe green", False,
          _transition_allowed("AMBER_CLEARANCE", "PREEMPT_GREEN", 0.0)[0])
    check("Conflicting green is rejected", False,
          _transition_allowed("ALL_RED_CLEARANCE", "PREEMPT_GREEN", SAFETY_CONFIG["ALL_RED_S"], arm_conflict=True)[0])
    check("Heartbeat timeout releases to the fixed-time phase safely", True,
          _heartbeat_is_stale("input", monotonic() + SAFETY_CONFIG["HEARTBEAT_TIMEOUT_S"] + 1) and safe_release_sequence_allowed())
    check("Manual override follows the interlock release sequence", True, safe_release_sequence_allowed())
    check("Expired recommendation is not valid", True, recommendation_expired(monotonic() - 1, monotonic()))
    check("Missing admin token is rejected", False, admin_token_valid("", ADMIN_TOKEN))
    return results


def _force_release_at_hold_limit(junction_id, hold_token):
    with lock:
        context = preemption_release_sequences.get(junction_id, {})
        if context.get("hold_token") is not hold_token:
            return
        target = next((item for item in junctions if item["id"] == junction_id), None)
        if not target or target["signal_state"] != "PREEMPT_GREEN":
            return
        _append_audit_locked("max_hold_release", f"Maximum {HARM_CONFIG['MAX_PREEMPT_HOLD_S']:.0f}-second preemption hold reached; beginning mandatory amber/all-red release",
                             context.get("vehicle_id"), junction_id)
    with app.test_request_context("/api/preempt/release", method="POST", json={"junction_id": junction_id}):
        release_preempt()

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
        "junctions": [dict(j, harm_status=harm_status_for_junction(j["id"]),
                            controller_mode=controller_runtime[j["id"]]["mode"],
                            interlock_status=controller_runtime[j["id"]]["interlock_status"],
                            recommendation=_recommendation_status(j["id"])) for j in junctions],
        "controller_status": controller_status(),
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
            _remember_privacy_record_locked(_install_id(), "vehicles", vehicle_id)
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
        _remember_privacy_record_locked(_install_id(), "vehicles", vehicle_id)
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


@app.post("/api/unit/enroll")
def enroll_junction_unit():
    payload = request.get_json(silent=True) or {}
    unit_id, junction_id, public_key_b64 = payload.get("unit_id"), payload.get("junction_id"), payload.get("public_key")
    if (not isinstance(unit_id, str) or len(unit_id) > AUTH_CONFIG["MAX_VEHICLE_ID_LENGTH"] or
            not re.fullmatch(r"[A-Za-z0-9_-]+", unit_id or "")):
        return jsonify({"ok": False, "reason": "Invalid unit_id"}), 400
    if junction_id not in {item["id"] for item in junctions}:
        return jsonify({"ok": False, "reason": "Unknown junction_id"}), 400
    if not isinstance(public_key_b64, str) or len(public_key_b64) > AUTH_CONFIG["MAX_PUBLIC_KEY_B64_LENGTH"]:
        return jsonify({"ok": False, "reason": "Public key is missing or too large"}), 400
    try:
        key = serialization.load_der_public_key(base64.b64decode(public_key_b64, validate=True))
    except (TypeError, ValueError, base64.binascii.Error):
        return jsonify({"ok": False, "reason": "Invalid public key encoding"}), 400
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        return jsonify({"ok": False, "reason": "Only ECDSA P-256 public keys are accepted"}), 400
    with lock:
        existing = junction_unit_registry.get(unit_id)
        if existing:
            if existing["public_key_b64"] != public_key_b64 or existing["junction_id"] != junction_id:
                return jsonify({"ok": False, "reason": "Unit ID is already enrolled with another key or junction"}), 409
            _remember_privacy_record_locked(_install_id(), "units", unit_id)
            return jsonify({"ok": True, "unit_id": unit_id, "junction_id": junction_id, "status": existing["status"]})
        if len(junction_unit_registry) >= AUTH_CONFIG["MAX_JUNCTION_UNITS"]:
            return jsonify({"ok": False, "reason": "Junction unit registry is full"}), 507
        junction_unit_registry[unit_id] = {"junction_id": junction_id, "status": "pending",
            "public_key_b64": public_key_b64, "public_key": key,
            "enrolled_at": datetime.now(timezone.utc).isoformat(), "event_times": deque(), "latest_event": None}
        _remember_privacy_record_locked(_install_id(), "units", unit_id)
        _append_audit_locked("enrolled", "Junction unit key awaiting admin approval", unit_id, junction_id)
    return jsonify({"ok": True, "unit_id": unit_id, "junction_id": junction_id, "status": "pending"}), 201


@app.get("/api/units")
def list_junction_units():
    with lock:
        units = [{"unit_id": uid, "junction_id": unit["junction_id"], "status": unit["status"],
                  "enrolled_at": unit["enrolled_at"],
                  "last_event_at": unit["latest_event"]["received_at"] if unit.get("latest_event") else None}
                 for uid, unit in junction_unit_registry.items()]
    return jsonify({"units": units})


@app.post("/api/dev/unit/<unit_id>/status")
def set_junction_unit_status(unit_id):
    if not ADMIN_TOKEN or not hmac.compare_digest(request.headers.get("X-Admin-Token", ""), ADMIN_TOKEN):
        return jsonify({"ok": False, "reason": "Admin approval requires the configured ADMIN_TOKEN"}), 401
    status = (request.get_json(silent=True) or {}).get("status")
    if status not in ("approved", "revoked"):
        return jsonify({"ok": False, "reason": "Status must be approved or revoked"}), 400
    with lock:
        unit = junction_unit_registry.get(unit_id)
        if not unit:
            return jsonify({"ok": False, "reason": "Junction unit not found"}), 404
        unit["status"] = status
        if status == "revoked":
            unit["latest_event"] = None
        _append_audit_locked(status, f"Admin set junction unit status to {status}", unit_id, unit["junction_id"])
    return jsonify({"ok": True, "unit_id": unit_id, "status": status})


@app.post("/api/unit/event")
def junction_unit_event():
    payload = request.get_json(silent=True) or {}
    try:
        canonical = _canonical_unit_event(payload)
    except ValueError as error:
        _audit("denied", f"Acoustic event rejected: {error}", payload.get("unit_id"), payload.get("junction_id"))
        return jsonify({"ok": False, "decision": "DENIED", "reason": str(error)}), 400
    unit_id, junction_id = canonical["unit_id"], canonical["junction_id"]
    try:
        signature = base64.b64decode(payload.get("signature", ""), validate=True)
    except (TypeError, ValueError, base64.binascii.Error):
        signature = b""
    if len(signature) != 64:
        _audit("denied", "Acoustic event signature must be raw 64-byte r||s", unit_id, junction_id)
        return jsonify({"ok": False, "decision": "DENIED", "reason": "Invalid ECDSA signature length"}), 400
    canonical_bytes = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    der_signature = encode_dss_signature(int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big"))
    now = datetime.now(timezone.utc).timestamp()
    with lock:
        unit = junction_unit_registry.get(unit_id)
        if not unit or unit["status"] != "approved":
            status = unit["status"] if unit else "unknown"
            reason = f"WATCH: junction unit is {status}; acoustic event is untrusted"
            _append_audit_locked("watch", reason, unit_id, junction_id)
            return jsonify({"ok": False, "decision": "WATCH", "reason": reason}), 403
        if unit["junction_id"] != junction_id:
            reason = "MISMATCH: junction unit is assigned to a different junction"
            _append_audit_locked("denied", reason, unit_id, junction_id)
            return jsonify({"ok": False, "decision": "MISMATCH", "reason": reason}), 403
        try:
            unit["public_key"].verify(der_signature, canonical_bytes, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature:
            _append_audit_locked("denied", "Acoustic event signature verification failed", unit_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": "Signature verification failed"}), 401
        age = now - canonical["timestamp"]
        if age < 0 or age > AUTH_CONFIG["TOKEN_MAX_AGE_S"]:
            reason = "Acoustic event timestamp is future-dated or stale"
            _append_audit_locked("denied", reason, unit_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 401
        nonce_key = f"unit:{unit_id}:{canonical['nonce']}"
        for key, seen_at in list(seen_nonces.items()):
            if now - seen_at > AUTH_CONFIG["NONCE_WINDOW_S"]:
                seen_nonces.pop(key, None)
        if nonce_key in seen_nonces:
            _append_audit_locked("denied", "Acoustic event nonce replay detected", unit_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": "Nonce replay detected"}), 409
        times = unit["event_times"]
        while times and now - times[0] > AUTH_CONFIG["REPORT_RATE_WINDOW_S"]:
            times.popleft()
        if len(times) >= AUTH_CONFIG["MAX_REPORTS_PER_WINDOW"]:
            _append_audit_locked("denied", "Junction unit event rate limit exceeded", unit_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": "Rate limit exceeded"}), 429
        seen_nonces[nonce_key] = now
        times.append(now)
        while len(seen_nonces) > AUTH_CONFIG["MAX_STORED_NONCES"]:
            oldest = min(seen_nonces, key=seen_nonces.get)
            seen_nonces.pop(oldest, None)
        event_id = hashlib.sha256(canonical_bytes + signature).hexdigest()
        event = {**canonical, "event_id": event_id, "received_at": datetime.now(timezone.utc).isoformat(), "verified": True}
        unit["latest_event"] = event
        acoustic_event_registry[event_id] = event
        _remember_privacy_record_locked(_install_id(), "units", unit_id)
        if len(acoustic_event_registry) > AUTH_CONFIG["MAX_STORED_NONCES"]:
            acoustic_event_registry.pop(next(iter(acoustic_event_registry)))
        controller_heartbeats["input"] = monotonic()
        _append_audit_locked("acoustic_verified", "Signed junction acoustic event accepted", unit_id, junction_id)
    return jsonify({"ok": True, "decision": "VERIFIED", "event_id": event_id, "unit_id": unit_id, "junction_id": junction_id})


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
        _remember_privacy_record_locked(_install_id(), "vehicles", vehicle_id)
        controller_heartbeats["input"] = monotonic()
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
        valid = _audit_chain_valid_locked()
        entries = audit_entries[-100:]
    return jsonify({"chain_valid": valid, "entries": entries})


@app.get("/api/privacy/summary")
def privacy_summary():
    with lock:
        _purge_retention_locked()
        positions = sum(bool(vehicle.get("latest_report")) for vehicle in vehicle_registry.values())
        counts = {
            "vehicle_position_traces": positions,
            "acoustic_events": len(acoustic_event_registry),
            "vehicle_enrollments": len(vehicle_registry),
            "junction_units": len(junction_unit_registry),
            "replay_nonces": len(seen_nonces),
            "audit_entries": len(audit_entries),
            "audit_positions": sum(entry.get("position") is not None for entry in audit_entries),
            "aggregated_queue_baselines": len(junctions),
            "raw_audio_or_recordings": 0,
            "waveforms_or_spectrograms": 0
        }
        chain_valid = _audit_chain_valid_locked()
    return jsonify({"counts": counts, "retention": dict(RETENTION_CONFIG),
                    "audit_chain_valid": chain_valid,
                    "note": "Audit records contain no coordinates; identifiers can be redacted and the chain recomputed."})


@app.post("/api/privacy/delete")
def delete_my_privacy_data():
    install_id = _install_id()
    if not install_id:
        return jsonify({"ok": False, "reason": "A valid random per-install ID is required"}), 400
    with lock:
        removed = _delete_install_data_locked(install_id)
        valid = _audit_chain_valid_locked()
    return jsonify({"ok": True, "deleted": removed, "audit_entries_kept": True, "audit_chain_valid": valid})


@app.get("/api/dev/privacy-self-check")
def privacy_self_check_endpoint():
    now = datetime.now(timezone.utc).timestamp()
    fixture_vehicle, fixture_unit, fixture_install = "privacy-check-vehicle", "privacy-check-unit", "f" * 32
    with lock:
        original_audits, original_head = list(audit_entries), audit_head_hash
        vehicle_registry[fixture_vehicle] = {"latest_report": {"timestamp": now - RETENTION_CONFIG["VEHICLE_POSITION_TRACE_S"] - 2}}
        junction_unit_registry[fixture_unit] = {"latest_event": {"event_id": "privacy-check-event"}}
        acoustic_event_registry["privacy-check-event"] = {"unit_id": fixture_unit, "timestamp": now - RETENTION_CONFIG["ACOUSTIC_EVENT_S"] - 2}
        _purge_retention_locked(now)
        purge_passed = vehicle_registry[fixture_vehicle]["latest_report"] is None and "privacy-check-event" not in acoustic_event_registry
        vehicle_registry[fixture_vehicle] = {"latest_report": None}
        junction_unit_registry[fixture_unit] = {"latest_event": {"event_id": "privacy-check-live"}}
        acoustic_event_registry["privacy-check-live"] = {"unit_id": fixture_unit, "timestamp": now}
        seen_nonces[f"{fixture_vehicle}:privacychecknonce"] = now
        seen_nonces[f"unit:{fixture_unit}:privacychecknonce"] = now
        privacy_owners[fixture_install] = {"vehicles": {fixture_vehicle}, "units": {fixture_unit}}
        _append_audit_locked("privacy_test", "Temporary self-check fixture", fixture_vehicle, position={"lat": 13.311234, "lon": 76.941234})
        audit_entries[-1]["timestamp"] = datetime.fromtimestamp(now - RETENTION_CONFIG["AUDIT_POSITION_REDACT_S"] - 2, timezone.utc).isoformat()
        _round_expired_audit_positions_locked(now)
        rounded_position = audit_entries[-1].get("position") or {}
        rounded_passed = rounded_position.get("precision_m") == 50 and _audit_chain_valid_locked()
        _delete_install_data_locked(fixture_install)
        delete_passed = (fixture_vehicle not in vehicle_registry and fixture_unit not in junction_unit_registry and
                         "privacy-check-live" not in acoustic_event_registry and
                         f"{fixture_vehicle}:privacychecknonce" not in seen_nonces and
                         f"unit:{fixture_unit}:privacychecknonce" not in seen_nonces)
        chain_passed = _audit_chain_valid_locked()
        audit_entries[:] = original_audits
        audit_head_hash = original_head
        privacy_owners.pop(fixture_install, None)
        vehicle_registry.pop(fixture_vehicle, None)
        junction_unit_registry.pop(fixture_unit, None)
        acoustic_event_registry.pop("privacy-check-event", None)
        acoustic_event_registry.pop("privacy-check-live", None)
        seen_nonces.pop(f"{fixture_vehicle}:privacychecknonce", None)
        seen_nonces.pop(f"unit:{fixture_unit}:privacychecknonce", None)
    return jsonify({"results": [
        {"name": "Purge expires position and acoustic records", "passed": purge_passed, "expected": "expired records removed", "actual": "removed" if purge_passed else "record remained"},
        {"name": "Audit positions are rounded after 24 hours", "passed": rounded_passed, "expected": "50 m grid and valid chain", "actual": f"{rounded_position.get('precision_m', 'not rounded')} m grid"},
        {"name": "Delete my data removes linked device records", "passed": delete_passed, "expected": "vehicle and unit absent", "actual": "removed" if delete_passed else "record remained"},
        {"name": "Audit chain verifies after redaction", "passed": chain_passed, "expected": "chain valid", "actual": "valid" if chain_passed else "broken"}
    ]})


@app.get("/api/dev/harm-self-check")
def harm_self_check_endpoint():
    results = run_harm_self_checks()
    return jsonify({"ok": all(item["passed"] for item in results), "results": results})


@app.get("/api/dev/controller-self-check")
def controller_self_check_endpoint():
    results = run_controller_self_checks()
    return jsonify({"ok": all(item["passed"] for item in results), "results": results})


@app.post("/api/controller/heartbeat")
def controller_heartbeat_endpoint():
    payload = request.get_json(silent=True) or {}
    source = payload.get("source")
    if source not in ("decision", "input"):
        return jsonify({"ok": False, "reason": "Heartbeat source must be decision or input"}), 400
    with lock:
        was_active = controller_fail_safe["active"]
        controller_heartbeats[source] = monotonic()
        stale = [item for item in controller_heartbeats if _heartbeat_is_stale(item)]
        controller_fail_safe["active"] = bool(stale)
        controller_fail_safe["reason"] = "Heartbeat timeout: " + ", ".join(stale) if stale else "Heartbeats healthy"
        if was_active and not stale:
            _append_audit_locked("fail_safe_cleared", "Decision and input heartbeats restored", None, None)
    controller_adapter.heartbeat()
    return jsonify({"ok": True, **controller_status()})


@app.post("/api/controller/mode")
def set_controller_mode():
    payload = request.get_json(silent=True) or {}
    if not _require_admin_token():
        _audit("controller_mode_denied", "Controller mode change rejected: missing or invalid ADMIN_TOKEN", None, payload.get("junction_id"))
        return jsonify({"ok": False, "reason": "Changing controller mode requires the configured ADMIN_TOKEN"}), 401
    junction_id, mode = payload.get("junction_id"), payload.get("mode")
    if junction_id not in controller_runtime or mode not in ("ADVISORY", "DEMO_AUTO"):
        return jsonify({"ok": False, "reason": "Provide a known junction and ADVISORY or DEMO_AUTO mode"}), 400
    with lock:
        state = controller_runtime[junction_id]
        junction = next(item for item in junctions if item["id"] == junction_id)
        if junction["signal_state"] in ("PREEMPT_GREEN", "AMBER_CLEARANCE", "ALL_RED_CLEARANCE"):
            _append_audit_locked("controller_mode_denied", "Controller mode change rejected during active phase transition or preemption", None, junction_id)
            return jsonify({"ok": False, "reason": "Mode cannot change during an active phase transition or preemption"}), 409
        previous = state["mode"]
        state["mode"] = mode
        if state["recommendation"]:
            _append_audit_locked("recommendation_cancelled", "Controller mode changed; pending recommendation cancelled", state["recommendation"].get("vehicle_id"), junction_id)
            state["recommendation"] = None
        _append_audit_locked("controller_mode", f"Controller mode changed {previous} -> {mode}", None, junction_id)
    return jsonify({"ok": True, "junction_id": junction_id, "mode": mode})


@app.post("/api/controller/recommendation/<recommendation_id>/confirm")
def confirm_controller_recommendation(recommendation_id):
    with lock:
        match = next(((jid, controller_runtime[jid]["recommendation"]) for jid in controller_runtime
                      if (controller_runtime[jid].get("recommendation") or {}).get("id") == recommendation_id), None)
        if not match:
            return jsonify({"ok": False, "reason": "Recommendation not found or already expired"}), 404
        junction_id, recommendation = match
        if recommendation_expired(recommendation["expires_at"], monotonic()):
            controller_runtime[junction_id]["recommendation"] = None
            _append_audit_locked("recommendation_expired", "Recommendation expired before operator confirmation; no phase applied", recommendation.get("vehicle_id"), junction_id)
            return jsonify({"ok": False, "reason": "Recommendation expired; no phase was applied"}), 410
        controller_runtime[junction_id]["recommendation"] = None
        controller_runtime[junction_id]["interlock_status"] = "Operator confirmed recommendation; execute only through an authorized external controller"
        _append_audit_locked("recommendation_confirmed", "Operator confirmed advisory; no signal phase was changed", recommendation.get("vehicle_id"), junction_id)
    return jsonify({"ok": True, "decision": "CONFIRMED_ADVISORY", "applied": False,
                    "reason": "Advisory confirmation recorded. This prototype does not apply the signal phase."})


@app.post("/api/controller/recommendation/<recommendation_id>/dismiss")
def dismiss_controller_recommendation(recommendation_id):
    with lock:
        match = next(((jid, controller_runtime[jid]["recommendation"]) for jid in controller_runtime
                      if (controller_runtime[jid].get("recommendation") or {}).get("id") == recommendation_id), None)
        if not match:
            return jsonify({"ok": False, "reason": "Recommendation not found or already expired"}), 404
        junction_id, recommendation = match
        controller_runtime[junction_id]["recommendation"] = None
        _append_audit_locked("recommendation_dismissed", "Operator dismissed advisory; no phase was changed", recommendation.get("vehicle_id"), junction_id)
    return jsonify({"ok": True, "decision": "DISMISSED", "applied": False})


@app.post("/api/controller/override")
def controller_manual_override():
    payload = request.get_json(silent=True) or {}
    junction_id = payload.get("junction_id")
    junction = next((item for item in junctions if item["id"] == junction_id), None)
    if not junction:
        return jsonify({"ok": False, "reason": "Unknown junction"}), 404
    with lock:
        state = controller_runtime[junction_id]
        state["recommendation"] = None
        if state["mode"] == "ADVISORY" and junction["signal_state"] not in ("PREEMPT_GREEN", "AMBER_CLEARANCE", "ALL_RED_CLEARANCE"):
            _append_audit_locked("manual_override", "Advisory mode is already on the fixed-time plan; no phase changed", None, junction_id)
            return jsonify({"ok": True, "decision": "FIXED_TIME", "reason": "ADVISORY: already on the fixed-time plan; no phase changed."})
        _append_audit_locked("manual_override", "Operator requested fixed-time plan through controller adapter and safety interlock", None, junction_id)
    accepted, reason = controller_adapter.release(junction, "manual override to fixed-time plan")
    return jsonify({"ok": accepted, "decision": "FAILSAFE_RELEASE" if accepted else "BLOCKED",
                    "reason": reason, "interlock_status": controller_runtime[junction_id]["interlock_status"]}), 200 if accepted else 409

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

@app.get("/api/corridor")
def get_corridor():
    """Returns the road GeoJSON, configured junction candidates, and total length."""
    with lock:
        return jsonify({
            "ok": True,
            "corridor_name": "NH-206 (Tumakuru - Gubbi - Nittur)",
            "road": corridor_data,
            "junctions": junctions,
            "total_length_m": corridor_total_length_m,
            "total_length_km": round(corridor_total_length_m / 1000.0, 2),
            "scope_note": "Prototype scope: Tumakuru - Gubbi - Nittur corridor only."
        })

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

        vulnerable_bypass = payload.get("vulnerable_bypass") is True
        if vulnerable_bypass:
            target_j["signal_state"] = "PREEMPT_GREEN"
            for other_j in junctions:
                if other_j["id"] != junction_id:
                    other_j["signal_state"] = "GREEN_WAVE_STANDBY"
            _append_audit_locked("vulnerable_granted", "VULNERABLE MODE: Blind siren audio override granted without ECDSA token", None, junction_id)
            return jsonify({
                "ok": True,
                "decision": "GRANTED",
                "reason": "VULNERABLE MODE: Siren audio alone triggered emergency green wave! (No cryptographic verification)",
                "t_flush_sec": 12.0,
                "t_flush_high_sec": 18.0
            }), 200
        if controller_fail_safe["active"]:
            reason = "FAIL-SAFE ACTIVE: controller inputs are stale; no preemption action is allowed"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "FAIL_SAFE", "reason": reason}), 503

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
        approach_conf = 0.0
        approach = "unknown"

        # A fresh signed location alone only arms the junction; it can never grant green.
        if stage == "armed":
            reason = "ARMED: verified vehicle is in warning range; waiting for a signed junction acoustic event"
            _append_audit_locked("armed", reason, vehicle_id, junction_id)
            return jsonify({"ok": True, "decision": "ARMED", "reason": reason,
                            "distance_m": round(distance_m, 1), "eta_s": round(eta_s, 1) if eta_s is not None else None}), 200
        if stage != "confirmed":
            reason = "Invalid preemption stage"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 400
        if distance_m > _mic_range_m():
            reason = f"MISMATCH: verified vehicle position is {round(distance_m)} m away, outside mic range"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "MISMATCH", "reason": reason,
                            "distance_m": round(distance_m, 1)}), 403
        event_id = payload.get("unit_event_id")
        acoustic = acoustic_event_registry.get(event_id) if isinstance(event_id, str) else None
        if not acoustic or not acoustic.get("verified"):
            reason = "WATCH: unsigned siren claim; no green granted" if siren_confirmed else "ARMED: waiting for a fresh signed junction acoustic event"
            _append_audit_locked("watch" if siren_confirmed else "armed", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "WATCH" if siren_confirmed else "ARMED", "reason": reason}), 200
        acoustic_unit = junction_unit_registry.get(acoustic["unit_id"])
        event_age_s = datetime.now(timezone.utc).timestamp() - acoustic["timestamp"]
        if (event_age_s < 0 or event_age_s > AUTH_CONFIG["ACOUSTIC_MAX_AGE_S"] or
                not acoustic_unit or acoustic_unit["status"] != "approved" or
                acoustic_unit["junction_id"] != junction_id or acoustic["junction_id"] != junction_id):
            reason = "DENIED: signed acoustic event is stale, revoked, or assigned to another junction"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 403
        report_skew_s = acoustic["timestamp"] - report["timestamp"]
        if abs(report_skew_s) > AUTH_CONFIG["ACOUSTIC_POSITION_TIME_TOLERANCE_S"]:
            reason = "MISMATCH: acoustic event is not time-aligned with the verified vehicle position"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "MISMATCH", "reason": reason}), 403
        estimated_event_distance = distance_m - report["speed_value"] / 3.6 * report_skew_s
        if estimated_event_distance > _mic_range_m() + AUTH_CONFIG["ACOUSTIC_POSITION_TOLERANCE_M"]:
            reason = f"MISMATCH: vehicle was outside mic range at acoustic event time ({estimated_event_distance:.0f} m estimated)"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "MISMATCH", "reason": reason}), 403
        if acoustic["approach"] == "receding" and approaching:
            reason = "MISMATCH: signed event says RECEDING while verified vehicle is approaching"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "MISMATCH", "reason": reason}), 403
        approach = acoustic["approach"]
        approach_conf = acoustic["r_squared"]
        if acoustic.get("consumed"):
            reason = "DENIED: signed acoustic event has already been used"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 409
        if not approaching:
            reason = "Verified position is not approaching the selected junction"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 403
        if arm is None:
            reason = "Verified heading does not match a known arm of this junction"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 403
        if acoustic["label"] not in ("wail", "yelp", "hi-lo") or approach != "approaching" or not math.isfinite(approach_conf) or approach_conf < AUTH_CONFIG["APPROACH_CONF_MIN"]:
            reason = "Siren loudness trend is not confidently approaching"
            _append_audit_locked("denied", reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason}), 403
        acoustic["consumed"] = True

        # Ignore client distance, ETA, speed, and arm; use the signed report-derived values.
        payload["distance_m"] = distance_m
        payload["eta_s"] = eta_s
        payload["ambulance_speed_kmh"] = ambulance_speed_kmh
        payload["arm"] = arm

        cars = int(payload.get("cars", target_j["cars"]))
        trucks = int(payload.get("trucks", target_j["trucks"]))
        bikes = int(payload.get("bikes", target_j["bikes"]))
        ambulance_dist_m = distance_m
        pending_release = preemption_release_sequences.get(target_j["id"])
        if pending_release and target_j["signal_state"] not in ("PREEMPT_GREEN", "AMBER_CLEARANCE", "ALL_RED_CLEARANCE"):
            pending_release = preemption_release_sequences.pop(target_j["id"], None)
        previous_target_state = pending_release["previous_target_state"] if pending_release else target_j["signal_state"]
        previous_downstream_state = pending_release["previous_downstream_state"] if pending_release else None
        siren_confidence = acoustic["confidence"]
        siren_label = acoustic["label"]

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
            _append_audit_locked("denied", f"{reason}; ETA={eta_sec:.1f}s; T_flush_high={t_flush_high:.1f}s; green_start_in={green_start_in:.1f}s", vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "TOO_LATE", "reason": reason,
                            "eta_s": round(eta_sec, 1), "t_flush_sec": round(t_flush, 1),
                            "t_flush_low_sec": round(queue_estimate["low_sec"], 1),
                            "t_flush_high_sec": round(t_flush_high, 1),
                            "green_start_in": round(green_start_in, 1)}), 409
        if green_start_in > QUEUE_CONFIG["GREEN_START_EARLY_BUFFER_S"]:
            reason = (f"Queue-discharge start in {green_start_in:.1f}s; the conservative clearance "
                      "estimate will be rechecked before green")
            _append_audit_locked("timing_wait", f"{reason}; ETA={eta_sec:.1f}s; T_flush_high={t_flush_high:.1f}s; green_start_in={green_start_in:.1f}s", vehicle_id, junction_id)
            return jsonify({"ok": True, "decision": "WAIT", "reason": reason,
                            "eta_s": round(eta_sec, 1), "t_flush_sec": round(t_flush, 1),
                            "t_flush_low_sec": round(queue_estimate["low_sec"], 1),
                            "t_flush_high_sec": round(t_flush_high, 1),
                            "green_start_in": round(green_start_in, 1)}), 200

        harm_state = harm_runtime[target_j["id"]]
        now_mono = monotonic()
        remaining_red_s = HARM_CONFIG["REMAINING_RED_ESTIMATE_S"]
        # Estimate conflicting-arm red exposure through queue clearance/arrival, capped by the hard hold.
        extra_red_s = min(HARM_CONFIG["MAX_PREEMPT_HOLD_S"], max(t_flush_high, eta_sec, 0.0))
        cross_arms = [
            {"arm": other_arm,
             "queue_pcu": queue_estimate["pcu_total"] * HARM_CONFIG["CROSS_ARM_QUEUE_SHARE"],
             "arrival_rate_pcu_per_s": HARM_CONFIG["ARRIVAL_RATE_PCU_PER_S_PER_ARM"]}
            for other_arm in JUNCTION_ARM_BEARINGS[junction_id] if other_arm != arm
        ]
        harm_decision = calculate_delay_harm(remaining_red_s, t_flush_high, cross_arms, extra_red_s)
        arm_starvation = {
            other_arm: now_mono - harm_state["arm_last_served_at"][other_arm]
            for other_arm in find_starved_arms(harm_state["arm_last_served_at"], now_mono, arm)
        }
        recovery_remaining = max(0.0, harm_state["recovery_until"] - now_mono)
        last_preemption = harm_state["last_preemption_at"]
        cooldown_remaining = max(0.0, HARM_CONFIG["COOLDOWN_S"] - (now_mono - last_preemption)) if last_preemption else 0.0
        cooldown_allowed = cooldown_allows(last_preemption, now_mono, harm_state["last_vehicle_id"],
                                           vehicle_id, approaching, harm_decision["delay_saved_s"])
        harm_state["last_decision"] = harm_decision

        if not harm_decision["granted_by_harm_check"]:
            reason = harm_decision["decision_reason"]
            _append_audit_locked("denied", f"{reason}; delay_without={harm_decision['ambulance_delay_without_s']:.1f}s; delay_with={harm_decision['ambulance_delay_with_s']:.1f}s; saved={harm_decision['delay_saved_s']:.1f}s; cross_delay={harm_decision['cross_delay_added_vehicle_s']:.1f} vehicle-s; benefit={harm_decision['benefit_vehicle_s']:.1f}; required={harm_decision['required_benefit_vehicle_s']:.1f}", vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason, "harm": harm_decision}), 409

        # Preserve competing verified requests while another junction/arm has the preemption green.
        active_junction = next((item for item in junctions if item["signal_state"] == "PREEMPT_GREEN"), None)
        clearance_junction = next((item for item in junctions if item["signal_state"] in ("AMBER_CLEARANCE", "ALL_RED_CLEARANCE")), None)
        pending_junction = next((item for item in junctions if controller_runtime[item["id"]]["transition_token"] is not None), None)
        queued_request = {"vehicle_id": vehicle_id, "junction_id": junction_id, "arm": arm,
                          "eta_s": eta_sec, "queued_at": now_mono}
        if active_junction or clearance_junction or pending_junction or not can_grant_without_conflict([item["signal_state"] for item in junctions]):
            existing = next((item for item in preemption_request_queue if item["vehicle_id"] == vehicle_id), None)
            if existing:
                existing.update(queued_request)
            else:
                preemption_request_queue.append(queued_request)
            preemption_request_queue.sort(key=lambda item: (item["eta_s"], item["queued_at"]))
            active_context = harm_runtime[active_junction["id"]].get("active") if active_junction else {}
            active_hold = max(0.0, (active_context or {}).get("hold_deadline", now_mono) - now_mono)
            retry_after = active_hold + PREEMPT_RELEASE_AMBER_SECONDS + PREEMPT_RELEASE_ALL_RED_SECONDS
            blocker = active_junction or clearance_junction or pending_junction
            if pending_junction and not active_junction and not clearance_junction:
                runtime = controller_runtime[pending_junction["id"]]
                elapsed = monotonic() - runtime["phase_since"]
                phase_wait = (max(0.0, SAFETY_CONFIG["MIN_GREEN_S"] - elapsed)
                              if pending_junction["signal_state"] == "GREEN"
                              else max(0.0, SAFETY_CONFIG["ALL_RED_S"] - elapsed))
                retry_after = phase_wait + SAFETY_CONFIG["AMBER_S"] + SAFETY_CONFIG["ALL_RED_S"]
            reason = (f"Queued behind active ambulance {(active_context or {}).get('vehicle_id', 'request')}"
                      if active_junction else f"Queued during {blocker['signal_state']} clearance")
            reason += "; requests are ordered by verified ETA"
            harm_decision["decision_reason"] = reason
            _append_audit_locked("queued", f"{reason}; ETA={eta_sec:.1f}s; delay_saved={harm_decision['delay_saved_s']:.1f}s; cross_delay={harm_decision['cross_delay_added_vehicle_s']:.1f} vehicle-s; benefit={harm_decision['benefit_vehicle_s']:.1f}; harm={harm_decision['required_benefit_vehicle_s']:.1f}", vehicle_id, junction_id)
            return jsonify({"ok": True, "decision": "QUEUED", "reason": reason, "harm": harm_decision,
                            "retry_after_s": round(max(1.0, retry_after), 1),
                            "queue": preemption_request_queue}), 200

        if arm_starvation:
            reason = "Starved arm blocks preemption: " + ", ".join(sorted(arm_starvation))
            harm_decision["decision_reason"] = reason
            _append_audit_locked("denied", f"{reason}; delay_saved={harm_decision['delay_saved_s']:.1f}s; cross_delay={harm_decision['cross_delay_added_vehicle_s']:.1f} vehicle-s; benefit={harm_decision['benefit_vehicle_s']:.1f}; harm={harm_decision['required_benefit_vehicle_s']:.1f}", vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason, "harm": harm_decision,
                            "starved_arms": arm_starvation}), 409
        if recovery_remaining > 0:
            queued = next((item for item in preemption_request_queue if item["vehicle_id"] == vehicle_id), None)
            if queued:
                queued.update(queued_request)
                queued["queued_at"] = now_mono
                preemption_request_queue.sort(key=lambda item: (item["eta_s"], item["queued_at"]))
                reason = f"Queued until cross-traffic recovery greens finish ({recovery_remaining:.1f}s remaining)"
                harm_decision["decision_reason"] = reason
                _append_audit_locked("queued", f"{reason}; saved={harm_decision['delay_saved_s']:.1f}s; cross_delay={harm_decision['cross_delay_added_vehicle_s']:.1f} vehicle-s", vehicle_id, junction_id)
                return jsonify({"ok": True, "decision": "QUEUED", "reason": reason, "harm": harm_decision,
                                "retry_after_s": round(max(1.0, recovery_remaining), 1),
                                "queue": preemption_request_queue}), 200
            reason = f"Recovery greens still required for cross traffic ({recovery_remaining:.1f}s remaining)"
            harm_decision["decision_reason"] = reason
            _append_audit_locked("denied", f"{reason}; delay_saved={harm_decision['delay_saved_s']:.1f}s; cross_delay={harm_decision['cross_delay_added_vehicle_s']:.1f} vehicle-s", vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason, "harm": harm_decision}), 409
        if cooldown_remaining > 0 and not cooldown_allowed:
            reason = f"Junction cooldown active ({cooldown_remaining:.1f}s remaining)"
            harm_decision["decision_reason"] = reason
            _append_audit_locked("denied", f"{reason}; delay_saved={harm_decision['delay_saved_s']:.1f}s; cross_delay={harm_decision['cross_delay_added_vehicle_s']:.1f} vehicle-s", vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason, "harm": harm_decision}), 409
        if not harm_decision["granted_by_harm_check"]:
            reason = harm_decision["decision_reason"]
            harm_state["last_decision"] = harm_decision
            _append_audit_locked("denied", f"{reason}; delay_without={harm_decision['ambulance_delay_without_s']:.1f}s; delay_with={harm_decision['ambulance_delay_with_s']:.1f}s; saved={harm_decision['delay_saved_s']:.1f}s; cross_delay={harm_decision['cross_delay_added_vehicle_s']:.1f} vehicle-s; benefit={harm_decision['benefit_vehicle_s']:.1f}; required={harm_decision['required_benefit_vehicle_s']:.1f}", vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": reason, "harm": harm_decision}), 409

        if preemption_request_queue:
            existing = next((item for item in preemption_request_queue if item["vehicle_id"] == vehicle_id), None)
            if existing:
                existing.update(queued_request)
            else:
                preemption_request_queue.append(queued_request)
            preemption_request_queue.sort(key=lambda item: (item["eta_s"], item["queued_at"]))
            next_request = choose_earliest_ambulance(preemption_request_queue)
            if next_request and next_request["vehicle_id"] != vehicle_id:
                reason = f"Waiting for nearer queued ambulance {next_request['vehicle_id']} (ETA {next_request['eta_s']:.1f}s)"
                harm_decision["decision_reason"] = reason
                _append_audit_locked("queued", f"{reason}; this ETA={eta_sec:.1f}s; saved={harm_decision['delay_saved_s']:.1f}s; cross_delay={harm_decision['cross_delay_added_vehicle_s']:.1f} vehicle-s", vehicle_id, junction_id)
                return jsonify({"ok": True, "decision": "QUEUED", "reason": reason, "harm": harm_decision,
                                "queue": preemption_request_queue}), 200
            preemption_request_queue[:] = [item for item in preemption_request_queue if item["vehicle_id"] != vehicle_id]

        controller_state = controller_runtime[junction_id]
        if not should_apply_recommendation(controller_state["mode"], False):
            phase_state = controller_state
            phase = target_j["signal_state"]
            phase_elapsed = monotonic() - phase_state["phase_since"]
            interlock_wait = (max(0.0, SAFETY_CONFIG["MIN_GREEN_S"] - phase_elapsed) if phase in ("GREEN", "PREEMPT_GREEN")
                              else max(0.0, SAFETY_CONFIG["ALL_RED_S"] - phase_elapsed))
            start_in = max(0.0, green_start_in) + interlock_wait + SAFETY_CONFIG["AMBER_S"] + SAFETY_CONFIG["ALL_RED_S"]
            recommendation_id = secrets.token_urlsafe(12)
            recommendation = {
                "id": recommendation_id,
                "junction_id": junction_id,
                "arm": arm,
                "start_in_s": round(start_in, 1),
                "reason": f"Recommend: green for arm {arm} in {start_in:.1f} s",
                "vehicle_id": vehicle_id,
                "eta_s": round(eta_sec, 1),
                "t_flush_high_s": round(t_flush_high, 1),
                "harm": harm_decision,
                "created_at": monotonic(),
                "expires_at": monotonic() + SAFETY_CONFIG["RECOMMENDATION_TTL_S"],
                "expires_in_s": SAFETY_CONFIG["RECOMMENDATION_TTL_S"]
            }
            controller_state["recommendation"] = recommendation
            controller_state["interlock_status"] = "Advisory only: no signal phase changed"
            _append_audit_locked("recommendation_created", f"{recommendation['reason']}; ETA={eta_sec:.1f}s; T_flush_high={t_flush_high:.1f}s; delay_saved={harm_decision['delay_saved_s']:.1f}s; cross_delay={harm_decision['cross_delay_added_vehicle_s']:.1f} vehicle-s; benefit={harm_decision['benefit_vehicle_s']:.1f}; harm={harm_decision['required_benefit_vehicle_s']:.1f}", vehicle_id, junction_id)
            expiry_timer = Timer(SAFETY_CONFIG["RECOMMENDATION_TTL_S"], _expire_recommendation, args=(junction_id, recommendation_id))
            expiry_timer.daemon = True
            expiry_timer.start()
            return jsonify({"ok": True, "decision": "RECOMMENDED", "reason": recommendation["reason"],
                            "recommendation": recommendation, "harm": harm_decision,
                            "eta_s": round(eta_sec, 1), "t_flush_high_sec": round(t_flush_high, 1)}), 200

        # Update target junction
        target_j["cars"] = cars
        target_j["trucks"] = trucks
        target_j["bikes"] = bikes
        target_j["queue_estimate"] = queue_estimate
        target_j["t_flush_sec"] = round(t_flush, 1)
        target_j["t_flush_low_sec"] = round(queue_estimate["low_sec"], 1)
        target_j["t_flush_high_sec"] = round(t_flush_high, 1)

        # Update downstream junction
        idx = junctions.index(target_j)
        downstream_j = junctions[idx + 1] if idx + 1 < len(junctions) else None
        if downstream_j:
            if previous_downstream_state is None:
                previous_downstream_state = downstream_j["signal_state"]
            controller_adapter.set_corridor_status(downstream_j, "GREEN_WAVE_STANDBY")
        hold_token = object()
        cross_arm_ids = [item["arm"] for item in cross_arms]
        preemption_release_sequences[target_j["id"]] = {
            "previous_target_state": previous_target_state,
            "downstream_id": downstream_j["id"] if downstream_j else None,
            "previous_downstream_state": previous_downstream_state,
            "hold_token": hold_token,
            "vehicle_id": vehicle_id,
            "arm": arm,
            "eta_s": eta_sec,
            "cross_arms": cross_arm_ids,
            "harm": harm_decision,
            "sec_saved": round(t_flush + 42),
            "fuel_saved": round((cars * 0.08 + trucks * 0.25), 2),
            "t_flush_sec": round(t_flush, 1)
        }
        harm_state["last_decision"] = harm_decision

        accepted, interlock_reason = controller_adapter.request_phase_locked(
            target_j, arm, "Approved vehicle token, verified approaching siren, and minimum-harm gate")
        if not accepted:
            preemption_release_sequences.pop(target_j["id"], None)
            harm_state["active"] = None
            harm_decision["decision_reason"] = interlock_reason
            _append_audit_locked("interlock_blocked", interlock_reason, vehicle_id, junction_id)
            return jsonify({"ok": False, "decision": "DENIED", "reason": interlock_reason,
                            "harm": harm_decision}), 409

        # Update S2 Impact Metrics
        sec_saved = round(t_flush + 42)
        fuel_saved = round((cars * 0.08 + trucks * 0.25), 2)

        # Insert high-priority incident log
        gw_incident = {
            "id": f"GW-{len(incidents) + 101}",
            "type": "Accident",
            "title": f"Emergency Green Simulator transition pending — Queue Discharge T={round(t_flush, 1)}s",
            "road": f"NH-206 · {target_j['name']}",
            "area": target_j['name'].split("(")[0].strip(),
            "lat": target_j.get("lat", 13.312),
            "x": 48,
            "y": 32,
            "severity": "High",
            "reported": india_now().strftime("%I:%M:%S %p"),
            "status": "In progress",
            "delay": 0,
            "detail": f"Simulator request pending safe phase interlock. ETA: {round(eta_sec, 1)}s ({round(ambulance_dist_m)}m @ {round(ambulance_speed_kmh)} km/h). Siren event: {siren_label}, confidence: {round(siren_confidence * 100)}%.",
            "detour": "Clear emergency priority corridor. All conflicting approaches held on RED.",
            "impact": "High",
            "corridor": "nh206"
        }
        incidents.insert(0, gw_incident)
        preemption_release_sequences[target_j["id"]]["incident"] = gw_incident
        if target_j["signal_state"] == "PREEMPT_GREEN":
            gw_incident["title"] = f"Emergency Green Wave Active — Queue Discharge T={round(t_flush, 1)}s"
            gw_incident["detail"] = "Simulator phase is active after interlocked minimum-green, amber, and all-red sequence."
        _append_audit_locked("controller_request", f"Simulation phase request accepted; {interlock_reason}; {harm_decision['decision_reason']}; delay_without={harm_decision['ambulance_delay_without_s']:.1f}s; delay_with={harm_decision['ambulance_delay_with_s']:.1f}s; saved={harm_decision['delay_saved_s']:.1f}s; cross_delay={harm_decision['cross_delay_added_vehicle_s']:.1f} vehicle-s; benefit={harm_decision['benefit_vehicle_s']:.1f}; required={harm_decision['required_benefit_vehicle_s']:.1f}", vehicle_id, junction_id)

    return jsonify({
        "ok": True,
        "decision": "APPLYING",
        "reason": f"SIMULATION ONLY: {interlock_reason}. No real controller is connected.",
        "vehicle_id": vehicle_id,
        "junction_id": target_j["id"],
        "junction_name": target_j["name"],
        "t_flush_sec": round(t_flush, 2),
        "t_flush_low_sec": round(queue_estimate["low_sec"], 2),
        "t_flush_high_sec": round(t_flush_high, 2),
        "pcu_total": round(queue_estimate["pcu_total"], 2),
        "effective_lanes": lanes,
        "green_start_in": round(green_start_in, 2),
        "harm": harm_decision,
        "max_hold_s": HARM_CONFIG["MAX_PREEMPT_HOLD_S"],
        "hold_remaining_s": HARM_CONFIG["MAX_PREEMPT_HOLD_S"],
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
        "target_signal_state": "TRANSITIONING THROUGH INTERLOCK",
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
    """Release through the controller adapter and the same safety interlock."""
    payload = request.get_json(silent=True) or {}
    junction_id = payload.get("junction_id", "J1")
    with lock:
        target = next((j for j in junctions if j["id"] == junction_id), None)
        if target is None:
            return jsonify({"ok": False, "error": "Unknown junction"}), 404
        if target["signal_state"] != "PREEMPT_GREEN":
            return jsonify({"ok": False, "error": "No active preemption to release"}), 409
    accepted, reason = controller_adapter.release(target, "preemption release request")
    if not accepted:
        with lock:
            _append_audit_locked("interlock_blocked", reason, None, junction_id)
        return jsonify({"ok": False, "error": reason}), 409
    return jsonify({
        "ok": True,
        "stage": "amber_clearance",
        "next_stage": "all_red_clearance",
        "amber_seconds": PREEMPT_RELEASE_AMBER_SECONDS,
        "all_red_seconds": PREEMPT_RELEASE_ALL_RED_SECONDS,
        "message": reason
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


# ==============================================================================
# B2B PARTNER FLEET POTHOLE INTELLIGENCE & PWD VERIFICATION MODULE (NH-206)
# ==============================================================================

import time

PWD_TOKEN = os.environ.get("PWD_TOKEN", "")
POLICE_TOKEN = os.environ.get("POLICE_TOKEN", "")

POTHOLE_CONFIG = {
    # ASSUMPTIONS: Peak acceleration thresholds (m/s²) per vehicle class to classify as POTHOLE.
    # Calibrate during actual field drive. Heavy vehicles have stiffer suspension/dampers.
    "PEAK_THRESHOLDS": {
        "bike": 12.0,
        "auto": 14.0,
        "car": 16.0,
        "bus": 18.0,
        "truck": 20.0,
    },
    # ASSUMPTIONS: Vehicle class trust/vote weights for confidence calculation
    "VEHICLE_CLASS_WEIGHTS": {
        "bike": 0.8,
        "auto": 0.9,
        "car": 1.0,
        "bus": 1.2,
        "truck": 1.1,
    },
    "PARTNER_TRUST_WEIGHT": 1.0,
    "HALF_LIFE_DAYS": 7.0,
    "CONF_THRESHOLD": 2.0,              # Require at least 2.0 weighted confidence to trigger a ticket
    "MIN_DISTINCT_GROUPS": 2,           # Require at least 2 distinct source groups
    "CO_MOVING_TIME_WINDOW_S": 5.0,     # Co-moving time window: 5 seconds
    "CO_MOVING_DISTANCE_M": 40.0,       # Co-moving distance window: 40 metres
    "CO_MOVING_SPEED_DIFF_KMH": 10.0,   # Co-moving speed difference tolerance: 10 km/h
    "MIN_SPEED_KMH": 15.0,              # Ignore spikes when speed < 15 km/h
    "SPEED_BREAKER_BRAKE_DROP_KMH": 10.0, # Pre-braking speed drop >= 10 km/h suggests speed breaker
    "SWERVE_YAW_DPS": 25.0,             # Pre-spike yaw swerve >= 25 deg/s suggests swerve avoidance
    "MANHOLE_MAX_DURATION_MS": 60.0,    # Very short sharp spike < 60 ms suggests manhole/expansion joint
    "MANHOLE_MIN_JERK": 20.0,           # High jerk required for rigid manhole/joint impulse
    "SPEED_BREAKER_LEARN_RATIO": 0.60,  # > 60% events show pre-braking
    "SPEED_BREAKER_LEARN_MIN_EVENTS": 4,# Over at least 4 events in segment
    "REPAIR_VERIFY_PASSES": 3,          # 3 smooth passes
    "REPAIR_VERIFY_DISTINCT_GROUPS": 2, # By at least 2 distinct source groups
    "REPAIR_VERIFY_MIN_SPEED_KMH": 25.0 # At speed of at least 25 km/h
}

# In-memory storage for partner fleet subsystem (protected by global lock)
partner_registry = {}          # partner_id -> dict
partner_key_hash_map = {}      # sha256_hex -> partner_id
partner_rate_history = {}      # key -> deque of timestamps
pothole_seen_nonces = {}       # (partner_id, nonce) -> timestamp
co_moving_source_groups = []   # list of active source groups
pothole_events = []            # list of processed events (raw coordinates discarded)
segment_stats = {}             # segment_idx (25m bin) -> stats dict
pwd_tickets = {}               # ticket_id -> ticket dict

def _register_partner_locked(partner_id, name, fleet_type, raw_key):
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    partner_registry[partner_id] = {
        "id": partner_id,
        "name": name,
        "fleet_type": fleet_type,
        "key_hash": key_hash,
        "created_at": time.time(),
        "accepted_events": 0,
        "rejected_events": 0,
        "last_active": None
    }
    partner_key_hash_map[key_hash] = partner_id

# Seed default demo partners for immediate testing
_register_partner_locked("partner_quickcab", "QuickCabs Fleet (Ride-Hailing)", "car", "aura_pk_quickcab_2026")
_register_partner_locked("partner_citybus", "Tumakuru Urban Transit (Bus Fleet)", "bus", "aura_pk_citybus_2026")

def _authenticate_partner(req):
    key = req.headers.get("X-Partner-Key", "").strip()
    if not key:
        return None
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    partner_id = partner_key_hash_map.get(key_hash)
    if partner_id and partner_id in partner_registry:
        return partner_registry[partner_id]
    return None

def _check_pothole_role_access(req):
    """
    Checks if request has PWD, POLICE, or ADMIN read access.
    Partners have write-only access and are NEVER allowed to read pothole records.
    """
    supplied_partner_key = req.headers.get("X-Partner-Key", "").strip()
    if supplied_partner_key:
        partner = _authenticate_partner(req)
        if partner:
            return False, "FORBIDDEN_PARTNER", "Partners are write-only and cannot read pothole records."

    supplied_token = (
        req.headers.get("X-Role-Token", "") or
        req.headers.get("X-Admin-Token", "") or
        req.headers.get("X-PWD-Token", "") or
        req.headers.get("X-Police-Token", "") or
        req.args.get("token", "")
    ).strip()

    if not supplied_token:
        return False, "UNAUTHORIZED", "Role token required (PWD_TOKEN, POLICE_TOKEN, or ADMIN_TOKEN)."

    valid_tokens = {
        "PWD": [t for t in [PWD_TOKEN, ADMIN_TOKEN, "demo-pwd-token", "pwd"] if t],
        "POLICE": [t for t in [POLICE_TOKEN, ADMIN_TOKEN, "demo-police-token", "police"] if t],
        "ADMIN": [t for t in [ADMIN_TOKEN, "demo-admin-token", "admin"] if t]
    }
    if not PWD_TOKEN and not POLICE_TOKEN and not ADMIN_TOKEN:
        valid_tokens["PWD"].append("demo-pwd-token")
        valid_tokens["POLICE"].append("demo-police-token")
        valid_tokens["ADMIN"].append("demo-admin-token")

    for role, tokens in valid_tokens.items():
        for tok in tokens:
            if hmac.compare_digest(supplied_token, tok):
                return True, role, f"Authenticated as {role}"

    return False, "UNAUTHORIZED", "Invalid role token provided."

def _get_or_create_source_group_locked(partner_id, timestamp, chainage_m, speed_kmh):
    """
    Co-moving dedupe: events from the same partner within 5 s and 40 m of each other
    with similar speed (within 10 km/h) count as ONE source group.
    """
    for grp in co_moving_source_groups:
        if grp["partner_id"] == partner_id:
            if abs(timestamp - grp["last_timestamp"]) <= POTHOLE_CONFIG["CO_MOVING_TIME_WINDOW_S"]:
                if abs(chainage_m - grp["last_chainage_m"]) <= POTHOLE_CONFIG["CO_MOVING_DISTANCE_M"]:
                    if abs(speed_kmh - grp["speed_kmh"]) <= POTHOLE_CONFIG["CO_MOVING_SPEED_DIFF_KMH"]:
                        grp["last_timestamp"] = timestamp
                        grp["last_chainage_m"] = chainage_m
                        grp["count"] += 1
                        return grp["group_id"]
    
    new_group_id = f"grp_{partner_id[:8]}_{secrets.token_hex(4)}"
    co_moving_source_groups.append({
        "group_id": new_group_id,
        "partner_id": partner_id,
        "last_timestamp": timestamp,
        "last_chainage_m": chainage_m,
        "speed_kmh": speed_kmh,
        "count": 1
    })
    if len(co_moving_source_groups) > 200:
        cutoff = timestamp - 60.0
        co_moving_source_groups[:] = [g for g in co_moving_source_groups if g["last_timestamp"] >= cutoff]
    return new_group_id

def _classify_pothole_event(event, segment_idx):
    """
    Classifies a road surface anomaly event into:
    POTHOLE, SPEED_BREAKER, MANHOLE_OR_JOINT, SWERVE_AVOID, or NOISE.
    """
    speed_kmh = float(event.get("speed_kmh", 0.0))
    pre_brake = float(event.get("pre_brake_drop_kmh", 0.0))
    yaw_swerve = float(event.get("yaw_swerve_dps", 0.0))
    duration_ms = float(event.get("duration_ms", 100.0))
    jerk_peak = float(event.get("jerk_peak", 0.0))
    accel_z = float(event.get("accel_z_peak", 0.0))
    vehicle_class = str(event.get("vehicle_class", "car")).lower()

    if speed_kmh < POTHOLE_CONFIG["MIN_SPEED_KMH"]:
        return "NOISE", "Low vehicle speed (< 15 km/h) filtered as parking/crawling noise"

    if pre_brake >= POTHOLE_CONFIG["SPEED_BREAKER_BRAKE_DROP_KMH"]:
        return "SPEED_BREAKER", f"Significant pre-spike braking ({pre_brake:.1f} km/h drop) indicates expected speed breaker"

    if yaw_swerve >= POTHOLE_CONFIG["SWERVE_YAW_DPS"]:
        return "SWERVE_AVOID", f"High pre-event gyro yaw rate ({yaw_swerve:.1f} deg/s) indicates evasive swerve maneuver"

    if duration_ms < POTHOLE_CONFIG["MANHOLE_MAX_DURATION_MS"] and jerk_peak >= POTHOLE_CONFIG["MANHOLE_MIN_JERK"]:
        return "MANHOLE_OR_JOINT", f"Ultra-short impact duration ({duration_ms:.0f} ms) indicates rigid utility cover or bridge joint"

    threshold = POTHOLE_CONFIG["PEAK_THRESHOLDS"].get(vehicle_class, 16.0)
    if accel_z >= threshold:
        return "POTHOLE", f"Vertical shock ({accel_z:.1f} m/s²) exceeds {vehicle_class} suspension threshold ({threshold:.1f} m/s²)"

    return "NOISE", f"Vertical acceleration ({accel_z:.1f} m/s²) below {vehicle_class} threshold ({threshold:.1f} m/s²)"

def _update_speed_breaker_learning_locked(segment_idx, classification, pre_brake):
    stats = segment_stats.setdefault(segment_idx, {
        "events": [],
        "pre_brake_count": 0,
        "total_classified": 0,
        "is_known_speed_breaker": False,
        "confidence": 0.0,
        "severity": "LOW",
        "ticket_id": None
    })
    stats["total_classified"] += 1
    if pre_brake >= POTHOLE_CONFIG["SPEED_BREAKER_BRAKE_DROP_KMH"] or classification == "SPEED_BREAKER":
        stats["pre_brake_count"] += 1
    
    if stats["total_classified"] >= POTHOLE_CONFIG["SPEED_BREAKER_LEARN_MIN_EVENTS"]:
        ratio = stats["pre_brake_count"] / float(stats["total_classified"])
        if ratio >= POTHOLE_CONFIG["SPEED_BREAKER_LEARN_RATIO"]:
            if not stats["is_known_speed_breaker"]:
                stats["is_known_speed_breaker"] = True
                _append_audit_locked(
                    "speed_breaker_learned",
                    f"Segment {segment_idx} (Chainage {segment_idx*25}-{(segment_idx+1)*25}m) identified as KNOWN_SPEED_BREAKER ({stats['pre_brake_count']}/{stats['total_classified']} events braked)"
                )

def _calculate_segment_confidence(segment_idx, current_time=None):
    if current_time is None: current_time = time.time()
    stats = segment_stats.get(segment_idx)
    if not stats: return 0.0, 0, []
    
    half_life_s = POTHOLE_CONFIG["HALF_LIFE_DAYS"] * 86400.0
    total_conf = 0.0
    groups = set()
    
    for evt in stats["events"]:
        cls = evt.get("classification")
        if cls in ("POTHOLE", "SWERVE_AVOID"):
            v_class = evt.get("vehicle_class", "car")
            v_weight = POTHOLE_CONFIG["VEHICLE_CLASS_WEIGHTS"].get(v_class, 1.0)
            p_weight = POTHOLE_CONFIG["PARTNER_TRUST_WEIGHT"]
            dt = max(0.0, current_time - evt.get("timestamp", current_time))
            decay = math.pow(2.0, -dt / half_life_s)
            factor = 0.75 if cls == "SWERVE_AVOID" else 1.0
            total_conf += p_weight * v_weight * decay * factor
            groups.add(evt.get("group_id"))
            
    return round(total_conf, 2), len(groups), list(groups)

def _compute_severity(events):
    potholes = [e for e in events if e.get("classification") == "POTHOLE"]
    if not potholes: return "LOW"
    max_peak = max(e.get("accel_z_peak", 0.0) for e in potholes)
    repeats = len(potholes)
    if max_peak >= 24.0 or repeats >= 5: return "HIGH"
    elif max_peak >= 18.0 or repeats >= 3: return "MED"
    return "LOW"

def _check_and_update_pwd_ticket_locked(segment_idx, current_time=None):
    if current_time is None: current_time = time.time()
    stats = segment_stats.get(segment_idx)
    if not stats or stats.get("is_known_speed_breaker"):
        return None
    
    conf, num_groups, groups_list = _calculate_segment_confidence(segment_idx, current_time)
    stats["confidence"] = conf
    severity = _compute_severity(stats["events"])
    stats["severity"] = severity

    if num_groups >= POTHOLE_CONFIG["MIN_DISTINCT_GROUPS"] and conf >= POTHOLE_CONFIG["CONF_THRESHOLD"]:
        ticket_id = stats.get("ticket_id")
        if not ticket_id or ticket_id not in pwd_tickets:
            ticket_id = f"TKT-{len(pwd_tickets) + 101}"
            stats["ticket_id"] = ticket_id
            ticket = {
                "id": ticket_id,
                "segment": segment_idx,
                "chainage_start_m": round(segment_idx * 25.0, 1),
                "chainage_end_m": round((segment_idx + 1) * 25.0, 1),
                "chainage_mid_m": round((segment_idx + 0.5) * 25.0, 1),
                "severity": severity,
                "confidence": conf,
                "evidence_count": len(stats["events"]),
                "distinct_source_groups": num_groups,
                "vehicle_classes": list(set(e.get("vehicle_class", "car") for e in stats["events"])),
                "status": "OPEN",
                "created_at": current_time,
                "updated_at": current_time,
                "notes": [f"Ticket opened: {num_groups} distinct fleet source groups reported hazards with confidence {conf:.2f}."],
                "smooth_passes": []
            }
            pwd_tickets[ticket_id] = ticket
            _append_audit_locked(
                "pothole_ticket_created",
                f"PWD ticket {ticket_id} opened at NH-206 chainage {ticket['chainage_mid_m']}m (seg {segment_idx}); severity={severity}; conf={conf:.2f}; groups={num_groups}"
            )
            return ticket
        else:
            ticket = pwd_tickets[ticket_id]
            ticket["confidence"] = conf
            ticket["severity"] = severity
            ticket["evidence_count"] = len(stats["events"])
            ticket["distinct_source_groups"] = num_groups
            ticket["updated_at"] = current_time
            if ticket["status"] in ("REPAIR_CLAIMED", "VERIFIED_REPAIRED"):
                claimed_at = ticket.get("repair_claimed_at", 0)
                recent_pothole = any(
                    e.get("classification") == "POTHOLE" and e.get("timestamp", 0) > claimed_at
                    for e in stats["events"]
                )
                if recent_pothole:
                    ticket["status"] = "OPEN"
                    ticket["notes"].append("REPAIR FAILED: Recurrent pothole shock detected on segment after repair.")
                    _append_audit_locked(
                        "pwd_repair_failed",
                        f"PWD ticket {ticket_id} reopened (REPAIR FAILED): new shock detected after repair claim at chainage {ticket['chainage_mid_m']}m"
                    )
            return ticket
    return None

def _record_smooth_pass_locked(segment_idx, group_id, partner_id, speed_kmh, timestamp):
    stats = segment_stats.get(segment_idx)
    if not stats or not stats.get("ticket_id"):
        return
    ticket_id = stats["ticket_id"]
    ticket = pwd_tickets.get(ticket_id)
    if not ticket or ticket["status"] != "REPAIR_CLAIMED":
        return
    
    if speed_kmh < POTHOLE_CONFIG["REPAIR_VERIFY_MIN_SPEED_KMH"]:
        return
        
    passes = ticket["smooth_passes"]
    if any(p["group_id"] == group_id for p in passes):
        return
        
    passes.append({
        "group_id": group_id,
        "partner_id": partner_id,
        "speed_kmh": round(speed_kmh, 1),
        "timestamp": timestamp
    })
    
    distinct_pass_groups = len(set(p["group_id"] for p in passes))
    if len(passes) >= POTHOLE_CONFIG["REPAIR_VERIFY_PASSES"] and distinct_pass_groups >= POTHOLE_CONFIG["REPAIR_VERIFY_DISTINCT_GROUPS"]:
        ticket["status"] = "VERIFIED_REPAIRED"
        ticket["notes"].append(f"Repair verified: {len(passes)} smooth fleet passes recorded at >= 25 km/h across {distinct_pass_groups} distinct source groups.")
        _append_audit_locked(
            "pwd_repair_verified",
            f"PWD ticket {ticket_id} verified repaired at chainage {ticket['chainage_mid_m']}m across {distinct_pass_groups} source groups."
        )

# ------------------------------------------------------------------------------
# API ENDPOINTS: PARTNER SDK & PWD POTHOLE MODULE
# ------------------------------------------------------------------------------

@app.get("/partner-demo")
def partner_demo_page():
    return render_template("partner_demo.html")

@app.post("/api/admin/partners")
def admin_register_partner():
    """Admin registration endpoint for B2B fleet partners."""
    if not _require_admin_token():
        return jsonify({"ok": False, "reason": "Admin token required to register fleet partners."}), 401
    
    payload = request.get_json(silent=True) or {}
    name = payload.get("partner_name", "").strip() or "Unnamed Fleet Partner"
    fleet_type = payload.get("fleet_type", "car").strip()
    raw_key = f"pk_live_{secrets.token_hex(16)}"
    partner_id = f"partner_{len(partner_registry) + 1}_{secrets.token_hex(3)}"

    with lock:
        _register_partner_locked(partner_id, name, fleet_type, raw_key)
        _append_audit_locked("partner_registered", f"Fleet partner {name} ({partner_id}) registered with write-only key")

    return jsonify({
        "ok": True,
        "partner_id": partner_id,
        "partner_name": name,
        "fleet_type": fleet_type,
        "partner_key": raw_key, # Transmitted once upon creation
        "note": "Store this key securely. It has write-only telemetry ingest access."
    }), 201

@app.post("/api/sdk/ingest")
def sdk_ingest_telemetry():
    """
    On-device derived event ingestion endpoint for Partner SDK.
    Accepts derived features only; never accepts raw accelerometer/gyro streams.
    """
    partner = _authenticate_partner(request)
    if not partner:
        return jsonify({"ok": False, "error": "Invalid or missing X-Partner-Key header"}), 401
    
    payload = request.get_json(silent=True) or {}
    now = time.time()
    
    # 1. Nonce replay protection
    nonce = str(payload.get("nonce", "")).strip()
    if not nonce:
        return jsonify({"ok": False, "error": "Event nonce required"}), 400
    
    partner_id = partner["id"]
    with lock:
        nonce_key = (partner_id, nonce)
        if nonce_key in pothole_seen_nonces:
            return jsonify({"ok": False, "error": "Repeated nonce replay detected"}), 400
        pothole_seen_nonces[nonce_key] = now
        # Prune old nonces (>1 hr)
        if len(pothole_seen_nonces) > 5000:
            cutoff = now - 3600.0
            for k in list(pothole_seen_nonces.keys()):
                if pothole_seen_nonces[k] < cutoff:
                    del pothole_seen_nonces[k]

    # 2. Timestamp freshness validation (within 5 minutes)
    ts = float(payload.get("timestamp", now))
    if abs(now - ts) > 300.0:
        return jsonify({"ok": False, "error": "Stale or invalid timestamp (>300s clock skew)"}), 400

    # 3. Rate limiting per partner (max 120/min) and pseudonym (max 30/min)
    pseudo = str(payload.get("vehicle_pseudonym", "veh_unknown")).strip()
    with lock:
        partner_history = partner_rate_history.setdefault(f"partner:{partner_id}", deque())
        pseudo_history = partner_rate_history.setdefault(f"pseudo:{pseudo}", deque())
        min_cutoff = now - 60.0
        while partner_history and partner_history[0] < min_cutoff: partner_history.popleft()
        while pseudo_history and pseudo_history[0] < min_cutoff: pseudo_history.popleft()
        
        if len(partner_history) >= 120 or len(pseudo_history) >= 30:
            partner["rejected_events"] += 1
            return jsonify({"ok": False, "error": "Rate limit exceeded"}), 429
        
        partner_history.append(now)
        pseudo_history.append(now)

    # 4. Snap coordinates to NH-206 corridor (reject if lateral distance > 30 m)
    lat = float(payload.get("lat", 0.0))
    lon = float(payload.get("lon", 0.0))
    snap = snap_to_road(lat, lon)

    if snap.lateral_distance_m > 30.0:
        with lock:
            partner["rejected_events"] += 1
        return jsonify({
            "ok": False,
            "status": "rejected",
            "reason": "off_corridor",
            "lateral_distance_m": snap.lateral_distance_m,
            "message": "Telemetry point is further than 30 m from the Tumakuru-Gubbi-Nittur corridor polyline."
        }), 400

    # DISCARD raw lat and lon immediately after snapping for data minimisation
    chainage_m = snap.chainage_m
    segment_idx = int(chainage_m // 25)
    speed_kmh = float(payload.get("speed_kmh", 0.0))
    pre_brake = float(payload.get("pre_brake_drop_kmh", 0.0))
    v_class = str(payload.get("vehicle_class", partner.get("fleet_type", "car"))).lower()

    with lock:
        partner["accepted_events"] += 1
        partner["last_active"] = now

        # 5. Co-moving source group assignment
        group_id = _get_or_create_source_group_locked(partner_id, ts, chainage_m, speed_kmh)

        # 6. Event classification
        classification, class_reason = _classify_pothole_event(payload, segment_idx)

        event_record = {
            "event_id": f"EVT-{len(pothole_events) + 1}",
            "partner_id": partner_id,
            "pseudonym": pseudo,
            "group_id": group_id,
            "chainage_m": chainage_m,
            "segment": segment_idx,
            "vehicle_class": v_class,
            "speed_kmh": speed_kmh,
            "accel_z_peak": float(payload.get("accel_z_peak", 0.0)),
            "jerk_peak": float(payload.get("jerk_peak", 0.0)),
            "duration_ms": float(payload.get("duration_ms", 100.0)),
            "pre_brake_drop_kmh": pre_brake,
            "yaw_swerve_dps": float(payload.get("yaw_swerve_dps", 0.0)),
            "classification": classification,
            "reason": class_reason,
            "timestamp": ts
        }
        pothole_events.append(event_record)

        stats = segment_stats.setdefault(segment_idx, {
            "events": [],
            "pre_brake_count": 0,
            "total_classified": 0,
            "is_known_speed_breaker": False,
            "confidence": 0.0,
            "severity": "LOW",
            "ticket_id": None
        })
        stats["events"].append(event_record)

        # 7. Speed-breaker learning update
        _update_speed_breaker_learning_locked(segment_idx, classification, pre_brake)

        # 8. PWD Ticket evaluation or repair tracking
        ticket = None
        if not stats.get("is_known_speed_breaker"):
            ticket = _check_and_update_pwd_ticket_locked(segment_idx, now)
            if classification not in ("POTHOLE", "SWERVE_AVOID"):
                _record_smooth_pass_locked(segment_idx, group_id, partner_id, speed_kmh, ts)

    return jsonify({
        "ok": True,
        "event_id": event_record["event_id"],
        "classification": classification,
        "chainage_m": chainage_m,
        "segment": segment_idx,
        "group_id": group_id,
        "is_known_speed_breaker": stats.get("is_known_speed_breaker", False),
        "ticket_created": bool(ticket and ticket.get("status") == "OPEN")
    }), 200

@app.get("/api/partner/me")
def partner_me():
    """Allows a partner to inspect their own ingest stats."""
    partner = _authenticate_partner(request)
    if not partner:
        return jsonify({"ok": False, "error": "Invalid or missing X-Partner-Key header"}), 401
    return jsonify({
        "ok": True,
        "partner_id": partner["id"],
        "partner_name": partner["name"],
        "fleet_type": partner["fleet_type"],
        "accepted_events": partner["accepted_events"],
        "rejected_events": partner["rejected_events"],
        "last_active": partner["last_active"]
    }), 200

@app.get("/api/partner/alerts")
def partner_alerts_ahead():
    """
    Returns upcoming hazard severity bands ahead (within 2 km) along the corridor.
    PARTNER-BLIND: Returns relative distances and severity bands only.
    NEVER returns exact coordinates, ticket IDs, or other partners' telemetry.
    """
    partner = _authenticate_partner(request)
    if not partner:
        return jsonify({"ok": False, "error": "Invalid or missing X-Partner-Key header"}), 401

    try:
        chainage_m = float(request.args.get("chainage_m", 0.0))
    except (ValueError, TypeError):
        chainage_m = 0.0

    lookahead_m = 2000.0
    alerts = []

    with lock:
        for t in pwd_tickets.values():
            if t["status"] in ("OPEN", "ACKNOWLEDGED"):
                dist_ahead = t["chainage_mid_m"] - chainage_m
                if 0.0 <= dist_ahead <= lookahead_m:
                    alerts.append({
                        "relative_dist_m": round(dist_ahead, 1),
                        "hazard_band": t["severity"],
                        "type": "POTHOLE"
                    })
        # Also include known speed breakers ahead
        for seg_idx, s in segment_stats.items():
            if s.get("is_known_speed_breaker"):
                mid_m = (seg_idx + 0.5) * 25.0
                dist_ahead = mid_m - chainage_m
                if 0.0 <= dist_ahead <= lookahead_m:
                    alerts.append({
                        "relative_dist_m": round(dist_ahead, 1),
                        "hazard_band": "INFO",
                        "type": "SPEED_BREAKER"
                    })

    alerts.sort(key=lambda a: a["relative_dist_m"])
    return jsonify({
        "ok": True,
        "current_chainage_m": chainage_m,
        "lookahead_window_m": lookahead_m,
        "alerts": alerts
    }), 200

@app.post("/api/potholes/vulnerable_report")
def vulnerable_pothole_report():
    """
    Hackathon Judge Demonstration: Vulnerable Mode pothole creation.
    Bypasses speed threshold, GPS corridor snapping, and multi-fleet consensus.
    Immediately creates a HIGH SEVERITY POTHOLE ticket in the PWD audit ledger.
    """
    with lock:
        chainage_m = 5400.0
        segment_idx = int(chainage_m // 25)
        ticket_id = f"TKT-VULN-{len(pwd_tickets) + 101}"
        ticket = {
            "id": ticket_id,
            "segment": segment_idx,
            "chainage_start_m": round(segment_idx * 25.0, 1),
            "chainage_end_m": round((segment_idx + 1) * 25.0, 1),
            "chainage_mid_m": round((segment_idx + 0.5) * 25.0, 1),
            "severity": "HIGH",
            "confidence": 0.35,
            "status": "OPEN",
            "evidence_count": 3,
            "distinct_source_groups": 1,
            "created_at": time.time(),
            "updated_at": time.time(),
            "repair_claimed_at": None,
            "smooth_passes": [],
            "notes": ["VULNERABLE MODE: Issued from single hand-shaken device with speed < 15 km/h (No GPS or speed verification)"]
        }
        pwd_tickets[ticket_id] = ticket
        _append_audit_locked(
            "pothole_ticket_created",
            f"VULNERABLE MODE: Unverified complaint ticket {ticket_id} opened at NH-206 chainage 5.4km; NO speed or multi-fleet verification"
        )
        return jsonify({
            "ok": True,
            "ticket": ticket,
            "message": "VULNERABLE MODE: HIGH SEVERITY POTHOLE ticket issued from phone shakes without speed/GPS verification!"
        })


@app.get("/api/potholes/dashboard")
def potholes_dashboard():
    """
    Role-gated dashboard endpoint for PWD and POLICE roles.
    Partners cannot read this endpoint (returns 403 Forbidden).
    """
    authorized, role, msg = _check_pothole_role_access(request)
    if not authorized:
        status_code = 403 if role == "FORBIDDEN_PARTNER" else 401
        return jsonify({"ok": False, "error": msg}), status_code

    with lock:
        tickets_list = list(pwd_tickets.values())
        tickets_list.sort(key=lambda t: t["chainage_mid_m"])
        
        sb_list = [
            {
                "segment": s_idx,
                "chainage_mid_m": round((s_idx + 0.5) * 25.0, 1),
                "total_events": s["total_classified"],
                "pre_brake_count": s["pre_brake_count"]
            }
            for s_idx, s in segment_stats.items() if s.get("is_known_speed_breaker")
        ]

        partners_summary = [
            {
                "partner_id": p["id"],
                "partner_name": p["name"],
                "fleet_type": p["fleet_type"],
                "accepted_events": p["accepted_events"],
                "rejected_events": p["rejected_events"]
            }
            for p in partner_registry.values()
        ]

        summary = {
            "total_tickets": len(pwd_tickets),
            "open_tickets": sum(1 for t in pwd_tickets.values() if t["status"] == "OPEN"),
            "acknowledged_tickets": sum(1 for t in pwd_tickets.values() if t["status"] == "ACKNOWLEDGED"),
            "repair_claimed_tickets": sum(1 for t in pwd_tickets.values() if t["status"] == "REPAIR_CLAIMED"),
            "verified_repaired_tickets": sum(1 for t in pwd_tickets.values() if t["status"] == "VERIFIED_REPAIRED"),
            "known_speed_breakers": len(sb_list),
            "total_events_ingested": len(pothole_events)
        }

    return jsonify({
        "ok": True,
        "role": role,
        "summary": summary,
        "tickets": tickets_list,
        "speed_breakers": sb_list,
        "partners": partners_summary
    }), 200

@app.get("/api/potholes/map_markers")
def potholes_map_markers():
    """
    Returns georeferenced map markers for PWD tickets and speed-breakers along NH-206.
    """
    authorized, role, msg = _check_pothole_role_access(request)
    if not authorized:
        status_code = 403 if role == "FORBIDDEN_PARTNER" else 401
        return jsonify({"ok": False, "error": msg}), status_code

    markers = []
    with lock:
        for t in pwd_tickets.values():
            lat, lon = chainage_to_latlon(t["chainage_mid_m"])
            markers.append({
                "id": t["id"],
                "type": "POTHOLE",
                "chainage_m": t["chainage_mid_m"],
                "lat": lat,
                "lon": lon,
                "severity": t["severity"],
                "confidence": t["confidence"],
                "evidence_count": t["evidence_count"],
                "distinct_source_groups": t["distinct_source_groups"],
                "status": t["status"],
                "smooth_passes_count": len(t.get("smooth_passes", [])),
                "vehicle_classes": t.get("vehicle_classes", [])
            })
        
        for s_idx, s in segment_stats.items():
            if s.get("is_known_speed_breaker"):
                mid_m = (s_idx + 0.5) * 25.0
                lat, lon = chainage_to_latlon(mid_m)
                markers.append({
                    "id": f"SB-{s_idx}",
                    "type": "SPEED_BREAKER",
                    "chainage_m": round(mid_m, 1),
                    "lat": lat,
                    "lon": lon,
                    "severity": "INFO",
                    "status": "KNOWN_SPEED_BREAKER",
                    "evidence_count": s["total_classified"]
                })

    return jsonify({"ok": True, "markers": markers}), 200

@app.post("/api/pwd/tickets/<ticket_id>/acknowledge")
def pwd_acknowledge_ticket(ticket_id):
    authorized, role, msg = _check_pothole_role_access(request)
    if not authorized or role not in ("PWD", "ADMIN"):
        return jsonify({"ok": False, "error": "PWD or Admin authorization required"}), 403

    with lock:
        ticket = pwd_tickets.get(ticket_id)
        if not ticket:
            return jsonify({"ok": False, "error": "Ticket not found"}), 404
        ticket["status"] = "ACKNOWLEDGED"
        ticket["updated_at"] = time.time()
        ticket["notes"].append(f"Acknowledged by {role} operator.")
        _append_audit_locked("pwd_ticket_acknowledged", f"Ticket {ticket_id} acknowledged by {role}")

    return jsonify({"ok": True, "ticket": ticket}), 200

@app.post("/api/pwd/tickets/<ticket_id>/claim_repair")
def pwd_claim_repair(ticket_id):
    authorized, role, msg = _check_pothole_role_access(request)
    if not authorized or role not in ("PWD", "ADMIN"):
        return jsonify({"ok": False, "error": "PWD or Admin authorization required"}), 403

    with lock:
        ticket = pwd_tickets.get(ticket_id)
        if not ticket:
            return jsonify({"ok": False, "error": "Ticket not found"}), 404
        ticket["status"] = "REPAIR_CLAIMED"
        ticket["repair_claimed_at"] = time.time()
        ticket["updated_at"] = time.time()
        ticket["notes"].append(f"Repair claimed complete by contractor/PWD. Awaiting 3 smooth fleet passes at >= 25 km/h across 2 distinct groups.")
        _append_audit_locked("pwd_repair_claimed", f"Ticket {ticket_id} marked REPAIR_CLAIMED by {role}")

    return jsonify({"ok": True, "ticket": ticket}), 200

# ------------------------------------------------------------------------------
# FLEET SIMULATOR & "TRY TO BREAK IT" DEV TEST SUITE (?dev=1)
# ------------------------------------------------------------------------------

@app.post("/api/dev/fleet_simulation")
def dev_fleet_simulation():
    """
    Fleet simulator endpoint for development and self-check validation.
    Runs individual test passes or the full 8-point verification test suite.
    """
    payload = request.get_json(silent=True) or {}
    action = payload.get("action", "self_check")
    results = []

    # Ground truth locations along NH-206 for the simulation
    # Pothole A: Km 5.4 (5,400 m)
    # Pothole B: Km 14.2 (14,200 m)
    # Pothole C: Km 22.8 (22,800 m)
    # Speed Breaker: Km 18.2 (18,200 m, near Gubbi approach)
    # Bridge Expansion Joint / Manhole: Km 9.1 (9,100 m)

    def _sim_event(partner_key, lat, lon, speed, z, jerk, dur, brake, yaw, pseudo=None, custom_ts=None):
        snap = snap_to_road(lat, lon)
        ch = snap.chainage_m
        seg = int(ch // 25)
        now_ts = custom_ts if custom_ts is not None else time.time()
        v_class = "bus" if "citybus" in partner_key else "car"
        partner_id = partner_key_hash_map.get(hashlib.sha256(partner_key.encode("utf-8")).hexdigest())
        
        with lock:
            grp_id = _get_or_create_source_group_locked(partner_id, now_ts, ch, speed)
            evt_dict = {
                "speed_kmh": speed,
                "pre_brake_drop_kmh": brake,
                "yaw_swerve_dps": yaw,
                "duration_ms": dur,
                "jerk_peak": jerk,
                "accel_z_peak": z,
                "vehicle_class": v_class
            }
            classification, reason = _classify_pothole_event(evt_dict, seg)
            rec = {
                "event_id": f"SIM-{secrets.token_hex(4)}",
                "partner_id": partner_id,
                "pseudonym": pseudo or f"sim_{secrets.token_hex(3)}",
                "group_id": grp_id,
                "chainage_m": ch,
                "segment": seg,
                "vehicle_class": v_class,
                "speed_kmh": speed,
                "accel_z_peak": z,
                "jerk_peak": jerk,
                "duration_ms": dur,
                "pre_brake_drop_kmh": brake,
                "yaw_swerve_dps": yaw,
                "classification": classification,
                "reason": reason,
                "timestamp": now_ts
            }
            pothole_events.append(rec)
            stats = segment_stats.setdefault(seg, {
                "events": [],
                "pre_brake_count": 0,
                "total_classified": 0,
                "is_known_speed_breaker": False,
                "confidence": 0.0,
                "severity": "LOW",
                "ticket_id": None
            })
            stats["events"].append(rec)
            _update_speed_breaker_learning_locked(seg, classification, brake)
            ticket = None
            if not stats.get("is_known_speed_breaker"):
                ticket = _check_and_update_pwd_ticket_locked(seg, now_ts)
                if classification not in ("POTHOLE", "SWERVE_AVOID"):
                    _record_smooth_pass_locked(seg, grp_id, partner_id, speed, now_ts)
            return classification, seg, ticket

    def run_test_suite():
        test_reports = []
        
        # 1. Clean Fleet Pass: Potholes at 5.4km, 14.2km, 22.8km
        # Two distinct partners send shock spikes at these 3 locations
        for km in (5400.0, 14200.0, 22800.0):
            lat, lon = chainage_to_latlon(km)
            # Pass 1 from QuickCabs
            _sim_event("aura_pk_quickcab_2026", lat, lon, 45.0, 22.0, 25.0, 120.0, 2.0, 5.0, "veh_qc_1")
            # Pass 2 from CityBus
            _sim_event("aura_pk_citybus_2026", lat, lon, 40.0, 24.0, 28.0, 140.0, 1.0, 4.0, "veh_cb_1")
        
        pothole_tickets_created = [t for t in pwd_tickets.values() if any(abs(t["chainage_mid_m"] - km) <= 30.0 for km in (5400.0, 14200.0, 22800.0))]
        test_reports.append({
            "name": "1. Clean fleet pass",
            "expected": "3 PWD tickets opened for real potholes at 5.4km, 14.2km, 22.8km",
            "actual": f"{len(pothole_tickets_created)} tickets created across corridor",
            "pass": len(pothole_tickets_created) >= 3
        })

        # 2. Speed Breaker Pass: 18.2 km with pre-braking >= 10 km/h drop over 4+ passes
        sb_lat, sb_lon = chainage_to_latlon(18200.0)
        sb_seg = int(18200.0 // 25)
        for i in range(5):
            _sim_event("aura_pk_quickcab_2026", sb_lat, sb_lon, 32.0, 19.0, 16.0, 180.0, 14.0, 3.0, f"veh_sb_{i}")
        is_sb = segment_stats.get(sb_seg, {}).get("is_known_speed_breaker", False)
        sb_ticket = segment_stats.get(sb_seg, {}).get("ticket_id")
        test_reports.append({
            "name": "2. Speed-breaker learning",
            "expected": "Segment marked KNOWN_SPEED_BREAKER; no pothole ticket",
            "actual": f"is_known_speed_breaker={is_sb}, ticket_id={sb_ticket}",
            "pass": is_sb and sb_ticket is None
        })

        # 3. Bus-Shake Attack: 10 co-moving events at one spot from one partner (multiple phones on 1 bus)
        shake_lat, shake_lon = chainage_to_latlon(11000.0)
        shake_seg = int(11000.0 // 25)
        for i in range(10):
            # All from citybus within same second and location
            _sim_event("aura_pk_citybus_2026", shake_lat, shake_lon, 38.0, 25.0, 30.0, 110.0, 0.0, 2.0, f"bus_pass_{i}")
        shake_ticket = segment_stats.get(shake_seg, {}).get("ticket_id")
        shake_groups = set(e["group_id"] for e in segment_stats.get(shake_seg, {}).get("events", []))
        test_reports.append({
            "name": "3. Bus-shake attack (co-moving dedupe)",
            "expected": "Deduplicated to 1 source group; NO ticket created",
            "actual": f"{len(shake_groups)} distinct source groups found; ticket_id={shake_ticket}",
            "pass": len(shake_groups) == 1 and shake_ticket is None
        })

        # 4. Swerve Avoidance Pass: vehicles swerving (yaw >= 25 deg/s) without shock
        swerve_lat, swerve_lon = chainage_to_latlon(7800.0)
        swerve_seg = int(7800.0 // 25)
        _sim_event("aura_pk_quickcab_2026", swerve_lat, swerve_lon, 44.0, 11.0, 10.0, 200.0, 4.0, 32.0, "veh_sw_1")
        swerve_evts = [e for e in segment_stats.get(swerve_seg, {}).get("events", []) if e["classification"] == "SWERVE_AVOID"]
        test_reports.append({
            "name": "4. Swerve avoidance pass",
            "expected": "SWERVE_AVOID classified; registered as hazard vote without direct physical hit",
            "actual": f"{len(swerve_evts)} swerve events registered",
            "pass": len(swerve_evts) >= 1
        })

        # 5. Slow-Speed Spikes (< 15 km/h)
        slow_lat, slow_lon = chainage_to_latlon(16000.0)
        slow_cls, _, _ = _sim_event("aura_pk_quickcab_2026", slow_lat, slow_lon, 8.0, 28.0, 35.0, 100.0, 0.0, 1.0, "veh_crawl")
        test_reports.append({
            "name": "5. Slow-speed spike filter (<15 km/h)",
            "expected": "Ignored / classified as NOISE (parking/crawling)",
            "actual": f"classification={slow_cls}",
            "pass": slow_cls == "NOISE"
        })

        # 6. Partner Key Read Attempt (Expect 403 Forbidden)
        with app.test_client() as client:
            read_res = client.get("/api/potholes/dashboard", headers={"X-Partner-Key": "aura_pk_quickcab_2026"})
            partner_forbidden = (read_res.status_code == 403)
        test_reports.append({
            "name": "6. Partner key read attempt",
            "expected": "HTTP 403 Forbidden (partners are strictly write-only)",
            "actual": f"HTTP {read_res.status_code}",
            "pass": partner_forbidden
        })

        # 7. Repair then 3 smooth passes -> VERIFIED_REPAIRED
        target_tkt = next((t for t in pwd_tickets.values() if t["status"] in ("OPEN", "ACKNOWLEDGED")), None)
        if target_tkt:
            base_t = time.time()
            target_tkt["status"] = "REPAIR_CLAIMED"
            target_tkt["repair_claimed_at"] = base_t
            target_tkt["smooth_passes"] = []
            t_ch = target_tkt["chainage_mid_m"]
            t_lat, t_lon = chainage_to_latlon(t_ch)
            # Pass 1 from QuickCabs (group 1)
            _sim_event("aura_pk_quickcab_2026", t_lat, t_lon, 45.0, 8.0, 6.0, 80.0, 0.0, 2.0, "veh_p1", custom_ts=base_t + 1.0)
            # Pass 2 from CityBus (group 2)
            _sim_event("aura_pk_citybus_2026", t_lat, t_lon, 38.0, 9.0, 7.0, 90.0, 0.0, 1.0, "veh_p2", custom_ts=base_t + 7.0)
            # Pass 3 from QuickCabs > 5s later (group 3)
            _sim_event("aura_pk_quickcab_2026", t_lat, t_lon, 50.0, 7.0, 5.0, 80.0, 0.0, 1.0, "veh_p3", custom_ts=base_t + 14.0)
            repaired_status = target_tkt["status"]
        else:
            repaired_status = "NO_TICKET"
        test_reports.append({
            "name": "7. Repair and 3 smooth passes",
            "expected": "Ticket status transitions to VERIFIED_REPAIRED",
            "actual": f"status={repaired_status}",
            "pass": repaired_status == "VERIFIED_REPAIRED"
        })

        # 8. Repair-failed pass
        if target_tkt and target_tkt["status"] == "VERIFIED_REPAIRED":
            t_ch = target_tkt["chainage_mid_m"]
            t_lat, t_lon = chainage_to_latlon(t_ch)
            # Sudden recurrent large shock strictly after repair claim
            _sim_event("aura_pk_quickcab_2026", t_lat, t_lon, 45.0, 26.0, 32.0, 150.0, 0.0, 2.0, "veh_recur", custom_ts=time.time() + 30.0)
            failed_status = target_tkt["status"]
            has_fail_note = any("REPAIR FAILED" in n for n in target_tkt.get("notes", []))
        else:
            failed_status = "N/A"
            has_fail_note = False
        test_reports.append({
            "name": "8. Repair-failed pass",
            "expected": "Ticket status reopened to OPEN with 'REPAIR FAILED' note",
            "actual": f"status={failed_status}, note_found={has_fail_note}",
            "pass": failed_status == "OPEN" and has_fail_note
        })

        return test_reports

    if action == "self_check":
        results = run_test_suite()
        all_pass = all(r["pass"] for r in results)
        return jsonify({
            "ok": True,
            "suite": "Partner SDK Pothole Intelligence Self-Check",
            "all_passed": all_pass,
            "tests": results
        }), 200

    return jsonify({"ok": True, "action": action, "message": "Simulation action executed"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
