"""Interactive 3D viewer for Streamlit, made with three.js.

The STL is embedded in the page (base64) and drawn by three.js in the
browser: rotate with the left button, pan with the right one, zoom with the
wheel. three.js (MIT licence) is included in textacad/static/three, so the
viewer works without internet access.
"""
from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path

import streamlit.components.v1 as components

THREE_DIR = Path(__file__).with_name("static") / "three"

_TEMPLATE = r"""
<div id="wrap" style="position:relative;width:100%;height:__HEIGHT__px;border-radius:8px;overflow:hidden;
     background:linear-gradient(#f4f6f9,#dde3ea);font-family:sans-serif;">
  <div id="views" style="position:absolute;top:8px;left:8px;z-index:2;display:flex;gap:4px;">
    <button data-v="iso">Iso</button><button data-v="top">Superior</button>
    <button data-v="front">Frontal</button><button data-v="right">Lateral</button>
  </div>
  <div id="msg" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#567;">
    Carregant el visor 3D…</div>
</div>
<style>
  #views button{border:1px solid #b8c2cc;background:#fff;border-radius:4px;padding:3px 8px;
                font-size:12px;cursor:pointer;color:#234}
  #views button:hover{background:#e8eef5}
</style>
<script>
// The three.js files travel inside this page as text. We turn each one into a
// "blob" URL and use an import map so `import ... from "three"` finds them.
const LIBS = __LIBS__;
window.addEventListener("DOMContentLoaded", () => {
const blobUrl = src => URL.createObjectURL(new Blob([src], { type: "text/javascript" }));
const im = document.createElement("script");
im.type = "importmap";
im.textContent = JSON.stringify({ imports: { three: blobUrl(LIBS.three) } });
document.head.appendChild(im);
const main = document.getElementById("main-src").textContent
  .replace("__ORBIT_URL__", blobUrl(LIBS.orbit))
  .replace("__STLLOADER_URL__", blobUrl(LIBS.stl));
const mod = document.createElement("script");
mod.type = "module";
mod.textContent = main;
document.body.appendChild(mod);
});
</script>
<script type="text/plain" id="main-src">
import * as THREE from "three";
import { OrbitControls } from "__ORBIT_URL__";
import { STLLoader } from "__STLLOADER_URL__";

const wrap = document.getElementById("wrap");
const b64 = "__STL__";
const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
const geom = new STLLoader().parse(bytes.buffer);
geom.computeVertexNormals();
geom.computeBoundingBox();
const bb = geom.boundingBox, size = new THREE.Vector3(), center = new THREE.Vector3();
bb.getSize(size); bb.getCenter(center);
const radius = Math.max(size.length() / 2, 1);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(wrap.clientWidth, wrap.clientHeight);
wrap.appendChild(renderer.domElement);
document.getElementById("msg").remove();

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, wrap.clientWidth / wrap.clientHeight, radius / 100, radius * 100);
camera.up.set(0, 0, 1);                       // Z up, like SolidWorks "Isometric"

scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
scene.add(sun);

const mesh = new THREE.Mesh(geom, new THREE.MeshStandardMaterial({
  color: 0x6f9fd8, metalness: 0.1, roughness: 0.55,
  polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }));
scene.add(mesh);
// Sharp edges (angle > 25 deg) drawn as lines, so it looks like a CAD model.
scene.add(new THREE.LineSegments(new THREE.EdgesGeometry(geom, 25),
          new THREE.LineBasicMaterial({ color: 0x1f2d3d })));

// Grid on the XY plane (z = 0) with 10 mm squares, and small XYZ axes.
const gridSize = Math.ceil(Math.max(size.x, size.y) * 1.6 / 10) * 10 + 20;
const grid = new THREE.GridHelper(gridSize, gridSize / 10, 0x8a99a8, 0xc5ced8);
grid.rotation.x = Math.PI / 2;
grid.position.set(center.x, center.y, bb.min.z);
scene.add(grid);
const axes = new THREE.AxesHelper(radius * 0.4);
axes.position.set(bb.min.x - radius * 0.15, bb.min.y - radius * 0.15, bb.min.z);  // just outside the part
scene.add(axes);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.copy(center);
controls.enableDamping = true;

const dirs = { iso: [1, -1, 0.8], top: [0, 0, 1], front: [0, -1, 0], right: [1, 0, 0] };
function setView(name) {
  const d = new THREE.Vector3(...dirs[name]).normalize();
  const dist = radius / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * 1.15;
  camera.up.set(0, name === "top" ? 1 : 0, name === "top" ? 0 : 1);
  camera.position.copy(center).addScaledVector(d, dist);
  controls.target.copy(center);
  camera.lookAt(center);
  controls.update();
}
document.querySelectorAll("#views button").forEach(b => b.onclick = () => setView(b.dataset.v));
setView("iso");

new ResizeObserver(() => {
  camera.aspect = wrap.clientWidth / wrap.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(wrap.clientWidth, wrap.clientHeight);
}).observe(wrap);

(function loop() {
  requestAnimationFrame(loop);
  controls.update();
  sun.position.copy(camera.position);
  renderer.render(scene, camera);
})();
</script>
"""


@lru_cache(maxsize=1)
def _libs_json() -> str:
    libs = {
        "three": (THREE_DIR / "three.module.min.js").read_text(encoding="utf-8"),
        "orbit": (THREE_DIR / "OrbitControls.js").read_text(encoding="utf-8"),
        "stl": (THREE_DIR / "STLLoader.js").read_text(encoding="utf-8"),
    }
    # "</" inside a <script> would close it early: escape it.
    return json.dumps(libs).replace("</", "<\\/")


def viewer_html(stl_bytes: bytes, height: int = 520) -> str:
    return (
        _TEMPLATE.replace("__STL__", base64.b64encode(stl_bytes).decode("ascii"))
        .replace("__HEIGHT__", str(height))
        .replace("__LIBS__", _libs_json())
    )


def show_stl(stl_bytes: bytes, height: int = 520) -> None:
    """Draw the STL inside the Streamlit page."""
    components.html(viewer_html(stl_bytes, height), height=height + 10)
