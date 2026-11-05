// 3D viewer: draws the STL of the part with three.js.
// Extras: the reference component as a ghost, the previous version for
// comparison, stress colours and the (exaggerated) deformed shape.
import * as THREE from "three";
import { OrbitControls } from "/static/three/OrbitControls.js";
import { STLLoader } from "/static/three/STLLoader.js";

const PART_COLOR = 0x6f9fd8;
const DIRS = { iso: [1, -1, 0.8], top: [0, 0, 1], front: [0, -1, 0], right: [1, 0, 0] };
// Stress colour ramp (low -> high), same stops as the legend in styles.css.
const RAMP = [[0x2b, 0x3a, 0x8f], [0x1f, 0xa3, 0xd4], [0x3c, 0xb4, 0x4b], [0xf5, 0xd2, 0x1f], [0xd6, 0x27, 0x28]];

function rampColor(t) {
  const x = Math.min(Math.max(t, 0), 1) * (RAMP.length - 1);
  const i = Math.min(Math.floor(x), RAMP.length - 2);
  const f = x - i;
  return RAMP[i].map((c, k) => (c + (RAMP[i + 1][k] - c) * f) / 255);
}

async function fetchGeometry(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`Could not load ${url}`);
  const geometry = new STLLoader().parse(await response.arrayBuffer());
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  return geometry;
}

export class Viewer {
  constructor(container) {
    this.container = container;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    container.prepend(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(35, 1, 0.1, 10000);
    this.camera.up.set(0, 0, 1);                     // Z up, like SolidWorks "Isometric"
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.6));
    this.sun = new THREE.DirectionalLight(0xffffff, 1.6);
    this.scene.add(this.sun);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;

    this.part = null;        // { group, mesh, edges }
    this.simMesh = null;     // skin of the simulated model, coloured by stress
    this.helpers = [];       // grid and axes
    this.ghost = null;
    this.compare = null;
    this.stress = null;      // { base, displacement, maxDisp }
    this.stressVisible = true;
    this.deformFraction = 0.6;
    this.center = new THREE.Vector3();
    this.radius = 50;
    this.framed = false;

