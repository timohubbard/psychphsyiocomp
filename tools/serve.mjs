#!/usr/bin/env node
/**
 * Static dev server for the capture page.
 *
 * Sends COOP/COEP so the page is cross-origin isolated, which unlocks the
 * finer performance.now() clamp (5us instead of 100us) — see REPORT.md §3.3
 * and web/src/clock.js. Also serves from the repo root rather than web/, since
 * the page imports the engine from engines/ and a browser cannot escape the
 * served root.
 */
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { join, extname, resolve, normalize, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = Number(process.env.PORT) || 5173;

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.task': 'application/octet-stream',
  '.wasm': 'application/wasm',
};

const server = createServer(async (req, res) => {
  try {
    const parsed = new URL(req.url, 'http://x');
    const urlPath = decodeURIComponent(parsed.pathname);

    // REDIRECT, not an internal rewrite. Serving web/index.html *at* `/` would
    // leave the document's base URL as `/`, so its relative `./src/main.js`
    // would resolve to `/src/main.js` — one directory above where the file
    // actually is — and 404 silently. The page still renders, because the HTML
    // and inline CSS are fine; it is just completely inert, which is a much
    // worse failure than a blank screen. Redirecting moves the base URL to
    // /web/index.html so relative imports resolve where the files are.
    //
    // The query string MUST survive the redirect. It did not, and `?study=`
    // lives there: `/?study=au-expressions` arrived as a bare /web/index.html,
    // the page fell back to m0, and a session meant to record posed facial
    // movements recorded the whole gaze pilot instead.
    if (urlPath === '/') {
      res.writeHead(302, { Location: `/web/index.html${parsed.search}` }).end();
      return;
    }

    // Contain path traversal: resolve, then confirm it stayed under ROOT.
    const filePath = resolve(join(ROOT, normalize(urlPath)));
    if (!filePath.startsWith(ROOT)) {
      res.writeHead(403).end('forbidden');
      return;
    }

    const info = await stat(filePath);
    if (info.isDirectory()) {
      res.writeHead(404).end('not found');
      return;
    }

    const body = await readFile(filePath);
    res.writeHead(200, {
      'Content-Type': TYPES[extname(filePath)] ?? 'application/octet-stream',
      // Cross-origin isolation, for the finer clock resolution.
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'credentialless',
      'Cache-Control': 'no-store',
    });
    res.end(body);
  } catch (err) {
    res.writeHead(err.code === 'ENOENT' ? 404 : 500).end(String(err.code ?? err));
  }
});

// A port already in use used to end in a raw EADDRINUSE stack trace. The
// likely cause is an earlier capture server still running — and that one is
// NOT equivalent to a fresh start: it re-reads the page files on every request,
// but its own routing (this file) is whatever was loaded when it started. That
// is how a server started before the `?study=` redirect fix kept dropping the
// query string after the fix was committed.
server.on('error', (err) => {
  if (err.code !== 'EADDRINUSE') throw err;
  console.error(`
  Port ${PORT} is already in use — probably an earlier capture server.

  If tools/serve.mjs has changed since it started, it is still running the OLD
  server code. Stop it and start again:
    Windows:  Get-NetTCPConnection -LocalPort ${PORT} -State Listen | % { Stop-Process -Id $_.OwningProcess }
    macOS:    lsof -ti tcp:${PORT} | xargs kill
  Or run this one elsewhere:  PORT=5180 npm run serve
`);
  process.exit(1);
});

server.listen(PORT, () => {
  console.log(`\n  capture page:  http://localhost:${PORT}/\n`);
  console.log('  Camera access needs a secure context; localhost counts as one.\n');
});
