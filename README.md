# DeadBolt MCP for Docker

**Give agents tools. Keep control.** A free, Apache-2.0 stdio MCP container from
[NextEleven](https://www.nexteleven.dev/deadbolt).

Start with two read-only setup tools. When you deliberately supply private
operator configuration and a trusted downstream server, the same container gates
that server's routed `tools/call` requests. It does not protect other MCP servers
in your gateway, client built-in tools, or processes outside this container.

This Docker package is the **2.0.0-rc.2 developer preview**, built from the
exact DeadBolt engine **2.0.0-rc.2** source at
`d166c7b039800bbd6d8acb1bc5c66f9add472f5f`. The earlier Docker package 1.0.0
remains available from its source revision
`e5efc1595bc87683ccf96bc367448012a9e170ee`, with engine 1.0.3. This preview
requires version 2 operator configuration and a fresh run identity; it does not
silently migrate an existing idle-only run.

The container launcher supports broad one-shot irreversible-tool approval. It
strips inherited `DEADBOLT_*` variables before starting the gate and does not
provision exact-action grants. Use the separate Rust/Python or raw-proxy
integration when your executor requires exact-action grants.
Docker MCP Catalog inclusion requires Docker's review. The source and local
installation are available independently of catalog acceptance.

## Start in minutes

You need Docker with a running Linux engine and Git. Node and Rust are built into
the image/build stages; you do not install them on your host.

```sh
git clone https://github.com/seanebones-lang/deadbolt-docker-mcp.git
cd deadbolt-docker-mcp
git checkout v2.0.0-rc.2
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
  "version": 2,
  "hard_deadline_at": 0,
  "renewal_mode": "activity",
  "offline_tools": [],
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

**Replace `hard_deadline_at: 0` before launch.** It is an invalid placeholder,
not an unlimited lifetime. Calculate a future integer Unix timestamp for your
chosen run length, for example `python3 -c 'import time; print(int(time.time()) + 3600)'`
for a one-hour maximum. A fixed timestamp stays fixed across restarts; do not
regenerate it for the same run ID.

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
`kill --agent ID` only as a deliberate local operator action. Activity mode has a 60-second idle TTL; live admission renews it only within
the fixed deadline. Silence expires the run. Supervisor mode requires a trusted
operator to provision and run renewal separately; admissions never renew it.
Neither mode moves the hard deadline. A late heartbeat, restart, resume or
policy change cannot revive an expired/killed run. Use a fresh ID for each run.

Configured mode installs the supplied destination allow-list, including an
empty one. Every routed tool must declare an allowed destination unless the
operator explicitly lists that tool in `offline_tools`. With both lists empty,
no routed tool call is admitted. For reviewed, local-only dummy tools, explicitly
list their actual names in `offline_tools`; for network-capable tools, supply
allowed destination tokens and require a destination in the call. Exceptions default to empty and cannot override an explicitly
foreign destination. These declarations do not prevent a tool from making
unreported connections; use OS/container egress restrictions for enforcement.
Never classify a general-purpose shell as offline unless you accept that trust.

For a supervised container, keep the renewal credential out of its environment
and downstream process. Run the sidecar/heartbeat on the trusted operator side
against the same private state. It needs its own explicitly configured private
socket/credential mount; the networkless setup entry does not create that
connection. Follow the [pinned supervisor guide](https://github.com/seanebones-lang/deadbolt/blob/v2.0.0-rc.2/docs/SUPERVISION.md)
and use the RC2 Python client/finite heartbeat helper. Start renewal before the
idle TTL lapses. For simply trying the container, use the finite activity-mode
example above.

The separate [container supervisor reference](examples/supervisor/README.md)
uses the published RC2 Python helper, a private Linux socket and operator-only
credential mounts. Its runnable lifecycle checks real heartbeat extension,
busy-workload idle expiry, failed late renewal and the fixed deadline. It is
additional example/test source, not a replacement for the frozen RC2 MCP image.

## Reproduce the effect checks

With Python 3.11+ and the image built:

```sh
python3 tests/acceptance.py n11-deadbolt-docker:local
```

The suite builds a disposable downstream image, creates private temporary config
and state, and tests actual marker effects. It checks setup, invalid config,
allow/deny, one-shot approval/replay, pause/resume, clip, idle expiry and
terminal kill with reconnect. RC2 adds destination/exception behavior, old or
changed configuration refusal, supervisor-mode non-renewal, a real wall-clock
fixed deadline, and a running store outage. Denials must be MCP tool-error
results with the expected reason code and retry hint, and must have no marker
effect. Idle expiry is operator-forced; the fixed deadline is observed in real
time. The suite does not test a live supervisor heartbeat or a model session. It removes its derived image and private fixture afterward.
No account, network connection, paid provider or model session is used.

With Docker Desktop's MCP Toolkit installed, also run:

```sh
python3 tests/gateway_acceptance.py
```

This uses an explicit disposable catalog and empty config/secrets files. It does
not import/reset your catalog or change client connections. CI repeats the
gateway check using the checksum-pinned official Docker MCP Gateway v0.42.0.

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
[Engine source and trust guide](https://github.com/seanebones-lang/deadbolt/blob/v2.0.0-rc.2/docs/TRUST.md) ·
[Other installation routes](https://www.nexteleven.dev/deadbolt#install)
