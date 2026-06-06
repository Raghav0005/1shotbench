import http from 'node:http';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadCatalog, runEvaluation } from './anserini.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PUBLIC_DIR = path.join(ROOT, 'public');
const PORT = Number(process.env.PORT || 3000);

function sendJson(res, status, payload) {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store'
  });
  res.end(body);
}

function sendError(res, status, error) {
  sendJson(res, status, {
    error: error.message || String(error),
    artifactDir: error.artifactDir,
    failurePath: error.failurePath
  });
}

async function readBody(req) {
  let raw = '';
  for await (const chunk of req) raw += chunk.toString();
  if (!raw.trim()) return {};
  return JSON.parse(raw);
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8'
};

async function serveStatic(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const requested = url.pathname === '/' ? '/index.html' : url.pathname;
  const normalized = path.normalize(decodeURIComponent(requested)).replace(/^\.\.(\/|\\|$)/, '');
  const filePath = path.join(PUBLIC_DIR, normalized);
  if (!filePath.startsWith(PUBLIC_DIR)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }
  try {
    const data = await fs.readFile(filePath);
    res.writeHead(200, { 'content-type': MIME[path.extname(filePath)] || 'application/octet-stream' });
    res.end(data);
  } catch {
    res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
    res.end('Not found');
  }
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`);
    if (req.method === 'GET' && url.pathname === '/api/catalog') {
      const catalog = await loadCatalog({ force: url.searchParams.get('refresh') === '1' });
      sendJson(res, 200, catalog);
      return;
    }
    if (req.method === 'POST' && url.pathname === '/api/evaluate') {
      const body = await readBody(req);
      const result = await runEvaluation({ indexName: body.indexName, metricId: body.metricId });
      sendJson(res, 200, result);
      return;
    }
    if (req.method === 'GET' && url.pathname === '/api/health') {
      const catalog = await loadCatalog();
      sendJson(res, 200, { ok: true, fatjar: catalog.fatjar, java: catalog.java, indexes: catalog.indexes.length });
      return;
    }
    if (req.method === 'GET') {
      await serveStatic(req, res);
      return;
    }
    res.writeHead(405, { allow: 'GET, POST' });
    res.end('Method not allowed');
  } catch (error) {
    console.error(error);
    sendError(res, 500, error);
  }
});

server.listen(PORT, () => {
  console.log(`Anserini Prebuilt Index Evaluator listening on http://localhost:${PORT}`);
});
