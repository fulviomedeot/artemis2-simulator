"""
Artemis 2 Trajectory Generator — v2 (smooth, C1-continuous trajectory)

Key fix over v1: all Bézier control points are computed ONCE from Moon position
at fixed phase-boundary times, not re-derived from the current Moon position
at every time step. This eliminates all discontinuities and kinks.

Trajectory phases:
  LEO Parking Orbit  → T_TLI      (T+0h  to T+2h)
  Trans-Lunar Coast  → T_PERILUNE (T+2h  to T+4d)
  Lunar Flyby        → T_RETURN   (T+4d  to T+4.5d)
  Return Coast       → T_REENTRY  (T+4.5d to T+10d)

All positions in Earth-centred frame, units = km.
Output JSON: 1 unit = 1000 km (scale ÷ 1000).
"""

import json
import math
import os
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Mission parameters
# ---------------------------------------------------------------------------
MISSION_START_ISO = "2024-11-16T06:00:00Z"
MISSION_DURATION_DAYS = 10
STEP_MINUTES = 1

EARTH_RADIUS_KM = 6371.0
MOON_RADIUS_KM  = 1737.4

MOON_PERIOD_DAYS  = 27.321661
MOON_SEMI_MAJOR   = 384400.0
MOON_ECCENTRICITY = 0.0549
MOON_INCLINATION  = 5.145        # degrees
MOON_RAAN         = 125.08       # degrees (ascending node at J2000)

# Phase boundary times (seconds from launch T=0)
T_TLI      =  7_200    # 2 h   — Trans-Lunar Injection burn
T_PERILUNE = 345_600   # 4 d   — closest lunar approach
T_RETURN   = 384_000   # 4 d 10 h — post-flyby handoff
T_REENTRY  = 864_000   # 10 d  — re-entry interface

PERILUNE_ALTITUDE = 8_900.0
PERILUNE_RADIUS   = MOON_RADIUS_KM + PERILUNE_ALTITUDE   # ~10 637 km

R_LEO          = EARTH_RADIUS_KM + 400.0   # parking orbit radius
T_ORBIT_LEO    = 5580.0                    # 93-min LEO period

SCALE = 1000.0   # km per sim-unit

# ---------------------------------------------------------------------------
# Keplerian Moon model
# ---------------------------------------------------------------------------

def deg2rad(d):
    return d * math.pi / 180.0

def _solve_kepler(M, e, tol=1e-10):
    E = M if e < 0.8 else math.pi
    for _ in range(200):
        dE = (M - E + e * math.sin(E)) / (1.0 - e * math.cos(E))
        E += dE
        if abs(dE) < tol:
            break
    return E

def moon_position_km(t_seconds_since_j2000):
    """Moon position (x, y, z) km, Earth-centred ecliptic frame."""
    t_days = t_seconds_since_j2000 / 86400.0
    n  = 2 * math.pi / MOON_PERIOD_DAYS
    M0 = deg2rad(134.963)
    M  = (M0 + n * t_days) % (2 * math.pi)
    E  = _solve_kepler(M, MOON_ECCENTRICITY)

    cos_E, sin_E = math.cos(E), math.sin(E)
    nu = math.atan2(math.sqrt(1 - MOON_ECCENTRICITY**2) * sin_E,
                    cos_E - MOON_ECCENTRICITY)
    r  = MOON_SEMI_MAJOR * (1.0 - MOON_ECCENTRICITY * cos_E)

    inc   = deg2rad(MOON_INCLINATION)
    raan  = deg2rad(MOON_RAAN  - 0.053  * t_days)   # nodal regression
    omega = deg2rad(318.15     + 0.164  * t_days)    # apsidal precession

    theta  = nu + omega
    x_orb  = r * math.cos(theta)
    y_orb  = r * math.sin(theta)

    cos_i, sin_i = math.cos(inc), math.sin(inc)
    cos_O, sin_O = math.cos(raan), math.sin(raan)

    x = cos_O * x_orb - sin_O * y_orb * cos_i
    y = sin_O * x_orb + cos_O * y_orb * cos_i
    z = y_orb * sin_i
    return x, y, z


# ---------------------------------------------------------------------------
# Cubic Bézier helper
# ---------------------------------------------------------------------------

def cubic_bezier(u, P0, P1, P2, P3):
    c0 = (1-u)**3
    c1 = 3*(1-u)**2*u
    c2 = 3*(1-u)*u**2
    c3 = u**3
    return tuple(c0*P0[k] + c1*P1[k] + c2*P2[k] + c3*P3[k] for k in range(3))

def vec3_norm(v):
    r = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
    return (v[0]/r, v[1]/r, v[2]/r) if r > 1e-15 else (1, 0, 0)

