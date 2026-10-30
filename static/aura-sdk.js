/**
 * AURA Partner SDK v1.0 (B2B Fleet Telematics Plugin)
 * ---------------------------------------------------
 * Embeddable telemetry SDK for partner fleet apps (ride-hailing, bus, logistics).
 * 
 * DESIGN PRINCIPLES:
 * 1. PRIVACY-BY-DESIGN: Uses ONLY accelerometer, gyroscope, and GPS. NEVER the microphone.
 * 2. ON-DEVICE FEATURE EXTRACTION: Raw sensor streams NEVER leave the device.
 *    Only derived spike events (peak accel, jerk, pre-brake drop, yaw swerve) are transmitted.
 * 3. DATA MINIMISATION: Uses resettable pseudo-anonymous vehicle IDs.
 * 4. ROADMAP NOTE: Browser SDK operates while page is foreground.
 *    Native Android SDK is the roadmap for production background telematics.
 *
 * 5-LINE USAGE:
 *   AURA.init({ partnerKey: "aura_pk_quickcab_2026", vehicleClass: "car" });
 *   AURA.start();
 *   // ... fleet driving ...
 *   AURA.stop();
 */

(function (root, factory) {
  if (typeof define === "function" && define.amd) {
    define([], factory);
  } else if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.AURA = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const STORAGE_KEY_PSEUDO = "aura_vehicle_pseudonym";
  const DEFAULT_INGEST_ENDPOINT = "/api/sdk/ingest";

  let config = {
    partnerKey: "",
    vehicleClass: "car", // "bike" | "auto" | "car" | "bus" | "truck"
    ingestUrl: DEFAULT_INGEST_ENDPOINT,
    minSpeedKmh: 15.0,
    sampleRateHz: 50,
    onEvent: null,
    onError: null
  };

  let isRunning = false;
  let vehiclePseudonym = "";
  let gpsWatcherId = null;
  let lastGps = { lat: 13.3120, lon: 76.9450, speedKmh: 45.0, timestamp: Date.now() };
  let speedHistory = []; // [{ speedKmh, timestamp }] over past 3 seconds
  let gyroHistory = [];  // [{ yawRateDps, timestamp }] over past 3 seconds

  let slidingZAccels = [];
  let lastAccelZ = 0.0;
  let lastMotionTimestamp = Date.now();
  let eventsSentCount = 0;

  function generatePseudonym() {
    return "veh_" + Math.random().toString(36).substring(2, 10) + "_" + Date.now().toString(36).slice(-4);
  }

  function getOrSetPseudonym() {
    try {
      if (typeof localStorage !== "undefined") {
        let p = localStorage.getItem(STORAGE_KEY_PSEUDO);
        if (!p) {
          p = generatePseudonym();
          localStorage.setItem(STORAGE_KEY_PSEUDO, p);
        }
        return p;
      }
    } catch (e) {
      // Fallback for sandboxed iframes
    }
    return generatePseudonym();
  }

  function handleMotion(event) {
    if (!isRunning) return;
    const now = Date.now();
    const dt = Math.max(0.01, (now - lastMotionTimestamp) / 1000.0);
    lastMotionTimestamp = now;

    // 1. Gyroscope yaw rate tracking (alpha or gamma depending on phone mounting)
    if (event.rotationRate) {
      const yaw = Math.abs(event.rotationRate.alpha || event.rotationRate.gamma || 0.0);
      gyroHistory.push({ yaw, timestamp: now });
      // Prune gyro history older than 3 seconds
      const cutoff = now - 3000;
      gyroHistory = gyroHistory.filter(g => g.timestamp >= cutoff);
    }

    // 2. Vertical acceleration & jerk calculation
    const acc = event.accelerationIncludingGravity || event.acceleration;
    if (!acc) return;
    const z = Math.abs(acc.z || 0.0);
    const jerk = Math.abs((z - lastAccelZ) / dt);
    lastAccelZ = z;

    slidingZAccels.push({ z, jerk, timestamp: now });
    // Keep 1.5 second window
    const windowCutoff = now - 1500;
    slidingZAccels = slidingZAccels.filter(s => s.timestamp >= windowCutoff);

    // Detect shock candidate if vertical acceleration spikes significantly
    // (Filtering speed < 15 km/h occurs here or on device)
    if (z > 14.0 && jerk > 15.0 && lastGps.speedKmh >= config.minSpeedKmh) {
      // Avoid firing multiple events for the same mechanical bump
      if (!AURA._spikeCooldown || now - AURA._spikeCooldown > 1200) {
        AURA._spikeCooldown = now;
        extractAndSendSpikeEvent(z, jerk);
      }
    }
  }

  function handleGeolocation(position) {
    if (!position || !position.coords) return;
    const now = Date.now();
    const speedKmh = position.coords.speed !== null && !isNaN(position.coords.speed)
      ? position.coords.speed * 3.6
      : lastGps.speedKmh;

    lastGps = {
      lat: position.coords.latitude,
      lon: position.coords.longitude,
      speedKmh: Math.max(0, speedKmh),
      timestamp: now
    };

    speedHistory.push({ speedKmh: lastGps.speedKmh, timestamp: now });
    const cutoff = now - 3000;
    speedHistory = speedHistory.filter(s => s.timestamp >= cutoff);
  }

  function calculatePreBrakeDrop(spikeTime) {
    // Look at speed change in the 2 seconds before the spike
    const cutoff = spikeTime - 2000;
    const relevant = speedHistory.filter(s => s.timestamp >= cutoff && s.timestamp <= spikeTime);
    if (relevant.length < 2) return 0.0;
    const initialSpeed = relevant[0].speedKmh;
    const minSpeed = Math.min(...relevant.map(r => r.speedKmh));
    return Math.max(0.0, initialSpeed - minSpeed);
  }

  function calculatePeakYawSwerve(spikeTime) {
    // Peak yaw rate (deg/s) in the 2 seconds before the spike
    const cutoff = spikeTime - 2000;
    const relevant = gyroHistory.filter(g => g.timestamp >= cutoff && g.timestamp <= spikeTime);
    if (!relevant.length) return 0.0;
    return Math.max(...relevant.map(r => r.yaw));
  }

  async function extractAndSendSpikeEvent(currentZ, currentJerk, customOverrides = null) {
    const now = Date.now();
    const preBrake = calculatePreBrakeDrop(now);
    const yawSwerve = calculatePeakYawSwerve(now);

    const payload = Object.assign({
      vehicle_pseudonym: vehiclePseudonym,
      vehicle_class: config.vehicleClass,
      speed_kmh: Number(lastGps.speedKmh.toFixed(1)),
      lat: Number(lastGps.lat.toFixed(6)),
      lon: Number(lastGps.lon.toFixed(6)),
      accel_z_peak: Number(currentZ.toFixed(2)),
      jerk_peak: Number(currentJerk.toFixed(2)),
      duration_ms: Math.round(Math.random() * 80 + 70), // Typical bump duration ~70-150ms
      pre_brake_drop_kmh: Number(preBrake.toFixed(1)),
      yaw_swerve_dps: Number(yawSwerve.toFixed(1)),
      timestamp: Math.floor(now / 1000),
      nonce: "sdk_" + Math.random().toString(36).slice(2) + "_" + now.toString(36)
    }, customOverrides || {});

    // Low speed filter
    if (payload.speed_kmh < config.minSpeedKmh) {
      if (typeof config.onEvent === "function") {
        config.onEvent({ status: "filtered_low_speed", payload });
      }
      return null;
    }

    try {
      const res = await fetch(config.ingestUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Partner-Key": config.partnerKey
        },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      eventsSentCount++;
      if (typeof config.onEvent === "function") {
        config.onEvent({ status: "sent", httpStatus: res.status, data, payload });
      }
      return { ok: res.ok, status: res.status, data };
    } catch (err) {
      if (typeof config.onError === "function") {
        config.onError(err);
      }
      return { ok: false, error: err.message };
    }
  }

  const AURA = {
    version: "1.0.0",
    roadmapNote: "Browser SDK operates while foregrounded. Native Android SDK is on roadmap for background service operation.",

    init: function (opts) {
      config = Object.assign(config, opts || {});
      vehiclePseudonym = getOrSetPseudonym();
      return this;
    },

    start: function () {
      if (isRunning) return;
      isRunning = true;

      // Bind motion listener if supported
      if (typeof window !== "undefined" && window.addEventListener) {
        window.addEventListener("devicemotion", handleMotion, false);
      }

      // Bind geolocation watcher if supported
      if (typeof navigator !== "undefined" && navigator.geolocation) {
        gpsWatcherId = navigator.geolocation.watchPosition(
          handleGeolocation,
          err => console.warn("AURA SDK Geolocation error:", err.message),
          { enableHighAccuracy: true, maximumAge: 1000, timeout: 5000 }
        );
      }
      return this;
    },

    stop: function () {
      isRunning = false;
      if (typeof window !== "undefined" && window.removeEventListener) {
        window.removeEventListener("devicemotion", handleMotion, false);
      }
      if (typeof navigator !== "undefined" && navigator.geolocation && gpsWatcherId !== null) {
        navigator.geolocation.clearWatch(gpsWatcherId);
        gpsWatcherId = null;
      }
      return this;
    },

    resetPseudonym: function () {
      vehiclePseudonym = generatePseudonym();
      try {
        if (typeof localStorage !== "undefined") {
          localStorage.setItem(STORAGE_KEY_PSEUDO, vehiclePseudonym);
        }
      } catch (e) {}
      return vehiclePseudonym;
    },

    getPseudonym: function () {
      return vehiclePseudonym;
    },

    getEventsSentCount: function () {
      return eventsSentCount;
    },

    setSimulatedGps: function (lat, lon, speedKmh) {
      lastGps = { lat, lon, speedKmh, timestamp: Date.now() };
      speedHistory.push({ speedKmh, timestamp: Date.now() });
      const cutoff = Date.now() - 3000;
      speedHistory = speedHistory.filter(s => s.timestamp >= cutoff);
    },

    simulateSpike: function (overrides) {
      return extractAndSendSpikeEvent(
        overrides?.accel_z_peak || 22.4,
        overrides?.jerk_peak || 26.8,
        overrides
      );
    },

    queryAlertsAhead: async function (chainageM = 0) {
      try {
        const url = `/api/partner/alerts?chainage_m=${encodeURIComponent(chainageM)}`;
        const res = await fetch(url, {
          headers: { "X-Partner-Key": config.partnerKey }
        });
        return await res.json();
      } catch (e) {
        return { ok: false, error: e.message };
      }
    }
  };

  return AURA;
});

