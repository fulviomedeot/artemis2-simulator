# Artemis 2 — 3D Space Simulator

An interactive 3D simulator of the NASA Artemis 2 mission. Navigate through space and watch the real trajectory of the Orion spacecraft as it flies around the Moon.

**Live Demo**: https://fulviomedeot.github.io/artemis2-simulator/

## Features

- **3D Navigation** — Orbit, pan, and zoom with the mouse
- **Real Orbital Mechanics** — Moon orbit and Artemis 2 trajectory from NASA ephemeris data
- **Time Control** — Play forward/backward at 1×, 2×, 5×, 10×, 30×, 50×, or 100× real time
- **Time Scrubber** — Jump to any moment of the mission
- **Object Labels** — Always-visible name tags for Earth, Moon, and Artemis II
- **Trail Mode** — Configurable trail length showing past trajectories
- **Camera Presets** — Overview, Follow Artemis, From Moon, From Earth

## Controls

| Action | Control |
|--------|---------|
| Orbit | Left-click + drag |
| Pan | Right-click + drag |
| Zoom | Scroll wheel |
| Play / Pause | Space bar or button |

## Running Locally

No installation required. Just serve the files over HTTP:

```bash
python3 -m http.server 8080
```

Then open [http://localhost:8080](http://localhost:8080) in your browser.

> **Note**: A local server is required (not `file://`) because ES modules need HTTP.

## Regenerating Trajectory Data

The Artemis 2 trajectory is pre-computed and stored in `data/artemis2_trajectory.json`. To regenerate it:

```bash
pip install -r requirements.txt
python3 scripts/generate_trajectory.py
```

## Project Structure

```
index.html                  ← App entry point
src/js/
  main.js                   ← Three.js scene and render loop
  simulation.js             ← Orbital mechanics and time engine
  objects.js                ← Earth, Moon, Artemis meshes
  labels.js                 ← 3D-anchored labels
  trails.js                 ← Trajectory trail rendering
  controls.js               ← UI panel
src/css/
  style.css                 ← Dark glass UI theme
data/
  artemis2_trajectory.json  ← Pre-computed trajectory (1-min resolution)
scripts/
  generate_trajectory.py    ← Trajectory data generator
```

## Data Sources & Accuracy

| Object | Source | Accuracy |
|--------|--------|---------|
| **Moon position** | NASA JPL Horizons real ephemeris (body 301) | Sub-km (real data) |
| **Artemis 2 trajectory** | Parametric model | Educational approximation |

**Moon positions** are fetched directly from NASA JPL Horizons and are accurate to the sub-kilometre level for the April 2026 mission window.

**Artemis 2 trajectory** is a parametric model based on the published mission profile (free-return lunar flyby, ~10 days). The real SPICE kernels for Artemis 2 are not yet available in JPL Horizons (typically released months after mission completion). The model reproduces the correct mission phases — LEO parking orbit, trans-lunar coast, lunar flyby, return coast — with physically plausible dynamics, but does not match the real trajectory precisely.

The spacecraft's flyby arc is computed in the Moon's reference frame and correctly tracks the Moon's motion, preventing visual collisions.

## About Artemis 2

Artemis 2 (April 2026) is NASA's first crewed lunar mission since Apollo 17 (1972). The Orion spacecraft with four astronauts — Reid Wiseman, Victor Glover, Christina Koch, and Jeremy Hansen — performed a free-return trajectory around the Moon, flying out to lunar distance, swinging around the far side, and returning to Earth in approximately 10 days.

## License

MIT License — see [LICENSE](LICENSE) for details.
