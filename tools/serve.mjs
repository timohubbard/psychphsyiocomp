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
import { stat } from 'node:fs/promises';
import { join, resolve, normalize, dirname, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { sendFile } from './static.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = Number(process.env.PORT) || 5173;

/**
 * The only top-level folders the capture page loads from. An ALLOW list,
 * because this server used to serve the whole repo root on every network
 * interface — tempdata/ (participant recordings) and out/ (every derived
 * measurement) included, to anyone on the same network while it ran. The
 * face model comes from Google's CDN, not models/.
 */
const SERVED = new Set(['web', 'engines', 'studies']);

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

    // Contain path traversal: resolve, then confirm it stayed under ROOT and
    // inside a served folder. `relative` rather than a string prefix, so
    // C:\repo-other is not "under" C:\repo.
    const filePath = resolve(join(ROOT, normalize(urlPath)));
    const rel = relative(ROOT, filePath);
    if (rel.startsWith('..') || !SERVED.has(rel.split(sep)[0])) {
      res.writeHead(403).end('forbidden');
      return;
    }

    const info = await stat(filePath);
    if (info.isDirectory()) {
      res.writeHead(404).end('not found');
      return;
    }

    await sendFile(req, res, filePath, {
      // Cross-origin isolation, for the finer clock resolution.
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'credentialless',
      'Cache-Control': 'no-store',
    });
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

// Loopback only, like the researcher app. Camera access needs a secure context
// and localhost is one; nothing else needs to reach a development server.
server.listen(PORT, '127.0.0.1', () => {
  console.log(`\n  capture page:  http://localhost:${PORT}/\n`);
  console.log('  Camera access needs a secure context; localhost counts as one.\n');
});
