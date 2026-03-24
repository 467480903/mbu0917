const http = require('http');
const fs = require('fs');
const path = require('path');

const root = __dirname;
const host = process.env.HOST || '0.0.0.0';
const port = Number(process.env.PORT || 8003);
const mimeTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
};

http.createServer((request, response) => {
  if (request.url === '/favicon.ico') {
    response.writeHead(204).end();
    return;
  }
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  } catch (_) {
    response.writeHead(400).end('Bad request');
    return;
  }
  const relative = pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '');
  const filename = path.resolve(root, relative);
  if (filename !== root && !filename.startsWith(root + path.sep)) {
    response.writeHead(403).end('Forbidden');
    return;
  }
  fs.stat(filename, (statError, stat) => {
    const target = !statError && stat.isDirectory() ? path.join(filename, 'index.html') : filename;
    fs.readFile(target, (error, data) => {
      if (error) {
        response.writeHead(error.code === 'ENOENT' ? 404 : 500).end('Not found');
        return;
      }
      response.writeHead(200, {
        'Content-Type': mimeTypes[path.extname(target).toLowerCase()] || 'application/octet-stream',
        'Cache-Control': 'no-store',
      });
      response.end(data);
    });
  });
}).listen(port, host, () => {
  console.log(`[web2] http://${host}:${port}`);
});
