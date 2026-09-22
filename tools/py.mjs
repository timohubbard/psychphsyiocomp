#!/usr/bin/env node
/**
 * Cross-platform venv Python launcher.
 *
 * npm runs scripts through cmd.exe on Windows and sh elsewhere, so a single
 * hardcoded interpreter path cannot work in both. This resolves the venv
 * interpreter for the current platform and forwards its exit code, so a failing
 * pytest run actually fails `npm run check` rather than passing silently.
 *
 * Usage:  node tools/py.mjs -m pytest
 */

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

/** venv layout differs by platform: Scripts/python.exe vs bin/python. */
const CANDIDATES = [
  join(REPO_ROOT, '.venv', 'Scripts', 'python.exe'),
  join(REPO_ROOT, '.venv', 'bin', 'python3'),
  join(REPO_ROOT, '.venv', 'bin', 'python'),
];

const interpreter = CANDIDATES.find((p) => existsSync(p));

if (!interpreter) {
  console.error('');
  console.error('  No virtualenv found at .venv/');
  console.error('');
  console.error('  Create one, then install dependencies:');
  console.error('    py -m venv .venv                     (Windows)');
  console.error('    python3 -m venv .venv                (macOS/Linux)');
  console.error('    node tools/py.mjs -m pip install -r requirements.txt');
  console.error('    node tools/py.mjs tools/fetch_models.py');
  console.error('');
  process.exit(127);
}

const result = spawnSync(interpreter, process.argv.slice(2), {
  stdio: 'inherit',
  cwd: REPO_ROOT,
});

if (result.error) {
  console.error(`  Failed to launch ${interpreter}: ${result.error.message}`);
  process.exit(127);
}

// Forward the real exit code — a failing test run must fail the npm script.
process.exit(result.status ?? 1);