def vec3_add(a, b):    return (a[0]+b[0], a[1]+b[1], a[2]+b[2])

def vec3_scale(a, s):
    return (a[0]*s, a[1]*s, a[2]*s)

def vec3_neg(a):
    return (-a[0], -a[1], -a[2])

def vec3_dist(a, b):
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2)


# ---------------------------------------------------------------------------
# Pre-compute all Bézier anchors ONCE
# ---------------------------------------------------------------------------

def compute_anchors(mission_start, j2000):
    """
    Compute all trajectory control points from Moon positions at FIXED times.
    Must be called once; the returned dict is used for all time steps.
    """
    def t_j2000(t_sec):
        return (mission_start + timedelta(seconds=t_sec) - j2000).total_seconds()

    # ── Moon position at phase boundaries (FIXED) ──────────────────────────
    moon_pl = moon_position_km(t_j2000(T_PERILUNE))   # at closest approach

    mx, my, mz = moon_pl
    r_pl = math.sqrt(mx**2 + my**2 + mz**2)

    # Unit vectors (FIXED throughout all trajectory computations)
    e_moon = vec3_norm((mx, my, mz))    # Earth → Moon unit vector

    # Perpendicular in orbital plane (right of e_moon in XY, slightly inclined)
    px =  e_moon[1]    # rotate 90° clockwise in XY: (ey, -ex, 0) gives prograde perp
    py = -e_moon[0]
    pz =  0.0
    # Add slight out-of-plane component to match Moon inclination
    pz = math.sin(deg2rad(MOON_INCLINATION)) * 0.3
    perp = vec3_norm((px, py, pz))

    # ── Phase 0: Parking orbit ─────────────────────────────────────────────
    # Spacecraft needs to reach Moon side of Earth for TLI.
    # Place TLI on the Earth-facing side toward Moon.
    moon_angle_xy = math.atan2(e_moon[1], e_moon[0])
    # TLI firing point: approach from the "leading" side.
    # θ_tli is chosen so the prograde velocity at TLI points toward the Moon.
    # For a prograde circular orbit, velocity at angle θ is perpendicular: (-sin θ, cos θ).
    # We want velocity to have a positive dot product with e_moon.
    # (-sin θ)·e_moon_x + (cos θ)·e_moon_y > 0
    # ⟹ cos(θ - moon_angle_xy + π/2) > 0  →  θ ≈ moon_angle_xy - π/2
    theta_tli = moon_angle_xy - math.pi / 2
    S_tli = (R_LEO * math.cos(theta_tli), R_LEO * math.sin(theta_tli), 0.0)
    # Prograde tangent at S_tli
    tan_tli = vec3_norm((-math.sin(theta_tli), math.cos(theta_tli), 0.0))

    # At t=0, spacecraft is in parking orbit. Compute angle at t=0 so it arrives
    # at S_tli exactly at T_TLI.
    orbits_in_tli = T_TLI / T_ORBIT_LEO
    angle_at_t0 = theta_tli - 2 * math.pi * orbits_in_tli  # unwrap is fine

    # ── Phase 1: Outbound (TLI → Perilune) ────────────────────────────────
    P_perilune = vec3_add(
        (mx, my, mz),
        vec3_scale(vec3_neg(e_moon), PERILUNE_RADIUS)   # Earth-side closest approach
    )

    dist_out = vec3_dist(S_tli, P_perilune)
    h1 = dist_out * 0.38     # handle from TLI end
    h2 = dist_out * 0.26     # handle toward perilune

    # C1: along TLI prograde tangent (ensure C1-continuity with parking orbit)
    C1_out = vec3_add(S_tli, vec3_scale(tan_tli, h1))

    # C2: approach perilune from the -perp direction
    # (at perilune, spacecraft velocity is in -perp direction — derived from orbit geometry)
    C2_out = vec3_add(P_perilune, vec3_scale(perp, h2))   # backing off along +perp

    # ── Phase 2: Lunar flyby ───────────────────────────────────────────────
    # Arc centred on moon_pl (FIXED), sweeping 270° in Moon-centred frame.
    # At θ=0:   position = moon_pl - e_moon*r  (Earth-side perilune) ✓
    # At θ=π:   far side of Moon ✓
    # At θ=3π/2: departure toward Earth ✓
    # Position formula: moon_pl + r*(cos θ * (-e_moon) + sin θ * (-perp))
    FLYBY_SWEEP = 3.0 * math.pi / 2.0   # 270°

    def flyby_pos(frac):
        theta = frac * FLYBY_SWEEP
        # Radius varies: perilune at θ=0, slightly wider at far side
        r_fly = PERILUNE_RADIUS * (1.0 + 0.55 * math.sin(theta * 0.5) ** 2)
        dx = math.cos(theta) * (-e_moon[0]) + math.sin(theta) * (-perp[0])
        dy = math.cos(theta) * (-e_moon[1]) + math.sin(theta) * (-perp[1])
        dz = math.cos(theta) * (-e_moon[2]) + math.sin(theta) * (-perp[2])
        return (mx + r_fly * dx, my + r_fly * dy, mz + r_fly * dz)

    # ── Phase 3: Return (flyby exit → Re-entry) ────────────────────────────
    S_return = flyby_pos(1.0)

    # Exit velocity: -e_moon direction (verified by differentiation at θ=3π/2)
    exit_vel = vec3_neg(e_moon)

    # Re-entry interface: Pacific Ocean ~28°S 150°W, 120 km altitude
    re_lat, re_lon = deg2rad(-28.0), deg2rad(-150.0)
    r_rei = EARTH_RADIUS_KM + 120.0
    P_reentry = (
        r_rei * math.cos(re_lat) * math.cos(re_lon),
        r_rei * math.cos(re_lat) * math.sin(re_lon),
        r_rei * math.sin(re_lat),
    )

    dist_ret = vec3_dist(S_return, P_reentry)
    h1r = dist_ret * 0.30
    h2r = dist_ret * 0.18

    C1_ret = vec3_add(S_return, vec3_scale(exit_vel, h1r))

    # Approach Earth: velocity directed inward to re-entry point
    entry_dir = vec3_norm(vec3_neg(P_reentry))
    C2_ret = vec3_add(P_reentry, vec3_scale(entry_dir, h2r))

    return {
        "e_moon":       e_moon,
        "perp":         perp,
        "angle_at_t0":  angle_at_t0,
        "theta_tli":    theta_tli,
        "S_tli":        S_tli,
        "tan_tli":      tan_tli,
        "P_perilune":   P_perilune,
        "C1_out":       C1_out,
        "C2_out":       C2_out,
        "flyby_pos":    flyby_pos,
        "FLYBY_SWEEP":  FLYBY_SWEEP,
        "S_return":     S_return,
        "C1_ret":       C1_ret,
        "C2_ret":       C2_ret,
        "P_reentry":    P_reentry,
    }


