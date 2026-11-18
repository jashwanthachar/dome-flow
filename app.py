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
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from ai_triage import analyze_complaint, optimize_image_for_ai

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))

app = Flask(__name__)
# Load SECRET_KEY from environment variable (never hardcode)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY") or os.urandom(24).hex()
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
    after_photo_path = db.Column(db.String(255), nullable=True)
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
            "after_photo_path": self.after_photo_path,
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
            "after_photo_path",
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

            # -------------------------------------------------------------
            # Duplicate Grievance: Skip Gemini call entirely and reuse parent
            # -------------------------------------------------------------
            complaint.detected_issue = nearby_parent.detected_issue or issue_type
            complaint.ai_summary = nearby_parent.ai_summary
            complaint.suggested_action = nearby_parent.suggested_action
            complaint.severity = nearby_parent.severity
            complaint.severity_reasons = nearby_parent.severity_reasons
            complaint.image_matches_report = nearby_parent.image_matches_report
            complaint.ai_confidence = nearby_parent.ai_confidence
            complaint.ai_source = nearby_parent.ai_source or "gemini"
            complaint.department_id = nearby_parent.department_id

            # Audit note for inherited AI triage
            ai_history = StatusHistory(
                complaint_id=complaint.id,
                status="Submitted",
                note="AI triage completed (inherited from nearby report)"
            )
            db.session.add(ai_history)

            # Update parent metrics
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

        db.session.commit()

        # -------------------------------------------------------------
        # Fresh Grievance: Downscale photo with Pillow & run AI triage
        # -------------------------------------------------------------
        ai_photo_path = optimize_image_for_ai(photo_save_path, max_dimension=1024, quality=80)

        # Execute AI triage analysis (with optional audio note)
        triage = analyze_complaint(
            category=norm_cat,
            issue_type=issue_type,
            description=description,
            photo_path=ai_photo_path,
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

        db.session.commit()

        return redirect(url_for("success", tracking_id=tracking_id))

    # GET request
    return render_template("report.html", category=norm_cat, config=config)


@app.route("/success/<tracking_id>")
def success(tracking_id):
    """Display confirmation page with large tracking ID."""
    complaint = Complaint.query.filter_by(tracking_id=tracking_id).first_or_404()
    return render_template("success.html", complaint=complaint)


@app.route("/track", methods=["GET"])
@app.route("/track/<tracking_id>", methods=["GET"])
def track(tracking_id=None):
    """
    Search and track complaint status with vertical timeline, map, and AI triage.
    Reachable via /track, /track?id=... and /track/<tracking_id>.
    """
    query_id = (tracking_id or request.args.get("id", "")).strip()
    complaint = None
    searched = bool(query_id)

    if query_id:
        complaint = Complaint.query.filter(
            db.func.upper(Complaint.tracking_id) == query_id.upper()
        ).first()

    history_timeline = []
    if complaint:
        # Chronological order for the vertical progression timeline
        history_timeline = (
            StatusHistory.query.filter_by(complaint_id=complaint.id)
            .order_by(StatusHistory.changed_at.asc(), StatusHistory.id.asc())
            .all()
        )

    return render_template(
        "track.html",
        complaint=complaint,
        tracking_id=query_id,
        searched=searched,
        history_timeline=history_timeline,
    )


# -------------------------------------------------------------
# Admin Authentication Helper
# -------------------------------------------------------------
def admin_required(f):
    """Decorator to enforce admin authentication via session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


# -------------------------------------------------------------
# Admin Routes
# -------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Admin portal login using ADMIN_PASSWORD env var and Flask session."""
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    error = None
    if request.method == "POST":
        entered_password = request.form.get("password", "").strip()
        admin_password = os.environ.get("ADMIN_PASSWORD", "").strip()

        if not admin_password:
            error = "ADMIN_PASSWORD is not configured in the server environment."
        elif entered_password == admin_password:
            session["is_admin"] = True
            next_url = request.args.get("next")
            if not next_url or not next_url.startswith("/"):
                next_url = url_for("admin_dashboard")
            return redirect(next_url)
        else:
            error = "Invalid administrator password. Please try again."

    return render_template("admin_login.html", error=error)


@app.route("/admin/logout", methods=["GET", "POST"])
def admin_logout():
    """Log out of the admin portal."""
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    """
    Admin dashboard: table of parent complaints only, sortable and filterable.
    Default sorted by severity then report_count.
    """
    # Base query: parent complaints only
    query = Complaint.query.filter(Complaint.parent_id.is_(None))

    # Filters
    category_filter = request.args.get("category", "all").strip().lower()
    if category_filter and category_filter != "all":
        query = query.filter(Complaint.category == category_filter)

    status_filter = request.args.get("status", "all").strip()
    if status_filter and status_filter != "all":
        query = query.filter(Complaint.status == status_filter)

    severity_filter = request.args.get("severity", "all").strip()
    if severity_filter and severity_filter != "all":
        try:
            query = query.filter(Complaint.severity == int(severity_filter))
        except ValueError:
            pass

    # Sorting: default sorted by severity then report_count
    sort_by = request.args.get("sort", "default").strip()
    order = request.args.get("order", "desc").strip().lower()

    if sort_by == "date":
        query = query.order_by(Complaint.created_at.asc() if order == "asc" else Complaint.created_at.desc())
    elif sort_by == "reports":
        query = query.order_by(
            Complaint.report_count.asc() if order == "asc" else Complaint.report_count.desc(),
            Complaint.severity.desc()
        )
    elif sort_by == "status":
        query = query.order_by(Complaint.status.asc() if order == "asc" else Complaint.status.desc())
    elif sort_by == "severity":
        query = query.order_by(
            Complaint.severity.asc() if order == "asc" else Complaint.severity.desc(),
            Complaint.report_count.desc()
        )
    else:
        # Default: sorted by severity then report_count
        query = query.order_by(
            Complaint.severity.desc(),
            Complaint.report_count.desc(),
            Complaint.created_at.desc()
        )

    complaints = query.all()

    # KPI counts for parent complaints
    total_parent_count = Complaint.query.filter(Complaint.parent_id.is_(None)).count()
    active_count = Complaint.query.filter(Complaint.parent_id.is_(None), Complaint.status != "Resolved").count()
    high_sev_count = Complaint.query.filter(Complaint.parent_id.is_(None), Complaint.severity >= 4).count()
    resolved_count = Complaint.query.filter(Complaint.parent_id.is_(None), Complaint.status == "Resolved").count()

    return render_template(
        "admin_dashboard.html",
        complaints=complaints,
        category_filter=category_filter,
        status_filter=status_filter,
        severity_filter=severity_filter,
        sort_by=sort_by,
        order=order,
        total_parent_count=total_parent_count,
        active_count=active_count,
        high_sev_count=high_sev_count,
        resolved_count=resolved_count,
    )


@app.route("/admin/complaint/<int:complaint_id>", methods=["GET", "POST"])
@admin_required
def admin_complaint_detail(complaint_id):
    """
    Admin complaint detail view with actions:
    (a) Override severity (1-5) with required reason -> saved to StatusHistory
    (b) Reassign department from category-filtered dropdown -> saved to StatusHistory
    (c) Update status with note -> saved to StatusHistory, applies to duplicate children too
    (d) Optionally upload after photo -> saved as after_photo_path, saved to StatusHistory
    """
    complaint = Complaint.query.get_or_404(complaint_id)

    # Filter departments by this complaint's category
    category_departments = Department.query.filter_by(category=complaint.category).all()
    if not category_departments:
        category_departments = Department.query.all()

    if request.method == "POST":
        changes_count = 0

        # (a) Override Severity (1-5) with required reason
        new_sev_str = request.form.get("severity", "").strip()
        sev_reason = request.form.get("severity_reason", "").strip()
        if new_sev_str:
            try:
                new_sev = int(new_sev_str)
                if 1 <= new_sev <= 5 and new_sev != complaint.severity:
                    if not sev_reason:
                        flash("A reason is required when overriding the severity rating.", "error")
                        return redirect(url_for("admin_complaint_detail", complaint_id=complaint.id))

                    old_sev = complaint.severity or "Unrated"
                    complaint.severity = new_sev

                    # Required StatusHistory format:
                    # "Severity changed from X to Y by admin: reason"
                    hist_note = f"Severity changed from {old_sev} to {new_sev} by admin: {sev_reason}"
                    h_sev = StatusHistory(
                        complaint_id=complaint.id,
                        status=complaint.status,
                        note=hist_note
                    )
                    db.session.add(h_sev)

                    # Update severity_reasons list
                    reasons = list(complaint.reasons_list)
                    reasons.append(f"Admin override: {sev_reason}")
                    complaint.severity_reasons = json.dumps(reasons)
                    changes_count += 1
            except ValueError:
                pass

        # (b) Reassign Department from dropdown filtered by category
        new_dept_id_str = request.form.get("department_id", "").strip()
        if new_dept_id_str:
            try:
                new_dept_id = int(new_dept_id_str)
                if new_dept_id != complaint.department_id:
                    new_dept = Department.query.get(new_dept_id)
                    if new_dept:
                        old_dept_name = complaint.department.name if complaint.department else "Unassigned"
                        complaint.department_id = new_dept.id
                        h_dept = StatusHistory(
                            complaint_id=complaint.id,
                            status=complaint.status,
                            note=f"Department reassigned from {old_dept_name} to {new_dept.name} by admin"
                        )
                        db.session.add(h_dept)
                        changes_count += 1
            except ValueError:
                pass

        # (c) Update status through Submitted > Under Review > Assigned > In Progress > Resolved with note
        new_status = request.form.get("status", "").strip()
        status_note = request.form.get("status_note", "").strip()
        valid_statuses = ["Submitted", "Under Review", "Assigned", "In Progress", "Resolved"]

        if new_status and new_status in valid_statuses:
            if new_status != complaint.status or status_note:
                complaint.status = new_status
                effective_note = status_note if status_note else f"Status updated to {new_status} by admin"

                h_status = StatusHistory(
                    complaint_id=complaint.id,
                    status=new_status,
                    note=effective_note
                )
                db.session.add(h_status)

                # When a parent complaint's status changes, apply it to all duplicate children too
                if complaint.children:
                    for child in complaint.children:
                        child.status = new_status
                        child_note = (
                            f"Status updated to {new_status} (synced from parent {complaint.tracking_id}): {status_note}"
                            if status_note
                            else f"Status updated to {new_status} (synced from parent {complaint.tracking_id})"
                        )
                        h_child = StatusHistory(
                            complaint_id=child.id,
                            status=new_status,
                            note=child_note
                        )
                        db.session.add(h_child)

                changes_count += 1

        # (d) Optionally upload an "after" photo (store as after_photo_path)
        after_file = request.files.get("after_photo")
        if after_file and after_file.filename:
            ext = os.path.splitext(secure_filename(after_file.filename))[1].lower()
            if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
                ext = ".jpg"
            after_filename = f"after_{uuid.uuid4().hex[:14]}{ext}"
            after_save_path = os.path.join(app.config["UPLOAD_FOLDER"], after_filename)
            after_file.save(after_save_path)
            complaint.after_photo_path = f"uploads/{after_filename}"

            h_photo = StatusHistory(
                complaint_id=complaint.id,
                status=complaint.status,
                note="Resolution 'after' photo uploaded by municipal admin"
            )
            db.session.add(h_photo)
            changes_count += 1

        if changes_count > 0:
            db.session.commit()
            flash("Grievance updated successfully.", "success")
        else:
            flash("No changes were submitted.", "info")

        return redirect(url_for("admin_complaint_detail", complaint_id=complaint.id))

    # GET request: fetch chronological timeline
    history_timeline = (
        StatusHistory.query.filter_by(complaint_id=complaint.id)
        .order_by(StatusHistory.changed_at.asc(), StatusHistory.id.asc())
        .all()
    )

    return render_template(
        "admin_detail.html",
        complaint=complaint,
        departments=category_departments,
        history_timeline=history_timeline,
    )


@app.route("/dashboard")
def dashboard():
    """
    Public civic transparency dashboard for Tumakuru:
    - No login required.
    - Total unique issues (parent complaints) & total citizen reports counted separately.
    - Open, resolved, and average resolution time (hours/days).
    - Bar chart data of complaints by category (for Chart.js).
    - Department performance table with open, resolved, and avg resolution time.
    - Leaflet map with a marker per unique issue, coloured by severity, with category and status in popups.
    - "Recently fixed" list with before/after photos where available.
    - Strict privacy: never exposes personal data or audio.
    """
    # 1. Unique complaints (parent complaints only)
    unique_complaints = (
        Complaint.query.filter(Complaint.parent_id.is_(None))
        .order_by(Complaint.created_at.desc())
        .all()
    )
    total_unique = len(unique_complaints)

    # Total citizen reports (sum of report_count across unique issues, or total complaint rows)
    total_reports_sum = (
        db.session.query(db.func.sum(Complaint.report_count))
        .filter(Complaint.parent_id.is_(None))
        .scalar()
    )
    all_complaints_count = Complaint.query.count()
    total_citizen_reports = int(total_reports_sum) if total_reports_sum else all_complaints_count
    if total_citizen_reports < total_unique:
        total_citizen_reports = total_unique

    # Status counts for unique issues
    open_complaints = [c for c in unique_complaints if c.status != "Resolved"]
    resolved_complaints = [c for c in unique_complaints if c.status == "Resolved"]
    open_count = len(open_complaints)
    resolved_count = len(resolved_complaints)

    # Resolution duration helper
    def get_resolution_seconds(c):
        """Calculates seconds elapsed between complaint creation and resolution."""
        sh = (
            StatusHistory.query.filter_by(complaint_id=c.id, status="Resolved")
            .order_by(StatusHistory.changed_at.desc())
            .first()
        )
        if not sh or not c.created_at:
            return None
        t_start = c.created_at
        t_end = sh.changed_at
        if t_start and t_end:
            if t_start.tzinfo is not None and t_end.tzinfo is None:
                t_end = t_end.replace(tzinfo=t_start.tzinfo)
            elif t_start.tzinfo is None and t_end.tzinfo is not None:
                t_start = t_start.replace(tzinfo=t_end.tzinfo)
            diff = (t_end - t_start).total_seconds()
            return max(0.0, diff)
        return None

    def format_resolution_time(seconds):
        if seconds is None:
            return "N/A"
        hours = seconds / 3600.0
        if hours < 1:
            mins = max(1, int(seconds / 60.0))
            return f"{mins}m"
        elif hours < 24:
            return f"{hours:.1f} hrs" if (hours != int(hours) and hours < 10) else f"{round(hours)} hrs"
        else:
            days = hours / 24.0
            return f"{days:.1f} days" if (days != int(days) and days < 10) else f"{round(days)} days"

    # Global average resolution time
    valid_durations = [get_resolution_seconds(c) for c in resolved_complaints]
    valid_durations = [d for d in valid_durations if d is not None]
    avg_resolution_seconds = (sum(valid_durations) / len(valid_durations)) if valid_durations else None
    avg_resolution_time_display = format_resolution_time(avg_resolution_seconds)

    # 2. Complaints by category for Chart.js
    categories_spec = [
        {"key": "road", "label": "Road Damage", "color": "rgba(56, 189, 248, 0.85)", "border": "#38bdf8"},
        {"key": "pollution", "label": "Sanitation & Pollution", "color": "rgba(52, 211, 153, 0.85)", "border": "#34d399"},
        {"key": "water", "label": "Water Supply & Sewage", "color": "rgba(96, 165, 250, 0.85)", "border": "#60a5fa"},
    ]
    category_chart_data = {
        "labels": [cat["label"] for cat in categories_spec],
        "keys": [cat["key"] for cat in categories_spec],
        "counts": [
            sum(1 for c in unique_complaints if c.category == cat["key"])
            for cat in categories_spec
        ],
        "backgroundColors": [cat["color"] for cat in categories_spec],
        "borderColors": [cat["border"] for cat in categories_spec],
    }

    # 3. Department performance table
    departments = Department.query.order_by(Department.category.asc(), Department.name.asc()).all()
    dept_stats = []
    for dept in departments:
        dept_parents = [c for c in unique_complaints if c.department_id == dept.id]
        d_open = sum(1 for c in dept_parents if c.status != "Resolved")
        d_resolved = sum(1 for c in dept_parents if c.status == "Resolved")
        d_durations = [get_resolution_seconds(c) for c in dept_parents if c.status == "Resolved"]
        d_durations = [d for d in d_durations if d is not None]
        d_avg_sec = (sum(d_durations) / len(d_durations)) if d_durations else None

        dept_stats.append({
            "id": dept.id,
            "name": dept.name,
            "category": dept.category,
            "open_count": d_open,
            "resolved_count": d_resolved,
            "total_count": len(dept_parents),
            "avg_resolution_time": format_resolution_time(d_avg_sec),
        })

    # 4. Leaflet map markers for unique issues
    map_markers = []
    for c in unique_complaints:
        if c.latitude is not None and c.longitude is not None:
            cat_label = (
                "Road Damage" if c.category == "road"
                else "Sanitation & Pollution" if c.category == "pollution"
                else "Water Supply & Sewage"
            )
            map_markers.append({
                "id": c.id,
                "tracking_id": c.tracking_id,
                "lat": float(c.latitude),
                "lng": float(c.longitude),
                "category": c.category,
                "category_label": cat_label,
                "issue_type": c.issue_type or cat_label,
                "status": c.status,
                "severity": c.severity or 3,
                "address": c.address_text or "Tumakuru, Karnataka",
                "reports": c.report_count or 1,
            })

    # 5. Recently Fixed grievances (with before/after photos where available)
    # Strictly no personal data or audio
    recently_fixed_raw = [c for c in unique_complaints if c.status == "Resolved"]
    recently_fixed_list = []
    for c in recently_fixed_raw[:8]:
        res_sec = get_resolution_seconds(c)
        sh_res = (
            StatusHistory.query.filter_by(complaint_id=c.id, status="Resolved")
            .order_by(StatusHistory.changed_at.desc())
            .first()
        )
        resolved_date_str = (
            sh_res.changed_at.strftime("%d %b %Y, %I:%M %p")
            if sh_res and sh_res.changed_at
            else c.created_at.strftime("%d %b %Y")
        )
        recently_fixed_list.append({
            "id": c.id,
            "tracking_id": c.tracking_id,
            "category": c.category,
            "issue_type": c.issue_type or "Civic Grievance",
            "description": c.description,
            "address_text": c.address_text or "Tumakuru, Karnataka",
            "photo_path": c.photo_path,
            "after_photo_path": c.after_photo_path,
            "resolution_time": format_resolution_time(res_sec),
            "resolved_date": resolved_date_str,
            "report_count": c.report_count or 1,
        })

    return render_template(
        "public_dashboard.html",
        total_unique=total_unique,
        total_citizen_reports=total_citizen_reports,
        open_count=open_count,
        resolved_count=resolved_count,
        avg_resolution_time=avg_resolution_time_display,
        category_chart_data=category_chart_data,
        dept_stats=dept_stats,
        map_markers=map_markers,
        recently_fixed=recently_fixed_list,
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
