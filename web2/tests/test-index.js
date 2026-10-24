import { modules } from '../js/modules/index.js';

const links = document.querySelector('#links');

links.innerHTML = modules.map(module => `
  <li>
    <a href="./${module.key}.html">${module.title}</a>
    — ${module.description}（${module.commands.length} 项）
  </li>
`).join('') + `
  <li>
    <a href="./runtime-debug.html">代码单步调试</a>
    — 程序列表、复制 main.py 和 trace 单步执行
  </li>
`;

links.insertAdjacentHTML('beforeend', `
  <li>
    <a href="./joint-teaching.html">关节示教</a>
    — 读取和微调关节，创建全身、左右臂或任意单关节变量
  </li>
  <li>
    <a href="./pose-teaching.html">末端位姿与夹爪</a>
    — 左右末端坐标运动、坐标变量和双夹爪控制
  </li>
  <li>
    <a href="./urdf.html">Three.js / URDF 模型</a>
    — 解析机器人模型，并验证鼠标旋转和滚轮缩放
  </li>
  <li>
    <a href="./datastore.html">变量存储与运动</a>
    — 保存并读取当前关节、左右手关节和末端位姿
  </li>
  <li>
    <a href="/service-tests/maptest.html">地图与底盘测试</a>
    — 地图、激光、点位、电量、底盘遥控与点位同步
  </li>
  <li>
    <a href="/service-tests/camera.html">摄像头集成测试</a>
    — 四路相机单帧预览、关闭显示和自动保存拍照
  </li>
`);
