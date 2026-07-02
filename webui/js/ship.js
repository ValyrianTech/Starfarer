// Ship marker: glowing beacon at the current system, animated jumps with a trail.

import * as THREE from "three";

const JUMP_DURATION = 2.4; // seconds
const TRAIL_POINTS = 60;

export class ShipMarker {
  constructor(scene) {
    this.group = new THREE.Group();
    scene.add(this.group);

    // Diamond-shaped beacon.
    const beacon = new THREE.Mesh(
      new THREE.OctahedronGeometry(1.4),
      new THREE.MeshBasicMaterial({ color: 0x7ee8a2 }),
    );
    this.beacon = beacon;
    this.group.add(beacon);

    // Pulsing halo ring.
    this.halo = new THREE.Mesh(
      new THREE.TorusGeometry(3.2, 0.16, 8, 40),
      new THREE.MeshBasicMaterial({
        color: 0x7ee8a2,
        transparent: true,
        opacity: 0.7,
        blending: THREE.AdditiveBlending,
      }),
    );
    this.halo.rotation.x = Math.PI / 2;
    this.group.add(this.halo);

    this.light = new THREE.PointLight(0x7ee8a2, 60, 90);
    this.group.add(this.light);

    // Engine trail as a fading line strip.
    this.trailPositions = new Float32Array(TRAIL_POINTS * 3);
    const trailGeo = new THREE.BufferGeometry();
    trailGeo.setAttribute("position", new THREE.BufferAttribute(this.trailPositions, 3));
    this.trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({
      color: 0x7ee8a2,
      transparent: true,
      opacity: 0.0,
      blending: THREE.AdditiveBlending,
    }));
    scene.add(this.trail);

    this.jump = null; // { from, to, elapsed }
  }

  /** Instantly place the ship (initial load). */
  setPosition(vec3) {
    this.group.position.copy(vec3);
    this._resetTrail(vec3);
  }

  /** Animate a jump to a new position. */
  jumpTo(vec3) {
    if (this.group.position.distanceToSquared(vec3) < 0.01) return;
    this.jump = {
      from: this.group.position.clone(),
      to: vec3.clone(),
      elapsed: 0,
    };
    this.trail.material.opacity = 0.85;
  }

  get position() {
    return this.group.position;
  }

  _resetTrail(vec3) {
    for (let i = 0; i < TRAIL_POINTS; i++) {
      this.trailPositions[i * 3] = vec3.x;
      this.trailPositions[i * 3 + 1] = vec3.y;
      this.trailPositions[i * 3 + 2] = vec3.z;
    }
    this.trail.geometry.attributes.position.needsUpdate = true;
  }

  update(t, dt) {
    // Idle animations.
    this.beacon.rotation.y += dt * 1.2;
    const pulse = 1 + Math.sin(t * 2.4) * 0.18;
    this.halo.scale.setScalar(pulse);
    this.halo.material.opacity = 0.45 + Math.sin(t * 2.4) * 0.25;

    // Jump animation with a slight arc.
    if (this.jump) {
      this.jump.elapsed += dt;
      const raw = Math.min(this.jump.elapsed / JUMP_DURATION, 1);
      const eased = raw < 0.5 ? 2 * raw * raw : 1 - Math.pow(-2 * raw + 2, 2) / 2;
      const pos = this.jump.from.clone().lerp(this.jump.to, eased);
      pos.y += Math.sin(raw * Math.PI) * 14; // arc above the plane
      this.group.position.copy(pos);
      if (raw >= 1) {
        this.jump = null;
      }
    } else if (this.trail.material.opacity > 0) {
      this.trail.material.opacity = Math.max(0, this.trail.material.opacity - dt * 0.5);
    }

    // Shift trail points toward the current position.
    const p = this.trailPositions;
    for (let i = TRAIL_POINTS - 1; i > 0; i--) {
      p[i * 3] = p[(i - 1) * 3];
      p[i * 3 + 1] = p[(i - 1) * 3 + 1];
      p[i * 3 + 2] = p[(i - 1) * 3 + 2];
    }
    p[0] = this.group.position.x;
    p[1] = this.group.position.y;
    p[2] = this.group.position.z;
    this.trail.geometry.attributes.position.needsUpdate = true;
  }
}
