# DeadBolt MCP for Docker

**Give agents tools. Keep control.** A free, Apache-2.0 stdio MCP container from
[NextEleven](https://www.nexteleven.dev/deadbolt).

Start with two read-only setup tools. When you deliberately supply private
operator configuration and a trusted downstream server, the same container gates
that server's routed `tools/call` requests. It does not protect other MCP servers
in your gateway, client built-in tools, or processes outside this container.

This Docker package is **1.0.0**, built from stable **DeadBolt engine 1.0.3** at
`3a857f8438dcda4bdaadb414d37f128508dc44f1`. It is separate from MCPB 1.1.0 and
the engine 1.1.0-rc.1 preview. The stable engine's irreversible-tool permission
is a broad one-shot grant; exact-action preview behavior is not included here.

Docker MCP Catalog inclusion requires Docker's review. The source and local
installation are available independently of catalog acceptance.

## Start in minutes

You need Docker with a running Linux engine and Git. Node and Rust are built into
the image/build stages; you do not install them on your host.

```sh
git clone https://github.com/seanebones-lang/deadbolt-docker-mcp.git
cd deadbolt-docker-mcp
docker build -t n11-deadbolt-docker:local .
```

The build uses checksum-pinned engine source, locked Cargo dependencies and
digest-pinned official base images. It builds natively for Linux ARM64 or AMD64.
The first build needs network access to public sources and dependency registries.
Startup makes no download or account connection.

Configure an MCP client with:

```json
{
  "mcpServers": {
    "deadbolt": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "n11-deadbolt-docker:local"]
    }
  }
}
```

Do not add `-t`: a terminal corrupts the stdio protocol. Keep Docker running.
There are no required secrets or mounts in setup mode.

Try these requests:

1. “Verify the local DeadBolt container engine and tell me if protection is active.”
2. “Get the stdio integration guide and explain how I configure a protected server.”
3. “Show the Rust integration guide and identify what stays outside its boundary.”

`deadbolt_check_bundle` verifies the built executable against its image metadata;
it is corruption detection, not independent signature verification or a security
test. `deadbolt_get_integration_guide` returns instructions without writing files
or granting an action. **Setup mode provides no active protection.**

## Put a trusted server behind the gate

A downstream server must run **inside the same container**. It is not enough to
enable DeadBolt next to another server in Docker MCP Toolkit. Build a derived
image that installs your reviewed downstream and its locked dependencies:

```dockerfile
FROM n11-deadbolt-docker:local
COPY my-reviewed-server.cjs /opt/downstream/server.cjs
```

Create two operator-owned folders outside agent-editable workspaces: one for
configuration, one for state. Keep their permissions private. In the config
folder, create `config.json` and replace every policy choice deliberately:

```json
{
  "version": 1,
  "agent": "replace-with-a-fresh-run-id",
  "database": "/state/deadbolt.db",
  "events": "/state/events.jsonl",
  "command": "/usr/local/bin/node",
  "args": ["/opt/downstream/server.cjs"],
  "tools": ["replace_with_actual_tool"],
  "destinations": [],
  "irreversible_tools": [],
  "spend_cap_usd": 10
}
```

Paths in the JSON refer to the container filesystem. Launch your derived image
with those two exact folders mounted, using your operator UID/GID:

```sh
docker run --rm -i --read-only --network none --cap-drop ALL \
  --security-opt no-new-privileges --user "$(id -u):$(id -g)" \
  --mount type=bind,src=/absolute/private/config,dst=/operator,readonly \
  --mount type=bind,src=/absolute/private/state,dst=/state \
  -e DEADBOLT_OPERATOR_CONFIG=/operator/config.json my-reviewed-deadbolt-image
```

Use no networking for disposable/local-only tools. A server that needs a remote
service needs a deliberate network configuration and its own credentials. Do
not mount your home directory or Docker socket to reach host tools. Do not grant
privileged mode. The downstream remains trusted and can access the mounted data
and environment you explicitly give it.

Invalid supplied configuration refuses startup. Blank configuration exposes only
setup tools. Configured mode replaces setup tools with downstream tools; operator
policy, approval, pause, resume, clip and kill are never agent-facing MCP tools.

The operator can use the engine in another short-lived container against the
same private state. For example, pause the selected run:

```sh
docker run --rm --read-only --network none --user "$(id -u):$(id -g)" \
  --mount type=bind,src=/absolute/private/state,dst=/state \
  -e DEADBOLT_DB=/state/deadbolt.db -e DEADBOLT_EVENTS=/state/events.jsonl \
  --entrypoint /usr/local/bin/deadbolt n11-deadbolt-docker:local \
  pause --agent replace-with-a-fresh-run-id
```

Use `resume`, `approve --agent ID --tool TOOL`, `clip TOOL --agent ID`, or
`kill --agent ID` only as a deliberate local operator action. The stable engine
has a 60-second sliding lease; silence expires it. Use a fresh ID for each run,
never share it across concurrent sessions, and never reuse a killed identity.

## Reproduce the effect checks

With Python 3.11+ and the image built:

```sh
python3 tests/acceptance.py n11-deadbolt-docker:local
```

The suite builds a disposable downstream image, creates private temporary config
and state, and tests actual marker effects. It checks setup, invalid config,
allow/deny, one-shot approval/replay, pause/resume, clip, expiry and terminal kill
with reconnect. It removes its derived image and private fixture afterward.
No account, network connection, paid provider or model session is used.

The test's `acceptance-report.json` records the actual image ID and architecture.
This is container/protocol acceptance, not independent certification or proof of
model behavior in every client.

## Boundaries and removal

- DeadBolt gates routed `tools/call` requests. Downstream startup, other MCP
  methods, already-running tool bodies and arbitrary downstream OS/network
  access are outside that gate. A denied next call does not cancel an existing
  effect. Docker adds the container boundary configured by its operator.
- Policy/state must stay outside agent control. A downstream allowed to edit
  those files can undermine the gate; the simple same-user setup is not a
  hostile-downstream sandbox. Do not connect untrusted servers.
- Spend enforcement depends on trusted reporting. Local evidence is
  operator-writable. Neither a checksum nor a catalog entry proves compliance.
- Remove the MCP client entry and stop its container to disconnect. `--rm`
  removes that container; it does not delete your private bind-mounted state.
  Back up or deliberately remove state separately. Existing kills persist.

## Privacy and support

Setup reads only this image's metadata, documentation and executable hash. It
stores no operator state and sends no data to NextEleven. Configured mode reads
your supplied JSON and forwards requests/responses to your chosen downstream.
Tool arguments and responses may contain personal data. Leases, policy and
audit events live at your explicit local state paths; their retention is yours
to control. Downstream and client services have their own privacy policies.

The container itself adds no telemetry or cloud account. Docker may contact its
own services for image/catalog management outside the server runtime. Consult
your Docker and MCP client's policies.

Use [issues](https://github.com/seanebones-lang/deadbolt-docker-mcp/issues) for
installation problems. Send private security concerns to
**nextelevenstudios@gmail.com**; do not put secrets or private messages in issues.

[Captioned walkthrough](https://www.nexteleven.dev/deadbolt#watch) ·
[Engine source and trust guide](https://github.com/seanebones-lang/deadbolt/blob/v1.0.3/docs/TRUST.md) ·
[Other installation routes](https://www.nexteleven.dev/deadbolt#install)
