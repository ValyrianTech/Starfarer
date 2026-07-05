// Three.js scene setup: renderer, camera with slow auto-orbit, backdrop starfield.

import * as THREE from "three";

export class SpectatorScene {
  constructor(canvas) {
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setClearColor(0x05070f, 1);

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x05070f, 0.00075);

    this.camera = new THREE.PerspectiveCamera(
      55,
      window.innerWidth / window.innerHeight,
      0.1,
      4000,
    );

    // Camera orbits a target point that eases toward the ship.
    this.cameraTarget = new THREE.Vector3(0, 0, 0);
    this.desiredTarget = new THREE.Vector3(0, 0, 0);
    this.orbitAngle = 0;
    this.orbitRadius = 210;
    this.orbitHeight = 110;
    this.desiredOrbitRadius = 210;
    this.desiredOrbitHeight = 110;

    this.scene.add(new THREE.AmbientLight(0x30405f, 1.4));

    this._buildBackdrop();

    this.updaters = [];
    this.clock = new THREE.Clock();

    window.addEventListener("resize", () => this._onResize());
    this._animate = this._animate.bind(this);
    requestAnimationFrame(this._animate);
  }

  _buildBackdrop() {
    // Distant background stars: three shells of random points.
    const rng = mulberry32(1337);
    for (const [count, radius, size, color] of [
      [1400, 1600, 2.2, 0x8899bb],
      [900, 1200, 1.6, 0x5f6f95],
      [500, 900, 1.2, 0x445070],
    ]) {
      const positions = new Float32Array(count * 3);
      for (let i = 0; i < count; i++) {
        const theta = rng() * Math.PI * 2;
        const phi = Math.acos(2 * rng() - 1);
        positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
        positions[i * 3 + 1] = radius * Math.cos(phi);
        positions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      const mat = new THREE.PointsMaterial({
        color,
        size,
        sizeAttenuation: false,
        transparent: true,
        opacity: 0.8,
        depthWrite: false,
      });
      this.scene.add(new THREE.Points(geo, mat));
    }
  }

  /** Register a per-frame updater: fn(elapsedSeconds, deltaSeconds). */
  addUpdater(fn) {
    this.updaters.push(fn);
  }

  /** Set the point the camera should drift toward and orbit. */
  setFocus(vec3) {
    this.desiredTarget.copy(vec3);
  }

  /** Set the desired camera orbit distance and height (eased). */
  setZoom(radius, height) {
    this.desiredOrbitRadius = radius;
    this.desiredOrbitHeight = height;
  }

  _onResize() {
    this.camera.aspect = window.innerWidth / window.innerHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(window.innerWidth, window.innerHeight);
  }

  _animate() {
    requestAnimationFrame(this._animate);
    const dt = Math.min(this.clock.getDelta(), 0.1);
    const t = this.clock.elapsedTime;

    for (const fn of this.updaters) fn(t, dt);

    // Ease the orbit target toward the focus point.
    this.cameraTarget.lerp(this.desiredTarget, 1 - Math.exp(-dt * 1.5));

    // Ease the zoom level toward the desired orbit distance.
    const zoomEase = 1 - Math.exp(-dt * 1.2);
    this.orbitRadius += (this.desiredOrbitRadius - this.orbitRadius) * zoomEase;
    this.orbitHeight += (this.desiredOrbitHeight - this.orbitHeight) * zoomEase;

    // Slow auto-orbit with a gentle vertical breathing motion.
    this.orbitAngle += dt * 0.06;
    const bob = Math.sin(t * 0.11) * (this.orbitRadius / 210) * 20;
    this.camera.position.set(
      this.cameraTarget.x + Math.cos(this.orbitAngle) * this.orbitRadius,
      this.cameraTarget.y + this.orbitHeight + bob,
      this.cameraTarget.z + Math.sin(this.orbitAngle) * this.orbitRadius,
    );
    this.camera.lookAt(this.cameraTarget);

    this.renderer.render(this.scene, this.camera);
  }
}

/** Small deterministic PRNG for backdrop generation. */
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
