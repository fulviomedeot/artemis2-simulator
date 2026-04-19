/**
 * main.js — Three.js scene setup and render loop
 */

import * as THREE from "https://esm.sh/three@0.170.0";
import { OrbitControls } from "https://esm.sh/three@0.170.0/addons/controls/OrbitControls.js";
import { CSS2DRenderer } from "https://esm.sh/three@0.170.0/addons/renderers/CSS2DRenderer.js";

import { createEarth, createMoon, createArtemis, createStarfield, createSunLight } from "./objects.js";
import { LabelManager } from "./labels.js";
import { TrailManager } from "./trails.js";
import { Simulation } from "./simulation.js";
import { Controls } from "./controls.js";

// ── Scene globals ────────────────────────────────────────────────────────
const container = document.getElementById("canvas-container");
const labelContainer = document.getElementById("label-renderer");

export const scene    = new THREE.Scene();
export const camera   = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.01, 100000);
export const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
export const css2d    = new CSS2DRenderer({ element: labelContainer });

// ── State shared across modules ──────────────────────────────────────────
export const state = {
  playing:      false,
  speedMultiplier: 1,
  cameraMode:   "overview",
  trailsEnabled: false,
  labelsEnabled: true,
  orbitsEnabled: true,
  atmosphereEnabled: true,
};

// ── Object references ────────────────────────────────────────────────────
let earth, moon, artemis, atmosphereMesh;
let moonOrbitLine, artemisOrbitLine;
let labelMgr, trailMgr, sim, controls;
let clock;

// ── Init ─────────────────────────────────────────────────────────────────
async function init() {
  // Renderer
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.9;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  container.appendChild(renderer.domElement);

  // CSS2D renderer
  css2d.setSize(window.innerWidth, window.innerHeight);
  css2d.domElement.style.position = "absolute";
  css2d.domElement.style.top = "0";
  css2d.domElement.style.pointerEvents = "none";

  // Camera
  camera.position.set(0, 120, 500);
  camera.lookAt(0, 0, 0);

  // Orbit controls
  const orbitCtrl = new OrbitControls(camera, renderer.domElement);
  orbitCtrl.enableDamping = true;
  orbitCtrl.dampingFactor = 0.06;
  orbitCtrl.minDistance = 10;
  orbitCtrl.maxDistance = 2000;
  orbitCtrl.target.set(0, 0, 0);
  state.orbitControls = orbitCtrl;

  // Lighting
  const { sun, ambient } = createSunLight();
  scene.add(sun, ambient);

  // Background starfield
  scene.add(createStarfield());

  // Earth
  const earthGroup = await createEarth();
  earth = earthGroup.mesh;
  atmosphereMesh = earthGroup.atmosphere;
  scene.add(earthGroup.group);

  // Moon
  const moonGroup = await createMoon();
  moon = moonGroup.mesh;
  scene.add(moonGroup.group);

  // Artemis
  const artemisGroup = createArtemis();
  artemis = artemisGroup.mesh;
  scene.add(artemisGroup.group);

  // Expose mesh refs
  state.earth    = earth;
  state.moon     = moon;
  state.artemis  = artemis;
  state.moonGroup    = moonGroup.group;
  state.artemisGroup = artemisGroup.group;
  state.earthGroup   = earthGroup.group;
  state.atmosphereMesh = atmosphereMesh;

  // Orbit path lines (static preview arcs)
  moonOrbitLine = buildMoonOrbitLine();
  artemisOrbitLine = null;  // built dynamically from trajectory
  scene.add(moonOrbitLine);

  // Simulation
  sim = new Simulation();
  await sim.load();
  state.sim = sim;

  // Artemis trajectory orbit line (from data)
  artemisOrbitLine = sim.buildOrbitLine();
  scene.add(artemisOrbitLine);
  state.artemisOrbitLine = artemisOrbitLine;
  state.moonOrbitLine    = moonOrbitLine;

  // Labels
  labelMgr = new LabelManager(scene, css2d);
  labelMgr.add(earthGroup.group,   "Earth",      "label-earth");
  labelMgr.add(moonGroup.group,    "Moon",       "label-moon");
  labelMgr.add(artemisGroup.group, "Artemis II", "label-artemis");
  state.labelMgr = labelMgr;

  // Trails
  trailMgr = new TrailManager(scene);
  trailMgr.add("moon",    0xc8d8e8, 720);
  trailMgr.add("artemis", 0xff8833, 1440);
  state.trailMgr = trailMgr;

  // UI controls
  controls = new Controls(state);

  // Clock
  clock = new THREE.Clock();

  // Hide loading overlay
  document.getElementById("loading").classList.add("hidden");

  // Keyboard shortcuts
  window.addEventListener("keydown", onKey);
  window.addEventListener("resize",  onResize);

  // Start
  animate();
}

