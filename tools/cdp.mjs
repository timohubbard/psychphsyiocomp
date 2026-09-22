/**
 * Minimal Chrome DevTools Protocol driver, shared by the browser checks.
 *
 * Node 24's built-in WebSocket and fetch are enough; no puppeteer. Used by
 * smoke_capture.mjs (the capture page end to end) and verify_playback.mjs (the
 * annotation page's video source) — the two checks that have to be done in a
 * real browser because the failures they catch only exist there.
 */

import { spawn } from 'node:child_process';
import { existsSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';

export const CHROME_CANDIDATES = [
  process.env.CHROME,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
].filter(Boolean);

/** Launch Chrome with a throwaway profile. Returns { proc, page, browser }. */
export async function launch({ headed = false, port = 9333, profileName = 'chrome-cdp-profile',
                               extraArgs = [] } = {}) {
  const chrome = CHROME_CANDIDATES.find((p) => existsSync(p));
  if (!chrome) throw new Error('no Chrome found; set CHROME=<path>');
  const profile = resolve('tempdata', profileName);
  rmSync(profile, { recursive: true, force: true });

  const proc = spawn(chrome, [
    ...(headed ? [] : ['--headless=new']),
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    '--autoplay-policy=no-user-gesture-required',
    // A backgrounded tab suspends rAF and rVFC entirely (measured on this
    // project), and timers are throttled; neither is what a participant gets.
    '--disable-background-timer-throttling',
    '--disable-renderer-backgrounding',
    '--disable-backgrounding-occluded-windows',
    '--window-size=1280,800',
    ...extraArgs,
    'about:blank',
  ], { stdio: 'ignore' });

  let version;
  for (let i = 0; i < 60 && !version; i += 1) {
    try { version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(); } catch { await sleep(250); }
  }
  if (!version) { proc.kill(); throw new Error('Chrome did not open its debugging port'); }
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = connect(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
  const browser = connect(version.webSocketDebuggerUrl);
  return { proc, page, browser };
}

/** A CDP session over one WebSocket. */
export function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  const handlers = new Map();
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) {
      const { ok, fail } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) fail(new Error(`${msg.error.message} (${msg.error.code})`));
      else ok(msg.result);
    } else if (msg.method) {
      for (const h of handlers.get(msg.method) ?? []) h(msg.params);
    }
  };
  const open = new Promise((ok, fail) => { ws.onopen = ok; ws.onerror = fail; });
  const session = {
    async send(method, params = {}) {
      await open;
      id += 1;
      const myId = id;
      ws.send(JSON.stringify({ id: myId, method, params }));
      return new Promise((ok, fail) => pending.set(myId, { ok, fail }));
    },
    on(method, h) { handlers.set(method, [...(handlers.get(method) ?? []), h]); },
    /** Evaluate in the page, awaiting promises, returning a plain value. */
    async js(expression) {
      const r = await session.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      if (r.exceptionDetails) throw new Error(`page threw: ${r.exceptionDetails.exception?.description ?? r.exceptionDetails.text}`);
      return r.result.value;
    },
    /** Poll an expression until truthy. */
    async until(expression, what, ms = 30_000) {
      const end = Date.now() + ms;
      while (Date.now() < end) {
        if (await session.js(expression).catch(() => false)) return;
        await sleep(250);
      }
      throw new Error(`timed out waiting for ${what}`);
    },
  };
  return session;
}
