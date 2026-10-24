const http = require('http');
const fs = require('fs');
const path = require('path');

const root = __dirname;
const serviceTestsRoot = path.resolve(__dirname, '..', 'test', 'services2');
const imagesRoot = path.resolve(__dirname, '..', 'images');
const legacyRoot = path.resolve(__dirname, '..', 'web');
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
  '.stl': 'model/stl',
  '.urdf': 'application/xml; charset=utf-8',
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
  const isServiceTest = pathname.startsWith('/service-tests/');
  const isImage = pathname.startsWith('/images/');
  const isLegacy = pathname.startsWith('/legacy/');
  const selectedRoot = isServiceTest
    ? serviceTestsRoot
    : (isImage ? imagesRoot : (isLegacy ? legacyRoot : root));
  const relative = isServiceTest
    ? pathname.slice('/service-tests/'.length)
    : (isImage
      ? pathname.slice('/images/'.length)
      : (isLegacy
        ? pathname.slice('/legacy/'.length)
        : (pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, ''))));
  const filename = path.resolve(selectedRoot, relative);
  if (filename !== selectedRoot && !filename.startsWith(selectedRoot + path.sep)) {
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
