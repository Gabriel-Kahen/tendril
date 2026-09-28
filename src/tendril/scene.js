import * as THREE from "./vendor/three.module.js";

const vector = (value) =>
  Array.isArray(value) && value.length === 3 && value.every(Number.isFinite);
const point = (value) => new THREE.Vector3(...value);
const UP = new THREE.Vector3(0, 1, 0);

// Flex indices are local to each flex. Discard shared tetrahedron faces and
// never interpret a 1D connection's two indices as a tissue tetrahedron.
export function surfaceTriangles(frame) {
  const vertices = frame.flex_vertices || [];
  const elements = (frame.flex_elements || []).flat();
  const faces = new Map();
  for (const flex of frame.flexes || []) {
    if (flex.dim !== 2 && flex.dim !== 3) continue;
    const stride = flex.dim + 1;
    for (let n = 0; n < flex.element_count; n++) {
      const start = flex.element_address + n * stride;
      const t = elements
        .slice(start, start + stride)
        .map((i) => i + flex.vertex_address);
      if (t.length !== stride) continue;
      const candidates =
        stride === 3
          ? [t]
          : [
              [t[0], t[2], t[1]],
              [t[0], t[1], t[3]],
              [t[0], t[3], t[2]],
              [t[1], t[2], t[3]],
            ];
      for (const triangle of candidates) {
        const key = [...triangle].sort((a, b) => a - b).join(",");
        const previous = faces.get(key);
        if (previous) previous.count++;
        else faces.set(key, { triangle, count: 1 });
      }
    }
  }
  return [...faces.values()]
    .filter((face) => face.count === 1)
    .map((face) => face.triangle.map((i) => vertices[i]))
    .filter((triangle) => triangle.every(vector));
}

