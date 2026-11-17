"""
CivicEye - Tumakuru Civic Grievance System
A modern civic grievance reporting and resolution platform for Tumakuru.
"""

import os
import json
import uuid
import math
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from ai_triage import analyze_complaint

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "civiceye-tumakuru-dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'civiceye.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Photo upload configuration
UPLOAD_FOLDER = os.path.join(basedir, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

db = SQLAlchemy(app)


# -----------------------------------------------------------------------------
# Category Configurations & Issue Types
# -----------------------------------------------------------------------------

CATEGORY_CONFIG = {
    "road": {
        "title": "Road Damage",
        "icon": "🛣️",
        "tagline": "Report potholes, broken footpaths & damaged road surfaces",
        "issue_types": [
            "Pothole",
            "Broken footpath",
            "Damaged road edge",
            "Other"
        ]
    },
    "pollution": {
        "title": "Pollution",
        "icon": "🏭",
        "tagline": "Report garbage burning, open dumping & environmental hazards",
        "issue_types": [
            "Garbage burning",
            "Garbage dump",
            "Drain/sewage overflow",
            "Dust or smoke",
            "Other"
        ]
    },
    "water": {
        "title": "Water Leak",
        "icon": "🚰",
        "tagline": "Report pipeline bursts, water leaks & drainage contamination",
        "issue_types": [
            "Pipe leakage",
            "Burst pipe",
            "No water supply",
            "Dirty water",
            "Other"
        ]
    }
}


# -----------------------------------------------------------------------------
# Database Models
# -----------------------------------------------------------------------------

class Department(db.Model):
    """Simulated municipal & governmental departments in Tumakuru."""
    __tablename__ = "department"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # road / pollution / water
    contact_email = db.Column(db.String(120), nullable=False)

    complaints = db.relationship("Complaint", backref="department", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "contact_email": self.contact_email,
        }


class Complaint(db.Model):
    """Citizen grievance complaint record."""
    __tablename__ = "complaint"

    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False)  # road / pollution / water
    issue_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    photo_path = db.Column(db.String(255), nullable=True)
    audio_path = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    address_text = db.Column(db.String(255), nullable=True)
    status = db.Column(
        db.String(50),
        nullable=False,
        default="Submitted"
    )  # Submitted / Under Review / Assigned / In Progress / Resolved
    severity = db.Column(db.Integer, nullable=True)  # 1-5 (nullable for now)
    ai_summary = db.Column(db.Text, nullable=True)
    severity_reasons = db.Column(db.Text, nullable=True)  # JSON text
    image_matches_report = db.Column(db.Boolean, nullable=True)
    ai_confidence = db.Column(db.Float, nullable=True)
    ai_source = db.Column(db.String(20), nullable=True)  # "gemini" or "fallback"
    parent_id = db.Column(db.Integer, db.ForeignKey("complaint.id"), nullable=True)
    report_count = db.Column(db.Integer, default=1, nullable=False)
    detected_issue = db.Column(db.String(150), nullable=True)
    suggested_action = db.Column(db.String(255), nullable=True)
    transcription = db.Column(db.Text, nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    parent = db.relationship(
        "Complaint",
        remote_side=[id],
        backref=db.backref("children", lazy=True)
    )

    history = db.relationship(
        "StatusHistory",
        backref="complaint",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="StatusHistory.changed_at.desc()"
    )

    @property
    def reasons_list(self):
        """Helper returning parsed list of severity reasons."""
        if not self.severity_reasons:
            return []
        try:
            parsed = json.loads(self.severity_reasons)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict) and "reasons" in parsed:
                return parsed["reasons"]
            return [str(parsed)]
        except Exception:
            return [self.severity_reasons]

    def to_dict(self):
        return {
            "id": self.id,
            "tracking_id": self.tracking_id,
            "category": self.category,
            "issue_type": self.issue_type,
            "description": self.description,
            "photo_path": self.photo_path,
            "audio_path": self.audio_path,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "address_text": self.address_text,
            "status": self.status,
            "severity": self.severity,
            "ai_summary": self.ai_summary,
            "severity_reasons": self.reasons_list,
            "image_matches_report": self.image_matches_report,
            "ai_confidence": self.ai_confidence,
            "ai_source": self.ai_source,
            "parent_id": self.parent_id,
            "report_count": self.report_count,
            "detected_issue": self.detected_issue,
            "suggested_action": self.suggested_action,
            "transcription": self.transcription,
            "department_id": self.department_id,
            "created_at": self.created_at.isoformat(),
        }


