# CivicEye Tumakuru 👁️🏛️

**CivicEye** is an AI-powered municipal grievance reporting and resolution tracking platform designed specifically for the citizens and local administration of **Tumakuru, Karnataka, India**.

---

## 1. Problem Statement

In many rapidly growing Indian cities like Tumakuru, civic grievance redressal faces significant operational hurdles:
- **High Reporting Friction:** Citizens struggle with rigid text forms, language barriers, and lack of visual proof or precise geo-tagging.
- **Duplicate Complaint Overload:** The same pothole, garbage dump, or burst water pipe is often reported by dozens of nearby citizens, causing fragmented ticketing and wasted administrative resources.
- **Opaque Processing & Lack of Accountability:** Citizens submit grievances into a "black box" with no visibility into which municipal department owns the issue or how priority is determined.
- **Unverified Field Closures:** Grievances are frequently marked "Resolved" by contractors or field personnel without verifiable visual proof that the defect was actually fixed on the ground.

---

## 2. Who Faces This Problem?

- **Citizens of Tumakuru:** Pedestrians, commuters, auto-rickshaw drivers, and residents navigating damaged roads, open garbage burning, overflowing storm drains, or drinking water supply leaks across municipal wards.
- **Municipal Engineers & Field Crews:** Operations personnel from **Tumakuru City Corporation (Sanitation & Engineering Wings)**, **PWD Tumakuru Division**, and **KUWS&DB** who need instant visual categorization, automated severity rating, and verified photographic closure.
- **City Administrators & Corporators:** Ward officers and municipal leaders who require transparent city-wide analytics, average resolution times, and department accountability without manual data entry.

---

## 3. Key Features

- **Mobile-First Grievance Reporting:**
  - One-tap category selection: **Road Damage**, **Sanitation & Pollution**, and **Water Supply & Sewage**.
  - Photo upload with server-side downscaling (max 1024px with Pillow) for low latency on 4G/5G mobile connections.
  - Multilingual voice note recording in **Kannada**, **Hindi**, or **English**, translated and transcribed server-side.
  - Interactive Leaflet map with auto-geolocation and reverse geocoding inside Tumakuru city.
- **Duplicate Clustering & Crowd Consensus:**
  - Automatically detects existing grievances within **50 meters** using the Haversine formula.
  - Skips redundant AI API calls, links reports to the parent complaint, and automatically escalates severity once a cluster reaches 3+ citizen reports ("Reported by N citizens").
- **Multimodal AI Triage:**
  - Powered by Google Gemini: generates detected issue labels, 1–5 severity rating with factors, municipal impact summary, and recommended field actions.
  - Resilient fallback cascade: primary model &rarr; 503/429 retry after 2 seconds &rarr; fallback model &rarr; deterministic rule-based triage.
- **Live Citizen Tracking (`/track` and `/track/<tracking_id>`):**
  - Searchable by unique tracking ID (e.g., `CE-2026-0004`).
  - Vertical audit timeline (`StatusHistory`), status pills, assigned municipal department contact, crowd counter, and incident pin map.
  - AI attribution badge (**"Analyzed by Gemini"** or **"Basic analysis, AI unavailable"**).
- **Public Transparency Dashboard (`/dashboard`):**
  - No authentication required; strictly protects citizen privacy (zero personal data or audio exposed).
  - Key performance metrics: total unique grievances, total citizen reports, open vs. resolved counts, and average resolution time.
  - Chart.js breakdown of grievances by category and department performance table.
  - Full-screen Leaflet map colored by severity, and a "Recently Fixed" gallery showing before & after evidence photos.
- **Municipal Administration Portal (`/admin`):**
  - Secure single-password login with session management.
  - Filterable, sortable grievance table default-sorted by severity and report count.
  - Detail console allowing severity rating override with required justification, department reassignment, and status progression (`Submitted` &rarr; `Under Review` &rarr; `Assigned` &rarr; `In Progress` &rarr; `Resolved`).
  - Automatic synchronization of status updates to all duplicate child grievances.
- **AI-Verified Fix Verification:**
  - When marking a complaint `Resolved` with an after-photo, Gemini multimodal AI compares the before and after photos.
  - Returns `fixed: true/false`, confidence score, and visual finding note.
  - If unverified (`fixed: false`), triggers an explicit admin warning requiring manual **"Confirm & Resolve Anyway"** override logged to the audit history.
  - Displays **"AI-verified fix"** badges across tracking and public dashboard cards.
- **Resilience & Seeding:**
  - Automated deterministic seed script populating 40 realistic Tumakuru grievances across road, pollution, and water categories on startup.

---

## 4. System Architecture

