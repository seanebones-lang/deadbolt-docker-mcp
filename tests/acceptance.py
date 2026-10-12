"""Real container/tool effects; private disposable mounts, no accounts or model."""
from contextlib import closing
import json
import os
from pathlib import Path
import queue
import sqlite3
import subprocess
import sys
import tempfile
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    result = subprocess.run(args, text=True, capture_output=True, timeout=120, **kwargs)
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout


class Client:
    def __init__(self, command):
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, bufsize=1)
        self.lines = queue.Queue()
        self.sequence = 0
        def read():
            for line in self.proc.stdout:
                self.lines.put(line)
        threading.Thread(target=read, daemon=True).start()

    def rpc(self, method, params=None):
        self.sequence += 1
        self.proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':self.sequence,
                                         'method':method,'params':params or {}})+'\n')
        self.proc.stdin.flush()
        response = json.loads(self.lines.get(timeout=30))
        assert response['id'] == self.sequence, response
        return response

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        self.proc.stdout.close()
        self.proc.stderr.close()


def verify(image):
    checks = []
    def passed(name):
        checks.append({'case':name,'passed':True})
    info = json.loads(run('docker','image','inspect',image))[0]
    assert info['Config']['User']=='10001:10001'
    assert not info['Config'].get('ExposedPorts') and not info['Config'].get('Volumes')
    assert info['Config']['Entrypoint']==['node','/opt/deadbolt/server/entry.cjs']
    passed('nonroot_stdio_image_with_no_declared_ports_or_host_mounts')
    base = ['docker','run','--rm','-i','--network','none','--read-only',
            '--cap-drop','ALL','--security-opt','no-new-privileges',
            '--pids-limit','64','--memory','256m']
    # Build the downstream into a derived image, instead of giving it the host
    # workspace, a Docker socket or account credentials.
    fixture_image = 'n11-deadbolt-fixture:' + uuid.uuid4().hex[:12]
    clients=[]
    with tempfile.TemporaryDirectory(prefix='n11-docker-effects-') as temporary:
        work=Path(temporary)
        (work/'fixture.cjs').write_bytes((ROOT/'tests/fixture.cjs').read_bytes())
        (work/'Dockerfile').write_text('FROM '+image+'\nCOPY fixture.cjs /opt/downstream/fixture.cjs\n')
        run('docker','build','-q','-t',fixture_image,str(work))
        state=work/'state';state.mkdir(mode=0o700)
        operator=work/'operator';operator.mkdir(mode=0o700)
        config={'version':1,'agent':'container-disposable-run','database':'/state/deadbolt.db',
                'events':'/state/events.jsonl','command':'/usr/local/bin/node',
                'args':['/opt/downstream/fixture.cjs'],'tools':['echo','write_marker'],
                'destinations':[],'irreversible_tools':['write_marker'],'spend_cap_usd':10}
        (operator/'config.json').write_text(json.dumps(config));(operator/'config.json').chmod(0o600)
        mount=['--user',str(os.getuid())+':'+str(os.getgid()),
               '--mount','type=bind,src='+str(operator)+',dst=/operator,readonly',
               '--mount','type=bind,src='+str(state)+',dst=/state']
        def launch(value=None, configured=False):
            command=base + (mount if configured else [])
            if value is not None: command+=['-e','DEADBOLT_OPERATOR_CONFIG='+value]
            client=Client(command+[fixture_image if configured else image])
            clients.append(client);return client
        def operator_command(*args):
            return run(*(base+mount+['-e','DEADBOLT_DB=/state/deadbolt.db',
                         '-e','DEADBOLT_EVENTS=/state/events.jsonl',
                         '--entrypoint','/usr/local/bin/deadbolt',image,*args]))
        try:
            for label,value in [('absent',None),('blank','')]:
                client=launch(value)
                assert client.rpc('initialize')['result']['serverInfo']['name']=='deadbolt-setup'
                tools=client.rpc('tools/list')['result']['tools']
                assert len(tools)==2 and all(t['annotations']['readOnlyHint'] and t['title'] for t in tools)
                for route in ['stdio_client','claude_desktop','rust','http']:
                    data=client.rpc('tools/call',{'name':'deadbolt_get_integration_guide','arguments':{'route':route}})['result']['structuredContent']
                    assert data['route']==route and data['steps']
                data=client.rpc('tools/call',{'name':'deadbolt_check_bundle','arguments':{}})['result']['structuredContent']
                assert data['checksum_matches'] and data['active_protection'] is False
                assert data['engine_version']=='1.0.3'
                assert 'error' in client.rpc('tools/call',{'name':'kill','arguments':{}})
                assert not list(state.iterdir())
                client.close();passed('read_only_networkless_setup_'+label)
            for label,value in [('relative','operator.json'),('missing','/operator/missing.json')]:
                client=launch(value,True);client.proc.wait(timeout=30)
                assert client.proc.returncode!=0 and not list(state.iterdir())
                client.close();passed('supplied_invalid_configuration_starts_no_downstream_'+label)
            client=launch('/operator/config.json',True)
            assert client.rpc('initialize')['result']['serverInfo']['name']=='disposable-docker-fixture'
            tools=client.rpc('tools/list')['result']['tools']
            assert not any(t['name'].startswith('deadbolt_') for t in tools)
            passed('configured_container_discovers_only_trusted_downstream_tools')
            effects=state/'effects.txt'
            def call(name,allowed):
                before=effects.read_text() if effects.exists() else ''
                response=client.rpc('tools/call',{'name':name,'arguments':{}})
                after=effects.read_text() if effects.exists() else ''
                if allowed: assert 'result' in response and after==before+name+'\n'
                else: assert after==before and ('error' in response or response.get('result',{}).get('isError'))
            call('echo',True);passed('allowed_call_has_real_marker_effect')
            call('off_list',False);passed('off_policy_call_has_no_effect')
            call('write_marker',False);passed('irreversible_action_needs_local_operator_grant')
            operator_command('approve','--agent',config['agent'],'--tool','write_marker')
            call('write_marker',True);call('write_marker',False);passed('one_grant_one_effect_replay_refused')
            operator_command('pause','--agent',config['agent']);call('echo',False);passed('pause_blocks_next_effect')
            operator_command('resume','--agent',config['agent']);call('echo',True);passed('resume_restores_allowed_effect')
            operator_command('clip','echo','--agent',config['agent']);call('echo',False);passed('clip_blocks_selected_effect')
            operator_command('resume','--agent',config['agent'])
            with closing(sqlite3.connect(state/'deadbolt.db')) as db:
                db.execute('UPDATE leases SET expires_at=0 WHERE agent_id=?',(config['agent'],));db.commit()
            call('echo',False);passed('expired_lease_blocks_effect')
            operator_command('kill','--agent',config['agent']);call('echo',False);passed('terminal_kill_blocks_effect')
            client.close()
            before=(state/'starts.txt').read_text()
            client=launch('/operator/config.json',True);client.proc.wait(timeout=30)
            assert client.proc.returncode!=0 and (state/'starts.txt').read_text()==before
            client.close();assert (state/'deadbolt.db').exists()
            passed('reconnect_retains_state_and_does_not_revive_killed_identity')
        finally:
            for client in clients:
                if client.proc.poll() is None: client.close()
            run('docker','image','rm',fixture_image)
    return {'passed':True,'image':image,'image_id':info['Id'],'container_architecture':info['Architecture'],
            'scope':'Real stdio containers and disposable effects; no accounts, network, or model-mediated invocation',
            'checks':checks,'temporary_fixture_image_and_private_mounts_removed':True}


if __name__=='__main__':
    report=verify(sys.argv[1] if len(sys.argv)>1 else 'n11-deadbolt-docker:local')
    (ROOT/'acceptance-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