export class SceneView {
  constructor(canvas) {
    this.canvas = canvas;
    try {
      this.renderer = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: false,
      });
    } catch (error) {
      throw new Error(
        "The 3D viewer needs WebGL 2. Enable browser graphics acceleration and reload.",
        { cause: error },
      );
    }
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.3;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color("#142126");
    this.scene.fog = new THREE.Fog("#142126", 2, 8);
    this.camera = new THREE.PerspectiveCamera(43, 1, 0.001, 40);
    this.camera.up.set(0, 0, 1);
    this.target = new THREE.Vector3(0, 0, 0.08);
    this.azimuth = -Math.PI / 3;
    this.elevation = 0.48;
    this.distance = 0.95;
    this.fitRadius = 0.25;
    this.wireframe = false;
    this.parts = new Map();
    this.sphere = new THREE.SphereGeometry(1, 24, 16);
    this.cylinder = new THREE.CylinderGeometry(1, 1, 1, 24);
    this.organism = new THREE.Group();
    this.scene.add(this.organism);

    const ambient = new THREE.HemisphereLight("#d5eeed", "#182629", 2.4);
    ambient.position.set(0, 0, 4);
    this.scene.add(ambient);
    this.key = new THREE.DirectionalLight("#fff0dc", 4.3);
    this.key.position.set(-0.7, -0.8, 1.5);
    this.key.castShadow = true;
    this.key.shadow.mapSize.set(2048, 2048);
    this.key.shadow.bias = -0.00004;
    this.key.shadow.normalBias = 0.0007;
    this.key.shadow.camera.near = 0.01;
    this.key.shadow.camera.far = 12;
    this.scene.add(this.key, this.key.target);
    const rim = new THREE.DirectionalLight("#85cbd6", 2.5);
    rim.position.set(1, 0.8, 0.8);
    this.scene.add(rim);

    // The simulated ground is z = 0. The tiny offset only prevents grid z-fighting.
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(20, 20),
      new THREE.MeshStandardMaterial({
        color: "#26383b",
        roughness: 0.94,
        metalness: 0.05,
      }),
    );
    floor.position.z = -0.0005;
    floor.receiveShadow = true;
    this.scene.add(floor);
    const grid = new THREE.GridHelper(10, 100, "#49605f", "#344947");
    grid.rotation.x = Math.PI / 2;
    grid.position.z = 0.0001;
    grid.material.transparent = true;
    grid.material.opacity = 0.36;
    grid.material.depthWrite = false;
    this.scene.add(grid);
    this.object = new THREE.Mesh(
      this.sphere,
      new THREE.MeshStandardMaterial({
        color: "#dba166",
        roughness: 0.36,
        metalness: 0.18,
      }),
    );
    this.object.scale.setScalar(0.025); // Recorded assay sphere radius, in metres.
    this.object.castShadow = this.object.receiveShadow = true;
    this.object.visible = false;
    this.scene.add(this.object);
    this.tissue = null;
    this.bindControls();
    this.resize();
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(canvas);
  }

  material(color) {
    return new THREE.MeshStandardMaterial({
      color,
      roughness: 0.34,
      metalness: 0.2,
      wireframe: this.wireframe,
    });
  }

  capsule(key, a, b, radius, color) {
    let part = this.parts.get(key);
    if (!part) {
      const material = this.material(color);
      const group = new THREE.Group();
      for (const geometry of [this.cylinder, this.sphere, this.sphere]) {
        const mesh = new THREE.Mesh(geometry, material);
        mesh.castShadow = mesh.receiveShadow = true;
        group.add(mesh);
      }
      this.organism.add(group);
      part = { group, material };
      this.parts.set(key, part);
    }
    part.material.color.set(color);
    const start = point(a),
      end = point(b),
      delta = end.clone().sub(start);
    const length = delta.length();
    const [shaft, capA, capB] = part.group.children;
    shaft.position.copy(start).add(end).multiplyScalar(0.5);
    shaft.scale.set(radius, Math.max(length, 1e-8), radius);
    if (length > 1e-8)
      shaft.quaternion.setFromUnitVectors(UP, delta.normalize());
    capA.position.copy(start);
    capB.position.copy(end);
    capA.scale.setScalar(radius);
    capB.scale.setScalar(radius);
    return key;
  }

  setFrame(frame) {
    if (frame === this.frame) return;
    this.frame = frame;
    const live = new Set();
    const segments = frame.segments || [];
    const tips = new Map();
    for (const segment of segments) {
      if (!vector(segment.a) || !vector(segment.b) || !(segment.radius > 0))
        continue;
      let start = point(segment.a),
        end = point(segment.b);
      tips.set(segment.id, segment.b);
      // Match the physics capsule's small junction clearance, not an invented rod.
      if (segment.parent != null) {
        const delta = end.clone().sub(start);
        start.addScaledVector(
          delta.normalize(),
          Math.min(2 * segment.radius, start.distanceTo(end) * 0.4),
        );
      }
      const activity = Math.max(0, Math.min(1, Number(segment.signal) || 0));
      const color = new THREE.Color("#70bfae").lerp(
        new THREE.Color("#d0e4b2"),
        activity * 0.55,
      );
      live.add(
        this.capsule(
          `segment-${segment.id}`,
          start.toArray(),
          segment.b,
          segment.radius,
          color,
        ),
      );
    }
    for (const link of frame.links || []) {
      if (tips.has(link.a) && tips.has(link.b))
        live.add(
          this.capsule(
            `link-${link.id}`,
            tips.get(link.a),
            tips.get(link.b),
            0.003,
            "#aaa3dc",
          ),
        );
    }
    for (const [key, part] of this.parts) {
      if (live.has(key)) continue;
      this.organism.remove(part.group);
      part.material.dispose();
      this.parts.delete(key);
    }
    const triangles = surfaceTriangles(frame);
    if (this.tissue && !triangles.length) {
      this.organism.remove(this.tissue);
      this.tissue.geometry.dispose();
      this.tissue.material.dispose();
      this.tissue = null;
    }
    if (triangles.length) {
      // Reuse the current mesh and GPU buffers while its vertex count is stable.
      // Topology still comes from this frame, including newly grown tissue.
      let geometry = this.tissue?.geometry;
      if (geometry?.getAttribute("position")?.count !== triangles.length * 3) {
        geometry?.dispose();
        geometry = new THREE.BufferGeometry();
        geometry.setAttribute(
          "position",
          new THREE.Float32BufferAttribute(triangles.length * 9, 3),
        );
      }
      if (!this.tissue) {
        const material = this.material("#d4b1a2");
        material.side = THREE.DoubleSide;
        material.roughness = 0.65;
        material.metalness = 0.02;
        this.tissue = new THREE.Mesh(geometry, material);
        this.tissue.castShadow = this.tissue.receiveShadow = true;
        this.organism.add(this.tissue);
      }
      this.tissue.geometry = geometry;
      const positions = geometry.getAttribute("position");
      let offset = 0;
      for (const triangle of triangles)
        for (const vertex of triangle) {
          positions.array.set(vertex, offset);
          offset += 3;
        }
      positions.needsUpdate = true;
      geometry.computeVertexNormals();
      geometry.computeBoundingSphere();
    }
    this.object.visible = vector(frame.object);
    if (this.object.visible) this.object.position.fromArray(frame.object);
    this.render();
  }

  fit(frames) {
    const bounds = new THREE.Box3();
    for (const frame of frames) {
      for (const segment of frame.segments || []) {
        for (const endpoint of [segment.a, segment.b]) {
          if (!vector(endpoint)) continue;
          const p = point(endpoint),
            r = Math.max(segment.radius || 0, 0);
          bounds.expandByPoint(p.clone().addScalar(r));
          bounds.expandByPoint(p.clone().addScalar(-r));
        }
      }
      for (const vertex of frame.flex_vertices || [])
        if (vector(vertex)) bounds.expandByPoint(point(vertex));
      if (vector(frame.object)) {
        bounds.expandByPoint(point(frame.object).addScalar(0.025));
        bounds.expandByPoint(point(frame.object).addScalar(-0.025));
      }
    }
    if (bounds.isEmpty()) return;
    bounds.getCenter(this.target);
    this.fitRadius = Math.max(
      bounds.getSize(new THREE.Vector3()).length() * 0.5,
      0.08,
    );
    this.azimuth = -Math.PI / 3;
    this.elevation = 0.48;
    this.distance = this.fittedDistance();
    this.updateLighting();
    this.render();
  }

  fittedDistance() {
    const vertical = THREE.MathUtils.degToRad(this.camera.fov * 0.5);
    const horizontal = Math.atan(Math.tan(vertical) * this.camera.aspect);
    return (this.fitRadius / Math.sin(Math.min(vertical, horizontal))) * 1.16;
  }

  updateLighting() {
    const extent = Math.max(this.fitRadius * 1.6, 0.4);
    this.key.target.position.copy(this.target);
    this.key.position
      .copy(this.target)
      .add(new THREE.Vector3(-extent, -extent, extent * 2.2));
    Object.assign(this.key.shadow.camera, {
      left: -extent,
      right: extent,
      top: extent,
      bottom: -extent,
      far: extent * 6,
    });
    this.key.shadow.camera.updateProjectionMatrix();
    this.scene.fog.near = Math.max(this.distance * 2, 1.2);
    this.scene.fog.far = Math.max(this.distance * 6, 5);
  }

  setWireframe(value) {
    this.wireframe = !!value;
    this.organism.traverse((child) => {
      if (child.isMesh) child.material.wireframe = this.wireframe;
    });
    this.render();
  }

  resize() {
    const width = Math.max(this.canvas.clientWidth, 1),
      height = Math.max(this.canvas.clientHeight, 1);
    const before = this.fittedDistance();
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.distance *= this.fittedDistance() / before;
    this.renderer.setSize(width, height, false);
    this.render();
  }

  render() {
    const horizontal = this.distance * Math.cos(this.elevation);
    this.camera.position
      .copy(this.target)
      .add(
        new THREE.Vector3(
          horizontal * Math.cos(this.azimuth),
          horizontal * Math.sin(this.azimuth),
          this.distance * Math.sin(this.elevation),
        ),
      );
    this.camera.lookAt(this.target);
    this.renderer.render(this.scene, this.camera);
  }

  pan(dx, dy) {
    const scale =
      (this.distance *
        2 *
        Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2))) /
      Math.max(this.canvas.clientHeight, 1);
    const right = new THREE.Vector3().setFromMatrixColumn(
      this.camera.matrixWorld,
      0,
    );
    const up = new THREE.Vector3().setFromMatrixColumn(
      this.camera.matrixWorld,
      1,
    );
    this.target
      .addScaledVector(right, -dx * scale)
      .addScaledVector(up, dy * scale);
  }

  bindControls() {
    const pointers = new Map();
    this.canvas.style.touchAction = "none";
    this.canvas.addEventListener("contextmenu", (event) =>
      event.preventDefault(),
    );
    this.canvas.addEventListener("pointerdown", (event) => {
      this.canvas.setPointerCapture(event.pointerId);
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    });
    this.canvas.addEventListener("pointermove", (event) => {
      const previous = pointers.get(event.pointerId);
      if (!previous) return;
      const next = { x: event.clientX, y: event.clientY };
      const dx = next.x - previous.x,
        dy = next.y - previous.y;
      if (pointers.size > 1) {
        const other = [...pointers.entries()].find(
          ([id]) => id !== event.pointerId,
        )[1];
        const oldGap = Math.hypot(previous.x - other.x, previous.y - other.y);
        const newGap = Math.hypot(next.x - other.x, next.y - other.y);
        if (oldGap > 0 && newGap > 0) this.distance *= oldGap / newGap;
        this.pan(dx * 0.5, dy * 0.5);
      } else if (event.shiftKey || event.buttons === 2 || event.buttons === 4)
        this.pan(dx, dy);
      else {
        this.azimuth -= dx * 0.008;
        this.elevation = THREE.MathUtils.clamp(
          this.elevation + dy * 0.008,
          0.045,
          Math.PI / 2 - 0.02,
        );
      }
      pointers.set(event.pointerId, next);
      this.distance = THREE.MathUtils.clamp(this.distance, 0.025, 15);
      this.render();
    });
    for (const type of ["pointerup", "pointercancel", "lostpointercapture"])
      this.canvas.addEventListener(type, (event) =>
        pointers.delete(event.pointerId),
      );
    this.canvas.addEventListener(
      "wheel",
      (event) => {
        event.preventDefault();
        const delta =
          event.deltaY *
          (event.deltaMode === 1
            ? 16
            : event.deltaMode === 2
              ? this.canvas.clientHeight
              : 1);
        this.distance = THREE.MathUtils.clamp(
          this.distance *
            Math.exp(THREE.MathUtils.clamp(delta * 0.001, -0.5, 0.5)),
          0.025,
          15,
        );
        this.render();
      },
      { passive: false },
    );
  }
}