```text
               +-------------------------------------------+
               |             Citizen / Admin UI            |
               | (HTML5 / Mobile-First CSS / Vanilla JS)   |
               +---------------------+---------------------+
                                     |
                                     v
                       +---------------------------+
                       |    Flask Application      |
                       |         (app.py)          |
                       +-------------+-------------+
                                     |
        +----------------------------+----------------------------+
        |                            |                            |
        v                            v                            v
+---------------+            +---------------+            +---------------+
|    SQLite     |            |  Pillow (PIL) |            |   ai_triage   |
| (SQLAlchemy)  |            | Image Resize  |            | (Google GenAI)|
|  civiceye.db  |            |  (max 1024px) |            | Gemini Models |
+---------------+            +---------------+            +-------+-------+
        ^                                                         |
        |                  +--------------------------------------+
        |                  |
        v                  v
+---------------+  +---------------+
|  Leaflet OSM  |  |   Chart.js    |
| Mapping Tiles |  | Visual Charts |
+---------------+  +---------------+
```

- **Backend:** Python 3.10+ with Flask and Flask-SQLAlchemy.
- **Database:** SQLite (persisted via `civiceye.db` or database URL).
- **AI Engine:** Official `google-genai` SDK using multimodal Flash models with automatic function calling disabled for speed and deterministic JSON schema validation via Pydantic.
- **Image Processing:** Pillow for server-side optimization and aspect ratio downscaling to 1024px at quality 80.
- **Frontend Mapping & Charts:** Leaflet.js with OpenStreetMap tiles, and Chart.js via CDN.

---

## 5. How AI is Used

1. **Grievance Triage:**
   - Evaluates citizen-uploaded photos alongside optional voice notes (Kannada, Hindi, or English).
   - Validates whether the image matches civic infrastructure (`image_matches_report`).
   - Assigns severity (1 to 5) and generates structured municipal remediation summaries and suggested department assignments.
2. **Fix Verification (Before vs. After):**
   - When a complaint is marked `Resolved` with a resolution photo, Gemini compares both downscaled images to answer: *Is the reported civic defect genuinely repaired?*
   - Detects incomplete repairs, unrelated site photos, or genuine fixes, preventing premature ticket closures.
3. **Resilient Multi-Model Fallback:**
   - Tries the primary model (`GEMINI_MODEL`).
   - If a transient `503` or `429` error is received, waits 2 seconds and retries the primary model once.
   - If unsuccessful, automatically calls the fallback model (`GEMINI_FALLBACK_MODEL`).
   - If AI services remain unavailable, gracefully uses deterministic rule-based heuristics without blocking complaint submission or resolution.

---

## 6. How to Run Locally

### Prerequisites
- Python 3.10, 3.11, or 3.12
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/jashwanthachar/dome-flow.git
cd dome-flow
```

### 2. Set Up Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Linux / macOS:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and fill in your Gemini API key and credentials (see section below).

### 5. Run the Server
```bash
python app.py
```
Open your browser at: **`http://127.0.0.1:5000`**

---

## 7. Environment Variables

The application reads the following environment variables (do **not** commit actual secrets):

| Variable | Description |
| :--- | :--- |
| `GEMINI_API_KEY` | Google Gemini API key from Google AI Studio. |
| `GEMINI_MODEL` | Primary Gemini model (defaults to `gemini-3.1-flash-lite`). |
| `GEMINI_FALLBACK_MODEL` | Optional secondary Gemini model invoked on primary failure. |
| `ADMIN_PASSWORD` | Administrator portal login password. |
| `SECRET_KEY` | Flask session secret key for cookie signing. |
| `DATABASE_URL` | Optional SQLAlchemy database URI (defaults to local SQLite `civiceye.db`). |
| `PORT` | Port number to bind the server to (defaults to `5000`). |

---

## 8. Known Limitations

- **Ephemeral Storage on Render Free Tier:**
  On Render's free web service tier, the underlying container filesystem is ephemeral. User-uploaded photos and SQLite database writes reset when the service spins down due to inactivity or redeploys. For permanent production storage, connect an external managed database (e.g., PostgreSQL) and object storage (e.g., Google Cloud Storage or AWS S3).
- **Simulated Department Workflows:**
  Department names, dispatch emails, and status progression notes represent a simulated municipal administration model for Tumakuru City Corporation and PWD Tumakuru. They do not trigger real-world government dispatches.

---

## 9. Credits & Attributions

- **Google Gemini API:** Multimodal AI triage, speech transcription, and visual fix verification powered by Google DeepMind's Gemini models via the official `google-genai` SDK.
- **Leaflet.js:** Open-source interactive mobile-friendly maps by Volodymyr Agafonkin.
- **OpenStreetMap:** Map data and tile layers &copy; [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), licensed under the Open Database License (ODbL).
- **Chart.js:** Responsive open-source HTML5 charts.
- **Pillow (PIL):** Python Imaging Library fork for high-performance server-side image downscaling.
- **Sample Photography:** Civic defect and repair seed images sourced from open civic datasets and public-domain photography collections (Unsplash & Wikimedia Commons).

---

## 10. License

Built for Tumakuru civic empowerment. Released under the MIT License.
