#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { pathToFileURL, fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const candidates = [
  path.join(__dirname, 'detector', 'detect-antipatterns.mjs'),
  path.join(__dirname, '..', '..', 'cli', 'engine', 'detect-antipatterns.mjs'),
];
const detectorPath = candidates.find(p => fs.existsSync(p));

if (!detectorPath) {
  const fallback = spawnSync('npx', ['impeccable', 'detect', ...process.argv.slice(2)], {
    stdio: 'inherit',
    shell: false,
  });
  process.exit(fallback.status ?? 1);
}

const { detectCli } = await import(pathToFileURL(detectorPath));

await detectCli();