    new ResizeObserver(() => this.resize()).observe(container);
    this.resize();
    const loop = () => {
      requestAnimationFrame(loop);
      this.controls.update();
      this.sun.position.copy(this.camera.position);
      this.renderer.render(this.scene, this.camera);
    };
    loop();
  }

  resize() {
    const w = Math.max(this.container.clientWidth, 10);
    const h = Math.max(this.container.clientHeight, 10);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
  }

  _dispose(obj) {
    if (!obj) return;
    this.scene.remove(obj);
    obj.traverse?.((o) => { o.geometry?.dispose(); o.material?.dispose(); });
  }

  clear() {
    this._dispose(this.part?.group);
    this.helpers.forEach((h) => this._dispose(h));
    this._dispose(this.ghost);
    this._dispose(this.compare);
    this._dispose(this.simMesh);
    this.part = null; this.helpers = []; this.ghost = null; this.compare = null; this.stress = null;
    this.simMesh = null;
    this.framed = false;
  }

  // Load the part. The camera is only re-framed for the first part or when
  // the size changes a lot, so that small edits keep the user's point of view.
  async loadPart(url) {
    const geometry = await fetchGeometry(url);
    const bb = geometry.boundingBox;
    const size = new THREE.Vector3(); bb.getSize(size);
    const center = new THREE.Vector3(); bb.getCenter(center);
    const radius = Math.max(size.length() / 2, 1);

    this._dispose(this.part?.group);
    this.helpers.forEach((h) => this._dispose(h));
    this.helpers = [];
    this._dispose(this.simMesh);
    this.simMesh = null;
    this.stress = null;

    const material = new THREE.MeshStandardMaterial({
      color: PART_COLOR, metalness: 0.1, roughness: 0.55,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    const mesh = new THREE.Mesh(geometry, material);
    // Sharp edges (angle > 25 deg) drawn as lines, so it looks like a CAD model.
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 25),
      new THREE.LineBasicMaterial({ color: 0x1f2d3d }));
    const group = new THREE.Group();
    group.add(mesh, edges);
    this.scene.add(group);
    this.part = { group, mesh, edges };

    // Grid on the plane under the part with 10 mm squares, and small XYZ axes.
    const gridSize = Math.ceil(Math.max(size.x, size.y) * 1.6 / 10) * 10 + 20;
    const grid = new THREE.GridHelper(gridSize, gridSize / 10, 0x8a99a8, 0xc5ced8);
    grid.rotation.x = Math.PI / 2;
    grid.position.set(center.x, center.y, bb.min.z);
    const axes = new THREE.AxesHelper(radius * 0.4);
    axes.position.set(bb.min.x - radius * 0.15, bb.min.y - radius * 0.15, bb.min.z);
    this.scene.add(grid, axes);
    this.helpers = [grid, axes];

    const changed = !this.framed || Math.abs(radius - this.radius) > 0.25 * this.radius
      || center.distanceTo(this.center) > 0.5 * this.radius;
    this.center.copy(center); this.radius = radius;
    this.camera.near = radius / 100; this.camera.far = radius * 100;
    this.camera.updateProjectionMatrix();
    if (changed) this.setView("iso");
    this.framed = true;
    return { size: [size.x, size.y, size.z] };
  }

  async _overlay(slot, url, material) {
    this._dispose(this[slot]);
    this[slot] = null;
    if (!url) return;
    const geometry = await fetchGeometry(url);
    const mesh = new THREE.Mesh(geometry, material);
    this[slot] = mesh;
    this.scene.add(mesh);
  }

  // Mating component (tube, sensor, motor...) drawn as a translucent ghost.
  setGhost(url) {
    return this._overlay("ghost", url, new THREE.MeshStandardMaterial({
      color: 0x8a949e, transparent: true, opacity: 0.32, roughness: 0.8, depthWrite: false }));
  }

  // Previous version, drawn in orange wireframe over the current one.
  setCompare(url) {
    return this._overlay("compare", url, new THREE.MeshBasicMaterial({
      color: 0xe2702a, wireframe: true, transparent: true, opacity: 0.35 }));
  }

  setGhostVisible(on) { if (this.ghost) this.ghost.visible = on; }

  // Simulation result: the skin of the simulated model with a colour per node.
  // points, displacement: Float32Array (x, y, z per node); triangles: Uint32Array;
  // levels: Uint8Array (0 = no stress ... 255 = top of the scale).
  setStress({ points, triangles, levels, displacement, maxDisp }) {
    this._dispose(this.simMesh);
    this.simMesh = null;
    const colors = new Float32Array(points.length);
    for (let i = 0; i < levels.length; i++) colors.set(rampColor(levels[i] / 255), 3 * i);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(points.slice(), 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geometry.setIndex(new THREE.BufferAttribute(triangles, 1));
    const material = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true, side: THREE.DoubleSide });
    this.simMesh = new THREE.Mesh(geometry, material);
    this.scene.add(this.simMesh);
    this.stress = { base: points, displacement, maxDisp };
    this._applyStress();
  }

  clearStress() {
    this._dispose(this.simMesh);
    this.simMesh = null;
    this.stress = null;
    this._applyStress();
  }

  setStressVisible(on) { this.stressVisible = on; this._applyStress(); }
  setDeformation(fraction) { this.deformFraction = fraction; this._applyStress(); }

  _applyStress() {
    const on = !!(this.stress && this.simMesh && this.stressVisible);
    if (this.part) this.part.group.visible = !on;
    if (!this.simMesh) return;
    this.simMesh.visible = on;
    if (!on) return;
    // Deformed shape: the largest movement is drawn as up to 16 % of the part's radius.
    const { base, displacement, maxDisp } = this.stress;
    const factor = maxDisp > 0 ? this.deformFraction * 0.16 * this.radius / maxDisp : 0;
    const pos = this.simMesh.geometry.attributes.position.array;
    for (let i = 0; i < pos.length; i++) pos[i] = base[i] + displacement[i] * factor;
    this.simMesh.geometry.attributes.position.needsUpdate = true;
    this.simMesh.geometry.computeBoundingSphere();
    this.deformFactor = factor;
  }

  setView(name) {
    const d = new THREE.Vector3(...(DIRS[name] || DIRS.iso)).normalize();
    const dist = this.radius / Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2)) * 1.2;
    this.camera.up.set(0, name === "top" ? 1 : 0, name === "top" ? 0 : 1);
    this.camera.position.copy(this.center).addScaledVector(d, dist);
    this.controls.target.copy(this.center);
    this.camera.lookAt(this.center);
    this.controls.update();
  }

  screenshot() {
    this.renderer.render(this.scene, this.camera);
    return this.renderer.domElement.toDataURL("image/png");
  }
}
