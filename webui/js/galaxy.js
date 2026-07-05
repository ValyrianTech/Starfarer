// Builds the 3D galaxy from /galaxy data: stars, glow, phenomena, labels.

import * as THREE from "three";

const WORLD_SCALE = 0.4;
const GALAXY_CENTER_X = 600;
const GALAXY_CENTER_Y = 400;
const Z_JITTER = 26;

/** Map game-space (x, y) plus a deterministic vertical jitter to world space. */
export function systemToWorld(sys) {
  return new THREE.Vector3(
    (sys.x - GALAXY_CENTER_X) * WORLD_SCALE,
    (hashString(sys.id) * 2 - 1) * Z_JITTER,
    (sys.y - GALAXY_CENTER_Y) * WORLD_SCALE,
  );
}

function hashString(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 10000) / 10000;
}

/** Radial-gradient glow texture generated on a canvas (avoids bloom pipeline). */
function makeGlowTexture(inner = "rgba(255,255,255,1)") {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  const grad = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0, inner);
  grad.addColorStop(0.25, "rgba(255,255,255,0.45)");
  grad.addColorStop(0.6, "rgba(255,255,255,0.08)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, size, size);
  return new THREE.CanvasTexture(canvas);
}

export function makeLabelSprite(text, color = "#cdd8f5") {
  const pad = 8;
  const fontSize = 26;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  ctx.font = `${fontSize}px "Segoe UI", sans-serif`;
  canvas.width = Math.ceil(ctx.measureText(text).width) + pad * 2;
  canvas.height = fontSize + pad * 2;
  const ctx2 = canvas.getContext("2d");
  ctx2.font = `${fontSize}px "Segoe UI", sans-serif`;
  ctx2.fillStyle = color;
  ctx2.textBaseline = "middle";
  ctx2.fillText(text, pad, canvas.height / 2);
  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
  });
  const sprite = new THREE.Sprite(material);
  const scale = 0.09;
  sprite.scale.set(canvas.width * scale, canvas.height * scale, 1);
  return sprite;
}

export class Galaxy {
  constructor(scene) {
    this.scene = scene;
    this.group = new THREE.Group();
    this.scene.add(this.group);
    this.glowTexture = makeGlowTexture();
    this.stars = new Map(); // system id -> star record
    this.pulsing = [];
  }

  build(galaxyData) {
    // Clear previous build (used on full refresh).
    this.group.clear();
    this.stars.clear();
    this.pulsing = [];

    for (const sys of galaxyData.systems) {
      this._buildSystem(sys);
    }
  }

