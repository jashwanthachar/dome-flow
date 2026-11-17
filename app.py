"""
CivicEye - Tumakuru Civic Grievance System
A modern civic grievance reporting and resolution platform for Tumakuru.
"""

import os
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

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
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    history = db.relationship(
        "StatusHistory",
        backref="complaint",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="StatusHistory.changed_at.desc()"
    )

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

        # Assign relevant simulated department for category
        dept = Department.query.filter_by(category=norm_cat).first()
        dept_id = dept.id if dept else None

        # Generate tracking ID and save Complaint
        tracking_id = generate_tracking_id()
        complaint = Complaint(
            tracking_id=tracking_id,
            category=norm_cat,
            issue_type=issue_type,
            description=description or f"{issue_type} reported in Tumakuru",
            photo_path=photo_rel_path,
            latitude=latitude,
            longitude=longitude,
            address_text=address_text,
            status="Submitted",
            department_id=dept_id
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
