'use strict';

// Configuration is operator-supplied, never inferred from a mounted workspace.
const path = require('node:path');
if (process.argv.length > 3 || process.argv.length < 2) {
  process.stderr.write('deadbolt-container:unexpected_arguments\n');
  process.exitCode = 1;
} else {
  const config = process.argv.length === 3
    ? process.argv[2] : process.env.DEADBOLT_OPERATOR_CONFIG || '';
  const setup = require('./setup.cjs');
  const titles = {
    deadbolt_get_integration_guide: 'DeadBolt integration guide',
    deadbolt_check_bundle: 'Verify the local DeadBolt container engine',
  };
  for (const tool of setup.definitions) {
    tool.title = titles[tool.name];
    tool.annotations = { ...tool.annotations, title: tool.title };
  }
  const entry = path.join(__dirname, 'launcher.cjs');
  process.argv = [process.argv[0], entry, config];
  require(entry);
}
