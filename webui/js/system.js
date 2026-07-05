// System detail view: orbiting bodies around the current star, biome colors,
// orbit rings, moons, trading station, and a landed-body highlight.

import * as THREE from "three";
import { makeLabelSprite } from "./galaxy.js";

// Mirrors backend/config.py BIOME_COLORS.
const BIOME_COLORS = {
  desert: 0xd4a853,
  tundra: 0xc8e0f0,
  jungle: 0x3d8c40,
  ocean: 0x2969a8,
  volcanic: 0x8b3a1a,
  barren: 0x8a8a8a,
  gas_giant: 0xc4a882,
  crystal: 0xa8e6cf,
};

const ORBIT_BASE = 6;
const ORBIT_STEP = 3.2;
const MOON_ORBIT_BASE = 1.6;
const MOON_ORBIT_STEP = 0.8;

function hashString(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 10000) / 10000;
}

function bodyRadius(body) {
  if (body.body_type === "moon") return 0.28 + body.size * 0.1;
  return 0.55 + body.size * 0.14;
}

export class SystemView {
  constructor(scene) {
    this.scene = scene;
    this.group = new THREE.Group();
    this.group.visible = false;
    this.scene.add(this.group);
    this.systemId = null;
    this.orbiters = []; // { pivot, speed } for planets and station
    this.bodies = new Map(); // body id -> { mesh (world-positioned via pivot), highlight }
    this.highlight = null;
    this.highlightedBodyId = null;
  }

  /** Build the detail view for a system at the given world position. */
  build(sysData, centerPos) {
    this.clear();
    if (!sysData || !centerPos) return;
    this.systemId = sysData.id;
    this.group.position.copy(centerPos);
    this.group.visible = true;

    // Light the planets from the star at the center.
    const starLight = new THREE.PointLight(0xfff2dd, 220, 90);
    this.group.add(starLight);

    const bodies = sysData.bodies || [];
    // Planets and belts orbit the star; moons orbit their parent planet.
    const parents = bodies.filter((b) => b.body_type !== "moon");
    const moons = bodies.filter((b) => b.body_type === "moon");

    parents.forEach((body, i) => {
      const orbitR = ORBIT_BASE + i * ORBIT_STEP;
      this._addOrbitRing(this.group, orbitR, 0.10);

      const pivot = new THREE.Group();
      pivot.rotation.y = hashString(body.id) * Math.PI * 2;
      this.group.add(pivot);
      const speed = 0.22 / Math.sqrt(orbitR / ORBIT_BASE);
      this.orbiters.push({ pivot, speed });

      const anchor = new THREE.Group();
      anchor.position.x = orbitR;
      pivot.add(anchor);

      if (body.body_type === "asteroid_belt") {
        this._addBelt(this.group, orbitR);
        this.bodies.set(body.id, { anchor });
        return;
      }

      const mesh = this._makeBodyMesh(body);
      anchor.add(mesh);

      const labelSprite = makeLabelSprite(body.name);
      labelSprite.position.y = bodyRadius(body) + 1.6;
      labelSprite.scale.multiplyScalar(0.55);
      labelSprite.material.opacity = body.explored ? 0.9 : 0.35;
      anchor.add(labelSprite);

      this.bodies.set(body.id, { anchor, mesh });

      // Attach this planet's moons.
      const myMoons = moons.filter((m) => m.id.startsWith(`${body.id}_m`));
      myMoons.forEach((moon, mi) => {
        const moonPivot = new THREE.Group();
        moonPivot.rotation.y = hashString(moon.id) * Math.PI * 2;
        anchor.add(moonPivot);
        const moonR = bodyRadius(body) + MOON_ORBIT_BASE + mi * MOON_ORBIT_STEP;
        const moonMesh = this._makeBodyMesh(moon);
        moonMesh.position.x = moonR;
        moonPivot.add(moonMesh);
        this.orbiters.push({ pivot: moonPivot, speed: 0.9 + mi * 0.25 });
        this.bodies.set(moon.id, { anchor: moonMesh, mesh: moonMesh });
      });
    });

    if (sysData.has_trading_station) {
      const stationR = ORBIT_BASE + parents.length * ORBIT_STEP;
      this._addOrbitRing(this.group, stationR, 0.06);
      const pivot = new THREE.Group();
      pivot.rotation.y = hashString(`${sysData.id}_station`) * Math.PI * 2;
      this.group.add(pivot);
      const station = new THREE.Mesh(
        new THREE.OctahedronGeometry(0.7),
        new THREE.MeshBasicMaterial({ color: 0xffb347, wireframe: true }),
      );
      station.position.x = stationR;
      pivot.add(station);
      const label = makeLabelSprite("Trading Station", "#ffb347");
      label.position.set(stationR, 1.8, 0);
      label.scale.multiplyScalar(0.5);
      pivot.add(label);
      this.orbiters.push({ pivot, speed: 0.12, spinner: station });
    }
  }

