'use strict';
const fs = require('node:fs');
const readline = require('node:readline');
fs.appendFileSync('/state/starts.txt', 'started\n');
readline.createInterface({ input: process.stdin }).on('line', line => {
  const r = JSON.parse(line);
  if (!Object.hasOwn(r, 'id')) return;
  let result = {};
  if (r.method === 'initialize') result = {
    protocolVersion: '2025-03-26', capabilities: { tools: {} },
    serverInfo: { name: 'disposable-docker-fixture', version: '1.0.0' },
  };
  else if (r.method === 'tools/list') result = { tools: ['echo', 'write_marker', 'off_list'].map(name => ({
    name, description: 'Disposable marker tool; no accounts or network',
    inputSchema: { type: 'object', properties: {url:{type:'string'}}, additionalProperties: false },
  })) };
  else if (r.method === 'tools/call') {
    fs.appendFileSync('/state/effects.txt', r.params.name + '\n');
    result = { content: [{ type: 'text', text: 'Disposable marker completed' }] };
  }
  process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: r.id, result }) + '\n');
});
