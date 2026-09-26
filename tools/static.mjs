/**
 * Serving a file the way a <video> needs it served: byte ranges, HTTP/1.1.
 *
 * Shared by the capture dev server (serve.mjs) and the playback control
 * (verify_playback.mjs --control). Chrome's media stack asks for ranges and
 * will not play a stimulus video — or seek in a recording — from a server that
 * answers every request with the whole file; the researcher app learned the
 * same thing in Python (app.py sets HTTP/1.1 for exactly this reason).
 */

import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { extname } from 'node:path';

export const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.task': 'application/octet-stream',
  '.wasm': 'application/wasm',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.webm': 'video/webm',
  '.mp4': 'video/mp4',
};

/**
 * Parse a single-range `Range: bytes=...` header against a file size.
 *
 * Returns null when there is no usable header (serve the whole file),
 * 'unsatisfiable' for a range wholly past the end (416), or {start, end}
 * inclusive. Multi-range requests are answered with the whole file, which
 * RFC 9110 permits and no media element needs otherwise.
 */
export function parseRange(header, size) {
  if (!header) return null;
  const m = /^bytes=(\d*)-(\d*)$/.exec(String(header).trim());
  if (!m) return null;
  const [, a, b] = m;
  if (a === '' && b === '') return null;
  let start;
  let end;
  if (a === '') {
    // Suffix range: the last N bytes.
    const n = Number(b);
    if (n === 0) return 'unsatisfiable';
    start = Math.max(0, size - n);
    end = size - 1;
  } else {
    start = Number(a);
    end = b === '' ? size - 1 : Math.min(Number(b), size - 1);
  }
  if (start >= size || start > end) return 'unsatisfiable';
  return { start, end };
}

/** Send a file, honouring a Range header. Extra headers are added to every response. */
export async function sendFile(req, res, filePath, extraHeaders = {}) {
  const info = await stat(filePath);
  const type = TYPES[extname(filePath).toLowerCase()] ?? 'application/octet-stream';
  const base = { 'Content-Type': type, 'Accept-Ranges': 'bytes', ...extraHeaders };
  const range = parseRange(req.headers.range, info.size);

  if (range === 'unsatisfiable') {
    res.writeHead(416, { ...base, 'Content-Range': `bytes */${info.size}` }).end();
    return;
  }
  if (range) {
    res.writeHead(206, {
      ...base,
      'Content-Range': `bytes ${range.start}-${range.end}/${info.size}`,
      'Content-Length': range.end - range.start + 1,
    });
    if (req.method === 'HEAD') { res.end(); return; }
    createReadStream(filePath, { start: range.start, end: range.end }).pipe(res);
    return;
  }
  res.writeHead(200, { ...base, 'Content-Length': info.size });
  if (req.method === 'HEAD') { res.end(); return; }
  createReadStream(filePath).pipe(res);
}