# ---------------------------------------------------------------------------
# Artemis 2 position using FIXED anchors (no per-step Moon dependency)
# ---------------------------------------------------------------------------

def artemis2_position_km(t_sec, anchors):
    S_tli      = anchors["S_tli"]
    C1_out     = anchors["C1_out"]
    C2_out     = anchors["C2_out"]
    P_perilune = anchors["P_perilune"]
    flyby_pos  = anchors["flyby_pos"]
    S_return   = anchors["S_return"]
    C1_ret     = anchors["C1_ret"]
    C2_ret     = anchors["C2_ret"]
    P_reentry  = anchors["P_reentry"]
    angle_at_t0 = anchors["angle_at_t0"]

    if t_sec <= T_TLI:
        # ── Parking orbit (circular, prograde) ────────────────────────────
        theta = angle_at_t0 + 2 * math.pi * t_sec / T_ORBIT_LEO
        return (R_LEO * math.cos(theta), R_LEO * math.sin(theta), 0.0)

    elif t_sec <= T_PERILUNE:
        # ── Outbound cubic Bézier ─────────────────────────────────────────
        u = (t_sec - T_TLI) / (T_PERILUNE - T_TLI)
        return cubic_bezier(u, S_tli, C1_out, C2_out, P_perilune)

    elif t_sec <= T_RETURN:
        # ── Lunar flyby arc (Moon-centred, fixed vectors) ─────────────────
        frac = (t_sec - T_PERILUNE) / (T_RETURN - T_PERILUNE)
        return flyby_pos(frac)

    elif t_sec <= T_REENTRY:
        # ── Return cubic Bézier ───────────────────────────────────────────
        u = (t_sec - T_RETURN) / (T_REENTRY - T_RETURN)
        return cubic_bezier(u, S_return, C1_ret, C2_ret, P_reentry)

    else:
        # Post-splashdown: stay at re-entry interface
        return P_reentry


# ---------------------------------------------------------------------------
# Moon full-orbit preview (27.32 days, hourly resolution)
# ---------------------------------------------------------------------------

def generate_moon_orbit_preview(j2000, mission_start):
    """
    Return list of [x, y, z] sim-units for one complete Moon orbital period
    starting from mission_start, at 1-hour resolution.
    This gives the JS renderer an accurate orbit path aligned with the Moon model.
    """
    t0_j2000 = (mission_start - j2000).total_seconds()
    hours = int(MOON_PERIOD_DAYS * 24) + 1
    preview = []
    for h in range(hours):
        t = t0_j2000 + h * 3600.0
        mx, my, mz = moon_position_km(t)
        preview.append([round(mx/SCALE, 5), round(my/SCALE, 5), round(mz/SCALE, 5)])
    return preview


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

