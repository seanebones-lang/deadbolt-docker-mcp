"""Real Linux-container supervisor lifecycle. No accounts, model or SQL edits."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import uuid

from acceptance import Client, ROOT, run


def verify(image, operator_image):
    suffix = uuid.uuid4().hex[:12]
    fixture_image = 'n11-deadbolt-supervised-fixture:' + suffix
    control_volume = 'n11-deadbolt-supervisor-' + suffix
    containers = []
    clients = []
    checks, calls = [], []
    uid = str(os.getuid()) + ':' + str(os.getgid())
    base = ['docker', 'run', '--rm', '--network', 'none', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--pids-limit', '64', '--memory', '256m', '--user', uid]
    def passed(name):
        checks.append({'case': name, 'passed': True})
        print('PASS ' + name, flush=True)
    def logs(name):
        result = subprocess.run(['docker', 'logs', name], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0
        return result.stdout + result.stderr
    assert run(*(base + [operator_image, 'engine', '--version'])).strip() == 'deadbolt 2.0.0-rc.2'
    assert run(*(base + ['--entrypoint', 'python', operator_image, '-c',
        'import importlib.metadata; print(importlib.metadata.version("n11-deadbolt-client"))'])).strip() == '2.0.0rc2'
    source_hash = run(*(base + ['--entrypoint', 'node', image, '-e',
        'console.log(require("node:crypto").createHash("sha256").update(require("node:fs").readFileSync("/usr/local/bin/deadbolt")).digest("hex"))'])).strip()
    copied_hash = run(*(base + ['--entrypoint', 'python', operator_image, '-c',
        'import hashlib; print(hashlib.sha256(open("/usr/local/bin/deadbolt","rb").read()).hexdigest())'])).strip()
    assert source_hash == copied_hash
    passed('matching_rc2_engine_bytes_and_installed_published_client')
    with tempfile.TemporaryDirectory(prefix='n11-docker-supervisor-') as temporary:
        work = Path(temporary)
        state, config_dir, credentials = (work / name for name in ('state', 'config', 'credentials'))
        for folder in (state, config_dir, credentials):
            folder.mkdir(mode=0o700)
        (credentials / 'operator-token').write_text(secrets.token_hex(32))
        (credentials / 'operator-token').chmod(0o600)
        # A downstream startup checks that the operator-only mounts and role
        # credentials are absent, before delegating to the ordinary dummy server.
        (work / 'fixture.cjs').write_text(
            "{ const fs=require('node:fs');\n"
            "if(fs.existsSync('/credentials')||fs.existsSync('/control')||"
            "process.env.DEADBOLT_TOKEN||process.env.DEADBOLT_ADMISSION_TOKEN)"
            "throw new Error('operator authority leaked to fixture'); }\n" +
            (ROOT / 'tests/fixture.cjs').read_text())
        (work / 'Dockerfile').write_text('FROM ' + image + '\nCOPY fixture.cjs /opt/downstream/fixture.cjs\n')
        run('docker', 'build', '-q', '-t', fixture_image, str(work))
        run('docker', 'volume', 'create', control_volume)
        state_mount = ['--mount', 'type=bind,src=' + str(state) + ',dst=/state']
        secret_mount = ['--mount', 'type=bind,src=' + str(credentials) + ',dst=/credentials,readonly']
        socket_mount = ['--mount', 'type=volume,src=' + control_volume + ',dst=/control']
        trusted = base + state_mount + secret_mount + socket_mount
        def operator(*args, success=True, writable_credentials=False):
            command = trusted
            if writable_credentials:
                command = base + state_mount + socket_mount + ['--mount', 'type=bind,src=' + str(credentials) + ',dst=/credentials']
            result = subprocess.run(command + [operator_image, *args], capture_output=True,
                                    text=True, timeout=30)
            assert (result.returncode == 0) is success, result.stderr
            return result
        def status(agent):
            return json.loads(operator('status', agent).stdout)['agents'][0]
        def detached(name, *args):
            containers.append(name)
            command = [part for part in trusted if part != '--rm']
            run(*(command[:2] + ['-d', '--name', name] + command[2:] + [operator_image, *args]))
        def call(client, allowed, deny=None):
            effect = state / 'effects.txt'
            before = effect.read_text() if effect.exists() else ''
            response = client.rpc('tools/call', {'name': 'echo', 'arguments': {}})
            after = effect.read_text() if effect.exists() else ''
            if allowed:
                assert 'result' in response and not response['result'].get('isError')
                assert after == before + 'echo\n'
            else:
                assert after == before and 'error' not in response
                assert response['result']['isError'] is True
                assert response['result']['_meta']['io.github.seanebones-lang/deadbolt'] == {'code': deny, 'retry': 'never'}
            calls.append({'allowed': allowed, 'body_ran': before != after, 'deny': deny})
        def launch(agent, deadline):
            config = {'version': 2, 'agent': agent, 'hard_deadline_at': deadline,
                      'renewal_mode': 'supervisor', 'offline_tools': ['echo'],
                      'database': '/state/deadbolt.db', 'events': '/state/events.jsonl',
                      'command': '/usr/local/bin/node', 'args': ['/opt/downstream/fixture.cjs'],
                      'tools': ['echo'], 'destinations': [], 'irreversible_tools': [], 'spend_cap_usd': 10}
            (config_dir / 'config.json').write_text(json.dumps(config))
            (config_dir / 'config.json').chmod(0o600)
            client = Client(base[:2] + ['-i'] + base[2:] + state_mount +
                            ['--mount', 'type=bind,src=' + str(config_dir) + ',dst=/operator,readonly',
                             '-e', 'DEADBOLT_OPERATOR_CONFIG=/operator/config.json', fixture_image])
            clients.append(client)
            assert 'result' in client.rpc('initialize')
            return client
        def provision(agent):
            operator('engine', 'supervisor', 'issue', '--agent', agent, '--id', agent + '-supervisor',
                     '--ttl-secs', '600', '--out', '/credentials/' + agent, writable_credentials=True)
            assert (credentials / agent).stat().st_mode & 0o077 == 0
        def heartbeat(agent, seconds):
            name = 'n11-heartbeat-' + agent + '-' + suffix
            # No state mount: the helper only needs socket and its read-only
            # credential. The operator token file is not mounted here.
            containers.append(name)
            detached_base = [part for part in base if part != '--rm']
            command = detached_base[:2] + ['-d', '--name', name] + detached_base[2:] + socket_mount + [
                '--mount', 'type=bind,src=' + str(credentials / agent) + ',dst=/renewal-key,readonly',
                operator_image, 'heartbeat', '--agent', agent, '--credential-file', '/renewal-key',
                '--interval-secs', '5', '--max-secs', str(seconds)]
            run(*command)
            for _ in range(60):
                output = logs(name)
                if 'supervisor heartbeat active' in output:
                    return name
                assert json.loads(run('docker', 'inspect', name))[0]['State']['Running']
                time.sleep(.1)
            raise AssertionError('heartbeat did not start')
        try:
            # Root is used only to prepare ownership of this disposable volume.
            run('docker', 'run', '--rm', '--network', 'none', '--read-only', '--user', '0:0',
                '-e', 'OP_UID=' + str(os.getuid()), '-e', 'OP_GID=' + str(os.getgid()),
                *socket_mount, '--entrypoint', 'python', operator_image, '-c',
                'import os; os.chown("/control",int(os.environ["OP_UID"]),int(os.environ["OP_GID"])); os.chmod("/control",0o700)')
            sidecar = 'n11-sidecar-' + suffix
            detached(sidecar, 'engine', 'serve', '--bind', '/control/deadbolt.sock')
            for _ in range(80):
                result = subprocess.run(trusted + [operator_image, 'status', 'missing'], capture_output=True, text=True, timeout=10)
                if result.stdout and json.loads(result.stdout) == {'agents': []}:
                    break
                time.sleep(.1)
            else:
                raise AssertionError('operator sidecar did not start: ' + result.stdout + result.stderr + logs(sidecar))
            socket_mode = run(*(trusted + ['--entrypoint', 'python', operator_image, '-c',
                'import os; print(oct(os.stat("/control/deadbolt.sock").st_mode & 0o777))'])).strip()
            assert socket_mode == '0o600'
            passed('private_linux_socket_sidecar_and_operator_credential_file')
            (credentials / 'operator-token').chmod(0o644)
            refused = operator('status', 'missing', success=False)
            assert not refused.stdout and 'operator setup unavailable' in refused.stderr
            (credentials / 'operator-token').chmod(0o600)
            passed('shared_operator_key_permissions_refused')
            agent = 'supervised-idle'
            client = launch(agent, int(time.time()) + 300)
            initial = status(agent)['expires_at']
            provision(agent)
            # The installed SDK receives the exact role header; no secret is
            # passed through argv/environment or printed by this probe.
            authority_probe = (
                'import json, deadbolt_client as c; from pathlib import Path; '
                'key=Path("/credentials/supervised-idle").read_text().strip(); '
                'a=c._call("GET","/status",headers={}); '
                'b=c._call("GET","/status",headers={"X-Deadbolt-Supervisor":key}); '
                'assert a.get("code")=="unauthorized" and b.get("code")=="forbidden"; '
                'print("role separation verified")')
            assert run(*(trusted + ['--entrypoint', 'python', operator_image, '-c', authority_probe])).strip() == 'role separation verified'
            passed('anonymous_and_renewal_only_credentials_cannot_read_operator_status')
            beat = heartbeat(agent, 90)
            finite_output = run(*(base + socket_mount + [
                '--mount', 'type=bind,src=' + str(credentials / agent) + ',dst=/renewal-key,readonly',
                operator_image, 'heartbeat', '--agent', agent, '--credential-file', '/renewal-key',
                '--interval-secs', '5', '--max-secs', '1']))
            assert 'supervisor heartbeat active' in finite_output
            passed('finite_helper_returns_at_operator_chosen_duration')
            call(client, True)
            passed('downstream_has_no_control_socket_or_operator_credentials')
            # Cross the original default 60-second expiry with genuine renewals.
            while time.time() <= initial + 2:
                assert json.loads(run('docker', 'inspect', beat))[0]['State']['Running']
                time.sleep(1)
            assert status(agent)['expires_at'] > initial
            call(client, True)
            passed('live_heartbeat_keeps_default_60_second_lease_live')
            run('docker', 'stop', '--time', '10', beat)
            expiry = status(agent)['expires_at']
            # Keep calling after stopping renewal: the workload cannot maintain
            # its own lease. No operator-forced timestamp edits are involved.
            while time.time() < expiry + .2:
                if time.time() < expiry - 3:
                    call(client, True)
                time.sleep(2)
            call(client, False, 'lease_expired')
            expired = status(agent)
            assert expired['state'] == 'expired' and expired['expires_at'] == expiry
            passed('busy_workload_expires_after_supervisor_stops_without_effect')
            # The SDK may add a failure code; only explicit ok:true is liveness.
            renewal = json.loads(operator('renew', agent, '/credentials/' + agent, success=False).stdout)
            assert renewal.get('ok') is False
            call(client, False, 'lease_expired')
            passed('late_renewal_refused_and_expired_run_stays_terminal')
            client.close()
            before = (state / 'starts.txt').read_text()
            rejected = Client(base[:2] + ['-i'] + base[2:] + state_mount + [
                '--mount', 'type=bind,src=' + str(config_dir) + ',dst=/operator,readonly',
                '-e', 'DEADBOLT_OPERATOR_CONFIG=/operator/config.json', fixture_image])
            clients.append(rejected)
            rejected.proc.wait(timeout=30)
            assert rejected.proc.returncode != 0 and (state / 'starts.txt').read_text() == before
            rejected.close()
            passed('expired_reconnect_starts_no_downstream')
            agent = 'supervised-deadline'
            cutoff = int(time.time()) + 25
            client = launch(agent, cutoff)
            provision(agent)
            beat = heartbeat(agent, 60)
            call(client, True)
            while time.time() <= cutoff + .2:
                time.sleep(.2)
            call(client, False, 'deadline_exceeded')
            assert status(agent)['hard_deadline_at'] == cutoff
            for _ in range(80):
                beat_state = json.loads(run('docker', 'inspect', beat))[0]['State']
                if not beat_state['Running']:
                    break
                time.sleep(.1)
            assert not beat_state['Running'] and beat_state['ExitCode'] == 1
            assert 'supervisor heartbeat stopped or unavailable' in logs(beat)
            passed('fixed_deadline_wins_over_heartbeat_and_helper_fails_closed')
            for name in containers:
                output = run('docker', 'inspect', name) + logs(name)
                for credential in credentials.iterdir():
                    assert credential.read_text().strip() not in output, 'credential leaked to Docker configuration or logs'
            passed('bearer_values_absent_from_docker_configuration_and_logs')
        finally:
            for client in clients:
                if client.proc.poll() is None:
                    client.close()
            for name in containers:
                subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=30)
            run('docker', 'volume', 'rm', control_volume)
            run('docker', 'image', 'rm', fixture_image)
    return {'passed': True, 'image': image, 'operator_image': operator_image,
            'image_id': json.loads(run('docker', 'image', 'inspect', image))[0]['Id'],
            'operator_image_id': json.loads(run('docker', 'image', 'inspect', operator_image))[0]['Id'],
            'architecture': json.loads(run('docker', 'image', 'inspect', image))[0]['Architecture'],
            'scope': 'NextEleven-operated real container heartbeat and MCP effects; no model or independent tester',
            'real_default_idle_ttl_secs': 60, 'operator_forced_expiry': False,
            'engine_source': 'd166c7b039800bbd6d8acb1bc5c66f9add472f5f',
            'python_client_version': '2.0.0rc2',
            'python_wheel_sha256': 'ce2c04cc68b4f19bf79e7aa63bed5864896ec7d8cb52ecee6f03f5aac8c7e9ac',
            'checks': checks, 'effect_calls': calls, 'disposable_containers_volume_and_mounts_removed': True}


if __name__ == '__main__':
    report = verify(sys.argv[1] if len(sys.argv) > 1 else 'n11-deadbolt-docker:local',
                    sys.argv[2] if len(sys.argv) > 2 else 'n11-deadbolt-operator:local')
    (ROOT / 'supervisor-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
