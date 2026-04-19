/**
 * controls.js — UI panel event handlers wired to the simulation state.
 */

export class Controls {
  constructor(state) {
    this.state = state;
    this.sim   = state.sim;

    // Expose state globally so simulation.js can read speedMultiplier
    window.__artemisState = state;

    this._bindAll();
    this.syncTimeDisplay();
    this.syncPlayButton();
  }

  _bindAll() {
    const s = this.state;
    const sim = this.sim;

    // ── Play / Pause ───────────────────────────────────────────────────
    document.getElementById("btn-play").addEventListener("click", () => {
      s.playing = !s.playing;
      this.syncPlayButton();
    });

    // ── Step buttons ───────────────────────────────────────────────────
    document.getElementById("btn-back").addEventListener("click", () => {
      sim.step(-60);
      s.trailMgr?.clearAll();
      this.syncTimeDisplay();
      this.syncScrubber();
    });

    document.getElementById("btn-forward").addEventListener("click", () => {
      sim.step(60);
      this.syncTimeDisplay();
      this.syncScrubber();
    });

    // ── Reset ──────────────────────────────────────────────────────────
    document.getElementById("btn-reset").addEventListener("click", () => {
      sim.seekToFraction(0);
      s.trailMgr?.clearAll();
      this.syncTimeDisplay();
      this.syncScrubber();
    });

    // ── Time scrubber ──────────────────────────────────────────────────
    const scrubber = document.getElementById("scrubber");
    scrubber.max = sim.getTotalSteps();
    scrubber.addEventListener("input", () => {
      sim.seekToFraction(scrubber.value / sim.getTotalSteps());
      s.trailMgr?.clearAll();
      this.syncTimeDisplay();
    });

    // ── Speed buttons ──────────────────────────────────────────────────
    document.querySelectorAll(".speed-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const speed = parseFloat(btn.dataset.speed);
        s.speedMultiplier = speed;
        document.querySelectorAll(".speed-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
      });
    });

    // ── Camera presets ─────────────────────────────────────────────────
    document.querySelectorAll(".cam-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        s.cameraMode = btn.dataset.cam;
        document.querySelectorAll(".cam-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");

        if (s.cameraMode === "overview") {
          s.orbitControls.target.set(0, 0, 0);
          s.orbitControls.object.position.set(0, 120, 500);
          s.orbitControls.update();
        }
      });
    });

    // ── Label toggle ───────────────────────────────────────────────────
    document.getElementById("toggle-labels").addEventListener("change", e => {
      s.labelsEnabled = e.target.checked;
    });

    // ── Trail toggle ───────────────────────────────────────────────────
    document.getElementById("toggle-trails").addEventListener("change", e => {
      s.trailsEnabled = e.target.checked;
      const trailSettings = document.getElementById("trail-settings");
      trailSettings.style.opacity       = s.trailsEnabled ? "1" : "0.4";
      trailSettings.style.pointerEvents = s.trailsEnabled ? "auto" : "none";
      if (!s.trailsEnabled) s.trailMgr?.clearAll();
    });

    // ── Atmosphere toggle ──────────────────────────────────────────────
    document.getElementById("toggle-atmosphere").addEventListener("change", e => {
      s.atmosphereEnabled = e.target.checked;
    });

    // ── Orbit paths toggle ─────────────────────────────────────────────
    document.getElementById("toggle-orbits").addEventListener("change", e => {
      s.orbitsEnabled = e.target.checked;
    });

    // ── Trail length sliders ───────────────────────────────────────────
    const trailArtemis = document.getElementById("trail-artemis");
    const trailMoon    = document.getElementById("trail-moon");
    const trailArtemisVal = document.getElementById("trail-artemis-val");
    const trailMoonVal    = document.getElementById("trail-moon-val");

    trailArtemis.addEventListener("input", () => {
      const h = Math.round(trailArtemis.value / 60);
      trailArtemisVal.textContent = h < 24 ? `${h} h` : `${(h/24).toFixed(1)} d`;
      s.trailMgr?.setMaxLength("artemis", parseInt(trailArtemis.value));
    });

    trailMoon.addEventListener("input", () => {
      const h = Math.round(trailMoon.value / 60);
      trailMoonVal.textContent = h < 24 ? `${h} h` : `${(h/24).toFixed(1)} d`;
      s.trailMgr?.setMaxLength("moon", parseInt(trailMoon.value));
    });
  }

  // ── Sync helpers ───────────────────────────────────────────────────────
  syncPlayButton() {
    const btn = document.getElementById("btn-play");
    btn.textContent = this.state.playing ? "⏸" : "▶";
    btn.title = this.state.playing ? "Pause (Space)" : "Play (Space)";
  }

  syncTimeDisplay() {
    const sim = this.sim;
    document.getElementById("time-display").textContent  = sim.getUTCString();
    document.getElementById("mission-day").textContent   = sim.getMissionDayString();
    document.getElementById("mission-phase").textContent = sim.getMissionPhase();
    this.syncScrubber();
  }

  syncScrubber() {
    const scrubber = document.getElementById("scrubber");
    scrubber.value = Math.round(this.sim.getProgressFraction() * this.sim.getTotalSteps());
  }
}