  _buildSystem(sys) {
    const pos = systemToWorld(sys);
    const color = new THREE.Color(sys.star_color || "#ffffff");
    const node = new THREE.Group();
    node.position.copy(pos);

    // Core star sphere.
    const core = new THREE.Mesh(
      new THREE.SphereGeometry(1.6, 16, 16),
      new THREE.MeshBasicMaterial({ color }),
    );
    node.add(core);

    // Additive glow sprite.
    const glowMat = new THREE.SpriteMaterial({
      map: this.glowTexture,
      color,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const glow = new THREE.Sprite(glowMat);
    glow.scale.setScalar(14);
    node.add(glow);

    // Name label above the star.
    const label = makeLabelSprite(sys.name);
    label.position.y = 6.5;
    node.add(label);

    // Body count sub-label, revealed once the system is scanned or visited.
    let subLabel = null;
    if (sys.body_count > 0) {
      subLabel = makeLabelSprite(`${sys.body_count} ${sys.body_count === 1 ? "body" : "bodies"}`, "#6b7a9e");
      subLabel.scale.multiplyScalar(0.75);
      subLabel.position.y = 4.6;
      node.add(subLabel);
    }

    // Trading station marker, revealed once known.
    let station = null;
    if (sys.has_trading_station) {
      station = new THREE.Mesh(
        new THREE.OctahedronGeometry(0.7),
        new THREE.MeshBasicMaterial({ color: 0xffb347, wireframe: true }),
      );
      station.position.set(3.2, 2.2, 0);
      node.add(station);
      this.pulsing.push({ spinner: station, speed: 0.9 });
    }

    this._addPhenomenon(node, sys, color);

    // Invisible, oversized sphere so clicks don't need pixel precision.
    const pick = new THREE.Mesh(
      new THREE.SphereGeometry(4.5, 8, 8),
      new THREE.MeshBasicMaterial({ visible: false }),
    );
    pick.userData.systemId = sys.id;
    node.add(pick);

    const record = { sys, node, core, glow, glowMat, label, subLabel, station, pick, ring: null };
    this._applyKnowledgeStyle(record);
    this.stars.set(sys.id, record);
    this.group.add(node);
  }

  _addPhenomenon(node, sys, color) {
    switch (sys.phenomenon) {
      case "nebula": {
        const nebulaColors = [0x9b5cff, 0x5c7fff, 0xd45cff];
        for (let i = 0; i < 3; i++) {
          const mat = new THREE.SpriteMaterial({
            map: this.glowTexture,
            color: nebulaColors[i % nebulaColors.length],
            transparent: true,
            opacity: 0.12,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
          });
          const cloud = new THREE.Sprite(mat);
          cloud.scale.setScalar(34 + i * 12);
          cloud.position.set((i - 1) * 6, (i % 2) * 4 - 2, (i - 1) * 4);
          node.add(cloud);
        }
        break;
      }
      case "pulsar": {
        const beacon = new THREE.Sprite(new THREE.SpriteMaterial({
          map: this.glowTexture,
          color: 0xaad4ff,
          transparent: true,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        }));
        beacon.scale.setScalar(18);
        node.add(beacon);
        this.pulsing.push({ sprite: beacon, speed: 6, base: 18, amp: 9 });
        break;
      }
      case "binary_star": {
        const companion = new THREE.Mesh(
          new THREE.SphereGeometry(1.0, 12, 12),
          new THREE.MeshBasicMaterial({ color: color.clone().offsetHSL(0.08, 0, 0.1) }),
        );
        companion.position.set(4, 0.5, 0);
        node.add(companion);
        this.pulsing.push({ orbiter: companion, radius: 4, speed: 0.8 });
        break;
      }
      case "black_hole": {
        const hole = new THREE.Mesh(
          new THREE.SphereGeometry(2.2, 24, 24),
          new THREE.MeshBasicMaterial({ color: 0x000000 }),
        );
        node.add(hole);
        const disk = new THREE.Mesh(
          new THREE.TorusGeometry(4.2, 0.5, 8, 48),
          new THREE.MeshBasicMaterial({
            color: 0xff8c42,
            transparent: true,
            opacity: 0.75,
            blending: THREE.AdditiveBlending,
          }),
        );
        disk.rotation.x = Math.PI / 2.4;
        node.add(disk);
        this.pulsing.push({ spinner: disk, speed: 1.6 });
        break;
      }
      case "asteroid_field": {
        const count = 26;
        const positions = new Float32Array(count * 3);
        for (let i = 0; i < count; i++) {
          const angle = (i / count) * Math.PI * 2;
          const r = 7 + (i % 4);
          positions[i * 3] = Math.cos(angle) * r;
          positions[i * 3 + 1] = ((i * 37) % 7) - 3;
          positions[i * 3 + 2] = Math.sin(angle) * r;
        }
        const geo = new THREE.BufferGeometry();
        geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        const belt = new THREE.Points(geo, new THREE.PointsMaterial({
          color: 0x9a8f7f,
          size: 0.9,
          transparent: true,
          opacity: 0.8,
        }));
        node.add(belt);
        this.pulsing.push({ spinner: belt, speed: 0.15 });
        break;
      }
      case "ancient_gate": {
        const gate = new THREE.Mesh(
          new THREE.TorusGeometry(5, 0.35, 8, 40),
          new THREE.MeshBasicMaterial({
            color: 0x7ee8a2,
            transparent: true,
            opacity: 0.85,
            blending: THREE.AdditiveBlending,
          }),
        );
        node.add(gate);
        this.pulsing.push({ spinner: gate, speed: 0.5, tumble: true });
        break;
      }
    }
  }

  _applyKnowledgeStyle(record) {
    const { core, glowMat, label, subLabel, station, sys } = record;
    const baseColor = new THREE.Color(sys.star_color || "#ffffff");
    if (sys.visited) {
      core.material.color.copy(baseColor);
      glowMat.opacity = 0.95;
      record.glow.scale.setScalar(14);
      label.material.opacity = 0.9;
    } else if (sys.scanned) {
      core.material.color.copy(baseColor.clone().multiplyScalar(0.65));
      glowMat.opacity = 0.55;
      record.glow.scale.setScalar(11);
      label.material.opacity = 0.55;
    } else {
      core.material.color.copy(baseColor.clone().multiplyScalar(0.35));
      glowMat.opacity = 0.28;
      record.glow.scale.setScalar(9);
      label.material.opacity = 0.22;
    }
    // Details are only revealed once the system is scanned or visited.
    const known = sys.visited || sys.scanned;
    if (subLabel) {
      subLabel.visible = known;
      subLabel.material.opacity = sys.visited ? 0.65 : 0.4;
    }
    if (station) station.visible = known;
  }

  markVisited(systemId) {
    const record = this.stars.get(systemId);
    if (record && !record.sys.visited) {
      record.sys.visited = true;
      this._applyKnowledgeStyle(record);
    }
  }

  getPosition(systemId) {
    const record = this.stars.get(systemId);
    return record ? record.node.position.clone() : null;
  }

  /** Meshes to raycast against for click-to-inspect. */
  getPickables() {
    return [...this.stars.values()].map((r) => r.pick);
  }

  /** Galaxy summary data (visited/scanned flags etc.) for a system. */
  getSystem(systemId) {
    const record = this.stars.get(systemId);
    return record ? record.sys : null;
  }

  /** Per-frame animation for phenomena. */
  update(t, dt) {
    for (const p of this.pulsing) {
      if (p.sprite) {
        p.sprite.scale.setScalar(p.base + Math.abs(Math.sin(t * p.speed)) * p.amp);
      } else if (p.orbiter) {
        p.orbiter.position.set(
          Math.cos(t * p.speed) * p.radius,
          0.5,
          Math.sin(t * p.speed) * p.radius,
        );
      } else if (p.spinner) {
        p.spinner.rotation.z += dt * p.speed;
        if (p.tumble) p.spinner.rotation.x += dt * p.speed * 0.6;
      }
    }
  }
}
