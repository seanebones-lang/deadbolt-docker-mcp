'use strict';

// Host-side launcher. This file exposes no operator commands as MCP tools.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn, spawnSync } = require('node:child_process');

const TARGETS = {
  'darwin-arm64': 'aarch64-apple-darwin',
  'darwin-x64': 'x86_64-apple-darwin',
  'linux-x64': 'x86_64-unknown-linux-gnu',
  'linux-arm64': 'aarch64-unknown-linux-gnu',
  'win32-x64': 'x86_64-pc-windows-msvc',
};
function fail(code) { throw new Error(code); }
function token(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_.:@/+\-]{1,128}$/.test(value)) fail('invalid_token');
  return value;
}
function absolute(value) {
  if (typeof value !== 'string' || !path.isAbsolute(value) || value.includes('\0')) fail('absolute_path_required');
  return value;
}
function list(value, required = false) {
  if (!Array.isArray(value) || value.length > 256 || (required && !value.length)) fail('explicit_policy_required');
  return value.map(token);
}
function readConfig(file) {
  absolute(file);
  if (fs.statSync(file).size > 65536) fail('config_too_large');
  const c = JSON.parse(fs.readFileSync(file, 'utf8'));
  const keys = ['version', 'agent', 'database', 'events', 'command', 'args', 'tools', 'destinations', 'irreversible_tools', 'spend_cap_usd'];
  if (!c || typeof c !== 'object' || Array.isArray(c) || Object.keys(c).some(k => !keys.includes(k)) || c.version !== 1) fail('invalid_config');
  token(c.agent);
  absolute(c.database); absolute(c.events); absolute(c.command);
  if (c.database === c.events || c.database === file || c.events === file) fail('distinct_paths_required');
  if (!Array.isArray(c.args) || c.args.length > 256 || c.args.some(a => typeof a !== 'string' || a.length > 16384 || a.includes('\0'))) fail('invalid_arguments');
  list(c.tools, true); list(c.destinations); list(c.irreversible_tools);
  if (c.irreversible_tools.some(t => !c.tools.includes(t))) fail('irreversible_tool_not_allowed');
  if (!Number.isFinite(c.spend_cap_usd) || c.spend_cap_usd < 0) fail('invalid_spend_cap');
  // Operator creates this directory and controls its filesystem permissions.
  for (const p of [c.database, c.events]) if (!fs.statSync(path.dirname(p)).isDirectory()) fail('state_directory_required');
  return c;
}
function binary(root, platform = process.platform, arch = process.arch) {
  const target = TARGETS[`${platform}-${arch}`];
  if (!target) fail('unsupported_platform');
  const file = path.join(root, 'native', target, platform === 'win32' ? 'deadbolt.exe' : 'deadbolt');
  const provenance = JSON.parse(fs.readFileSync(path.join(root, 'PROVENANCE.json'), 'utf8'));
  const expected = provenance.binaries[target]?.binary_sha256;
  if (!expected || crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') !== expected) fail('binary_checksum_mismatch');
  if (platform !== 'win32' && !(fs.statSync(file).mode & 0o111)) fs.chmodSync(file, 0o755);
  return file;
}
function environment(c) {
  const env = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.toUpperCase().startsWith('DEADBOLT_')));
  return { ...env, DEADBOLT_DB: c.database, DEADBOLT_EVENTS: c.events };
}
function runOperator(exe, c, args) {
  const r = spawnSync(exe, args, { env: environment(c), encoding: 'utf8', timeout: 10000, maxBuffer: 1048576, windowsHide: true, shell: false });
  if (r.error || r.status !== 0) fail('operator_setup_failed');
  return r.stdout;
}
function start(root, file) {
  const c = readConfig(file), exe = binary(root), env = environment(c);
  // Create a missing lease using the verified engine's version command, never
  // the configured server or process.execPath (an Electron helper in some hosts).
  // ensure_agent preserves terminal kill and does not renew an expired lease.
  runOperator(exe, c, ['mcp-proxy', '--agent', c.agent, '--', exe, '--version']);
  runOperator(exe, c, ['policy', '--agent', c.agent, '--tools', c.tools.join(','),
    '--dest', c.destinations.join(','), '--irreversible', c.irreversible_tools.join(','),
    '--spend-cap', String(c.spend_cap_usd)]);
  const child = spawn(exe, ['mcp-proxy', '--agent', c.agent, '--', c.command, ...c.args],
    { env, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true, shell: false });
  // Embedded hosts bridge JS writes to MCP; inherited native descriptors bypass
  // that bridge. Forward all streams explicitly in both ordinary and hosted Node.
  child.stdout.pipe(process.stdout);
  child.stderr.pipe(process.stderr);
  process.stdin.pipe(child.stdin);
  child.stdin.on('error', () => {}); // Native failure may close the pipe first.
  let timer;
  const stop = () => {
    process.stdin.unpipe(child.stdin);
    process.stdin.pause();
    child.stdin.end(); // EOF lets DeadBolt reap its immediate child.
    timer ??= setTimeout(() => child.kill(), 4000);
    timer.unref();
  };
  process.once('SIGINT', stop); process.once('SIGTERM', stop);
  child.once('error', () => { process.stderr.write('deadbolt-bundle:proxy_start_failed\n'); process.exitCode = 1; process.stdin.destroy(); });
  child.once('exit', code => {
    clearTimeout(timer); process.stdin.destroy();
    process.exitCode = Number.isInteger(code) ? code : 1;
  });
}
// This is an executable entry point, including when an MCP host imports it.
// A require.main guard silently skips startup in embedded Node runtimes.
try {
  if (process.argv.length < 2 || process.argv.length > 3) fail('invalid_arguments');
  const root = path.resolve(__dirname, '..');
  if (process.argv.length === 2 || process.argv[2] === '' || process.argv[2] === '${user_config.operator_config}') require('./setup.cjs').serve(root);
  else start(root, process.argv[2]);
} catch {
  // Do not echo configuration, paths, downstream arguments or credentials.
  process.stderr.write('deadbolt-bundle:setup_failed (check README and operator configuration)\n');
  process.exitCode = 1;
}