class StatusHistory(db.Model):
    """Audit log tracking complaint status progression."""
    __tablename__ = "status_history"

    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaint.id"), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    note = db.Column(db.Text, nullable=True)
    changed_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self):
        return {
            "id": self.id,
            "complaint_id": self.complaint_id,
            "status": self.status,
            "note": self.note,
            "changed_at": self.changed_at.isoformat(),
        }


# -----------------------------------------------------------------------------
# Database Initialization & Seeding
# -----------------------------------------------------------------------------

def seed_departments():
    """Seed the simulated departments across road, pollution, and water categories."""
    simulated_departments = [
        # Road
        Department(
            name="Tumakuru City Corporation - Engineering Wing",
            category="road",
            contact_email="engineering@tumakurucity.gov.in"
        ),
        Department(
            name="PWD Tumakuru Division",
            category="road",
            contact_email="pwd.tumakuru@karnataka.gov.in"
        ),
        # Pollution
        Department(
            name="Karnataka State Pollution Control Board - Tumakuru Office",
            category="pollution",
            contact_email="kspcb.tumakuru@kpcb.gov.in"
        ),
        Department(
            name="Tumakuru City Corporation - Sanitation Wing",
            category="pollution",
            contact_email="sanitation@tumakurucity.gov.in"
        ),
        # Water
        Department(
            name="Tumakuru City Corporation - Water Supply",
            category="water",
            contact_email="watersupply@tumakurucity.gov.in"
        ),
        Department(
            name="KUWS&DB Tumakuru",
            category="water",
            contact_email="kuwsdb.tumakuru@karnataka.gov.in"
        ),
    ]
    db.session.add_all(simulated_departments)
    db.session.commit()
    print("Database seeded with simulated Tumakuru departments.")


def init_db():
    """Ensure database tables exist and seed initial departments if empty."""
    inspector = db.inspect(db.engine)
    if inspector.has_table("complaint"):
        columns = [col["name"] for col in inspector.get_columns("complaint")]
        required_cols = {
            "severity_reasons",
            "image_matches_report",
            "ai_confidence",
            "ai_source",
            "parent_id",
            "report_count",
            "transcription",
        }
        if not required_cols.issubset(set(columns)):
            print("Detected missing columns in complaint table; dropping and recreating database...")
            db.drop_all()

    db.create_all()
    if Department.query.count() == 0:
        seed_departments()


def generate_tracking_id():
    """Generate a clean, unique tracking ID like CE-2026-0001."""
    year = datetime.now(timezone.utc).year
    count = Complaint.query.count() + 1
    candidate = f"CE-{year}-{count:04d}"
    while Complaint.query.filter_by(tracking_id=candidate).first():
        count += 1
        candidate = f"CE-{year}-{count:04d}"
    return candidate


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance in meters between two coordinates."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def find_nearby_open_complaint(category: str, latitude: float, longitude: float, max_meters: float = 50.0):
    """
    Find the closest open (not Resolved) complaint of the same category
    within max_meters submitted in the last 30 days.
    """
    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc - timedelta(days=30)
    cutoff_naive = datetime.utcnow() - timedelta(days=30)

    # Query all active (not Resolved) complaints in same category
    candidates = Complaint.query.filter(
        Complaint.category == category,
        Complaint.status != "Resolved",
        Complaint.latitude.isnot(None),
        Complaint.longitude.isnot(None)
    ).all()

    closest_parent = None
    min_dist = float("inf")

    for cand in candidates:
        if cand.created_at:
            cand_time = cand.created_at
            if cand_time.tzinfo is not None:
                if cand_time < cutoff_utc:
                    continue
            else:
                if cand_time < cutoff_naive:
                    continue

        dist = haversine_distance(latitude, longitude, cand.latitude, cand.longitude)
        if dist <= max_meters and dist < min_dist:
            min_dist = dist
            # Resolve to root parent if candidate is already a child
            closest_parent = cand.parent if cand.parent else cand

    return closest_parent, min_dist


# Automatically run on startup
with app.app_context():
    init_db()


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@app.route("/")
def index():
    """Render the CivicEye home page."""
    return render_template("index.html")


