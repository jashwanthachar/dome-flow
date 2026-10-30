# DOME Flow

DOME Flow is a Flask-based traffic management demonstration for the NH-206 Gubbi–Tumakuru corridor, with a Bengaluru scenario for comparison. It provides a responsive dashboard for traffic incidents and analytics, plus two feature demonstrations:

- **Emergency preemption:** browser microphone frequency analysis, a synthetic siren fallback, queue-clearance timing, and a simulated green-wave update.
- **Road shock reporting:** phone motion input or a manual simulator, with a three-hit counter that creates a demo blackspot incident and work order.

This is a simulation. It does not connect to real traffic signals or municipal work-order systems. The backend stores demo state in memory, so state resets when the server process restarts.

## Run locally on Windows

From PowerShell in the project folder:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000> on the laptop. Keep the terminal running.

To open the same local server on a phone, connect both devices to the same Wi-Fi network, find the laptop's Wi-Fi IPv4 address with `ipconfig`, then open `http://LAPTOP-IP:5000` on the phone. Allow Python through Windows Firewall on the private network if prompted. Some phone browsers restrict motion sensors on plain HTTP; use the HTTPS Render deployment for sensor testing.

## Deploy to Render

The included `render.yaml` defines a Python web service. Push the project to GitHub, then in Render choose **New → Blueprint** and connect the repository. Render reads the blueprint, installs `requirements.txt`, and starts the Flask app with Gunicorn. Open the resulting HTTPS `onrender.com` URL on both devices.

The service is configured with one Gunicorn worker so requests share the same in-memory demo state. A service restart or redeploy resets that state. Microphone and motion sensor access still require browser permission; motion sensor availability varies by device and browser.

## Suggested feature demo

1. Open **S2 Edge AI & Preemption** and allow microphone access. Play a siren recording near the device, or use the synthetic siren fallback if the microphone is unavailable. The detector searches 500–1800 Hz and looks for repeated wail, yelp, or hi-lo patterns; it is still a demo detector, not a validated emergency-vehicle classifier.
2. Show the live queue and ETA calculation, then trigger the emergency green wave. The dashboard updates the target and downstream junctions and records an incident.
3. On the phone, enable the accelerometer and shake the phone firmly to submit qualifying motion events. For a predictable presentation, use **Simulate Commuter Pothole Shock** three times instead. The third qualifying request creates a demo incident and work order.
4. Show the resulting changes in Overview, Road Management, and Analytics.

The three-hit demonstration counts qualifying requests; it does not validate that hits came from three separate phones or a real-world spatial cluster.

## Project files

- `app.py` — Flask routes, demo state, queue-clearance calculation, and REST API.
- `templates/index.html` — dashboard markup.
- `static/app.js` — dashboard interactions, microphone analysis, phone motion handling, and API requests.
- `static/style.css` — dashboard styling and responsive phone layout.
- `requirements.txt` — Flask and Gunicorn dependencies.
- `render.yaml` — Render deployment configuration.

## Siren detector self-check

Open the app with `?dev=1` appended to its URL, go to **S2 Edge AI & Preemption**, and select **Run self-check**. Open the browser developer console to see PASS/FAIL results for the six generated signals. Stop the live microphone first. Test audio is generated and analyzed in the browser; no audio is sent to Flask.
