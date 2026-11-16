# CivicEye

**CivicEye** is a civic grievance and public issues resolution platform built for the citizens and municipal administration of **Tumakuru, Karnataka**.

---

## Overview

CivicEye provides an accessible, transparent digital interface for reporting and tracking local civic problems across municipal wards in Tumakuru, including:
- **Roads & Footpaths:** Potholes, damaged pedestrian pavements, and road hazards.
- **Sanitation & Waste Management:** Garbage clearing, public bin maintenance, and debris removal.
- **Street Lighting:** Dark spots, non-functional streetlights, and electrical safety hazards.
- **Water & Drainage:** Water pipeline leaks, blocked stormwater drains, and sewage overflow.
- **Parks & Public Spaces:** Public garden upkeep, fallen branches, and playground maintenance.
- **Town Planning:** Encroachments and unauthorized public works.

---

## Project Structure

```text
CivicEye/
├── app.py                # Main Flask application and API routes
├── requirements.txt      # Python dependencies
├── render.yaml           # Render deployment blueprint
├── static/
│   ├── app.js            # Frontend JavaScript
│   └── style.css         # Styling and design system
├── templates/
│   └── index.html        # CivicEye home page
└── README.md             # Project documentation
```

---

## Local Development

### 1. Clone & Set Up Virtual Environment

```bash
# Create and activate Python virtual environment
python -m venv venv

# Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Linux / macOS:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Application

```bash
python app.py
```

Open your browser at: **`http://127.0.0.1:5000`**

---

## Deployment on Render

This repository includes a `render.yaml` blueprint configured for zero-configuration Python web service deployment using Gunicorn.

1. Push this repository to GitHub.
2. In Render, select **New +** > **Blueprint** and select your repository.
3. Render automatically provisions the web service running `gunicorn --workers 1 --threads 4 --bind 0.0.0.0:$PORT app:app`.
