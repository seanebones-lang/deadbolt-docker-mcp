'use strict';

// Read-only onboarding. No operator state, downstream process or network access.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const annotations = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false };
const string = description => ({ type: 'string', description });
const strings = description => ({ type: 'array', description, items: { type: 'string' } });
const object = properties => ({ type: 'object', properties, required: Object.keys(properties), additionalProperties: false });
const boundary = 'Setup mode only: no downstream server is running and no tools are protected. Configured mode gates routed tools/call requests, not startup, other MCP methods or arbitrary OS access. The downstream server remains trusted; this is not a sandbox or certification.';
const definitions = [
  {
    name: 'deadbolt_get_integration_guide',
    description: 'Get local, read-only DeadBolt setup steps for a supported integration route. Returns operator responsibilities, a placeholder configuration and the enforcement boundary. Does not create files, run a server or grant permission. Available only when operator configuration is blank.',
    inputSchema: object({ route: { type: 'string', enum: ['claude_desktop', 'stdio_client', 'rust', 'http'], description: 'Integration route: claude_desktop for this bundle, stdio_client for a terminal/editor MCP client, rust for embedding the crate, or http for the local sidecar.' } }),
    outputSchema: object({ route: string('Requested integration route.'), steps: strings('Ordered steps for the trusted developer/operator.'), operator_config_example: string('JSON template for the bundle; replace all placeholders deliberately. This tool does not save or apply it.'), boundary: string('Protection scope and setup-mode limitation.'), documentation_url: string('Official integration documentation URL; this tool performs no network request.') }),
    annotations,
  },
  {
    name: 'deadbolt_check_bundle',
    description: 'Read the bundled engine and provenance metadata, calculate its SHA-256 and report compatibility and packaging integrity for this host. Reads only this installed bundle; does not execute the engine, inspect operator state or test security. Available only when operator configuration is blank.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
    outputSchema: object({ bundle_version: string('Installed launcher bundle version.'), engine_version: string('Pinned stable engine version.'), target: string('Native target for this host, or unsupported.'), checksum_matches: { type: 'boolean', description: 'Whether the bundled executable matches its packaged SHA-256 metadata. This is corruption detection, not independent signature verification.' }, active_protection: { type: 'boolean', const: false, description: 'Always false in setup mode; no downstream server is configured.' }, boundary: string('Protection scope and setup-mode limitation.') }),
    annotations,
  },
];
function guide(route) {
  const common = [
    'Choose a downstream MCP server you trust. Its startup and ordinary OS access are outside the tool-call gate.',
    'Create private configuration and state folders outside agent-editable workspaces. Use container-absolute executable and state paths, an explicit nonempty tool allow-list, destination tokens and irreversible-tool classification. Put the trusted downstream server inside a derived image.',
    'For configured mode, explicitly bind the private configuration read-only at /operator, and private state read-write at /state. Set DEADBOLT_OPERATOR_CONFIG=/operator/config.json. Run with your operator UID/GID so that only you can write the state. Restart the container to change configuration. Invalid supplied configuration refuses startup.',
    'Verify allowed and denied dummy effects before connecting real accounts. Keep approval, pause, clip and kill with the local operator CLI. Client consent is separate from DeadBolt approval.',
    'The stable engine uses a 60-second sliding lease. Silence expires it; choose a fresh operator-assigned agent ID for a new run. Never reuse a killed ID or share one ID across concurrent sessions.',
  ];
  const routes = {
    claude_desktop: ['Configure Claude Desktop to launch docker run --rm -i with this image. Docker must be running. Do not add -t: the MCP transport is newline-delimited JSON over stdin/stdout.', ...common, 'Restart the MCP connection after configuration. Check local operator incident evidence for generic client denials.'],
    stdio_client: ['Run this container with docker run --rm -i, without a pseudo-terminal. No config or mounts are needed for read-only setup; this mode provides no active protection.', ...common, 'Only a downstream process inside this container is gated. Other Docker MCP servers, client built-in tools and host processes are not protected. Do not mount the Docker socket or your home folder to make host tools accessible. Follow the runnable disposable container example in the documentation.'],
    rust: ['Follow the build-in Rust example linked below. Put admission directly before each external effect and fail on denial or unavailable state.', 'Keep operator policy and approval access separate from the agent. Check decision evidence and executor outcomes using disposable effects.', 'This bundle configuration template is for the stdio launcher, not the Rust API.'],
    http: ['Follow the local HTTP sidecar example linked below. Bind the operator API locally and configure its authentication as documented.', 'Have the trusted executor admit immediately before each effect. Do not expose operator pause, kill, policy or approval endpoints as agent tools.', 'This bundle configuration template is for the stdio launcher, not the HTTP API.'],
  };
  return { route, steps: routes[route], operator_config_example: JSON.stringify({ version: 1, agent: 'replace-with-fresh-run-id', database: '/state/deadbolt.db', events: '/state/events.jsonl', command: '/absolute/container/path/to/trusted-server', args: [], tools: ['replace_with_actual_tool'], destinations: [], irreversible_tools: [], spend_cap_usd: 10 }, null, 2), boundary, documentation_url: 'https://github.com/seanebones-lang/deadbolt-docker-mcp#readme' };
}
function checkBundle(root) {
  const targets = { 'darwin-arm64': 'aarch64-apple-darwin', 'darwin-x64': 'x86_64-apple-darwin', 'linux-x64': 'x86_64-unknown-linux-gnu', 'linux-arm64': 'aarch64-unknown-linux-gnu', 'win32-x64': 'x86_64-pc-windows-msvc' };
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json'), 'utf8'));
  const provenance = JSON.parse(fs.readFileSync(path.join(root, 'PROVENANCE.json'), 'utf8'));
  const target = targets[`${process.platform}-${process.arch}`] || 'unsupported';
  const expected = provenance.binaries[target]?.binary_sha256;
  const matches = Boolean(expected && crypto.createHash('sha256').update(fs.readFileSync(path.join(root, 'native', target, process.platform === 'win32' ? 'deadbolt.exe' : 'deadbolt'))).digest('hex') === expected);
  return { bundle_version: manifest.version, engine_version: provenance.engine_version, target, checksum_matches: matches, active_protection: false, boundary };
}
function serve(root) {
  const send = value => process.stdout.write(JSON.stringify(value) + '\n');
  const error = (id, code, message) => send({ jsonrpc: '2.0', id, error: { code, message } });
  let initialized = false;
  function handle(line) {
    let r;
    try { r = JSON.parse(line); } catch { error(null, -32700, 'Invalid JSON'); return; }
    if (!r || Array.isArray(r) || r.jsonrpc !== '2.0' || typeof r.method !== 'string') { error(null, -32600, 'Invalid request'); return; }
    if (!Object.hasOwn(r, 'id')) return; // Notifications never get a response.
    if (!(typeof r.id === 'string' || typeof r.id === 'number' && Number.isFinite(r.id))) { error(null, -32600, 'Invalid request ID'); return; }
    let result;
    if (r.method === 'initialize') {
      const requested = r.params?.protocolVersion;
      const protocolVersion = ['2024-11-05', '2025-03-26', '2025-06-18'].includes(requested) ? requested : '2025-06-18';
      initialized = true;
      result = { protocolVersion, capabilities: { tools: {} }, serverInfo: { name: 'deadbolt-setup', version: JSON.parse(fs.readFileSync(path.join(root, 'manifest.json'), 'utf8')).version }, instructions: boundary };
    } else if (r.method === 'ping') result = {};
    else if (!initialized) { error(r.id, -32600, 'Initialize this read-only setup server first'); return; }
    else if (r.method === 'tools/list') {
      if (r.params?.cursor) { error(r.id, -32602, 'This setup server has no additional tool pages'); return; }
      result = { tools: definitions };
    } else if (r.method === 'tools/call') {
      const tool = definitions.find(t => t.name === r.params?.name);
      if (!tool) { error(r.id, -32602, 'Unknown setup tool; no downstream server is configured'); return; }
      const a = r.params?.arguments ?? {};
      const valid = a && typeof a === 'object' && !Array.isArray(a) && Object.keys(a).every(k => Object.hasOwn(tool.inputSchema.properties, k)) && (tool.name !== 'deadbolt_get_integration_guide' || tool.inputSchema.properties.route.enum.includes(a.route));
      if (!valid) result = { isError: true, content: [{ type: 'text', text: 'Invalid arguments. Use the tool input schema; setup tools do not accept filesystem paths or commands.' }] };
      else {
        try {
          const data = tool.name === 'deadbolt_get_integration_guide' ? guide(a.route) : checkBundle(root);
          result = { content: [{ type: 'text', text: JSON.stringify(data, null, 2) }], structuredContent: data };
        } catch { result = { isError: true, content: [{ type: 'text', text: 'Bundle verification could not read packaged metadata or executable. Reinstall a verified bundle; this result does not confirm integrity.' }] }; }
      }
    } else { error(r.id, -32601, 'Method not supported by read-only setup mode'); return; }
    send({ jsonrpc: '2.0', id: r.id, result });
  }
  // Bounded newline-delimited JSON. Never log diagnostics on the MCP stream.
  let pending = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => {
    pending += chunk;
    let end;
    while ((end = pending.indexOf('\n')) >= 0) {
      const line = pending.slice(0, end); pending = pending.slice(end + 1);
      if (Buffer.byteLength(line) > 1048576) { error(null, -32600, 'Request exceeds setup-mode limit'); continue; }
      if (line.trim()) handle(line);
    }
    if (Buffer.byteLength(pending) > 1048576) {
      process.stderr.write('deadbolt-setup:request_too_large\n');
      process.exitCode = 1; process.stdin.destroy();
    }
  });
  process.stdin.on('end', () => { if (pending.trim()) handle(pending); });
}
module.exports = { definitions, serve };
