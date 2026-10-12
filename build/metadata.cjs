'use strict';

// Build-time metadata describes this image's source-built executable. It is not
// an independent signature or the hash of the previously released MCPB binary.
const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');
const source = JSON.parse(fs.readFileSync('SOURCE.json', 'utf8'));
const target = { x64: 'x86_64-unknown-linux-gnu', arm64: 'aarch64-unknown-linux-gnu' }[process.arch];
if (process.platform !== 'linux' || !target) throw new Error('Unsupported container target');
const directory = path.join('native', target);
fs.mkdirSync(directory, { recursive: true });
fs.copyFileSync('/usr/local/bin/deadbolt', path.join(directory, 'deadbolt'));
fs.chmodSync(path.join(directory, 'deadbolt'), 0o555);
fs.writeFileSync('PROVENANCE.json', JSON.stringify({
  engine_version: source.engine_version,
  source_revision: source.engine_revision,
  source_archive_sha256: source.engine_archive_sha256,
  distribution: 'Source-built container; no independent signature certification',
  binaries: { [target]: {
    binary_sha256: crypto.createHash('sha256').update(fs.readFileSync('/usr/local/bin/deadbolt')).digest('hex'),
    source_revision: source.engine_revision,
  } },
}, null, 2) + '\n');