@app.route("/report/<category>", methods=["GET", "POST"])
def report(category):
    """Render category-specific grievance reporting form and handle citizen submissions."""
    norm_cat = category.lower()
    if norm_cat not in CATEGORY_CONFIG:
        return redirect(url_for("index"))

    config = CATEGORY_CONFIG[norm_cat]

    if request.method == "POST":
        issue_type = request.form.get("issue_type", "").strip()
        description = request.form.get("description", "").strip()
        latitude_val = request.form.get("latitude", "").strip()
        longitude_val = request.form.get("longitude", "").strip()
        address_text = request.form.get("address_text", "").strip() or "Tumakuru, Karnataka"
        photo = request.files.get("photo")

        # Basic Validation: Photo required
        if not photo or not photo.filename:
            return render_template(
                "report.html",
                category=norm_cat,
                config=config,
                error="Please capture or upload a photo of the grievance issue."
            )

        # Basic Validation: Location coordinates required
        try:
            latitude = float(latitude_val)
            longitude = float(longitude_val)
        except (TypeError, ValueError):
            return render_template(
                "report.html",
                category=norm_cat,
                config=config,
                error="Valid location coordinates are required. Please use the map pin or location button."
            )

        # Issue type required
        if not issue_type:
            return render_template(
                "report.html",
                category=norm_cat,
                config=config,
                error="Please select an issue type from the dropdown."
            )

        # Save photo securely to static/uploads
        ext = os.path.splitext(secure_filename(photo.filename))[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp", ".heic"]:
            ext = ".jpg"
        unique_filename = f"{uuid.uuid4().hex[:14]}{ext}"
        photo_save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
        photo.save(photo_save_path)
        photo_rel_path = f"uploads/{unique_filename}"

        # Check for optional citizen voice recording
        audio = request.files.get("audio")
        audio_save_path = None
        audio_rel_path = None
        if audio and audio.filename:
            safe_audio_name = secure_filename(audio.filename) or "voice.webm"
            audio_ext = os.path.splitext(safe_audio_name)[1].lower()
            if audio_ext not in [".webm", ".wav", ".mp3", ".ogg", ".m4a", ".aac"]:
                audio_ext = ".webm"
            unique_audio_name = f"voice_{uuid.uuid4().hex[:14]}{audio_ext}"
            audio_save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_audio_name)
            audio.save(audio_save_path)
            if os.path.exists(audio_save_path) and os.path.getsize(audio_save_path) > 0:
                audio_rel_path = f"uploads/{unique_audio_name}"
            else:
                audio_save_path = None
                audio_rel_path = None

        # Check for open complaint of same category within 50m in last 30 days
        nearby_parent, dist_m = find_nearby_open_complaint(norm_cat, latitude, longitude, max_meters=50.0)
        parent_id = nearby_parent.id if nearby_parent else None

        # Generate tracking ID and save Complaint
        tracking_id = generate_tracking_id()
        complaint = Complaint(
            tracking_id=tracking_id,
            category=norm_cat,
            issue_type=issue_type,
            description=description or f"{issue_type} reported in Tumakuru",
            photo_path=photo_rel_path,
            audio_path=audio_rel_path,
            latitude=latitude,
            longitude=longitude,
            address_text=address_text,
            status="Submitted",
            parent_id=parent_id,
            report_count=1,
        )
        db.session.add(complaint)
        db.session.flush()

        # Add initial StatusHistory audit entry
        status_entry = StatusHistory(
            complaint_id=complaint.id,
            status="Submitted",
            note="Grievance submitted by citizen via CivicEye web portal."
        )
        db.session.add(status_entry)

        if nearby_parent:
            nearby_entry = StatusHistory(
                complaint_id=complaint.id,
                status="Submitted",
                note=f"Linked to nearby active grievance {nearby_parent.tracking_id} ({int(dist_m)}m away)."
            )
            db.session.add(nearby_entry)

        db.session.commit()

        # Execute AI triage analysis (with optional audio note)
        triage = analyze_complaint(
            category=norm_cat,
            issue_type=issue_type,
            description=description,
            photo_path=photo_save_path,
            audio_path=audio_save_path,
        )

        # Store AI triage results on complaint
        complaint.severity = triage.get("severity")
        complaint.ai_summary = triage.get("summary")
        complaint.severity_reasons = json.dumps(triage.get("severity_reasons") or [])
        complaint.image_matches_report = triage.get("image_matches_report")
        complaint.ai_confidence = triage.get("confidence")
        complaint.ai_source = triage.get("ai_source", "gemini")
        complaint.detected_issue = triage.get("detected_issue") or issue_type
        complaint.suggested_action = triage.get("suggested_action")

        # Audio transcript handling (Kannada / Hindi / English)
        transcription = triage.get("transcription")
        if transcription:
            complaint.transcription = transcription
            # If description field is empty or generic, use the translated transcript
            if not description or not description.strip() or description.strip() == f"{issue_type} reported in Tumakuru":
                complaint.description = transcription.strip()

        # Department assignment: choose seeded department of matching category
        rec_cat = triage.get("recommended_department_type") or norm_cat
        dept = (
            Department.query.filter_by(category=rec_cat).first()
            or Department.query.filter_by(category=norm_cat).first()
        )
        complaint.department_id = dept.id if dept else None

        # Record AI triage audit note; status stays "Submitted"
        ai_history = StatusHistory(
            complaint_id=complaint.id,
            status="Submitted",
            note="AI triage completed"
        )
        db.session.add(ai_history)

        # If linked to a parent complaint, update parent metrics
        if nearby_parent:
            nearby_parent.report_count = (nearby_parent.report_count or 1) + 1

            # Raise parent's severity by 1 (max 5) once report_count reaches 3
            if nearby_parent.report_count >= 3:
                curr_sev = nearby_parent.severity or 1
                if curr_sev < 5:
                    nearby_parent.severity = min(5, curr_sev + 1)

                # Add crowd reason "Reported by N citizens"
                reasons = list(nearby_parent.reasons_list)
                crowd_reason = f"Reported by {nearby_parent.report_count} citizens"
                reasons = [r for r in reasons if not r.startswith("Reported by ")]
                reasons.append(crowd_reason)
                nearby_parent.severity_reasons = json.dumps(reasons)

            # Record duplicate linkage in parent's history
            parent_history = StatusHistory(
                complaint_id=nearby_parent.id,
                status=nearby_parent.status,
                note=f"Additional grievance report linked ({tracking_id}) from citizen within {int(dist_m)}m. Total reports: {nearby_parent.report_count}."
            )
            db.session.add(parent_history)

        db.session.commit()

        return redirect(url_for("success", tracking_id=tracking_id))

    # GET request
    return render_template("report.html", category=norm_cat, config=config)