  _makeBodyMesh(body) {
    const color = new THREE.Color(BIOME_COLORS[body.biome] ?? 0x8a8a8a);
    if (!body.explored) color.multiplyScalar(0.5);
    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(bodyRadius(body), 20, 20),
      new THREE.MeshStandardMaterial({
        color,
        roughness: 0.85,
        metalness: 0.05,
        emissive: color.clone().multiplyScalar(0.22),
      }),
    );
    return mesh;
  }

  _addOrbitRing(parent, radius, opacity) {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(radius, 0.02, 4, 96),
      new THREE.MeshBasicMaterial({
        color: 0x6ea8ff,
        transparent: true,
        opacity,
        depthWrite: false,
      }),
    );
    ring.rotation.x = Math.PI / 2;
    parent.add(ring);
  }

  _addBelt(parent, radius) {
    const count = 60;
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2;
      const r = radius + ((i * 13) % 5) * 0.2 - 0.5;
      positions[i * 3] = Math.cos(angle) * r;
      positions[i * 3 + 1] = ((i * 37) % 5) * 0.15 - 0.35;
      positions[i * 3 + 2] = Math.sin(angle) * r;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const belt = new THREE.Points(geo, new THREE.PointsMaterial({
      color: 0x9a8f7f,
      size: 0.35,
      transparent: true,
      opacity: 0.85,
    }));
    parent.add(belt);
    // Rotate the belt itself slowly.
    this.orbiters.push({ pivot: belt, speed: 0.05 });
  }

  /** Pulsing ring around the body the ship is landed on. */
  setLandedBody(bodyId) {
    if (this.highlightedBodyId === bodyId) return;
    this._removeHighlight();
    this.highlightedBodyId = bodyId;
    if (!bodyId) return;
    const record = this.bodies.get(bodyId);
    if (!record || !record.mesh) return;
    const r = record.mesh.geometry.parameters.radius ?? 1;
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(r + 0.7, 0.07, 8, 48),
      new THREE.MeshBasicMaterial({
        color: 0x7ee8a2,
        transparent: true,
        opacity: 0.8,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    ring.rotation.x = Math.PI / 2;
    record.mesh.add(ring);
    this.highlight = ring;
  }

  _removeHighlight() {
    if (this.highlight) {
      this.highlight.removeFromParent();
      this.highlight = null;
    }
    this.highlightedBodyId = null;
  }

  /** World position of a body (or null). */
  getBodyPosition(bodyId) {
    const record = this.bodies.get(bodyId);
    if (!record) return null;
    const target = record.mesh ?? record.anchor;
    return target.getWorldPosition(new THREE.Vector3());
  }

  clear() {
    this.group.clear();
    this.group.visible = false;
    this.systemId = null;
    this.orbiters = [];
    this.bodies.clear();
    this.highlight = null;
    this.highlightedBodyId = null;
  }

  update(t, dt) {
    for (const o of this.orbiters) {
      o.pivot.rotation.y += dt * o.speed;
      if (o.spinner) o.spinner.rotation.x += dt * 0.8;
    }
    if (this.highlight) {
      const pulse = 1 + Math.sin(t * 3) * 0.12;
      this.highlight.scale.setScalar(pulse);
      this.highlight.material.opacity = 0.55 + Math.sin(t * 3) * 0.25;
    }
  }
}