// ── Moon orbit preview line ──────────────────────────────────────────────
function buildMoonOrbitLine() {
  const points = [];
  const segments = 256;
  // Average Moon orbit radius in sim units (1 unit = 1000 km)
  const r = 384.4;
  const inc = 5.145 * Math.PI / 180;
  for (let i = 0; i <= segments; i++) {
    const theta = (i / segments) * Math.PI * 2;
    points.push(new THREE.Vector3(
      r * Math.cos(theta),
      r * Math.sin(theta) * Math.cos(inc),
      r * Math.sin(theta) * Math.sin(inc)
    ));
  }
  const geo = new THREE.BufferGeometry().setFromPoints(points);
  const mat = new THREE.LineBasicMaterial({ color: 0x334466, transparent: true, opacity: 0.35 });
  return new THREE.Line(geo, mat);
}

// ── Animate ──────────────────────────────────────────────────────────────
function animate() {
  requestAnimationFrame(animate);
  const delta = clock.getDelta();

  state.orbitControls.update();

  // Advance simulation
  if (state.playing) {
    sim.advance(delta, state.speedMultiplier);
    controls.syncTimeDisplay();
    controls.syncScrubber();
  }

  // Update positions
  const sp = sim.getPositions();

  // Earth rotates
  earth.rotation.y += delta * (2 * Math.PI / 86400) * state.speedMultiplier * 0.05;

  // Moon
  state.moonGroup.position.set(sp.moon.x, sp.moon.y, sp.moon.z);
  moon.rotation.y += delta * (2 * Math.PI / (27.32 * 86400)) * 0.05;

  // Artemis
  state.artemisGroup.position.set(sp.artemis.x, sp.artemis.y, sp.artemis.z);
  artemis.rotation.y += delta * 0.2;

  // Camera tracking
  updateCamera(sp);

  // Trails
  if (state.trailsEnabled) {
    trailMgr.push("moon",    sp.moon);
    trailMgr.push("artemis", sp.artemis);
    trailMgr.update();
  }

  // Labels
  labelMgr.setVisible(state.labelsEnabled);

  // Atmosphere visibility
  if (atmosphereMesh) atmosphereMesh.visible = state.atmosphereEnabled;

  // Orbit lines visibility
  if (moonOrbitLine)    moonOrbitLine.visible    = state.orbitsEnabled;
  if (artemisOrbitLine) artemisOrbitLine.visible = state.orbitsEnabled;

  renderer.render(scene, camera);
  css2d.render(scene, camera);
}

// ── Camera tracking ──────────────────────────────────────────────────────
function updateCamera(sp) {
  const ctrl = state.orbitControls;
  if (state.cameraMode === "artemis") {
    ctrl.target.lerp(new THREE.Vector3(sp.artemis.x, sp.artemis.y, sp.artemis.z), 0.05);
  } else if (state.cameraMode === "moon") {
    ctrl.target.lerp(new THREE.Vector3(sp.moon.x, sp.moon.y, sp.moon.z), 0.05);
  } else if (state.cameraMode === "earth") {
    ctrl.target.set(0, 0, 0);
  }
  // "overview" → let user orbit freely
}

// ── Resize ───────────────────────────────────────────────────────────────
function onResize() {
  const w = window.innerWidth, h = window.innerHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
  css2d.setSize(w, h);
}

// ── Keyboard ─────────────────────────────────────────────────────────────
function onKey(e) {
  if (e.target.tagName === "INPUT") return;
  if (e.code === "Space") {
    e.preventDefault();
    state.playing = !state.playing;
    controls.syncPlayButton();
  }
  if (e.code === "ArrowLeft")  { sim.step(-60); controls.syncTimeDisplay(); }
  if (e.code === "ArrowRight") { sim.step(60);  controls.syncTimeDisplay(); }
}

// ── Bootstrap ────────────────────────────────────────────────────────────
init().catch(err => {
  console.error("Init failed:", err);
  document.querySelector(".loading-sub").textContent = "Error: " + err.message;
});