@app.route("/success/<tracking_id>")
def success(tracking_id):
    """Display confirmation page with large tracking ID."""
    complaint = Complaint.query.filter_by(tracking_id=tracking_id).first_or_404()
    return render_template("success.html", complaint=complaint)


@app.route("/track")
def track():
    """Placeholder page for tracking grievance complaints."""
    req_id = request.args.get("id", "").strip()
    return render_template(
        "placeholder.html",
        title="Track Complaint",
        heading="Track Your Grievance",
        icon="🔍",
        message=f"Tracking ID: {req_id}. Enter your CivicEye tracking ID to view live status updates and department action notes." if req_id else "Enter your CivicEye tracking ID (e.g., CE-2026-0001) to view live status updates and department action notes."
    )


@app.route("/dashboard")
def dashboard():
    """Placeholder page for public transparency dashboard."""
    return render_template(
        "placeholder.html",
        title="Public Dashboard",
        heading="Tumakuru Public Dashboard",
        icon="📊",
        message="Public transparency metrics and ward-level resolution stats across Tumakuru City Corporation."
    )


@app.route("/health")
def health():
    """Health check endpoint for deployment monitoring."""
    dept_count = Department.query.count()
    return jsonify({
        "status": "healthy",
        "app": "CivicEye",
        "city": "Tumakuru",
        "departments_seeded": dept_count
    }), 200


@app.route("/api/status")
def api_status():
    """System status and environment info."""
    return jsonify({
        "app": "CivicEye",
        "name": "Tumakuru Civic Grievance System",
        "version": "1.0.0",
        "status": "online"
    }), 200


@app.route("/debug/ai")
def debug_ai():
    """
    Temporary diagnostic route for testing Gemini API connection.
    Protected by ?token= matching env var DEBUG_TOKEN.
    """
    expected_token = os.environ.get("DEBUG_TOKEN", "").strip()
    provided_token = request.args.get("token", "").strip()

    if not expected_token or provided_token != expected_token:
        return jsonify({
            "error": "Unauthorized. Make sure DEBUG_TOKEN is set in Render environment and passed as ?token=..."
        }), 403

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    model_name = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-2.5-flash"
    key_present = bool(api_key and api_key not in ("paste-your-key-here", "your_api_key_here"))

    if not key_present:
        return jsonify({
            "key_present": False,
            "model_name": model_name,
            "success": False,
            "error": "GEMINI_API_KEY is not set or empty in environment."
        }), 200

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=20000),  # 20-second timeout
        )
        resp = client.models.generate_content(
            model=model_name,
            contents="Reply with the word OK",
            config=types.GenerateContentConfig(
                temperature=0.0,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )
        )
        reply_text = resp.text.strip() if resp.text else ""
        return jsonify({
            "key_present": True,
            "model_name": model_name,
            "success": True,
            "response": reply_text,
            "error": None
        }), 200
    except Exception as exc:
        return jsonify({
            "key_present": True,
            "model_name": model_name,
            "success": False,
            "error": f"{exc.__class__.__name__}: {str(exc)}"
        }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
