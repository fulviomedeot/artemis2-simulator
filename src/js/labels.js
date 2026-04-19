/**
 * labels.js — CSS2DRenderer label management.
 * Attaches HTML name tags to 3D objects, always facing the camera.
 */

import { CSS2DObject } from "https://esm.sh/three@0.170.0/addons/renderers/CSS2DRenderer.js";

export class LabelManager {
  constructor(scene, renderer) {
    this.scene    = scene;
    this.renderer = renderer;
    this.labels   = [];
  }

  add(object3D, text, cssClass = "") {
    const div = document.createElement("div");
    div.className = `object-label ${cssClass}`;
    div.textContent = text;

    const label = new CSS2DObject(div);
    label.position.set(0, 0, 0);
    object3D.add(label);

    this.labels.push(label);
    return label;
  }

  setVisible(visible) {
    for (const lbl of this.labels) {
      lbl.element.style.display = visible ? "" : "none";
    }
  }
}
