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
