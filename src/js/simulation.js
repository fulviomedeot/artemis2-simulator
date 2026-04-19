/**
 * simulation.js — Time engine, trajectory loading, and position interpolation.
 *
 * Coordinate system: Earth-centred, 1 unit = 1000 km
 * Time: Unix timestamps (seconds)
 */

import * as THREE from "https://esm.sh/three@0.170.0";

// ── Mission phase definitions (seconds from mission start) ───────────────
const PHASES = [
  { tStart: 0,       tEnd: 7_200,   label: "LEO Parking Orbit" },
  { tStart: 7_200,   tEnd: 345_600, label: "Trans-Lunar Coast" },
  { tStart: 345_600, tEnd: 518_400, label: "Lunar Flyby" },
  { tStart: 518_400, tEnd: 864_000, label: "Return Coast" },
  { tStart: 864_000, tEnd: Infinity, label: "Re-entry & Splashdown" },
];

export class Simulation {
  constructor() {
    this.trajectory = null;   // array of { t, moon:[x,y,z], artemis:[x,y,z] }
    this.meta       = null;
    this.currentIdx = 0;
    this.simTime    = 0;      // current Unix timestamp
    this.missionStart = 0;
    this.missionEnd   = 0;
    this.stepSeconds  = 60;   // resolution (matches generator)
  }

  async load() {
    const res = await fetch("data/artemis2_trajectory.json");
    if (!res.ok) throw new Error(`Failed to load trajectory: ${res.status}`);
    const data = await res.json();
    this.trajectory   = data.trajectory;
    // Store moon preview inside meta for convenient access in buildMoonOrbitLine()
    this.meta         = { ...data.meta, _moonPreview: data.moon_orbit_preview || [] };
    this.missionStart = this.trajectory[0].t;
    this.missionEnd   = this.trajectory[this.trajectory.length - 1].t;
    this.simTime      = this.missionStart;
    this.currentIdx   = 0;
  }

  // ── Time advance ─────────────────────────────────────────────────────
  advance(deltaReal, speedMultiplier = 1) {
    this.step(deltaReal * speedMultiplier);
  }

  step(deltaSeconds) {
    this.simTime = Math.max(
      this.missionStart,
      Math.min(this.missionEnd, this.simTime + deltaSeconds)
    );
    this._updateIdx();
  }

  seekToFraction(frac) {
    frac = Math.max(0, Math.min(1, frac));
    this.simTime = this.missionStart + frac * (this.missionEnd - this.missionStart);
    this._updateIdx();
  }

  _updateIdx() {
    // Binary search for the bracket index
    const traj = this.trajectory;
    let lo = 0, hi = traj.length - 1;
    while (lo < hi - 1) {
      const mid = (lo + hi) >> 1;
      if (traj[mid].t <= this.simTime) lo = mid; else hi = mid;
    }
    this.currentIdx = lo;
  }

  // ── Interpolated positions ───────────────────────────────────────────
  getPositions() {
    const traj = this.trajectory;
    const i    = this.currentIdx;
    const j    = Math.min(i + 1, traj.length - 1);
    const a    = traj[i];
    const b    = traj[j];

    const t = (b.t > a.t) ? (this.simTime - a.t) / (b.t - a.t) : 0;
    const u = smoothstep(t);

    return {
      moon:    lerp3(a.moon,    b.moon,    u),
      artemis: lerp3(a.artemis, b.artemis, u),
    };
  }

  // ── Current mission phase label ──────────────────────────────────────
  getMissionPhase() {
    const elapsed = this.simTime - this.missionStart;
    for (const ph of PHASES) {
      if (elapsed >= ph.tStart && elapsed < ph.tEnd) return ph.label;
    }
    return "Mission Complete";
  }

  // ── Formatted time strings ───────────────────────────────────────────
  getUTCString() {
    return new Date(this.simTime * 1000).toISOString().replace("T", " ").slice(0, 16) + " UTC";
  }

  getMissionDayString() {
    const elapsed = this.simTime - this.missionStart;
    const days    = Math.floor(elapsed / 86400);
    const hh      = Math.floor((elapsed % 86400) / 3600);
    const mm      = Math.floor((elapsed % 3600)  / 60);
    const pad = n => String(n).padStart(2, "0");
    return `Mission Day ${days} — T+${pad(hh)}:${pad(mm)}`;
  }

  getProgressFraction() {
    return (this.simTime - this.missionStart) / (this.missionEnd - this.missionStart);
  }

  getTotalSteps() {
    return this.trajectory ? this.trajectory.length - 1 : 14400;
  }

  // ── Artemis full-mission orbit preview line (from trajectory data) ──────
  buildArtemisOrbitLine() {
    const traj = this.trajectory;
    const points = [];
    const step = Math.max(1, Math.floor(traj.length / 800));
    for (let i = 0; i < traj.length; i += step) {
      const p = traj[i].artemis;
      points.push(new THREE.Vector3(p[0], p[1], p[2]));
    }
    // Close the loop back to last point
    const last = traj[traj.length - 1].artemis;
    points.push(new THREE.Vector3(last[0], last[1], last[2]));

    const geo = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({
      color:       0x994400,
      transparent: true,
      opacity:     0.28,
    });
    return new THREE.Line(geo, mat);
  }

  // ── Moon full-orbit preview line (from moon_orbit_preview in JSON) ───────
  // This is EXACTLY aligned with the Moon's simulated position because it uses
  // the same Keplerian model as the trajectory data.
  buildMoonOrbitLine() {
    const preview = this.meta._moonPreview;
    if (!preview || preview.length === 0) {
      // Fallback: build from 10-day trajectory arc
      return this._buildMoonArcFromTrajectory();
    }
    const points = preview.map(p => new THREE.Vector3(p[0], p[1], p[2]));
    // Close the orbit loop
    points.push(points[0].clone());

    const geo = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({
      color:       0x334466,
      transparent: true,
      opacity:     0.35,
    });
    return new THREE.Line(geo, mat);
  }

  _buildMoonArcFromTrajectory() {
    const traj = this.trajectory;
    const points = [];
    const step = Math.max(1, Math.floor(traj.length / 400));
    for (let i = 0; i < traj.length; i += step) {
      const p = traj[i].moon;
      points.push(new THREE.Vector3(p[0], p[1], p[2]));
    }
    const geo = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({
      color: 0x334466, transparent: true, opacity: 0.35,
    });
    return new THREE.Line(geo, mat);
  }
}

// ── Math helpers ─────────────────────────────────────────────────────────
function smoothstep(t) {
  return t * t * (3 - 2 * t);
}

function lerp3(a, b, t) {
  return new THREE.Vector3(
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
    a[2] + (b[2] - a[2]) * t
  );
}
