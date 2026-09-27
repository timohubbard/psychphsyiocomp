#!/usr/bin/env node
/**
 * Check a deployment from the outside, the way a participant's browser meets it.
 *
 *   npm run deploy:check -- https://study.example.ac.uk
 *   npm run deploy:check -- http://localhost:5173 --allow-http     (local rehearsal)
 *
 * Every check is something the design relies on and a misconfiguration would
 * silently undo: HTTPS (the camera needs a secure context), the redirect that
 * keeps ?study= (a dropped query ran the wrong protocol once), the
 * cross-origin-isolation headers (the clock precision), the capture server
 * serving page code and nothing else, uploads reachable only through the
 * proxy, and the researcher app and ingest ports closed to the world.
 *
 * It sends nothing into the upload inbox: the one write it tries is a
 * malformed manifest the ingest service must reject.
 */

import net from 'node:net';

const argv = process.argv.slice(2);
const base = (argv.find((a) => !a.startsWith('--')) ?? '').replace(/\/$/, '');
const ALLOW_HTTP = argv.includes('--allow-http');
const EXPECT_UPLOAD = !argv.includes('--no-upload');

const checks = [];
const record = (name, ok, detail = '', level = 'fail') => checks.push({ name, ok, detail, level });

async function get(path, init = {}) {
  return fetch(base + path, { redirect: 'manual', cache: 'no-store', ...init });
}

function portOpen(host, port, ms = 3000) {
  return new Promise((resolve) => {
    const s = net.connect({ host, port });
    const done = (open) => { s.destroy(); resolve(open); };
    s.setTimeout(ms, () => done(false));
    s.on('connect', () => done(true));
    s.on('error', () => done(false));
  });
}

async function main() {
  if (!/^https?:\/\//.test(base)) throw new Error('usage: deploy_check.mjs <https://host> [--allow-http]');
  const url = new URL(base);
  const local = ['localhost', '127.0.0.1', '::1'].includes(url.hostname);

  // -- transport ---------------------------------------------------------
  const https = url.protocol === 'https:';
  record('served over HTTPS', https || ALLOW_HTTP,
    https ? '' : ALLOW_HTTP ? 'http allowed for a local rehearsal' : 'the camera needs a secure context');
  if (https && !local) {
    try {
      const plain = await fetch(`http://${url.host}/`, { redirect: 'manual' });
      const loc = plain.headers.get('location') ?? '';
      record('plain HTTP redirects to HTTPS', [301, 302, 307, 308].includes(plain.status) && loc.startsWith('https://'),
        `${plain.status} ${loc}`);
    } catch (err) {
      record('plain HTTP redirects to HTTPS', false, err.message);
    }
  }

  // -- the page ------------------------------------------------------------
  const root = await get('/?study=m0&PROLIFIC_PID=deploycheck');
  const loc = root.headers.get('location') ?? '';
  record('/?study= redirects and keeps the query', root.status === 302 && loc.includes('study=m0')
    && loc.includes('PROLIFIC_PID=deploycheck'), `${root.status} ${loc}`);

  const page = await get('/web/index.html');
  record('capture page loads', page.status === 200, String(page.status));
  record('cross-origin isolated (COOP same-origin)',
    page.headers.get('cross-origin-opener-policy') === 'same-origin', page.headers.get('cross-origin-opener-policy') ?? 'missing');
  record('cross-origin isolated (COEP)', !!page.headers.get('cross-origin-embedder-policy'),
    page.headers.get('cross-origin-embedder-policy') ?? 'missing');
  if (https) {
    record('HSTS set', !!page.headers.get('strict-transport-security'),
      page.headers.get('strict-transport-security') ?? 'missing');
  }
  record('no Server header naming the software', !page.headers.get('server') || local,
    page.headers.get('server') ?? '', 'warn');

  const index = await get('/studies/index.json');
  let studies = [];
  try { studies = (await index.json()).studies ?? []; } catch { /* checked below */ }
  record('study index loads', index.status === 200 && studies.length > 0, `${studies.length} studies`);
  let participantStudies = 0;
  for (const id of studies) {
    const r = await get(`/studies/${id}.json`);
    let s = null;
    try { s = await r.json(); } catch { /* reported */ }
    record(`study ${id} loads`, r.status === 200 && s?.study_id === id, String(r.status));
    if (s?.audience === 'participants') participantStudies += 1;
  }
  record('at least one study is approved for participants', participantStudies > 0,
    participantStudies ? `${participantStudies}` : 'all deployed studies are developer self-tests — nobody can be run as a participant yet',
    'warn');

  // -- what must not be served ------------------------------------------------
  for (const path of ['/tempdata/', '/out/', '/README.md', '/server/app.py', '/.git/config',
    '/out/_keys/pseudonym.key', '/web/../tempdata/', '/deploy/env.example']) {
    const r = await get(path);
    record(`not served: ${path}`, r.status === 403 || r.status === 404, String(r.status));
  }

  // -- uploads ---------------------------------------------------------------
  const health = await get('/ingest/health');
  if (EXPECT_UPLOAD) {
    record('uploads reachable through the proxy', health.status === 200, String(health.status));
    // A manifest naming another session: the ingest service must refuse it
    // (400) — proving the proxy authenticated (not 401) without storing anything.
    const probe = await get('/ingest/deploycheck/session.json', {
      method: 'PUT', body: JSON.stringify({ session_id: 'someone-else' }),
      headers: { 'content-type': 'application/json' },
    });
    record('ingest rejects a bad manifest (proxy authenticated)', probe.status === 400,
      `${probe.status}${probe.status === 401 ? ' — the proxy is not adding the token' : ''}`);
  } else {
    record('uploads not exposed', health.status === 404, String(health.status), 'warn');
  }

  // -- ports that must be closed to the world -------------------------------
  if (!local) {
    for (const [port, what] of [[5173, 'capture server'], [5174, 'researcher app'], [5175, 'ingest service']]) {
      const open = await portOpen(url.hostname, port);
      record(`port ${port} (${what}) closed from outside`, !open, open ? 'OPEN' : 'closed');
    }
  }
}

main()
  .catch((err) => record('check ran', false, err.message))
  .finally(() => {
    console.log(`\n  DEPLOY CHECK  ${base}`);
    console.log('  ' + '-'.repeat(72));
    for (const c of checks) {
      const tag = c.ok ? 'PASS' : c.level === 'warn' ? 'WARN' : 'FAIL';
      console.log(`  [${tag}]  ${c.name.padEnd(48)} ${c.detail}`);
    }
    const failed = checks.filter((c) => !c.ok && c.level !== 'warn');
    console.log(`\n  ${failed.length ? `DEPLOY CHECK FAILED (${failed.length})` : 'DEPLOY CHECK OK'}\n`);
    process.exitCode = failed.length ? 1 : 0;
  });
