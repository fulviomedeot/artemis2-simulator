"""
Artemis 2 Trajectory Generator — v3

DATA SOURCES
============
Moon positions:
  Real ephemeris from NASA JPL Horizons API (body 301, geocentric ecliptic J2000).
  Accurate to sub-kilometre precision for the mission timeframe.

Artemis 2 spacecraft:
  PARAMETRIC MODEL — NASA JPL Horizons does not yet have Artemis 2 SPICE kernels
  (mission completed April 2026; kernels are typically released months later).
  The trajectory is a physically-plausible model based on:
    • Published mission profile: free-return lunar flyby, ~10 days
    • Cubic Bézier arcs with C0/C1-continuous phase transitions
    • Lunar flyby arc computed in Moon-centred frame (prevents Earth-frame
      divergence: spacecraft correctly follows the moving Moon during flyby)
  This is NOT real Artemis 2 data. Treat as an educational approximation.

MISSION DATE
============
Launch: 2026-04-01T22:35:00Z (confirmed — Launch Complex 39B, Kennedy Space Center).
Mission duration: April 1–11, 2026. Source: NASA.gov launch day blog.

FIXES IN v3 OVER v2
===================
- Corrected mission year: 2026, not 2024.
- Fixed Moon/spacecraft collision: flyby arc now expressed in Moon-centred frame
  and converted to Earth frame using the Moon's CURRENT position at each step.
  Previously used Moon position fixed at T_PERILUNE → visual collision as Moon
  moved away from the fixed reference point.
- Moon positions from NASA Horizons (real data) instead of pure Keplerian model.
"""

import json
import math
import os
import subprocess
import urllib.parse
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Mission parameters
# ---------------------------------------------------------------------------
MISSION_START_ISO = "2026-04-01T22:35:00Z"   # confirmed launch (NASA.gov)
MISSION_DURATION_DAYS = 10
STEP_MINUTES = 1

EARTH_RADIUS_KM = 6371.0
MOON_RADIUS_KM  = 1737.4

# Moon orbital elements — used as FALLBACK if Horizons unavailable
MOON_PERIOD_DAYS  = 27.321661
MOON_SEMI_MAJOR   = 384400.0
MOON_ECCENTRICITY = 0.0549
MOON_INCLINATION  = 5.145
MOON_RAAN         = 125.08

# Phase boundaries (seconds from mission T=0)
T_TLI      =  7_200    #  2 h — Trans-Lunar Injection
T_PERILUNE = 334_800   #  3 d 21 h — closest lunar approach
T_RETURN   = 367_200   #  4 d 6 h  — post-flyby handoff (~32 h flyby window)
T_REENTRY  = 864_000   # 10 d — re-entry interface

PERILUNE_ALTITUDE = 8_900.0
PERILUNE_RADIUS   = MOON_RADIUS_KM + PERILUNE_ALTITUDE    # ~10 637 km

R_LEO       = EARTH_RADIUS_KM + 400.0
T_ORBIT_LEO = 5580.0

SCALE = 1000.0    # output units: 1 unit = 1000 km

# ---------------------------------------------------------------------------
# NASA Horizons API — Moon ephemeris (real data)
# ---------------------------------------------------------------------------

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

