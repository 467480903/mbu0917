import { modules } from '../js/modules/index.js';

const links = document.querySelector('#links');

links.innerHTML = modules.map(module => `
  <article class="card">
    <h2>${module.title}</h2>
    <p>${module.description}</p>
    <a class="test-link" href="./${module.key}.html">
      打开 ${module.commands.length} 项功能测试 →
    </a>
  </article>
`).join('');
