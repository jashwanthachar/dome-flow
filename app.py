"""
CivicEye - Tumakuru Civic Grievance System
A modern civic grievance reporting and resolution platform for Tumakuru.
"""

import os
from flask import Flask, render_template, jsonify

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "civiceye-tumakuru-dev-secret")


@app.route("/")
def index():
    """Render the CivicEye home page."""
    return render_template("index.html")


@app.route("/health")
def health():
    """Health check endpoint for deployment monitoring."""
    return jsonify({
        "status": "healthy",
        "app": "CivicEye",
        "city": "Tumakuru"
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
