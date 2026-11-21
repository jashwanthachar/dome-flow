# CivicEye Tumakuru — The Complete Project Guide & Hackathon Bible 👁️🏛️

> **Welcome to the CivicEye Project Guide!**  
> If you built this project with AI assistance and you are preparing to present it to hackathon judges, this document is your single source of truth. Every technical concept is explained using everyday analogies, tied directly to the real code in this repository, and organized so you can speak with confidence and clarity.

---

## Table of Contents
1. [One-Paragraph Summary](#1-one-paragraph-summary)
2. [Tools & Technologies](#2-tools--technologies)
3. [Project File Map](#3-project-file-map)
4. [How a Web Request Works Here (In Simple Terms)](#4-how-a-web-request-works-here)
5. [Frontend: User Interface, Maps & Media](#5-frontend-user-interface-maps--media)
6. [Backend: Routes & Core Python Functions](#6-backend-routes--core-python-functions)
7. [Database: Architecture, Models & Ephemeral Storage](#7-database-architecture-models--ephemeral-storage)
8. [The AI Pipeline Step by Step](#8-the-ai-pipeline-step-by-step)
9. [Features Explained One by One](#9-features-explained-one-by-one)
10. [Security & Safety Measures (And Real Weaknesses)](#10-security--safety-measures)
11. [Problems Hit & How We Solved Them](#11-problems-hit--how-we-solved-them)
12. [Deployment: From Laptop to GitHub to Render](#12-deployment-from-laptop-to-github-to-render)
13. [Limitations & Future Improvements](#13-limitations--future-improvements)
14. [Comprehensive Technical Glossary (40+ Terms)](#14-comprehensive-technical-glossary)
15. [Judge Q&A: 30+ Likely Questions & Spoken Answers](#15-judge-qa-30-likely-questions--spoken-answers)
16. [The 2-Minute Pitch Script & 10 Things to Know Cold](#16-the-2-minute-pitch-script--10-things-to-know-cold)

---

## 1. One-Paragraph Summary

**CivicEye** is an AI-powered civic grievance and transparency platform designed specifically for the city of **Tumakuru, Karnataka, India**. It allows citizens to report everyday municipal infrastructure failures—such as dangerous potholes on B.H. Road, overflowing garbage in Mandipet, or burst water mains in SIT Extension—in under 30 seconds by simply taking a photo, speaking a voice note in Kannada, Hindi, or English, and pinning their location on an interactive map. Instead of dumping complaints into an unorganized bureaucratic inbox, CivicEye uses Google Gemini multimodal AI to automatically classify the defect, verify that the photo is legitimate civic damage, assign a 1-to-5 urgency rating, suggest the right municipal department, and detect duplicate reports within 50 meters so nearby citizens back each other up without flooding city engineers. City administrators manage the workflow through a dedicated operations portal that requires photographic proof of repair before closing a ticket, while a public dashboard gives every citizen total transparency into municipal response times and SLA targets.

---

## 2. Tools & Technologies

Every technology in CivicEye was deliberately chosen to create a lightweight, fast, and accessible civic tool. Here is the full inventory of tools, why they were chosen, and where they live in the codebase:

### 1. Python 3 (Language)
- **What it is:** A readable, high-level programming language that powers the entire backend server.
- **Everyday Analogy:** If the project were an automobile, Python is the engine block where all the mechanical parts connect.
- **Why chosen:** Python has the best library support for AI models (Google GenAI), image processing (Pillow), and web development (Flask).
- **Where used:** [app.py](file:///d:/MODIFIED/app.py), [ai_triage.py](file:///d:/MODIFIED/ai_triage.py), and [seed_data.py](file:///d:/MODIFIED/seed_data.py).

### 2. Flask (Web Framework)
- **What it is:** A lightweight "micro" web framework for Python that routes web traffic, handles form submissions, and serves HTML pages.
- **Everyday Analogy:** The postmaster in a post office who reads the address on incoming mail and directs it to the correct department desk.
- **Why chosen:** Unlike heavy frameworks like Django, Flask does not force complicated boilerplate code. It gives total control over HTTP request handling, session cookies, and route logic.
- **Where used:** [app.py](file:///d:/MODIFIED/app.py#L13-L35) sets up `app = Flask(__name__)` and defines every single web URL route.

### 3. SQLite & Flask-SQLAlchemy (Database & ORM)
- **What it is:** **SQLite** is a file-based database that stores data inside a single file (`civiceye.db`) without requiring a separate database server. **Flask-SQLAlchemy** is an Object-Relational Mapper (ORM), a tool that lets Python code talk to database tables using Python classes instead of writing raw SQL queries.
- **Everyday Analogy:** SQLite is a tidy digital filing cabinet stored right in your project folder; SQLAlchemy is your bilingual executive assistant who translates your Python instructions into filing cabinet operations.
- **Why chosen:** Zero configuration, zero external service costs, and completely self-contained for hackathon development and testing.
- **Where used:** [app.py](file:///d:/MODIFIED/app.py#L24-L35) configures `db = SQLAlchemy(app)` and defines the `Department`, `Complaint`, and `StatusHistory` models.

### 4. Gunicorn (Production WSGI Server)
- **What it is:** "Green Unicorn", a production-grade Web Server Gateway Interface (WSGI) HTTP server for Python applications on Linux.
- **Everyday Analogy:** A professional restaurant hostess and fleet of waiters that can serve multiple tables at once, replacing the lone cook who was previously running out to take orders.
- **Why chosen:** Flask's built-in development server is only intended for local testing and can only handle one request at a time reliably. Gunicorn spawns worker processes to serve multiple citizens simultaneously in production on Render.
- **Where used:** [render.yaml](file:///d:/MODIFIED/render.yaml#L7) sets the start command: `gunicorn --workers 2 --threads 4 --timeout 60 --bind 0.0.0.0:$PORT app:app`.

### 5. Google GenAI SDK & Gemini API (`gemini-3.1-flash-lite`)
- **What it is:** Google's latest multimodal Artificial Intelligence API that can see images, listen to audio files, read text, and return structured JSON responses.
- **Everyday Analogy:** An expert municipal civil engineer sitting at the intake desk who looks at the citizen's photo, listens to their voice message, and fills out an inspection report in 2 seconds flat.
- **Why chosen:** Multimodal support in a single API call (analyzing photo + Kannada audio together), high speed, low cost, and reliable support for structured Pydantic JSON schemas.
- **Where used:** [ai_triage.py](file:///d:/MODIFIED/ai_triage.py#L441-L568) in `_call_gemini_api` and `_call_gemini_verify_fix`.

### 6. Pillow / PIL (Python Imaging Library)
- **What it is:** The standard Python library for opening, rotating, resizing, and optimizing image files.
- **Everyday Analogy:** An automated photo compressor that shrinks high-resolution 12-megapixel smartphone photos down to passport-sized digital files before they travel over the wire.
- **Why chosen:** Citizens upload 5MB–10MB photos taken on modern smartphone cameras. Sending full-size photos to Gemini causes network lag and API timeouts. Pillow downscales photos server-side to max 1024 pixels at JPEG quality 80, shrinking files by ~90% in milliseconds while keeping full visual defect detail.
- **Where used:** [ai_triage.py](file:///d:/MODIFIED/ai_triage.py#L400-L426) in `optimize_image_for_ai()`.

### 7. Leaflet.js & OpenStreetMap (Interactive Mapping)
- **What it is:** **Leaflet** is an open-source JavaScript mapping library. **OpenStreetMap (OSM)** is a free, crowd-sourced world map that provides the visual map tiles.
- **Everyday Analogy:** Leaflet is the glass interactive table; OpenStreetMap is the detailed city map of Tumakuru spread out beneath the glass.
- **Why chosen:** Free, open-source, requires zero paid Google Maps API billing cards, and provides smooth, mobile-friendly draggable map pins and popups.
- **Where used:** In [templates/report.html](file:///d:/MODIFIED/templates/report.html#L249-L274) (pinning grievance location), [templates/track.html](file:///d:/MODIFIED/templates/track.html) (showing grievance location), [templates/admin_detail.html](file:///d:/MODIFIED/templates/admin_detail.html) (admin inspection map), and [templates/public_dashboard.html](file:///d:/MODIFIED/templates/public_dashboard.html) (city-wide severity map).

### 8. Chart.js (Data Visualization)
- **What it is:** An open-source JavaScript library for drawing interactive charts on HTML5 `<canvas>` elements.
- **Everyday Analogy:** An automated infographic artist that turns a table of numbers into colorful bar graphs.
- **Why chosen:** Lightweight (loaded via CDN), responsive, and visually modern.
- **Where used:** [templates/public_dashboard.html](file:///d:/MODIFIED/templates/public_dashboard.html) to render the category volume bar chart (Road vs. Sanitation vs. Water).

### 9. Browser MediaRecorder API (Voice Notes)
- **What it is:** A native JavaScript web browser interface that records microphone audio directly inside the web browser without any mobile app download or browser plugins.
- **Everyday Analogy:** A built-in voice recorder on a mobile phone that records an audio clip and automatically attaches it as a file to a form.
- **Why chosen:** Allows citizens who cannot type in English or Kannada to speak their problem aloud for up to 30 seconds.
- **Where used:** [templates/report.html](file:///d:/MODIFIED/templates/report.html#L322-L446).

### 10. Render (Cloud Hosting Platform)
- **What it is:** A modern cloud platform that builds code directly from GitHub and hosts live web applications.
- **Everyday Analogy:** The landlord that provides the physical building, power, and internet address (`https://civiceye.onrender.com`) where your web application lives so anyone in the world can visit it.
- **Why chosen:** Native Python support, automated deploys on `git push`, support for `render.yaml` Infrastructure-as-Code, and a generous free tier.
- **Where used:** Configured via [render.yaml](file:///d:/MODIFIED/render.yaml).

### 11. GitHub & Git (Version Control)
- **What it is:** **Git** is a command-line tool that records snapshots of code changes over time. **GitHub** is the cloud website that hosts the git repository.
- **Everyday Analogy:** Git is your project's "time machine" and undo button; GitHub is the shared safety vault in the cloud where every snapshot is stored.
- **Where used:** Remote repository at `https://github.com/jashwanthachar/dome-flow.git`.

---

## 3. Project File Map

Here is the exact layout of files in the project and what role each plays:

```text
d:\MODIFIED\
├── app.py                      # Main Flask application: models, routes, logic & database setup
├── ai_triage.py                # AI module: Gemini multimodal calls, prompts, fallbacks, Pillow resizing
├── seed_data.py                # Deterministic startup seed generator (40 realistic Tumakuru complaints)
├── civiceye.db                 # SQLite database file containing all persistent tables
├── requirements.txt            # Python dependencies list for pip installation
├── render.yaml                 # Deployment blueprint configuration for Render cloud platform
├── .env                        # Local secret keys & environment variables (NEVER committed to git)
├── .env.example                # Template showing required variable names without values
├── .gitignore                  # Instructs Git which temporary, database, or secret files to ignore
├── README.md                   # High-level project documentation, credits, and architecture
├── docs/
│   └── PROJECT_GUIDE.md        # This comprehensive, beginner-friendly hackathon guide
├── static/                     # Static assets delivered directly to the citizen's browser
│   ├── style.css               # Comprehensive mobile-first CSS styling & dark theme
│   ├── app.js                  # Frontend client script for tactile button animations
│   ├── favicon.svg             # Custom SVG browser tab icon (CivicEye logo)
│   ├── uploads/                # Directory storing citizen before-photos & admin after-photos
│   │   └── .gitkeep            # Ensures empty folder is tracked in Git
│   └── seed/                   # Seed photo storage for sample data
│       ├── road/               # Sample road defect photos (potholes, cave-ins)
│       ├── pollution/          # Sample sanitation photos (garbage dumps, smoke)
│       ├── water/              # Sample water photos (pipe bursts, leaks)
│       └── after/              # Sample resolved after-photos for road repairs
└── templates/                  # Jinja2 HTML templates rendered by Flask
    ├── index.html              # Home page: category selection cards, stats, quick links
    ├── report.html             # Grievance reporting form (camera, map pin, voice recorder, loading screen)
    ├── success.html            # Confirmation page with large tracking code & AI attribution badge
    ├── track.html              # Citizen tracking screen with audit timeline, SLA timer & map pin
    ├── public_dashboard.html   # Public transparency portal: KPIs, charts, dept table & fixed gallery
    ├── admin_login.html        # Secure municipal administration login form
    ├── admin_dashboard.html    # Admin management registry: filterable, sortable complaints table
    ├── admin_detail.html       # Admin grievance detail console: severity override, after photo, resolve
    ├── 404.html                # Friendly custom error page for broken links
    └── placeholder.html        # Standby page for future municipal category expansions
```

---

## 4. How a Web Request Works Here

If a judge asks: *"Walk me through what happens under the hood when a citizen submits a complaint,"* here is the exact step-by-step lifecycle of a web request in simple, everyday language:

```text
[Citizen's Smartphone]
       │
       │ 1. Submits form (Photo + Kannada Voice + GPS Coordinates + Description)
       ▼
 [Flask Web Server (app.py)]
       │
       │ 2. Catches POST request at route: /report/road
       │ 3. Saves uploaded photo and audio to static/uploads/
       │ 4. Executes Haversine formula against database: Is there an existing complaint within 50m?
       │
       ├───► [YES: Duplicate Found within 50m]
       │         │
       │         ├─ Skips Gemini API call entirely (saving money & time).
       │         ├─ Links complaint as child to existing parent.
       │         ├─ Bumps parent report_count (+1). If count >= 3, raises severity.
       │         └─ Writes audit record to StatusHistory.
       │
       └───► [NO: Fresh Unique Grievance]
                 │
                 ├─ 5. Passes photo to Pillow: downscales image to max 1024px.
                 ├─ 6. Calls Google Gemini API in ai_triage.py with photo + audio.
                 │     (Gemini returns structured JSON: severity, summary, action, Kannada transcript).
                 ├─ 7. Writes new Complaint row and initial StatusHistory row in civiceye.db.
                 └─ 8. Redirects citizen's browser to /success/CE-2026-XXXX.
```

### Real Concrete Example: Reporting a Pothole on B.H. Road

1. **In the Browser (Client-side):**
   A citizen visits `https://civiceye.onrender.com/report/road`. Their browser downloads the HTML form rendered by Flask. The citizen taps the camera icon to upload a photo of a pothole, taps "Use My Location" to pin their GPS coordinates (`13.3392, 77.1140`), records an 8-second voice note saying in Kannada *"ಇಲ್ಲಿ ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಬಿದ್ದಿದೆ, ಗಾಡಿಗಳು ಬೀಳುತ್ತಿವೆ"* ("There is a big hole in the road here, vehicles are falling"), and taps **Submit Grievance**.
2. **Over the Wire (HTTP POST):**
   The browser bundles the photo, the audio clip, and the form fields into an `HTTP POST` request sent to `/report/road`. The frontend displays a full-screen loading overlay: *"Analyzing your complaint with AI..."*.
3. **The Server Catches the Request (`app.py`):**
   Flask recognizes that the URL matches `@app.route("/report/<category>", methods=["GET", "POST"])`. Because the request method is `POST`, it enters line 440 of [app.py](file:///d:/MODIFIED/app.py#L440).
4. **Saving Uploads:**
   The server sanitizes the filenames with `secure_filename()` and saves the photo and voice file into `static/uploads/`.
5. **The 50-Meter Haversine Duplicate Check:**
   The server queries the SQLite database for unresolved road complaints. It runs the Haversine mathematical formula on the coordinates. If another citizen reported this exact pothole 20 meters away 2 hours ago, the system links this submission as a duplicate child, raises the parent ticket's count, and skips Gemini completely.
6. **AI Analysis (`ai_triage.py`):**
   If no duplicate exists, Flask calls `analyze_complaint()` in `ai_triage.py`. Pillow opens the photo and creates an optimized copy (`opt_...jpg`) scaled down to 1024 pixels. The server sends this optimized photo and the audio recording to Gemini `gemini-3.1-flash-lite`. Gemini analyzes both, translates the Kannada audio to English, assigns Severity 4, writes a 2-sentence summary, and recommends assigning the issue to the *Tumakuru City Corporation Engineering Wing*.
7. **Database Persistence:**
   Flask creates a new `Complaint` row in SQLite with a unique tracking code (e.g., `CE-2026-0041`), creates an initial `StatusHistory` row ("Grievance registered in CivicEye portal"), and commits the transaction to `civiceye.db`.
8. **HTTP Redirect & Response:**
   The server issues an HTTP 302 redirect instructing the citizen's browser to navigate to `/success/CE-2026-0041`. The browser displays the success page with their tracking code, a copy button, and an "Analyzed by Gemini" badge.

---

## 5. Frontend: User Interface, Maps & Media

The frontend of CivicEye was built with pure, lightweight HTML5, modern CSS3, and vanilla JavaScript—**intentionally avoiding heavy frameworks like React, Angular, or Vue**. This makes the application load near-instantly on budget smartphones connected to patchy 3G/4G networks in semi-urban India.

### 1. Template Structure (Jinja2)
Flask uses the **Jinja2 templating engine**. Templates are HTML files with special placeholders like `{{ complaint.tracking_id }}` and control tags like `{% if complaint.status == 'Resolved' %}`. When a citizen requests a page, Python fills in the placeholders on the server and sends clean, fully-rendered HTML to the citizen's device.
- **`index.html`:** The home portal featuring 3 large category cards (Road, Sanitation, Water) with emoji badges, city statistics, and links to tracking and public dashboards.
- **`report.html`:** The intake form featuring photo dropzone/camera input, Leaflet map location picker, voice recorder, and category-tailored issue type dropdowns.
- **`track.html`:** The citizen tracking portal. Features a search bar, large tracking ID display, copy button, status pills, SLA countdown badge, vertical progression timeline, assigned department card, and incident location map.
- **`public_dashboard.html`:** City transparency dashboard with 4 KPI cards (Total Issues, Citizen Reports, Open Backlog, Avg. Resolution Time), Chart.js category bar chart, department performance table with `% Resolved within SLA`, full-width incident map, and a before/after fixed gallery.
- **`admin_dashboard.html`:** The municipal registry table displaying parent complaints, sortable by severity or report count, filterable by status, and displaying real-time SLA countdown badges.
- **`admin_detail.html`:** The administrative management console showing evidence photos, an embedded audio player with translated transcript, Gemini's AI analysis breakdown, an interactive map, and an action form to override severity, reassign departments, attach resolution photos, and update status.
- **`404.html`:** A friendly, branded error page with quick navigation back to home or tracking.

### 2. Styling System (`static/style.css`)
- **Design Language:** A modern, dark-themed municipal interface inspired by mission control dashboards (slate dark background `#0b1120`, navy card backgrounds `#1e293b`, crisp cyan accents `#38bdf8`, emerald green resolution pills `#10b981`, and crimson emergency alerts `#ef4444`).
- **Mobile-First Responsiveness:**
  - Designed from the ground up for a 375px mobile viewport (iPhone SE / budget Android screen width).
  - Strict minimum tap target size of **44px × 44px** on all buttons, dropdowns, and form inputs to prevent mis-taps on touchscreens.
  - Media queries adapt two-column desktop layouts into clean, single-column vertical flows on smaller screens.
  - Horizontal scrolling is strictly prevented using `box-sizing: border-box`, `max-width: 100%`, and `.table-responsive` wrappers.

### 3. Leaflet OpenStreetMap Integration
- Defined in [templates/report.html](file:///d:/MODIFIED/templates/report.html#L233-L319).
- Centered by default on central Tumakuru (`13.3392, 77.1140`) at zoom level 14.
- Includes a draggable marker: whenever the citizen drags the marker or taps anywhere on the map, JavaScript captures the latitude and longitude and updates hidden form inputs (`#input-latitude`, `#input-longitude`).
- **"Use My Location" Button:** Leverages the browser's native `navigator.geolocation.getCurrentPosition()` API with `enableHighAccuracy: true`. When tapped, it pans the map to the citizen's exact GPS coordinates and places the pin there.

### 4. Voice Recording with Browser MediaRecorder API
- Located in [templates/report.html](file:///d:/MODIFIED/templates/report.html#L322-L446).
- When the citizen taps **"Record Voice Note"**, the browser asks for microphone permission.
- It records audio chunks in 250ms increments using the browser's native `MediaRecorder` interface, automatically selecting supported codecs (`audio/webm` or `audio/mp4`).
- A countdown timer enforces a **strict 30-second maximum duration** to prevent oversized files.
- When recording stops, JavaScript creates an in-memory `Blob` (Binary Large Object), sets up an audio playback element so the citizen can listen to their recording, and uses the `DataTransfer` API to programmatically attach the audio file to the standard HTML form submission.

### 5. Full-Screen AI Loading Overlay
- Defined in [templates/report.html](file:///d:/MODIFIED/templates/report.html#L474-L481).
- Because sending a high-resolution photo and audio file to Gemini takes between 1.5 to 3.5 seconds, citizens might assume the page froze and tap submit multiple times.
- The instant the form submits, JavaScript intercepts the event, disables the submit button, and pops up a full-screen blurred dark overlay with an animated spinning loader: *"Analyzing your complaint with AI... Multimodal analysis in progress • Please wait"*.

---

## 6. Backend: Routes & Core Python Functions

All server routing and business logic lives inside [app.py](file:///d:/MODIFIED/app.py). Here is a complete breakdown of every route:

### Public & Citizen Routes
1. **`GET /` (`index`)**: Serves the homepage displaying civic grievance categories, introductory statistics, and quick navigation.
2. **`GET /report/<category>` & `POST /report/<category>` (`report`)**:
   - `GET`: Validates that the requested category is valid (`road`, `pollution`, or `water`) and renders the reporting form with category-specific issue types.
   - `POST`: Processes incoming multipart form data: saves the photo and voice recording, checks for duplicates within 50m using Haversine, triggers the AI pipeline or duplicate link, creates database records, and redirects to `/success/<tracking_id>`.
3. **`GET /success/<tracking_id>` (`success`)**: Displays the submission confirmation page with the large formatted tracking ID, category icon, and AI attribution badge.
4. **`GET /track` & `GET /track/<tracking_id>` (`track`)**: Citizen tracking portal. Retrieves grievance details by tracking ID (case-insensitive), fetches the full chronological `StatusHistory` timeline, computes the live SLA timer on the fly, and renders the tracking view.
5. **`GET /dashboard` (`dashboard`)**: Public transparency portal. Calculates summary KPIs (total unique issues, total citizen reports, open count, resolved count, global average resolution time), groups complaints by category for Chart.js, calculates department performance with `% Resolved within SLA`, extracts coordinates for the Leaflet map, and gathers the 8 most recently resolved complaints with before/after photos.
6. **`GET /health` (`health`)**: Lightweight JSON monitoring endpoint returning `{"status": "healthy", "departments_seeded": 7}` for deployment uptime monitors.
7. **`GET /api/status` (`api_status`)**: Public API endpoint returning system version and online status.
8. **`GET /favicon.ico` (`favicon`)**: Serves `static/favicon.svg` with the correct SVG MIME type.
9. **`@app.errorhandler(404)` (`page_not_found`)**: Catches all non-existent URLs and displays the custom branded `404.html` page with HTTP status code 404.

### Municipal Administration Routes
1. **`GET /admin/login` & `POST /admin/login` (`admin_login`)**:
   - `GET`: Renders the administrative login page.
   - `POST`: Verifies the submitted password against the `ADMIN_PASSWORD` environment variable. If correct, sets `session["is_admin"] = True` and redirects to `/admin`. If incorrect, displays a flash error message.
2. **`GET /admin/logout` (`admin_logout`)**: Removes the admin session flag (`session.pop("is_admin", None)`) and redirects back to the login screen.
3. **`GET /admin` (`admin_dashboard`)**: Protected by the `@admin_login_required` decorator. Displays parent complaints in a searchable, filterable table. Supports filtering by category (`road`, `pollution`, `water`), workflow status (`Submitted`, `Under Review`, `Assigned`, `In Progress`, `Resolved`), severity rating (1–5), and sorting by default (severity + report count), report count, submission date, or status progression.
4. **`GET /admin/complaint/<int:complaint_id>` & `POST /admin/complaint/<int:complaint_id>` (`admin_complaint_detail`)**:
   - `GET`: Loads the complete grievance console: evidence photos, citizen voice player and translated transcript, AI triage breakdown, map pin, status timeline, and action form.
   - `POST`: Handles municipal updates:
     - **(a) Severity Override:** Changes severity rating (1–5), requiring an admin justification note logged to `StatusHistory`.
     - **(b) Department Reassignment:** Reassigns the grievance to any valid department matching the category.
     - **(c) After-Photo Upload:** Saves a resolution photo to `static/uploads/after_...`.
     - **(d) Status Progression:** Updates status (`Submitted` &rarr; `Under Review` &rarr; `Assigned` &rarr; `In Progress` &rarr; `Resolved`). If marked `Resolved` with an after-photo, calls `verify_resolution_fix()`. If AI indicates the defect is still present, raises an explicit warning requiring a `"Resolve anyway"` override. Automatically synchronizes status changes to all linked duplicate child complaints.

---

## 7. Database: Architecture, Models & Ephemeral Storage

CivicEye uses **SQLite** through **Flask-SQLAlchemy**. The database schema consists of three relational tables:

```text
+---------------------+          +------------------------------------+          +-----------------------+
|     department      |          |             complaint              |          |    status_history     |
+---------------------+          +------------------------------------+          +-----------------------+
| id (PK, Integer)    |<---┐     | id (PK, Integer)                   |<---┐     | id (PK, Integer)      |
| name (String)       |    └────+| department_id (FK, Integer)        |    └────+| complaint_id (FK, Int)|
| category (String)   |          | tracking_id (String, Unique, Index)|          | status (String)       |
| contact_email (Str) |     ┌───+| parent_id (FK -> complaint.id)     |          | note (Text)           |
+---------------------+     │    | category (String)                  |          | changed_at (DateTime) |
                            └───>| issue_type (String)                |          +-----------------------+
                                 | description (Text)                 |
                                 | photo_path (String)                |
                                 | audio_path (String)                |
                                 | latitude (Float), longitude (Float)|
                                 | address_text (String)              |
                                 | status (String)                    |
                                 | severity (Integer: 1-5)            |
                                 | severity_reasons (Text, JSON)      |
                                 | ai_summary (Text)                  |
                                 | detected_issue (String)            |
                                 | suggested_action (String)          |
                                 | transcription (Text)               |
                                 | image_matches_report (Boolean)     |
                                 | ai_confidence (Float)              |
                                 | ai_source (String)                 |
                                 | ai_model (String)                  |
                                 | report_count (Integer)             |
                                 | after_photo_path (String)          |
                                 | fix_verified (Boolean)             |
                                 | fix_note (String)                  |
                                 | created_at (DateTime)              |
                                 +------------------------------------+
```

### Table Breakdown

#### 1. `Department` Table ([app.py](file:///d:/MODIFIED/app.py#L85-L103))
Stores the simulated governmental and municipal agencies in Tumakuru:
- `id`: Integer Primary Key.
- `name`: Full official department title (e.g., *"Tumakuru City Corporation - Engineering Wing"*, *"PWD Tumakuru Division"*, *"KUWS&DB Tumakuru"*).
- `category`: Matching civic category (`road`, `pollution`, `water`).
- `contact_email`: Official notification email (e.g., `engineering@tumakurucity.gov.in`).

#### 2. `Complaint` Table ([app.py](file:///d:/MODIFIED/app.py#L105-L210))
Stores every citizen grievance report and all associated AI findings:
- `id`: Integer Primary Key.
- `tracking_id`: Unique citizen tracking code formatted as `CE-YYYY-NNNN` (e.g., `CE-2026-0004`), indexed for lightning-fast search.
- `category` & `issue_type`: The citizen's selected category and issue description.
- `description`: Text notes entered by the citizen (or automatically filled from voice transcription).
- `photo_path` & `audio_path`: Relative disk paths inside `static/uploads/`.
- `latitude`, `longitude`, `address_text`: Incident coordinates and reverse-geocoded landmark text.
- `status`: Current lifecycle stage (`Submitted`, `Under Review`, `Assigned`, `In Progress`, `Resolved`).
- `severity`: Integer from 1 (minor) to 5 (critical emergency).
- `severity_reasons`: JSON-serialized array of strings explaining the rating.
- `ai_summary`: 2-sentence operational summary generated by Gemini.
- `detected_issue` & `suggested_action`: AI-identified defect label and remediation step.
- `transcription`: English translation of spoken Kannada, Hindi, or English audio.
- `image_matches_report`: Boolean flag set to `False` if the photo is spam or unrelated.
- `ai_confidence`: Float score between 0.0 and 1.0.
- `ai_source`: Attribution tag: `"gemini"` for live AI, `"fallback"` for rule-based heuristics, or `"seed"` for demonstration sample data.
- `ai_model`: Exact model name that answered (e.g., `gemini-3.1-flash-lite`).
- `parent_id`: Self-referencing Foreign Key pointing to `complaint.id`. If `None`, this is an original unique parent grievance. If populated, this complaint is a duplicate child report.
- `report_count`: Integer tracking how many citizens reported this exact defect (starts at 1; duplicate children increment the parent).
- `after_photo_path`: Relative disk path to resolution photo uploaded by municipal staff.
- `fix_verified` & `fix_note`: Boolean and note recording Gemini's before-vs-after repair verification.
- `department_id`: Foreign Key linking to `department.id`.
- `created_at`: UTC timestamp of submission.

#### 3. `StatusHistory` Table ([app.py](file:///d:/MODIFIED/app.py#L213-L234))
An immutable audit log recording every single state transition:
- `id`: Integer Primary Key.
- `complaint_id`: Foreign Key pointing to `complaint.id`.
- `status`: Status at that point in time.
- `note`: Audit text explaining what changed (e.g., *"Severity changed from 3 to 4 by admin: High bus traffic"*, *"AI-verified fix: Asphalt patch flush with road grade"*).
- `changed_at`: UTC timestamp of the update.

### Startup Database Creation & Seeding
In [app.py](file:///d:/MODIFIED/app.py#L425-L450):
1. When the Flask server starts, `init_db()` runs automatically.
2. `db.create_all()` creates all tables if they do not exist.
3. If the `Department` table is empty, `seed_departments()` seeds the 7 municipal departments across road, pollution, and water.
4. If the `Complaint` table is empty, `seed_complaints()` in [seed_data.py](file:///d:/MODIFIED/seed_data.py) executes, deterministically seeding 40 realistic Tumakuru grievances with authentic coordinates, categories, and duplicate clusters.

### Why Data Resets on Render's Free Tier (Ephemeral Storage)
- **The Concept:** Render's free tier uses **ephemeral disk storage**. "Ephemeral" means temporary or short-lived.
- **Everyday Analogy:** Imagine writing your notes on a whiteboard in a shared conference room. As long as you stay in the room, the whiteboard stays intact. But every night, the cleaning crew erases the board clean.
- **Why it happens:** Cloud platforms run free containers on dynamic virtual machines. Whenever the app goes to sleep after 15 minutes of inactivity, or whenever new code is deployed, Render destroys the old container and boots a brand-new container from the Git repository. Any SQLite database file (`civiceye.db`) or uploaded image saved on the local container disk is wiped clean.
- **How CivicEye handles this:** Because `seed_complaints()` runs on startup whenever the database is empty, the application **automatically self-heals**, regenerating 40 realistic Tumakuru complaints every time the container boots up.

---

## 8. The AI Pipeline Step by Step

The AI triage pipeline lives inside [ai_triage.py](file:///d:/MODIFIED/ai_triage.py). Here is how an image and voice recording travel through the AI:

### Step 1: Server-Side Photo Optimization (Pillow)
```python
# ai_triage.py line 400
def optimize_image_for_ai(original_path: str, max_dimension: int = 1024, quality: int = 80) -> str:
```
- Smartphone photos often exceed 4000 × 3000 pixels and 8MB in size.
- Uploading large images to cloud AI consumes high bandwidth and causes timeouts.
- Pillow inspects the image, applies `ImageOps.exif_transpose` (fixing smartphone camera rotation bugs), converts color spaces to RGB, scales the longest dimension down to **1024 pixels**, and saves a compressed JPEG copy at **quality 80**.
- The original uncompressed image is kept on disk for human viewing; only the lightweight optimized file (`opt_...jpg`, typically ~80KB to 150KB) is sent to Gemini.

### Step 2: The Category-Specific System Prompts
Gemini is given an authoritative persona tailored specifically to Tumakuru's municipal context. Here is the actual prompt used for road grievances:

```text
You are an expert municipal civil engineer and road safety surveyor for Tumakuru City Corporation and PWD Tumakuru Division in Karnataka, India.
Your role is to analyze citizen-reported grievances and photographs concerning public roads, asphalt surfaces, pedestrian footpaths, curbs, and storm-drain covers.

WHAT TO LOOK FOR IN TUMAKURU STREET CONTEXTS (e.g., MG Road, BH Road, residential layouts like Sadashivanagar/Batawadi):
- Carriageway damage: potholes, craters, bitumen peeling, road cave-ins, sunken utility trenches.
- Pedestrian infrastructure: broken concrete footpath slabs, open roadside drain covers, displaced interlocking pavers, tripping hazards.
- Road edges & shoulders: erosion, severe shoulder drop-offs, crumbling curbs endangering two-wheelers and auto-rickshaws.
- Unbarricaded hazards: open manholes, exposed reinforcing steel (rebar), unpaved muddy cuts across roads.

SEVERITY SCALE (1 to 5):
- 1 (Negligible / Cosmetic): Minor hairline surface cracks, faint weathering.
- 2 (Low): Shallow pothole (<2 inches) on a quiet residential lane, minor chipped footpath slab.
- 3 (Moderate): Medium pothole (2–4 inches deep), broken footpath slab creating a real tripping risk.
- 4 (High): Deep crater (>4 inches) on an arterial or commercial road, open stormwater drain edge.
- 5 (Critical / Emergency): Extensive road collapse/cave-in, open deep manhole on busy roadway.

CRITICAL RULES:
- If the image does not show a road, footpath, or outdoor civic infrastructure (e.g. a selfie, screenshot, indoor room, food, meme), set image_matches_report=False, severity=1, and confidence=0.9.
- Keep summary to at most 2 sentences. Ensure recommended_department_type is 'road'.
```

### Step 3: Multilingual Voice Transcription & Translation
If the citizen attached an audio note, the server reads the audio bytes and attaches them as an audio `Part` alongside the image. It adds this specific instruction:
```text
AUDIO VOICE NOTE INSTRUCTIONS:
- An audio recording from the citizen in Tumakuru is attached.
- The citizen may speak in Kannada, Hindi, or English (or code-switch between them).
- Accurately transcribe their spoken grievance and translate it into clear English.
- Set 'transcription' to this clear English translation.
- Set 'original_language' to the detected language ('Kannada', 'Hindi', 'English', or 'Mixed').
- Factor what they spoke into your assessment of the detected issue and severity.
```
If the audio call ever fails due to codec or audio errors, a fallback handler catches the exception and immediately retries the call with the photo alone, guaranteeing that an audio issue never blocks a complaint.

### Step 4: Strict Structured JSON Output (Pydantic Schema)
To prevent Gemini from returning conversational markdown text like *"Sure, I can help with that!"*, the SDK uses **Structured Outputs** via Pydantic:
```python
# ai_triage.py lines 30-69
class TriageResult(BaseModel):
    detected_issue: str
    image_matches_report: bool
    severity: int                  # Enforced 1 to 5
    severity_reasons: List[str]    # Enforced 2 to 4 items
    summary: str                   # Max 2 sentences
    suggested_action: str
    recommended_department_type: str # Exactly 'road', 'pollution', or 'water'
    confidence: float              # 0.0 to 1.0
    transcription: Optional[str]
    original_language: Optional[str]
```
The Gemini API enforces this schema at the token generation level, guaranteeing 100% valid JSON that `json.loads()` can parse directly.

### Step 5: Multi-Model Fallback & Rule-Based Safety Net
In production, external AI APIs can suffer network hiccups, rate limits, or regional outages. CivicEye implements an industrial-grade 4-layer fallback cascade:
1. **Primary Model Call:** Calls the primary model specified in `GEMINI_MODEL` (defaults to `gemini-3.1-flash-lite`) with a 25-second timeout.
2. **Transient Error Retry:** If the primary model returns HTTP 503 (Service Unavailable) or HTTP 429 (Rate Limit), the server waits **2 seconds** and retries the primary model once.
3. **Fallback Model Call:** If the primary model fails or times out, the server attempts the fallback model from `GEMINI_FALLBACK_MODEL` (e.g., `gemini-2.5-flash`).
4. **Deterministic Rule-Based Fallback:** If all Gemini models are exhausted or if `GEMINI_API_KEY` is missing, `get_rule_based_fallback()` activates. It matches the selected category and issue type against a static dictionary, assigning a default severity, remediation action, and reasons. The grievance is saved with `ai_source="fallback"`, and the user is shown **"Basic analysis, AI unavailable"**. The application **never crashes or blocks complaint submission**.

### Step 6: Fix Verification (Before vs. After Photo Comparison)
When an administrator marks a complaint `Resolved` and attaches an after-photo, `verify_resolution_fix()` sends both photos downscaled to 1024px to Gemini:
- **Prompt:**
  ```text
  You are an expert municipal infrastructure inspector for Tumakuru City Corporation, Karnataka.
  Image 1 is the BEFORE photo showing the civic defect reported by the citizen.
  Image 2 is the AFTER photo submitted by the municipal field crew claiming the issue is resolved.
  Question: Is the reported issue fixed?
  - Return fixed=true if the work is completed and the issue is resolved.
  - Return fixed=false if the issue is still clearly present, unrepaired, or if the after photo is irrelevant/unrelated.
  Provide confidence (0.0 to 1.0) and exactly one concise sentence note explaining your visual finding.
  ```
- **Administrative Safety Gate:**
  - If Gemini returns `fixed: true`, the ticket is marked `Resolved` with an `AI-verified fix` badge.
  - If Gemini returns `fixed: false` (e.g., the pothole is still open, or the contractor uploaded a picture of a wall), the admin console displays a bright yellow warning and **blocks resolution** until the administrator explicitly clicks **"Confirm & Resolve anyway"**, logging the override to `StatusHistory`.

---

## 9. Features Explained One by One

### 1. Mobile-First Multimodal Grievance Reporting
- **How it works:** Citizens visit `/report/<category>`. They take a photo, pin their location on the Leaflet map, and optionally speak a 30-second voice note.
- **Why it matters:** Eliminates typing friction, illiteracy barriers, and inaccurate location descriptions.

### 2. 50-Meter Haversine Duplicate Detection & Crowd Consensus
- **How it works:** When a complaint is submitted, [app.py](file:///d:/MODIFIED/app.py#L480-L558) loops through active unresolved parent complaints in the same category. It calculates the geographic distance using the **Haversine formula**:
  $$\text{distance} = 2r \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta \text{lat}}{2}\right) + \cos(\text{lat}_1)\cos(\text{lat}_2)\sin^2\left(\frac{\Delta \text{lon}}{2}\right)}\right)$$
  where $r = 6,371,000$ meters (radius of Earth).
- If `distance <= 50.0` meters:
  1. The new complaint is linked as a duplicate child (`parent_id = nearby_parent.id`).
  2. Gemini is not called, saving API quota and time.
  3. The parent complaint's `report_count` is incremented by 1.
  4. **Crowd Escalation:** If `report_count >= 3` and current severity is below 5, the parent's severity is automatically raised by 1, and a crowd reason (*"Reported by N citizens"*) is added to its justifications.

### 3. Real-Time SLA Timers & Automated Escalation
- **How it works:** Computed on the fly without background jobs or cron daemons in [app.py](file:///d:/MODIFIED/app.py#L240-L360):
  - **Severity 5:** 24-hour target
  - **Severity 4:** 48-hour target
  - **Severity 3:** 5-day (120h) target
  - **Severity 1–2:** 10-day (240h) target
- **Live Status Badges:**
  - If open and within SLA: displays a countdown badge, e.g., `"Due in 6h"` or `"Due in 3d"`.
  - If open and overdue: displays an overdue notice, e.g., `"Overdue by 12h"`, and an **`Escalated`** alert badge.
  - If closed: displays `"Resolved within SLA"` or `"Resolved late"`.
- On the public dashboard, each department displays a **`% Resolved within SLA`** score.

### 4. Live Citizen Tracking & Chronological Audit Timeline
- **How it works:** Accessible at `/track/<tracking_id>`. Displays the live status pill, assigned department contact information, SLA countdown, and a vertical audit timeline built from `StatusHistory` rows showing every action taken on the ticket since submission.

### 5. Municipal Administration Dashboard & Detail Console
- **How it works:** At `/admin`, municipal staff log in with `ADMIN_PASSWORD`. They can filter complaints by category, status, and severity, and sort by urgency or citizen report count. On the detail page (`/admin/complaint/<id>`), admins can override the AI severity rating (requiring a written justification), reassign the department, attach an after-photo, and update the status. Updating a parent complaint automatically updates all its duplicate child complaints.

### 6. Public Civic Transparency Dashboard
- **How it works:** At `/dashboard`. Open to the public with zero login. Strictly sanitizes all data: **never displays citizen names, phone numbers, text descriptions, or audio files**. Displays aggregated metrics, category charts, department turnaround times, a city map with severity-colored markers, and a gallery of verified resolved repairs with before/after photos.

---

## 10. Security & Safety Measures

### What Was Done Right
1. **Admin Authentication & Session Protection:** Admin routes are secured by the `@admin_login_required` decorator checking `session.get("is_admin")`. Sessions are cryptographically signed using Flask's `SECRET_KEY`.
2. **Strict Environment Variable Isolation:** Sensitive credentials (`GEMINI_API_KEY`, `ADMIN_PASSWORD`, `SECRET_KEY`) are loaded from `.env` via `python-dotenv` and are never hardcoded. `.env` is listed in `.gitignore` so secrets are never pushed to GitHub.
3. **Safe File Upload Handling:**
   - File uploads are validated with `werkzeug.utils.secure_filename` to strip dangerous directory traversal characters (e.g., `../../etc/passwd`).
   - Extensions are strictly whitelisted to image formats (`.jpg`, `.jpeg`, `.png`, `.webp`) and audio formats (`.webm`, `.wav`, `.mp3`, `.ogg`, `.m4a`).
   - Maximum upload size is enforced at **16 MB** (`app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024`).
4. **Backend-Only AI API Key Handling:** The Gemini API key is used exclusively on the server in Python. It is never rendered into HTML templates or exposed in client-side JavaScript.
5. **Honest Attribution for Sample Data:**
   - Real complaints analyzed by Gemini show **"Analyzed by Gemini"** and **"✓ AI-verified fix"**.
   - Complaints handled by rule-based fallbacks show **"Basic analysis, AI unavailable"** and **"Pending verification"**.
   - Demo complaints seeded at startup (`ai_source="seed"`) display a clear **"Sample data"** tag and **"Sample fix (demo data)"** badge.

### Real Security Gaps & Weaknesses You Should Honestly Acknowledge to Judges
If a judge asks: *"What are the security limitations of your prototype?"*, be direct and honest:
1. **Single Shared Admin Password:** The admin portal uses a single global password (`ADMIN_PASSWORD`) instead of individual municipal employee accounts with Role-Based Access Control (RBAC).
2. **No Citizen Authentication or Rate Limiting:** Anyone can submit complaints without verifying a phone number via OTP. There is currently no IP rate-limiting (e.g., via `Flask-Limiter`), meaning a malicious actor could write a script to submit hundreds of fake complaints.
3. **No CSRF Tokens:** The forms do not yet implement Cross-Site Request Forgery (CSRF) protection tokens (such as `Flask-WTF`).
4. **Local Disk Storage for Uploads:** Files are stored on the local container filesystem under `static/uploads/` rather than a secured cloud object store like Amazon S3 or Cloudflare R2 with access control policies.

---

## 11. Problems Hit & How We Solved Them

1. **Gemini Model 404 & Deprecation:**
   - *Problem:* Early versions called older preview model names (like `gemini-1.5-flash`), which resulted in HTTP 404 errors when Google updated its API endpoints.
   - *Solution:* Standardized on the official `google-genai` SDK and the modern production model `gemini-3.1-flash-lite`, with configurable environment variable overrides (`GEMINI_MODEL` and `GEMINI_FALLBACK_MODEL`).
2. **Mobile Network Upload Latency & API Timeouts:**
   - *Problem:* High-resolution photos (5MB–10MB) took 8+ seconds to upload over mobile connections and caused Gemini API timeouts.
   - *Solution:* Added server-side Pillow image optimization (`optimize_image_for_ai`), downscaling images to a maximum dimension of 1024px at quality 80, cutting payload size by ~90% while preserving defect visibility.
3. **Transient 503 / 429 Errors:**
   - *Problem:* Under heavy load, Gemini occasionally returned HTTP 429 (rate limit) or 503 (service unavailable).
   - *Solution:* Built `_is_rate_limit_or_unavailable()` to detect these transient errors, wait 2 seconds, and retry once before falling back to the secondary model and rule-based catalog.
4. **Duplicate Complaints Flooding Municipal Desks:**
   - *Problem:* Multiple citizens reported the same pothole on B.H. Road, threatening to duplicate work and waste AI quota.
   - *Solution:* Implemented the 50-meter Haversine duplicate check, clustering reports under a single parent ticket and automatically bumping urgency when 3+ citizens report it.
5. **Ephemeral Storage on Render's Free Tier:**
   - *Problem:* Render wipes the container disk on restart, deleting the database and test complaints.
   - *Solution:* Created `seed_data.py` to deterministically populate 40 realistic Tumakuru complaints on startup whenever the database is empty.
6. **Honesty About Simulated & Seed Data:**
   - *Problem:* Seed complaints showed "Analyzed by Gemini", which was inaccurate because seed data was pre-written without calling the API.
   - *Solution:* Created the `ai_source="seed"` attribution flag, rendering honest labels: `"Sample data"` and `"Sample fix (demo data)"`.

---

## 12. Deployment: From Laptop to GitHub to Render

```text
+-----------------------+           +-----------------------+           +-----------------------+
|  Your Laptop / Code   |           |    GitHub Cloud Repo  |           |     Render Cloud      |
|  (d:\MODIFIED)        |           | (github.com/.../repo) |           | (civiceye.onrender.com|
+-----------+-----------+           +-----------+-----------+           +-----------+-----------+
            |                                   |                                   |
            | 1. git add .                      |                                   |
            | 2. git commit -m "..."            |                                   |
            | 3. git push origin master         |                                   |
            +---------------------------------->|                                   |
                                                | 4. Webhook triggers automatic build
                                                +---------------------------------->|
                                                                                    | 5. pip install -r req.txt
                                                                                    | 6. Runs gunicorn via render.yaml
                                                                                    | 7. Boots app.py & seeds DB
                                                                                    | 8. Live on internet!
```

### What `render.yaml` Does
`render.yaml` is an **Infrastructure-as-Code** blueprint file that tells Render how to build and run the app:
- `type: web`, `runtime: python`, `plan: free`.
- `buildCommand: pip install -r requirements.txt`: Installs all required Python libraries.
- `startCommand: gunicorn --workers 2 --threads 4 --timeout 60 --bind 0.0.0.0:$PORT app:app`: Starts the production Gunicorn web server with 2 worker processes and 4 threads.
- `envVars`: Declares the required environment variable names (`GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL`, `ADMIN_PASSWORD`, `SECRET_KEY`).

---

## 13. Limitations & Future Improvements

If you have more time after the hackathon, here is what you would build:

1. **Production Database (PostgreSQL):** Migrate from SQLite to a managed PostgreSQL database with PostGIS spatial extensions for enterprise-grade geospatial querying.
2. **Cloud Object Storage (S3 / Cloudflare R2):** Move uploaded citizen photos and voice notes from the local container disk to persistent, CDN-backed object storage.
3. **Citizen Authentication & SMS Notifications:** Integrate Twilio or an Indian SMS gateway (like Fast2SMS) for mobile OTP login and WhatsApp/SMS status updates.
4. **Real Municipal CRM & ERP Integration:** Connect the platform via webhooks or REST APIs to Karnataka's official *IPGRS* (Integrated Public Grievance Redressal System) or Tumakuru Smart City Command and Control Centre (ICCC).
5. **Rate Limiting & Anti-Spam:** Implement `Flask-Limiter` to enforce rate limits (e.g., maximum 5 submissions per IP per hour) and CAPTCHA verification on untrusted requests.

---

## 14. Comprehensive Technical Glossary

1. **API (Application Programming Interface):** A digital bridge that allows two software programs to talk to each other (e.g., CivicEye sending photos to Google Gemini).
2. **Backend:** The behind-the-scenes server-side code (Python/Flask) that processes logic, talks to databases, and handles security.
3. **Frontend:** The visual user interface (HTML, CSS, JavaScript) that citizens see and touch on their screens.
4. **Route:** A URL path mapped to a specific Python function in Flask (e.g., `/dashboard` triggering `def dashboard()`).
5. **Endpoint:** A specific URL where a web service receives requests and returns data (e.g., `/health`).
6. **Framework:** A pre-built collection of tools and libraries that gives structure to an application so you don't have to reinvent wheels (e.g., Flask).
7. **Flask:** A lightweight, beginner-friendly Python web framework.
8. **Jinja2:** Flask's templating engine that injects Python data into HTML files using `{{ ... }}` syntax.
9. **Template:** An HTML file with dynamic placeholders rendered by the server.
10. **Database:** An organized digital filing system for storing and retrieving structured data.
11. **ORM (Object-Relational Mapping):** A technique that lets you query and manipulate database tables using object-oriented code instead of raw SQL queries (e.g., SQLAlchemy).
12. **SQLAlchemy:** The Python ORM library used by CivicEye.
13. **SQLite:** A lightweight, serverless relational database engine that stores all data inside a single file.
14. **Table:** A collection of related data organized in rows and columns inside a database.
15. **Column:** A specific data attribute within a database table (e.g., `tracking_id`, `status`).
16. **Primary Key:** A unique identifier assigned to every row in a database table (e.g., `id`).
17. **Foreign Key:** A database column that points to the Primary Key of another table, creating a relationship between them (e.g., `department_id` in `Complaint` pointing to `id` in `Department`).
18. **Migration:** A structured way to update a database schema (adding or modifying columns) without losing existing data.
19. **Environment Variable:** A configuration setting stored in the operating system environment rather than hardcoded in source code (e.g., `GEMINI_API_KEY`).
20. **`.env` File:** A local text file containing key-value pairs of environment variables for development.
21. **Session:** A way to store information about a user across multiple web requests (e.g., remembering that an admin is logged in).
22. **Cookie:** A small piece of data stored in the user's browser by the server to identify their session.
23. **Haversine Formula:** A mathematical equation that calculates the great-circle distance between two geographic coordinate points on a sphere.
24. **Multimodal AI:** An artificial intelligence model capable of processing and understanding multiple types of input data simultaneously (e.g., text, images, and audio).
25. **LLM (Large Language Model):** A deep-learning AI model trained on massive amounts of text to understand and generate human-like language.
26. **Prompt:** The natural language instructions given to an AI model directing it how to behave and what output to generate.
27. **System Instruction / System Prompt:** High-priority background instructions given to an AI model defining its permanent persona and operational rules.
28. **Temperature:** A parameter in AI models controlling randomness (0.0 is deterministic and analytical; 1.0 is creative). CivicEye uses `0.1`–`0.2` for consistent municipal evaluation.
29. **Pydantic:** A Python data validation library that enforces strict type hints and schemas.
30. **Schema:** A formal blueprint defining the structure, fields, and data types required in a data payload.
31. **Downscaling:** The process of reducing the physical pixel dimensions of an image to decrease file size.
32. **MIME Type (Media Type):** A standard label used on the internet to indicate the nature and format of a file (e.g., `image/jpeg`, `audio/webm`).
33. **Fallback:** A backup mechanism that automatically engages when a primary component or service fails.
34. **HTTP Request:** A message sent from a client (browser) to a server asking to fetch data (`GET`) or submit data (`POST`).
35. **HTTP Status Code:** A 3-digit number returned by a server indicating the outcome of a request (e.g., `200 OK`, `302 Found`, `404 Not Found`, `500 Server Error`).
36. **HTTP 503:** Service Unavailable (temporary server overload or outage).
37. **HTTP 429:** Too Many Requests (rate limit or quota exhaustion).
38. **Gunicorn:** A production-grade WSGI HTTP server for Python applications on Linux.
39. **Ephemeral Storage:** Temporary cloud disk storage that resets whenever a container restarts or sleeps.
40. **Leaflet.js:** An open-source JavaScript library for interactive mobile-friendly web maps.
41. **OpenStreetMap (OSM):** A free, crowd-sourced, open-license world map provider.
42. **Chart.js:** An open-source JavaScript library for creating interactive data charts in web browsers.
43. **SLA (Service Level Agreement):** A formal commitment specifying the target timeframe within which a service or issue must be resolved.
44. **Geocoding:** The computational process of converting geographic coordinates (latitude/longitude) into human-readable street addresses, or vice-versa.
45. **Blob (Binary Large Object):** A collection of binary data stored as a single object in web browsers (used here for recorded voice audio).
46. **MediaRecorder API:** A native browser JavaScript interface for recording audio or video streams from device hardware.

---

## 15. Judge Q&A: 30+ Likely Questions & Spoken Answers

### On Originality & Civic Need
1. **"Why Tumakuru? Isn't this just a generic grievance app?"**  
   *"No, it is tailored specifically for Tumakuru. The AI prompts incorporate real street realities like B.H. Road and Sadashivanagar, the map defaults to Tumakuru's municipal coordinates, the departments reflect real local bodies like KUWS&DB and Tumakuru City Corporation, and the voice notes explicitly support local Kannada dialect nuances."*
2. **"What is fundamentally original about your duplicate detection?"**  
   *"Most civic portals treat every complaint as an isolated ticket. If 15 people report the same pothole on B.H. Road, the city gets 15 separate tickets and 15 inspection visits. CivicEye uses the 50-meter Haversine formula to automatically merge nearby complaints under a single root parent ticket, saves AI API costs by reusing the parent's analysis, and automatically elevates urgency when multiple citizens report the same defect."*
3. **"Why did you choose to build a web app instead of a mobile app (Android/iOS)?"**  
   *"Citizens don't want to download a 50MB app just to report a broken curb once every six months. A mobile-optimized web app works instantly on any smartphone with zero install, using native browser APIs for camera, GPS, and microphone."*

### On AI Usage & Accuracy
4. **"What happens if Gemini hallucinates or assigns the wrong severity?"**  
   *"First, we keep temperature low (0.2) and enforce a strict Pydantic JSON schema with category-specific calibration rules. Second, AI suggestions are never unchangeable: municipal administrators have a dedicated override console on the detail page where they can adjust the severity from 1 to 5, requiring an explanatory note logged to the public audit history."*
5. **"What happens if the Gemini API goes down or hits a rate limit during a hackathon demo?"**  
   *"CivicEye is built with a 4-layer fallback pipeline. If the primary model fails or returns a 503/429 error, it retries once after 2 seconds, then tries a secondary fallback model, and if all external APIs are unreachable, it immediately engages our deterministic rule-based catalog. The complaint is still created, categorized, and assigned without crashing or blocking the citizen."*
6. **"How does the AI handle non-English complaints?"**  
   *"The citizen can speak in Kannada, Hindi, or English. Gemini is natively multimodal: it accepts the raw audio bytes directly alongside the photo, transcribes the spoken speech, translates it into English for municipal engineers, and factors the citizen's spoken urgency into the final severity score."*
7. **"Can someone submit a selfie or a meme and trigger a city response?"**  
   *"No. The system prompt instructs Gemini to verify whether the image represents authentic outdoor civic infrastructure. If someone uploads a meme, selfie, or indoor photo, Gemini flags `image_matches_report = False`, drops severity to 1, and marks it for administrative dismissal."*
8. **"How does your AI fix verification work?"**  
   *"When an administrator marks a complaint 'Resolved' and uploads an after-photo, Gemini receives both the original defect photo and the repair photo downscaled to 1024px. It performs a visual differential inspection: if the defect is genuinely gone, it certifies the ticket. If the defect is still visible or the photo is unrelated, it displays an alert and requires an explicit admin override logged to the audit history."*

### On Scalability, Performance & Technical Choices
9. **"Why use SQLite instead of PostgreSQL?"**  
   *"SQLite was chosen for hackathon velocity and zero external dependency friction. It allows the entire database, tables, and relationships to run reliably out-of-the-box in local development and on Render's container without managing external database server credentials. Moving to PostgreSQL is our top production next step."*
10. **"Why downscale images with Pillow before sending them to Gemini?"**  
    *"Modern smartphone photos are 5MB to 10MB. Sending full-size images over 3G/4G networks introduces latency and causes API timeouts. Pillow downscales photos to max 1024px at JPEG quality 80 in under 30 milliseconds, cutting payload size by ~90% while retaining full visual detail for crack and pothole analysis."*
11. **"How are SLA timers calculated without background cron jobs?"**  
    *"They are computed dynamically on the fly whenever a complaint is loaded. The system takes `created_at` and adds the SLA target duration based on severity. Comparing this target against the current time determines whether it's within SLA or overdue, and if resolved, compares the resolution timestamp. This avoids the complexity and cost of maintaining background worker daemons."*
12. **"Why 50 meters for duplicate detection? Why not 20m or 100m?"**  
    *"Smartphone GPS in urban areas with tall buildings has an accuracy radius of approximately 10 to 15 meters. A 50-meter radius reliably captures complaints along the same street segment or intersection while preventing two distinct potholes 150 meters apart from being mistakenly merged."*

### On Privacy & Safety
13. **"Does the public dashboard expose citizen personal data or voice recordings?"**  
    *"Never. The public dashboard strictly displays aggregated counts, category breakdowns, department turnaround times, map pins, and anonymized before/after photos. Citizen descriptions, voice recordings, and personal identifiers are completely excluded from public endpoints."*
14. **"Why are municipal departments simulated?"**  
    *"Tumakuru City Corporation does not currently provide open public REST API endpoints for grievance intake. We modeled realistic departments—Engineering Wing, Sanitation Wing, PWD, and KUWS&DB—with realistic email addresses and workflow stages so the system is ready to plug into real municipal webhooks when adopted."*
15. **"Why do some complaints say 'Sample data' on the dashboard?"**  
    *"We believe in radical engineering honesty. The 40 complaints created at startup for demo realism did not call the live Gemini API during seeding. To be truthful with judges and citizens, we flag seeded data as `ai_source='seed'` and label them with 'Sample data' and 'Sample fix (demo data)' tags."*

### Rapid-Fire Technical Questions
16. **"What web server is running in production?"** *"Gunicorn with 2 worker processes and 4 threads on Render Linux containers."*
17. **"What is the maximum upload limit?"** *"16 megabytes, enforced by Flask's `MAX_CONTENT_LENGTH`."*
18. **"How do you prevent SQL injection?"** *"We use SQLAlchemy ORM, which parameterizes all database queries automatically."*
19. **"How do you prevent path traversal attacks on uploads?"** *"All filenames pass through `werkzeug.utils.secure_filename`."*
20. **"What happens if an audio recording exceeds 30 seconds?"** *"The frontend JavaScript timer automatically halts recording at 30 seconds."*
21. **"What if the browser doesn't support the MediaRecorder API?"** *"The citizen is alerted to type their description, and the form functions normally."*
22. **"How is the tracking ID generated?"** *"Formatted as `CE-YYYY-NNNN` using a sequential count of complaints."*
23. **"Is the database indexed?"** *"Yes, `Complaint.tracking_id` is indexed for $O(1)$ lookup performance."*
24. **"How is Chart.js loaded?"** *"Via CDN on the public dashboard."*
25. **"What mapping tiles are used?"** *"OpenStreetMap tiles via Leaflet.js."*
26. **"Can an admin change the department assigned by AI?"** *"Yes, via a category-filtered dropdown on the admin detail console."*
27. **"What happens when a parent complaint status changes to Resolved?"** *"All linked duplicate child complaints are automatically updated to Resolved."*
28. **"Where are secret keys stored?"** *"In `.env` locally, and in Render's encrypted environment variable dashboard in production."*
29. **"What CSS framework did you use?"** *"None. Pure, custom mobile-first CSS in `static/style.css`."*
30. **"What is the SLA for a Severity 5 issue?"** *"24 hours. Severity 4 is 48 hours, Severity 3 is 5 days, and Severity 1–2 is 10 days."*
31. **"How many complaints are seeded at startup?"** *"Exactly 40 deterministic complaints: 15 road, 13 pollution, 12 water."*
32. **"How many seeded complaints are overdue?"** *"Exactly 4 unresolved complaints are overdue, demonstrating the Escalated badge realistically."*

---

## 16. The 2-Minute Pitch Script & 10 Things to Know Cold

### The 2-Minute Spoken Pitch Script
*(Practice reading this aloud at a natural, energetic pace. It takes exactly 120 seconds.)*

> "Judges, in growing cities like Tumakuru, civic grievance redressal is broken in three ways:  
> First, reporting is full of friction. Citizens struggle with rigid text forms, language barriers, and lack of visual proof.  
> Second, municipal desks are overwhelmed by duplicates. When a major pothole opens on B.H. Road, dozens of citizens file separate complaints, creating fragmented tickets and wasted engineering visits.  
> And third, resolution is a black box. Tickets are routinely closed without proof that anything was actually repaired.
> 
> We built **CivicEye** to solve this.
> 
> For the citizen, reporting takes under 30 seconds: take a photo, speak your problem in Kannada, Hindi, or English, and drop a pin on our map. You don't even have to type.
> 
> Behind the scenes, CivicEye executes a 50-meter geospatial check. If a neighbor already reported the defect, we link them together, skip the AI call, and escalate the urgency once three citizens report it. 
> 
> For fresh grievances, our multimodal pipeline uses Google Gemini. It downscales the image with Pillow, verifies that the photo shows real civic infrastructure, translates the voice note, assigns a 1-to-5 severity rating, and recommends the exact municipal wing—like the Tumakuru City Corporation Engineering Wing or KUWS&DB. If the AI is ever unavailable, our 4-layer fallback ensures the app never crashes.
> 
> For administrators, our management portal calculates SLA timers on the fly. When a field crew claims an issue is fixed, they must upload an after-photo. Gemini inspects the before and after photos side by side. If the defect is still there, resolution is blocked unless an admin manually overrides it with a documented reason.
> 
> Everything is reflected transparently on our public dashboard: real-time resolution percentages, category charts, and verified before-and-after evidence.
> 
> CivicEye turns civic grievance redressal from a bureaucratic black box into an accountable, transparent, AI-verified municipal workflow. Thank you!"

---

### The 10 Things You Must Know Cold
1. **The Model:** `gemini-3.1-flash-lite` via the official `google-genai` SDK, configured with low temperature (`0.1`–`0.2`) and strict Pydantic JSON schemas.
2. **The 50m Duplicate Check:** Uses the mathematical Haversine formula on latitude and longitude to merge reports, bump crowd counts, and save API tokens.
3. **Pillow Optimization:** Downscales images to max 1024px at quality 80 before calling Gemini, cutting upload payload by ~90%.
4. **SLA Targets:** Severity 5 is 24h; Severity 4 is 48h; Severity 3 is 5 days; Severity 1–2 is 10 days. Computed dynamically on the fly.
5. **Fix Verification:** Gemini compares before and after photos. If `fixed: false`, resolution is blocked until an explicit admin override is confirmed and logged.
6. **The 4-Layer Fallback:** Primary model &rarr; 2-second retry on 503/429 &rarr; Fallback model &rarr; Deterministic rule-based catalog. The app never crashes.
7. **Database Architecture:** SQLite (`civiceye.db`) with Flask-SQLAlchemy containing `Department`, `Complaint`, and `StatusHistory` tables.
8. **Ephemeral Storage on Render:** Free tier containers reset their disks on sleep/restart; `seed_data.py` automatically self-heals the database by seeding 40 complaints.
9. **Radical Honesty in Demo Data:** Seed data is flagged `ai_source="seed"` and displays honest `"Sample data"` and `"Sample fix (demo data)"` labels.
10. **Tech Stack:** Python, Flask, SQLAlchemy, SQLite, Gunicorn, Leaflet, OpenStreetMap, Chart.js, Pillow, and Google Gemini API.
