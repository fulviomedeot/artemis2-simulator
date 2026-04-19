/**
 * objects.js — 3D mesh creation for Earth, Moon, Artemis 2, starfield, and lighting.
 * Textures loaded from NASA/public CDN with procedural fallback.
 */

import * as THREE from "https://esm.sh/three@0.170.0";

// ── Scale constants (1 unit = 1000 km) ──────────────────────────────────
const EARTH_RADIUS  = 6.371;
const MOON_RADIUS   = 1.737;
const ARTEMIS_SCALE = 0.15;   // visual scale for the spacecraft

// ── Texture URLs ─────────────────────────────────────────────────────────
const TEX = {
  earthDay:    "https://cdn.jsdelivr.net/gh/mrdoob/three.js@r170/examples/textures/planets/earth_atmos_2048.jpg",
  earthNight:  "https://cdn.jsdelivr.net/gh/mrdoob/three.js@r170/examples/textures/planets/earth_lights_2048.png",
  earthBump:   "https://cdn.jsdelivr.net/gh/mrdoob/three.js@r170/examples/textures/planets/earth_normal_2048.jpg",
  earthSpec:   "https://cdn.jsdelivr.net/gh/mrdoob/three.js@r170/examples/textures/planets/earth_specular_2048.jpg",
  moonColor:   "https://cdn.jsdelivr.net/gh/mrdoob/three.js@r170/examples/textures/planets/moon_1024.jpg",
};

const loader = new THREE.TextureLoader();

function loadTex(url) {
  return new Promise(resolve => {
    loader.load(url, resolve, undefined, () => resolve(null));
  });
}

// ── Earth ────────────────────────────────────────────────────────────────
export async function createEarth() {
  const group = new THREE.Group();

  const [dayTex, bumpTex, specTex] = await Promise.all([
    loadTex(TEX.earthDay),
    loadTex(TEX.earthBump),
    loadTex(TEX.earthSpec),
  ]);

  const geo = new THREE.SphereGeometry(EARTH_RADIUS, 64, 64);
  const mat = new THREE.MeshPhongMaterial({
    map:         dayTex  || null,
    bumpMap:     bumpTex || null,
    bumpScale:   0.05,
    specularMap: specTex || null,
    specular:    new THREE.Color(0x333355),
    shininess:   25,
    color:       dayTex ? 0xffffff : 0x2255aa,
  });

  const mesh = new THREE.Mesh(geo, mat);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.rotation.x = THREE.MathUtils.degToRad(23.44);   // axial tilt
  group.add(mesh);

  // Atmosphere glow
  const atmoGeo = new THREE.SphereGeometry(EARTH_RADIUS * 1.025, 64, 64);
  const atmoMat = new THREE.MeshPhongMaterial({
    color:       0x4488ff,
    transparent: true,
    opacity:     0.12,
    side:        THREE.FrontSide,
    depthWrite:  false,
  });
  const atmosphere = new THREE.Mesh(atmoGeo, atmoMat);
  group.add(atmosphere);

  // Outer atmosphere halo
  const haloGeo = new THREE.SphereGeometry(EARTH_RADIUS * 1.07, 32, 32);
  const haloMat = new THREE.MeshPhongMaterial({
    color:       0x224488,
    transparent: true,
    opacity:     0.05,
    side:        THREE.BackSide,
    depthWrite:  false,
  });
  group.add(new THREE.Mesh(haloGeo, haloMat));

  return { group, mesh, atmosphere };
}

// ── Moon ─────────────────────────────────────────────────────────────────
export async function createMoon() {
  const group = new THREE.Group();

  const moonTex = await loadTex(TEX.moonColor);

  const geo = new THREE.SphereGeometry(MOON_RADIUS, 48, 48);
  const mat = new THREE.MeshPhongMaterial({
    map:       moonTex || null,
    color:     moonTex ? 0xffffff : 0x888888,
    shininess: 5,
    specular:  new THREE.Color(0x111111),
  });

  const mesh = new THREE.Mesh(geo, mat);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  group.add(mesh);

  return { group, mesh };
}