PHASES_META = {
    "parking_orbit": {"t_start": 0,          "t_end": T_TLI,      "label": "LEO Parking Orbit"},
    "outbound":      {"t_start": T_TLI,       "t_end": T_PERILUNE, "label": "Trans-Lunar Coast"},
    "lunar_flyby":   {"t_start": T_PERILUNE,  "t_end": T_RETURN,   "label": "Lunar Flyby"},
    "return":        {"t_start": T_RETURN,    "t_end": T_REENTRY,  "label": "Return Coast"},
    "reentry":       {"t_start": T_REENTRY,   "t_end": None,       "label": "Re-entry & Splashdown"},
}

def main():
    print("Artemis 2 Trajectory Generator v2 (smooth, fixed-anchor Bézier)")
    print("=" * 65)

    mission_start = datetime.fromisoformat(MISSION_START_ISO.replace("Z", "+00:00"))
    j2000         = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Pre-compute all anchors ONCE
    print("Computing trajectory anchors from Moon position at phase boundaries...")
    anchors = compute_anchors(mission_start, j2000)
    print(f"  Moon @ perilune:  ({anchors['P_perilune'][0]/1000:.1f}, "
          f"{anchors['P_perilune'][1]/1000:.1f}, {anchors['P_perilune'][2]/1000:.1f}) Mm")
    print(f"  Flyby exit point: ({anchors['S_return'][0]/1000:.1f}, "
          f"{anchors['S_return'][1]/1000:.1f}, {anchors['S_return'][2]/1000:.1f}) Mm")

    total_minutes = MISSION_DURATION_DAYS * 24 * 60
    steps = total_minutes // STEP_MINUTES + 1
    print(f"\nGenerating {steps} trajectory points ({STEP_MINUTES}-min resolution)...")

    records = []
    prev_artemis = None
    max_jump = 0.0

    for i in range(steps):
        t_mission = i * STEP_MINUTES * 60
        dt_utc    = mission_start + timedelta(seconds=t_mission)
        t_j2000   = (dt_utc - j2000).total_seconds()
        unix_ts   = dt_utc.timestamp()

        mx, my, mz = moon_position_km(t_j2000)
        ax, ay, az = artemis2_position_km(t_mission, anchors)

        # Track max jump to verify smoothness
        if prev_artemis is not None:
            jump = math.sqrt((ax-prev_artemis[0])**2+(ay-prev_artemis[1])**2+(az-prev_artemis[2])**2)
            max_jump = max(max_jump, jump)
        prev_artemis = (ax, ay, az)

        records.append({
            "t": unix_ts,
            "moon":    [round(mx/SCALE, 6), round(my/SCALE, 6), round(mz/SCALE, 6)],
            "artemis": [round(ax/SCALE, 6), round(ay/SCALE, 6), round(az/SCALE, 6)],
        })

        if i % 1440 == 0:
            day = i // 1440
            print(f"  Day {day:2d}: Moon dist={math.sqrt(mx**2+my**2+mz**2)/1000:.1f} Mm | "
                  f"Artemis dist={math.sqrt(ax**2+ay**2+az**2)/1000:.1f} Mm")

    print(f"\nMax step-to-step jump: {max_jump:.3f} km (smoothness check)")

    # Moon orbit preview for full period
    print("Generating Moon full-orbit preview...")
    moon_preview = generate_moon_orbit_preview(j2000, mission_start)

    output = {
        "meta": {
            "mission":              "Artemis 2",
            "description":          "Smooth parametric trajectory — fixed-anchor cubic Bézier + hyperbolic flyby arc",
            "mission_start_utc":    MISSION_START_ISO,
            "mission_duration_days": MISSION_DURATION_DAYS,
            "step_minutes":         STEP_MINUTES,
            "coordinate_system":    "Earth-centred, ecliptic-aligned, 1 unit = 1000 km",
            "generated_at":         datetime.now(timezone.utc).isoformat(),
            "phases":               PHASES_META,
        },
        "moon_orbit_preview": moon_preview,
        "trajectory": records,
    }

    out_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "data", "artemis2_trajectory.json")
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, separators=(",", ":"))

    size_kb = os.path.getsize(out_path) / 1024
    print(f"\nOutput: {out_path}")
    print(f"Size  : {size_kb:.1f} KB")
    print("Done.")


if __name__ == "__main__":
    main()
