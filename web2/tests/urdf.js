import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import URDFLoader from 'urdf-loader';

const viewer = document.querySelector('#viewer');
const status = document.querySelector('#status');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xffffff);

const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
viewer.appendChild(renderer.domElement);

scene.add(new THREE.HemisphereLight(0xffffff, 0x555555, 2));
const keyLight = new THREE.DirectionalLight(0xffffff, 2);
keyLight.position.set(4, 8, 5);
scene.add(keyLight);
scene.add(new THREE.GridHelper(8, 16, 0x444444, 0xcccccc));

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.target.set(0, 0.8, 0);

const state = { loaded: false, meshCount: 0, jointCount: 0, frames: 0, errors: [] };
let robot = null;

function cameraState() {
  return {
    position: camera.position.toArray().map(value => Number(value.toFixed(5))),
    target: controls.target.toArray().map(value => Number(value.toFixed(5))),
  };
}

function resize() {
  const width = viewer.clientWidth;
  const height = viewer.clientHeight;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function resetView() {
  camera.position.set(3, 1.8, 3);
  controls.target.set(0, 0.8, 0);
  controls.update();
}

function loadRobot() {
  status.textContent = '正在读取模型…';
  state.loaded = false;
  state.meshCount = 0;
  state.jointCount = 0;
  state.errors.length = 0;
  if (robot) scene.remove(robot);

  const stlLoader = new STLLoader();
  const loader = new URDFLoader();
  loader.loadMeshCb = (meshPath, manager, done) => {
    let cleanPath = new URL(meshPath, location.href).pathname;
    cleanPath = decodeURIComponent(cleanPath)
      .replace(/^\/?legacy\/meshes\//, '')
      .replace(/^\/?meshes\//, '')
      .replace(/^\.?\//, '')
      .replace(/\.stl$/i, '.STL');
    const url = `/legacy/meshes/${cleanPath}`;
    stlLoader.load(url, geometry => {
      state.meshCount += 1;
      done(new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xb8bec8, roughness: 0.7 })));
    }, undefined, error => {
      state.errors.push(url);
      console.error('STL 加载失败', url, error);
      done(new THREE.Mesh());
    });
  };

  loader.load('/legacy/meshes/model.urdf', loadedRobot => {
    robot = loadedRobot;
    robot.rotation.x = -Math.PI / 2;
    scene.add(robot);
    state.jointCount = Object.keys(robot.joints || {}).length;

    const box = new THREE.Box3().setFromObject(robot);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const distance = Math.max(size.x, size.y, size.z, 1) * 1.8;
    camera.position.set(center.x + distance, center.y + distance * 0.6, center.z + distance);
    controls.target.copy(center);
    controls.update();
    state.loaded = true;
    status.textContent = `读取完成：${state.jointCount} 个关节，已加载 ${state.meshCount} 个网格`;
  }, undefined, error => {
    state.errors.push('model.urdf');
    status.textContent = `读取失败：${error.message || error}`;
    console.error('URDF 加载失败', error);
  });
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
  state.frames += 1;
}

document.querySelector('#load').addEventListener('click', loadRobot);
document.querySelector('#reset').addEventListener('click', resetView);
window.addEventListener('resize', resize);

window.__URDF_TEST__ = {
  state,
  getCameraState: cameraState,
  loadRobot,
};

resize();
resetView();
animate();
