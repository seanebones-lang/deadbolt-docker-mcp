# A trusted supervisor for the RC2 container

Use this reference when the trusted job's continued participation, rather than
calls from its workload, should keep a run live. It uses the published
`2.0.0rc2` Python heartbeat helper and the exact RC2 engine already built in the
main image. Both the wheel checksum and official Python base-image digest are
pinned. Build-time downloads are public; runtime connects no external service.

This is a separate operator image, not an MCP server or downstream image. It
does not modify the frozen `v2.0.0-rc.2` MCP container. The reference and its tests
are added on the Docker repository's subsequent source revision.

## Reproduce the disposable lifecycle

From this repository, after building `n11-deadbolt-docker:local`:

Use a source revision containing `examples/supervisor` (current `main` after this
addition). The earlier frozen `v2.0.0-rc.2` source tag has the same engine/container
but does not include this later reference. Record `git rev-parse HEAD` alongside
the report when reproducing it.

```sh
docker build --build-arg DEADBOLT_IMAGE=n11-deadbolt-docker:local \
  -t n11-deadbolt-operator:local examples/supervisor
python3 tests/supervisor_acceptance.py \
  n11-deadbolt-docker:local n11-deadbolt-operator:local
```

Allow about three minutes. The driver starts a real token-authenticated Unix
sidecar and a finite heartbeat, then routes calls through a disposable MCP
marker server. It checks a private `0600` Linux socket; absent operator mounts
and role tokens in the downstream; heartbeat extension beyond the original
60-second expiry; busy-workload expiry after the heartbeat stops; failed late
renewal; refused reconnect; and the fixed deadline despite continued renewal.
Denials must be normal MCP tool-error results with their actual terminal reason
and no marker effect. At the fixed deadline the helper must fail closed.

`supervisor-report.json` records checks, calls and local image identities. State,
keys, test containers, socket volume and the derived dummy image are removed
after the run. No SQL mutation forces expiry. These are protocol/effect checks;
they do not establish graphical model invocation or independent reproduction.

## Apply the pattern to a trusted job

Keep these mounts distinct:

| Process | Mounts | Authority |
| --- | --- | --- |
| Model-facing MCP container | Read-only operator configuration; private state | In-process admission through the configured gate |
| Operator CLI | Private state; credential folder when issuing keys | Policy, pause, kill, credential provisioning |
| Sidecar | Private state; private operator-key file; Linux socket volume | Authenticated local operator and renewal endpoints |
| Finite heartbeat | Linux socket volume; one read-only renewal-key file | Renewal of its bound root only |

The heartbeat never mounts the state database or operator-key folder. The
workload never mounts the socket or credential folder. SQLite state and evidence
must be accessed by Linux containers on the same Docker engine; do not edit them
with native macOS/Windows SQLite concurrently. Use a Docker named volume for the
Unix socket, which remains entirely on that Linux engine.

The test driver is a runnable provisioning reference: it creates a private
volume, assigns its ownership to the operator UID/GID, starts the sidecar,
enables a fresh supervisor-configured run, issues its private renewal key, then
starts the helper within the launcher's 60-second idle window. Build everything
before starting that window. If setup lapses, use a fresh run identity; nothing
in this example silently renews or resurrects an expired run.

The operator image exposes four explicit entry modes:

```text
engine <deadbolt CLI arguments>
heartbeat --agent RUN --credential-file /renewal-key --interval-secs 10 --max-secs 600
status RUN
renew RUN /renewal-key
```

`engine serve --bind /control/deadbolt.sock` reads the private operator key from
`/credentials/operator-token`. Other engine commands run the existing operator
CLI. `status` requires that same operator file. `renew` uses only its specified
private renewal-key file and never falls back to operator or workload tokens.
These entry modes belong only to trusted operator processes, not model tools.

For the heartbeat, use the hardened flags from the main README, your operator
UID/GID, a read-only key bind mount and the private socket volume:

```sh
# Replace the mount values with the private volume/key you provisioned.
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --user "$(id -u):$(id -g)" \
  --mount type=volume,src=YOUR_PRIVATE_SOCKET_VOLUME,dst=/control \
  --mount type=bind,src=/absolute/private/RUN-renewal-key,dst=/renewal-key,readonly \
  n11-deadbolt-operator:local heartbeat --agent RUN \
  --credential-file /renewal-key --interval-secs 10 --max-secs 600
```

Keep it attached to the trusted job lifecycle. Do not leave an unconditional
detached renewal daemon running. Stop protected dispatch when this helper fails;
arrange executor cancellation separately for already-running work. Ending a
heartbeat stops future renewal, but the remaining idle window still applies.
Operator `kill` blocks new admissions immediately. Neither heartbeat nor kill
terminates an already-running tool or extends the fixed deadline.

The downstream remains trusted: it shares writable gate state under the same
user in this reference. Missing credential mounts do not make same-user state
tamper-proof. Use an isolated executor/OS boundary when the workload itself is
untrusted. No actual accounts, remote jobs or provider usage reconciliation are
covered here. See the pinned [supervision contract](https://github.com/seanebones-lang/deadbolt/blob/v2.0.0-rc.2/docs/SUPERVISION.md)
and [trust limits](https://github.com/seanebones-lang/deadbolt/blob/v2.0.0-rc.2/docs/TRUST.md).
