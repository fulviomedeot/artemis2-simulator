/**
 * trails.js — Ring-buffer trail rendering.
 * Each tracked object gets a growing Line that shows its recent path.
 */

import * as THREE from "https://esm.sh/three@0.170.0";

const MAX_TRAIL_POINTS = 14401;  // max possible (entire mission at 1-min resolution)

export class TrailManager {
  constructor(scene) {
    this.scene  = scene;
    this.trails = new Map();
  }

  /**
   * Register a new trail.
   * @param {string} key        Unique identifier
   * @param {number} color      Hex color
   * @param {number} maxLength  Maximum trail length in trajectory steps
   */
  add(key, color, maxLength = 1440) {
    const positions = new Float32Array(MAX_TRAIL_POINTS * 3);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setDrawRange(0, 0);

    const mat = new THREE.LineBasicMaterial({
      color:       color,
      transparent: true,
      opacity:     0.7,
    });

    const line = new THREE.Line(geo, mat);
    line.frustumCulled = false;
    this.scene.add(line);

    this.trails.set(key, {
      line,
      positions,
      buffer:     [],
      maxLength,
      writeHead:  0,
      count:      0,
    });
  }

  /**
   * Push a new position to the trail.
   * @param {string} key
   * @param {THREE.Vector3|{x,y,z}} pos
   */
  push(key, pos) {
    const trail = this.trails.get(key);
    if (!trail) return;

    trail.buffer.push({ x: pos.x, y: pos.y, z: pos.z });

    // Trim to maxLength
    if (trail.buffer.length > trail.maxLength) {
      trail.buffer.shift();
    }
  }

  /** Rebuild geometry from current buffer. */
  update() {
    for (const [, trail] of this.trails) {
      const { buffer, positions, line } = trail;
      const n = buffer.length;
      for (let i = 0; i < n; i++) {
        const p = buffer[i];
        positions[i * 3]     = p.x;
        positions[i * 3 + 1] = p.y;
        positions[i * 3 + 2] = p.z;
      }
      line.geometry.attributes.position.needsUpdate = true;
      line.geometry.setDrawRange(0, n);
    }
  }

  /** Change the max trail length of a registered trail. */
  setMaxLength(key, maxLength) {
    const trail = this.trails.get(key);
    if (!trail) return;
    trail.maxLength = Math.max(1, Math.min(maxLength, MAX_TRAIL_POINTS));
    // Trim buffer if needed
    while (trail.buffer.length > trail.maxLength) {
      trail.buffer.shift();
    }
  }

  /** Clear all trail buffers (e.g. when jumping time). */
  clearAll() {
    for (const [, trail] of this.trails) {
      trail.buffer = [];
      trail.line.geometry.setDrawRange(0, 0);
      trail.line.geometry.attributes.position.needsUpdate = true;
    }
  }

  setVisible(key, visible) {
    const trail = this.trails.get(key);
    if (trail) trail.line.visible = visible;
  }
}
