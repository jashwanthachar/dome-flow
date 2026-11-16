"""
CivicEye - Tumakuru Civic Grievance System
A modern civic grievance reporting and resolution platform for Tumakuru.
"""

import os
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "civiceye-tumakuru-dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'civiceye.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


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