// ── Artemis 2 (Orion spacecraft) ─────────────────────────────────────────
export function createArtemis() {
  const group = new THREE.Group();
  const s = ARTEMIS_SCALE;

  // Capsule (crew module) — slightly flattened cone-cylinder
  const capsGeo = new THREE.CylinderGeometry(s * 0.5, s * 0.8, s * 1.2, 16);
  const capsMat = new THREE.MeshPhongMaterial({
    color:     0xcccccc,
    shininess: 80,
    specular:  new THREE.Color(0x999999),
  });
  const capsule = new THREE.Mesh(capsGeo, capsMat);
  capsule.position.y = s * 0.8;
  group.add(capsule);

  // Heat shield (bottom disc)
  const shieldGeo = new THREE.CylinderGeometry(s * 0.82, s * 0.82, s * 0.08, 16);
  const shieldMat = new THREE.MeshPhongMaterial({ color: 0x1a1a1a });
  const shield = new THREE.Mesh(shieldGeo, shieldMat);
  shield.position.y = s * 0.16;
  group.add(shield);

  // Service module (cylinder below)
  const smGeo = new THREE.CylinderGeometry(s * 0.55, s * 0.55, s * 1.2, 16);
  const smMat = new THREE.MeshPhongMaterial({ color: 0x888899, shininess: 40 });
  const sm = new THREE.Mesh(smGeo, smMat);
  sm.position.y = -s * 0.4;
  group.add(sm);

  // Solar panels (4 cross-shaped, flat boxes)
  const panelGeo = new THREE.BoxGeometry(s * 2.4, s * 0.04, s * 0.7);
  const panelMat = new THREE.MeshPhongMaterial({
    color:     0x223366,
    emissive:  new THREE.Color(0x112244),
    shininess: 60,
  });

  for (let i = 0; i < 4; i++) {
    const panel = new THREE.Mesh(panelGeo, panelMat);
    panel.position.set(0, -s * 0.4, 0);
    panel.rotation.y = (i * Math.PI) / 2;
    group.add(panel);
  }

  // Engine nozzle
  const nozGeo = new THREE.CylinderGeometry(s * 0.12, s * 0.22, s * 0.35, 12);
  const nozMat = new THREE.MeshPhongMaterial({ color: 0x555566 });
  const nozzle = new THREE.Mesh(nozGeo, nozMat);
  nozzle.position.y = -s * 1.08;
  group.add(nozzle);

  // Orange engine glow (when thrusting — always visible for aesthetics)
  const glowGeo = new THREE.SphereGeometry(s * 0.18, 8, 8);
  const glowMat = new THREE.MeshBasicMaterial({
    color:       0xff6600,
    transparent: true,
    opacity:     0.0,   // off by default, could animate during burns
  });
  group.add(new THREE.Mesh(glowGeo, glowMat));

  const mesh = capsule;  // primary mesh for rotation
  return { group, mesh };
}

// ── Starfield ────────────────────────────────────────────────────────────
export function createStarfield() {
  const count = 8000;
  const positions = new Float32Array(count * 3);
  const colors    = new Float32Array(count * 3);

  for (let i = 0; i < count; i++) {
    const phi   = Math.acos(2 * Math.random() - 1);
    const theta = 2 * Math.PI * Math.random();
    const r     = 8000 + Math.random() * 2000;

    positions[i * 3]     = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = r * Math.cos(phi);

    // Slight colour variation (blue-white to warm-white)
    const warm = Math.random();
    colors[i * 3]     = 0.85 + warm * 0.15;
    colors[i * 3 + 1] = 0.85 + warm * 0.10;
    colors[i * 3 + 2] = 0.90 + (1 - warm) * 0.10;
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geo.setAttribute("color",    new THREE.BufferAttribute(colors, 3));

  const mat = new THREE.PointsMaterial({
    size:         1.2,
    vertexColors: true,
    transparent:  true,
    opacity:      0.9,
    sizeAttenuation: true,
  });

  return new THREE.Points(geo, mat);
}

// ── Lighting ─────────────────────────────────────────────────────────────
export function createSunLight() {
  // Directional sun light (from roughly Sun direction)
  const sun = new THREE.DirectionalLight(0xfffde8, 2.2);
  sun.position.set(5000, 500, 2000);
  sun.castShadow = true;
  sun.shadow.mapSize.width  = 2048;
  sun.shadow.mapSize.height = 2048;
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far  = 20000;
  sun.shadow.camera.left   = -600;
  sun.shadow.camera.right  =  600;
  sun.shadow.camera.top    =  600;
  sun.shadow.camera.bottom = -600;

  // Ambient (space is dark but we need some fill)
  const ambient = new THREE.AmbientLight(0x101826, 0.8);

  return { sun, ambient };
}