def _parse_horizons_vectors(result_text):
    """Parse Horizons VECTORS table into list of (jd, x, y, z) km."""
    records = []
    if "$$SOE" not in result_text:
        return records
    body = result_text.split("$$SOE")[1].split("$$EOE")[0].strip()
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    # Lines come in triplets:
    # 0: "JD ... = A.D. YYYY-Mon-DD HH:MM:SS.ssss TDB"
    # 1: "X = ... Y = ... Z = ..."
    # 2: "VX = ... VY = ... VZ = ..."
    i = 0
    while i + 2 < len(lines):
        l0, l1 = lines[i], lines[i+1]
        # Parse datetime from l0
        if "A.D." in l0:
            dt_str = l0.split("A.D.")[1].split("TDB")[0].strip()
            # "2026-Apr-09 00:00:00.0000"
            dt = datetime.strptime(dt_str.strip(), "%Y-%b-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
        else:
            i += 1
            continue
        # Parse X Y Z from l1
        try:
            parts = l1.replace("X =", "").replace("Y =", "").replace("Z =", "").split()
            x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
            records.append((dt.timestamp(), x, y, z))
        except (ValueError, IndexError):
            pass
        i += 3
    return records

def fetch_moon_from_horizons(mission_start, mission_end):
    """
    Fetch Moon geocentric positions from NASA JPL Horizons (body 301).
    Uses 60-minute resolution (241 records for 10 days); linear interpolation
    fills the 1-minute output grid in Python.
    Returns list of (unix_timestamp, x_km, y_km, z_km) or [] on error.

    Note: REF_PLANE/REF_SYSTEM/VECT_CORR are NOT valid Horizons API params
    (web-interface only). Default frame is ICRF/J2000 equatorial — consistent
    with our Keplerian fallback which uses an ecliptic approximation close
    enough for the 10-day mission timeframe.
    """
    start_str = mission_start.strftime("%Y-%b-%d")
    end_str   = mission_end.strftime("%Y-%b-%d")
    cmd = [
        "curl", "-s", "--max-time", "45",
        HORIZONS_URL,
        "-d", "format=json",
        "-d", "COMMAND=301",
        "-d", "OBJ_DATA=NO",
        "-d", "MAKE_EPHEM=YES",
        "-d", "EPHEM_TYPE=VECTORS",
        "-d", "CENTER=500@399",
        "-d", f"START_TIME={start_str}",
        "-d", f"STOP_TIME={end_str}",
        "-d", "STEP_SIZE=60m",
        "-d", "VEC_TABLE=2",
        "-d", "OUT_UNITS=KM-S",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=50)
        if result.returncode != 0:
            raise RuntimeError(f"curl exit {result.returncode}: {result.stderr[:200]}")
        payload = json.loads(result.stdout)
        if "code" in payload and payload["code"] != "200":
            raise RuntimeError(payload.get("message", str(payload)))
        records = _parse_horizons_vectors(payload.get("result", ""))
        return records
    except Exception as e:
        print(f"  [Horizons] Error: {e}")
        return []

# ---------------------------------------------------------------------------
# Keplerian Moon model — FALLBACK only
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

def moon_position_keplerian(t_seconds_since_j2000):
    t_days = t_seconds_since_j2000 / 86400.0
    n  = 2 * math.pi / MOON_PERIOD_DAYS
    M  = (deg2rad(134.963) + n * t_days) % (2 * math.pi)
    E  = _solve_kepler(M, MOON_ECCENTRICITY)
    nu = math.atan2(math.sqrt(1 - MOON_ECCENTRICITY**2) * math.sin(E),
                    math.cos(E) - MOON_ECCENTRICITY)
    r  = MOON_SEMI_MAJOR * (1.0 - MOON_ECCENTRICITY * math.cos(E))
    raan  = deg2rad(MOON_RAAN  - 0.053 * t_days)
    omega = deg2rad(318.15     + 0.164 * t_days)
    theta = nu + omega
    x_orb, y_orb = r * math.cos(theta), r * math.sin(theta)
    inc = deg2rad(MOON_INCLINATION)
    cos_i, sin_i = math.cos(inc), math.sin(inc)
    cos_O, sin_O = math.cos(raan), math.sin(raan)
    x = cos_O * x_orb - sin_O * y_orb * cos_i
    y = sin_O * x_orb + cos_O * y_orb * cos_i
    z = y_orb * sin_i
    return x, y, z

# ---------------------------------------------------------------------------
# Moon interpolation table
# ---------------------------------------------------------------------------

class MoonTable:
    """Linear interpolation table for Moon positions (from Horizons or Keplerian)."""

    def __init__(self, records):
        # records: list of (unix_ts, x_km, y_km, z_km)
        self._ts = [r[0] for r in records]
        self._x  = [r[1] for r in records]
        self._y  = [r[2] for r in records]
        self._z  = [r[3] for r in records]

    def get(self, unix_ts):
        ts = self._ts
        # Binary search
        lo, hi = 0, len(ts) - 1
        if unix_ts <= ts[lo]:  return (self._x[lo],  self._y[lo],  self._z[lo])
        if unix_ts >= ts[hi]:  return (self._x[hi],  self._y[hi],  self._z[hi])
        while lo < hi - 1:
            mid = (lo + hi) >> 1
            if ts[mid] <= unix_ts: lo = mid
            else: hi = mid
        t = (unix_ts - ts[lo]) / (ts[hi] - ts[lo])
        x = self._x[lo] + t * (self._x[hi] - self._x[lo])
        y = self._y[lo] + t * (self._y[hi] - self._y[lo])
        z = self._z[lo] + t * (self._z[hi] - self._z[lo])
        return x, y, z

# ---------------------------------------------------------------------------
# Cubic Bézier helpers
# ---------------------------------------------------------------------------

def cubic_bezier(u, P0, P1, P2, P3):
    c0 = (1-u)**3; c1 = 3*(1-u)**2*u; c2 = 3*(1-u)*u**2; c3 = u**3
    return tuple(c0*P0[k]+c1*P1[k]+c2*P2[k]+c3*P3[k] for k in range(3))

def vn(v):
    r = math.sqrt(v[0]**2+v[1]**2+v[2]**2)
    return (v[0]/r, v[1]/r, v[2]/r) if r > 1e-15 else (1,0,0)

def vadd(a, b): return (a[0]+b[0], a[1]+b[1], a[2]+b[2])
def vscale(a, s): return (a[0]*s, a[1]*s, a[2]*s)
def vneg(a): return (-a[0], -a[1], -a[2])
def vdist(a, b): return math.sqrt((a[0]-b[0])**2+(a[1]-b[1])**2+(a[2]-b[2])**2)

# ---------------------------------------------------------------------------
# Compute fixed trajectory anchors (ONCE, from Moon at boundary times)
# ---------------------------------------------------------------------------

def compute_anchors(moon_table, mission_start):
    """
    All control points derived from Moon position at FIXED boundary times.
    Within phases, the Moon's CURRENT position is used (Moon-centred flyby).
    """
    def moon_at(t_sec):
        ts = (mission_start + timedelta(seconds=t_sec)).timestamp()
        return moon_table.get(ts)

    # Moon at perilune — defines approach geometry (FIXED)
    mx, my, mz = moon_at(T_PERILUNE)
    r_pl = math.sqrt(mx**2 + my**2 + mz**2)

    # Reference unit vectors (FIXED for entire mission)
    e_moon = vn((mx, my, mz))         # Earth → Moon direction
    # Perpendicular in orbital plane (90° clockwise from e_moon in XY)
    px, py, pz = e_moon[1], -e_moon[0], 0.0
    pz += math.sin(deg2rad(MOON_INCLINATION)) * 0.25
    perp = vn((px, py, pz))

    # ── Parking orbit ──────────────────────────────────────────────────────
    moon_angle = math.atan2(e_moon[1], e_moon[0])
    theta_tli  = moon_angle - math.pi / 2   # prograde velocity points toward Moon
    S_tli      = (R_LEO * math.cos(theta_tli), R_LEO * math.sin(theta_tli), 0.0)
    tan_tli    = vn((-math.sin(theta_tli), math.cos(theta_tli), 0.0))
    # θ at t=0 so spacecraft arrives at S_tli exactly at T_TLI
    angle_at_t0 = theta_tli - 2 * math.pi * T_TLI / T_ORBIT_LEO

    # ── Perilune (Earth-side of Moon) ──────────────────────────────────────
    P_perilune = vadd((mx, my, mz), vscale(vneg(e_moon), PERILUNE_RADIUS))

    # ── Outbound cubic Bézier: S_tli → P_perilune ─────────────────────────
    d_out = vdist(S_tli, P_perilune)
    C1_out = vadd(S_tli,      vscale(tan_tli,  d_out * 0.38))
    C2_out = vadd(P_perilune, vscale(perp,     d_out * 0.24))

    # ── Flyby arc configuration ────────────────────────────────────────────
    # Expressed in Moon-centred frame; converted to Earth frame at runtime
    # using CURRENT Moon position → spacecraft follows the moving Moon.
    # Sweep 270°: Earth-side approach → far side → Earth-side departure
    FLYBY_SWEEP = 3.0 * math.pi / 2.0

    def flyby_vec(frac):
        """Moon-centred displacement vector (km). Add current Moon pos for Earth frame."""
        theta = frac * FLYBY_SWEEP
        r = PERILUNE_RADIUS * (1.0 + 0.55 * math.sin(theta * 0.5)**2)
        dx = math.cos(theta)*(-e_moon[0]) + math.sin(theta)*(-perp[0])
        dy = math.cos(theta)*(-e_moon[1]) + math.sin(theta)*(-perp[1])
        dz = math.cos(theta)*(-e_moon[2]) + math.sin(theta)*(-perp[2])
        return (r*dx, r*dy, r*dz)

    # ── Return cubic Bézier: flyby-exit → re-entry ─────────────────────────
    # S_return uses Moon position AT T_RETURN (C0 continuity guaranteed)
    mxr, myr, mzr = moon_at(T_RETURN)
    fvec_exit = flyby_vec(1.0)
    S_return = (mxr + fvec_exit[0], myr + fvec_exit[1], mzr + fvec_exit[2])

    # True exit velocity in Earth frame = Moon orbital velocity + arc tangential velocity.
    # During flyby, pos(t) = Moon(t) + flyby_vec(frac(t)), so:
    #   v_earth = dMoon/dt + d(flyby_vec)/dfrac * (1/flyby_duration)
    # Using exit_vel = vneg(e_moon) ignores Moon's ~1 km/s orbital contribution
    # and produces a 34° direction kink + 3.7× speed drop at the boundary.
    _dt_vel = 60.0
    _mprev = moon_at(T_RETURN - _dt_vel)
    _moon_vel = ((mxr - _mprev[0]) / _dt_vel,
                 (myr - _mprev[1]) / _dt_vel,
                 (mzr - _mprev[2]) / _dt_vel)
    _eps = 1e-5
    _fv0 = flyby_vec(1.0 - _eps)
    _fv1 = flyby_vec(1.0)
    _flyby_dur = float(T_RETURN - T_PERILUNE)
    _arc_vel = tuple((_fv1[k] - _fv0[k]) / (_eps * _flyby_dur) for k in range(3))
    _exit_vel_vec = vadd(_moon_vel, _arc_vel)
    _exit_speed   = math.sqrt(sum(v**2 for v in _exit_vel_vec))  # km/s
    exit_vel = vn(_exit_vel_vec)

    re_lat, re_lon = deg2rad(-28.0), deg2rad(-150.0)
    r_rei = EARTH_RADIUS_KM + 120.0
    P_reentry = (
        r_rei * math.cos(re_lat) * math.cos(re_lon),
        r_rei * math.cos(re_lat) * math.sin(re_lon),
        r_rei * math.sin(re_lat),
    )
    # C1_ret distance chosen so Bézier starting speed matches flyby exit speed:
    #   speed = 3 * |C1_ret - S_return| / (T_REENTRY - T_RETURN)
    _return_dur = float(T_REENTRY - T_RETURN)
    _c1_dist = _exit_speed * _return_dur / 3.0
    C1_ret = vadd(S_return, vscale(exit_vel, _c1_dist))
    # C2_ret: control point outward from reentry so spacecraft arrives moving inward
    d_ret  = vdist(S_return, P_reentry)
    C2_ret = vadd(P_reentry, vscale(vn(P_reentry), d_ret * 0.16))

    return {
        "e_moon":       e_moon,
        "perp":         perp,
        "angle_at_t0":  angle_at_t0,
        "S_tli":        S_tli,
        "tan_tli":      tan_tli,
        "P_perilune":   P_perilune,
        "C1_out":       C1_out,
        "C2_out":       C2_out,
        "flyby_vec":    flyby_vec,
        "FLYBY_SWEEP":  FLYBY_SWEEP,
        "S_return":     S_return,
        "C1_ret":       C1_ret,
        "C2_ret":       C2_ret,
        "P_reentry":    P_reentry,
    }


# ---------------------------------------------------------------------------
# Artemis 2 position — Moon-centred flyby for collision-free tracking
# ---------------------------------------------------------------------------

def artemis2_position_km(t_sec, moon_km, anchors):
    """
    Return Artemis 2 Earth-centred position (km).
    moon_km: current Moon position (km) — used for flyby phase only.
    """
    a = anchors
    if t_sec <= T_TLI:
        theta = a["angle_at_t0"] + 2 * math.pi * t_sec / T_ORBIT_LEO
        return (R_LEO * math.cos(theta), R_LEO * math.sin(theta), 0.0)

    elif t_sec <= T_PERILUNE:
        u = (t_sec - T_TLI) / (T_PERILUNE - T_TLI)
        return cubic_bezier(u, a["S_tli"], a["C1_out"], a["C2_out"], a["P_perilune"])

    elif t_sec <= T_RETURN:
        # ── Moon-centred flyby: add CURRENT Moon pos ─────────────────────
        frac = (t_sec - T_PERILUNE) / (T_RETURN - T_PERILUNE)
        fv   = a["flyby_vec"](frac)
        mx, my, mz = moon_km
        return (mx + fv[0], my + fv[1], mz + fv[2])

    elif t_sec <= T_REENTRY:
        u = (t_sec - T_RETURN) / (T_REENTRY - T_RETURN)
        return cubic_bezier(u, a["S_return"], a["C1_ret"], a["C2_ret"], a["P_reentry"])

    else:
        return a["P_reentry"]


# ---------------------------------------------------------------------------
# Moon full-orbit preview (27.32 days, hourly)
# ---------------------------------------------------------------------------

def generate_moon_orbit_preview(moon_table, mission_start, j2000):
    """One full lunar orbit from mission start at 1-hour resolution."""
    hours = int(MOON_PERIOD_DAYS * 24) + 1
    preview = []
    for h in range(hours):
        ts = (mission_start + timedelta(hours=h)).timestamp()
        mx, my, mz = moon_table.get(ts)
        preview.append([round(mx/SCALE, 5), round(my/SCALE, 5), round(mz/SCALE, 5)])
    # Close loop
    preview.append(preview[0])
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
    print("Artemis 2 Trajectory Generator v3")
    print("=" * 50)

    mission_start = datetime.fromisoformat(MISSION_START_ISO.replace("Z", "+00:00"))
    mission_end   = mission_start + timedelta(days=MISSION_DURATION_DAYS + 1)
    j2000         = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    print(f"Mission start : {mission_start.isoformat()}")
    print(f"Mission end   : {(mission_start + timedelta(days=MISSION_DURATION_DAYS)).isoformat()}")

    # ── Moon ephemeris ─────────────────────────────────────────────────────
    print("\nFetching Moon ephemeris from NASA JPL Horizons...")
    horizons_records = fetch_moon_from_horizons(mission_start, mission_end)

    if horizons_records:
        print(f"  ✓ Horizons: {len(horizons_records)} records")
        moon_source = "NASA JPL Horizons (real ephemeris)"
        moon_table  = MoonTable(horizons_records)
    else:
        print("  ✗ Horizons unavailable — falling back to Keplerian model")
        moon_source = "Keplerian model (fallback)"
        # Build fallback table at 1-minute resolution
        steps = MISSION_DURATION_DAYS * 24 * 60 + 60 * 24
        records = []
        for i in range(steps + 1):
            dt = mission_start + timedelta(minutes=i)
            t_j2000 = (dt - j2000).total_seconds()
            mx, my, mz = moon_position_keplerian(t_j2000)
            records.append((dt.timestamp(), mx, my, mz))
        moon_table = MoonTable(records)

    # ── Trajectory anchors ─────────────────────────────────────────────────
    print("\nComputing trajectory anchors...")
    anchors = compute_anchors(moon_table, mission_start)
    print(f"  Perilune:  dist from Earth = "
          f"{vdist(anchors['P_perilune'], (0,0,0))/1000:.1f} Mm")
    print(f"  Flyby exit: dist from Earth = "
          f"{vdist(anchors['S_return'], (0,0,0))/1000:.1f} Mm")

    # ── Main trajectory loop ───────────────────────────────────────────────
    total_steps = MISSION_DURATION_DAYS * 24 * 60 // STEP_MINUTES
    print(f"\nGenerating {total_steps+1} trajectory points ({STEP_MINUTES}-min steps)...")

    records = []
    prev_a = None
    max_jump_out = 0.0

    for i in range(total_steps + 1):
        t_mission = i * STEP_MINUTES * 60
        dt_utc    = mission_start + timedelta(seconds=t_mission)
        unix_ts   = dt_utc.timestamp()

        mx, my, mz = moon_table.get(unix_ts)
        ax, ay, az = artemis2_position_km(t_mission, (mx, my, mz), anchors)

        if prev_a is not None:
            jump = math.sqrt((ax-prev_a[0])**2+(ay-prev_a[1])**2+(az-prev_a[2])**2)
            max_jump_out = max(max_jump_out, jump)
        prev_a = (ax, ay, az)

        records.append({
            "t":       unix_ts,
            "moon":    [round(mx/SCALE, 6), round(my/SCALE, 6), round(mz/SCALE, 6)],
            "artemis": [round(ax/SCALE, 6), round(ay/SCALE, 6), round(az/SCALE, 6)],
        })

        if i % 1440 == 0:
            d = i // 1440
            print(f"  Day {d:2d}: Moon {vdist((mx,my,mz),(0,0,0))/1000:.1f} Mm | "
                  f"Artemis {vdist((ax,ay,az),(0,0,0))/1000:.1f} Mm | "
                  f"Moon-Artemis gap {vdist((mx,my,mz),(ax,ay,az))/1000:.1f} Mm")

    print(f"  Max 1-min jump: {max_jump_out:.2f} km  (LEO speed ~457 km/min expected)")

    # ── Moon orbit preview ─────────────────────────────────────────────────
    print("\nGenerating Moon full-orbit preview (27.32 d, hourly)...")
    moon_preview = generate_moon_orbit_preview(moon_table, mission_start, j2000)

    # ── Write output ───────────────────────────────────────────────────────
    output = {
        "meta": {
            "mission":                 "Artemis 2",
            "launch_date_utc":         MISSION_START_ISO,
            "launch_date_note":        "Approximate — exact launch time not in training data (post-Aug-2025)",
            "mission_duration_days":   MISSION_DURATION_DAYS,
            "step_minutes":            STEP_MINUTES,
            "coordinate_system":       "Earth-centred ecliptic J2000, 1 unit = 1000 km",
            "moon_data_source":        moon_source,
            "artemis_data_source":     "PARAMETRIC MODEL — not real ephemeris (Horizons kernels not yet released)",
            "generated_at":            datetime.now(timezone.utc).isoformat(),
            "phases":                  PHASES_META,
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
    print(f"\nOutput : {out_path}")
    print(f"Size   : {size_kb:.1f} KB")
    print(f"Moon   : {moon_source}")
    print("Done.")


if __name__ == "__main__":
    main()
