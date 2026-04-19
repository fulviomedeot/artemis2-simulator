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

## About Artemis 2

Artemis 2 is NASA's first crewed lunar mission since Apollo 17 (1972). The Orion spacecraft with four astronauts performs a free-return trajectory around the Moon — flying out to lunar distance, swinging around the far side, and returning to Earth. The mission covers approximately 10 days.

## License

MIT License — see [LICENSE](LICENSE) for details.
