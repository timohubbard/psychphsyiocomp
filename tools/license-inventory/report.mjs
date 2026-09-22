#!/usr/bin/env node
/**
 * License inventory — the "what would we rip out if we went commercial?" report.
 *
 * This build targets ACADEMIC / NON-PROFIT use, which is what makes OpenFace 3.0,
 * LibreFace and openSMILE usable at all. Several of those forbid commercial use
 * outright:
 *
 *   OpenFace 3.0   "ACADEMIC OR NON-PROFIT ORGANIZATION NONCOMMERCIAL RESEARCH
 *                   USE ONLY" — also bars providing third parties access
 *   openSMILE 3.0  "not allowed to use the open-source version of openSMILE for
 *                   any sort of commercial product"
 *   LibreFace      USC research licence
 *   audEERING SER  CC-BY-NC-SA-4.0
 *   rPPG-Toolbox   Responsible AI License — use-based restrictions, not OSI
 *
 * That is a fine position to be in. What is NOT fine is discovering the extent
 * of it eighteen months later. Every engine declares its licence in its
 * manifest; this walks them and prints the inventory.
 *
 * Exit codes:
 *   0  inventory printed (default, and the academic-build expectation)
 *   1  --fail-on-restricted was passed and a restricted engine is installed
 *   2  a manifest is missing required licence fields, or unreadable
 *
 * Usage:
 *   node tools/license-inventory/report.mjs
 *   node tools/license-inventory/report.mjs --json
 *   node tools/license-inventory/report.mjs --fail-on-restricted   # commercial build gate
 */

import { readdir, readFile, stat } from 'node:fs/promises';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const ENGINES_DIR = join(REPO_ROOT, 'engines');

const args = new Set(process.argv.slice(2));
const asJson = args.has('--json');
const failOnRestricted = args.has('--fail-on-restricted');

/** Engines are discovered by the presence of engine.manifest.json. */
async function findManifests(dir) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch (err) {
    if (err.code === 'ENOENT') return [];
    throw err;
  }

  const found = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const manifestPath = join(dir, entry.name, 'engine.manifest.json');
    try {
      await stat(manifestPath);
      found.push({ dir: entry.name, path: manifestPath });
    } catch {
      // Not an engine directory; ignore.
    }
  }
  return found;
}

const REQUIRED = ['engine_id', 'version', 'modality', 'license'];
const REQUIRED_LICENSE = ['spdx', 'commercial_use', 'url'];

function validate(manifest, path) {
  const problems = [];
  for (const field of REQUIRED) {
    if (manifest[field] === undefined) problems.push(`missing '${field}'`);
  }
  if (manifest.license) {
    for (const field of REQUIRED_LICENSE) {
      if (manifest.license[field] === undefined) {
        problems.push(`missing 'license.${field}'`);
      }
    }
    const use = manifest.license.commercial_use;
    if (use !== undefined && !['yes', 'no', 'unknown'].includes(use)) {
      problems.push(`license.commercial_use must be yes|no|unknown, got '${use}'`);
    }
  }
  return problems.map((p) => ({ path, problem: p }));
}

function bucket(manifest) {
  const use = manifest.license?.commercial_use;
  if (use === 'no') return 'restricted';
  // Fail safe, not fail open. A manifest that omits commercial_use, or carries
  // a value we do not recognise, is treated as unverified — never as permissive.
  // Defaulting the other way would let the one field this tool exists to
  // protect go missing silently.
  if (use !== 'yes') return 'unverified';
  return 'permissive';
}

const BUCKET_LABEL = {
  permissive: 'Commercial use OK',
  restricted: 'RESEARCH / NON-PROFIT ONLY',
  unverified: 'UNVERIFIED — licence not confirmed',
};

function pad(s, n) {
  s = String(s ?? '');
  return s.length >= n ? s : s + ' '.repeat(n - s.length);
}

async function main() {
  const manifestFiles = await findManifests(ENGINES_DIR);

  const engines = [];
  const problems = [];

  for (const { path } of manifestFiles) {
    let manifest;
    try {
      manifest = JSON.parse(await readFile(path, 'utf8'));
    } catch (err) {
      problems.push({ path, problem: `unreadable or invalid JSON: ${err.message}` });
      continue;
    }
    problems.push(...validate(manifest, path));
    engines.push({ manifest, path, bucket: bucket(manifest) });
  }

  const byBucket = {
    permissive: engines.filter((e) => e.bucket === 'permissive'),
    restricted: engines.filter((e) => e.bucket === 'restricted'),
    unverified: engines.filter((e) => e.bucket === 'unverified'),
  };

  if (asJson) {
    console.log(
      JSON.stringify(
        {
          build_target: 'academic-nonprofit',
          engine_count: engines.length,
          buckets: Object.fromEntries(
            Object.entries(byBucket).map(([k, v]) => [
              k,
              v.map((e) => ({
                engine_id: e.manifest.engine_id,
                version: e.manifest.version,
                modality: e.manifest.modality,
                spdx: e.manifest.license?.spdx,
                url: e.manifest.license?.url,
                notes: e.manifest.license?.notes,
                training_datasets: e.manifest.provenance?.training_datasets ?? [],
              })),
            ]),
          ),
          problems,
        },
        null,
        2,
      ),
    );
  } else {
    console.log('');
    console.log('  LICENCE INVENTORY  ·  build target: academic / non-profit');
    console.log('  ' + '-'.repeat(72));

    if (engines.length === 0) {
      console.log('  No engines found under engines/ (nothing installed yet).');
    }

    for (const key of ['restricted', 'unverified', 'permissive']) {
      const list = byBucket[key];
      if (list.length === 0) continue;
      console.log('');
      console.log(`  ${BUCKET_LABEL[key]}  (${list.length})`);
      for (const e of list) {
        const m = e.manifest;
        console.log(
          `    ${pad(m.engine_id, 34)} ${pad(m.version, 9)} ${pad(m.modality, 13)} ${m.license?.spdx ?? '?'}`,
        );
        if (m.license?.notes) console.log(`        note: ${m.license.notes}`);
        const ds = m.provenance?.training_datasets ?? [];
        if (key !== 'permissive' && ds.length) {
          console.log(`        trained on: ${ds.join(', ')}`);
        }
      }
    }

    const blocking = byBucket.restricted.length + byBucket.unverified.length;
    console.log('');
    console.log('  ' + '-'.repeat(72));
    if (blocking === 0) {
      console.log('  All installed engines permit commercial use.');
    } else {
      console.log(
        `  ${blocking} engine(s) would need replacing to go commercial:`,
      );
      for (const e of [...byBucket.restricted, ...byBucket.unverified]) {
        console.log(`    - ${e.manifest.engine_id} (${e.manifest.modality})`);
      }
      console.log('');
      console.log('  This is expected for an academic build. The list exists so the');
      console.log('  answer is never stale — not because anything is wrong.');
    }

    if (problems.length) {
      console.log('');
      console.log(`  MANIFEST PROBLEMS (${problems.length}) — these must be fixed:`);
      for (const p of problems) {
        console.log(`    ${p.path}`);
        console.log(`      ${p.problem}`);
      }
    }
    console.log('');
  }

  if (problems.length) process.exit(2);
  if (failOnRestricted && byBucket.restricted.length + byBucket.unverified.length > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(2);
});
