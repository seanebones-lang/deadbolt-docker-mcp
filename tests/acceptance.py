"""Real container/tool effects; private disposable mounts, no accounts or model."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
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
        self.diagnostics = []
        self.notifications = []
        self.sequence = 0
        def read():
            for line in self.proc.stdout:
                self.lines.put(line)
            self.lines.put(None)
        threading.Thread(target=read, daemon=True).start()
        def diagnostics():
            for line in self.proc.stderr:
                self.diagnostics.append(line.rstrip())
                del self.diagnostics[:-100]
        threading.Thread(target=diagnostics, daemon=True).start()

    def rpc(self, method, params=None):
        if method == 'initialize' and params is None:
            params = {'protocolVersion':'2025-03-26','capabilities':{},
                      'clientInfo':{'name':'n11-disposable-container-test','version':'1.0.0'}}
        self.sequence += 1
        self.proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':self.sequence,
                                         'method':method,'params':params or {}})+'\n')
        self.proc.stdin.flush()
        deadline = time.monotonic() + 30
        for _ in range(256):
            try:
                line = self.lines.get(timeout=max(0.001, deadline-time.monotonic()))
            except queue.Empty:
                raise AssertionError('No MCP response: '+ '\n'.join(self.diagnostics))
            assert line is not None, 'MCP process exited: '+ '\n'.join(self.diagnostics)
            response = json.loads(line)
            assert response.get('jsonrpc') == '2.0', response
            if 'id' not in response and isinstance(response.get('method'), str):
                # Gateways may notify about tool-list changes or logging before
                # replying. Keep only names, and preserve the request deadline.
                self.notifications.append(response['method'])
                del self.notifications[:-100]
                continue
            break
        else:
            raise AssertionError('Too many MCP notifications before the response')
        assert response['id'] == self.sequence, response
        if method == 'initialize' and 'result' in response:
            self.proc.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            self.proc.stdin.flush()
        return response

    def close(self):
        try: self.proc.stdin.close()
        except BrokenPipeError: pass
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        self.proc.stdout.close()
        self.proc.stderr.close()


def verify(image):
    checks = []
    effect_calls = []
    def passed(name):
        checks.append({'case':name,'passed':True})
    info = json.loads(run('docker','image','inspect',image))[0]
    assert info['Config']['User']=='10001:10001'
    assert not info['Config'].get('ExposedPorts') and not info['Config'].get('Volumes')
    assert info['Config']['Entrypoint']==['node','/opt/deadbolt/server/entry.cjs']
    engine_version=run('docker','run','--rm','--network','none','--read-only','--entrypoint','/usr/local/bin/deadbolt',image,'--version').strip()
    assert engine_version=='deadbolt 2.0.0-rc.2'
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
        config={'version':2,'hard_deadline_at':int(time.time())+1200,'renewal_mode':'activity','offline_tools':['echo','write_marker'],'agent':'container-disposable-run','database':'/state/deadbolt.db',
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
        def operator_sql(query, parameters=()):
            # Run SQLite on the Linux engine side of Docker Desktop's mount.
            # Host-side SQLite uses a different kernel/locking/cache boundary.
            script='const {DatabaseSync}=require("node:sqlite"); const db=new DatabaseSync("/state/deadbolt.db"); const rows=db.prepare(process.argv[1]).all(...JSON.parse(process.argv[2])); db.close(); console.log(JSON.stringify(rows));'
            return json.loads(run(*(base+mount+['--entrypoint','node',image,'-e',script,query,json.dumps(parameters)])))
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
                assert data['engine_version']=='2.0.0-rc.2' and data['bundle_version']=='2.0.0-rc.2'
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
            live_starts=(state/'starts.txt').read_text()
            for mutation in ({'hard_deadline_at':config['hard_deadline_at']+60},{'renewal_mode':'supervisor'}):
                (operator/'config.json').write_text(json.dumps({**config,**mutation}))
                rejected=launch('/operator/config.json',True);rejected.proc.wait(timeout=30)
                assert rejected.proc.returncode!=0 and (state/'starts.txt').read_text()==live_starts
                rejected.close()
            (operator/'config.json').write_text(json.dumps(config))
            passed('live_existing_run_deadline_and_renewal_mode_cannot_be_changed_on_restart')
            effects=state/'effects.txt'
            def call(name,allowed,deny=None,arguments=None):
                before=effects.read_text() if effects.exists() else ''
                response=client.rpc('tools/call',{'name':name,'arguments':arguments or {}})
                after=effects.read_text() if effects.exists() else ''
                if allowed: assert 'result' in response and after==before+name+'\n', {'response':response,'before':before,'after':after}
                else:
                    assert after==before and 'error' not in response and response['result']['isError'] is True, response
                    meta=response['result']['_meta']['io.github.seanebones-lang/deadbolt']
                    assert meta['code']==deny, response
                    assert response['result']['content'][0]['text'].startswith('DeadBolt denied: '+deny+'.'), response
                    retry=('never' if deny in ('killed','lease_expired','deadline_exceeded') else 'after_operator_resume' if deny=='paused' else 'after_service_recovery' if deny=='store_unavailable' else 'after_operator_intervention')
                    assert meta['retry']==retry, response
                effect_calls.append({'tool':name,'allowed':allowed,'body_ran':before!=after,'deny':deny})
            call('echo',True);passed('allowed_call_has_real_marker_effect')
            call('off_list',False,'purpose_exceeded');passed('off_policy_call_has_no_effect')
            call('write_marker',False,'needs_human');passed('irreversible_action_needs_local_operator_grant')
            operator_command('approve','--agent',config['agent'],'--tool','write_marker')
            call('write_marker',True);call('write_marker',False,'needs_human');passed('one_grant_one_effect_replay_refused')
            operator_command('pause','--agent',config['agent']);call('echo',False,'paused');passed('pause_blocks_next_effect')
            operator_command('resume','--agent',config['agent']);call('echo',True);passed('resume_restores_allowed_effect')
            operator_command('clip','echo','--agent',config['agent']);call('echo',False,'purpose_exceeded');passed('clip_blocks_selected_effect')
            operator_command('resume','--agent',config['agent'])
            operator_sql('UPDATE leases SET expires_at=0 WHERE agent_id=?',(config['agent'],))
            call('echo',False,'lease_expired');passed('expired_lease_blocks_effect')
            operator_command('kill','--agent',config['agent']);call('echo',False,'killed');passed('terminal_kill_blocks_effect')
            client.close()
            before=(state/'starts.txt').read_text()
            client=launch('/operator/config.json',True);client.proc.wait(timeout=30)
            assert client.proc.returncode!=0 and (state/'starts.txt').read_text()==before
            client.close();assert (state/'deadbolt.db').exists()
            passed('reconnect_retains_state_and_does_not_revive_killed_identity')

            def save_config():
                (operator/'config.json').write_text(json.dumps(config))
            for mutation in ({'version':1},{'offline_tools':['off_list']},{'hard_deadline_at':0},
                             {'renewal_mode':'anything'},{'hard_deadline_at':config['hard_deadline_at']+60},
                             {'renewal_mode':'supervisor'}):
                (operator/'config.json').write_text(json.dumps({**config,**mutation}))
                client=launch('/operator/config.json',True);client.proc.wait(timeout=30)
                assert client.proc.returncode!=0 and (state/'starts.txt').read_text()==before
                client.close()
            passed('legacy_invalid_and_existing_bound_changes_refused_before_downstream_start')
            config.update(agent='container-empty-destination-run',destinations=[],offline_tools=[])
            save_config();client=launch('/operator/config.json',True)
            assert 'result' in client.rpc('initialize')
            call('echo',False,'purpose_exceeded')
            call('echo',False,'purpose_exceeded',{'url':'https://allowed.example/'})
            client.close();passed('empty_explicit_destination_and_exception_lists_admit_no_effects')
            config.update(agent='container-destination-run',destinations=['allowed.example'],offline_tools=[])
            save_config();client=launch('/operator/config.json',True)
            assert 'result' in client.rpc('initialize')
            call('echo',False,'purpose_exceeded')
            call('echo',False,'purpose_exceeded',{'url':'https://foreign.example/'})
            call('echo',True,arguments={'url':'https://allowed.example/'})
            client.close();passed('all_routed_tools_require_allowed_destination_without_exception')
            config['offline_tools']=['echo'];save_config();client=launch('/operator/config.json',True)
            assert 'result' in client.rpc('initialize')
            call('echo',True);call('echo',False,'purpose_exceeded',{'url':'https://foreign.example/'})
            client.close();passed('offline_exception_does_not_override_declared_foreign_destination')
            config.update(agent='container-supervised-run',renewal_mode='supervisor')
            save_config();client=launch('/operator/config.json',True)
            assert 'result' in client.rpc('initialize')
            expires=operator_sql('SELECT expires_at FROM leases WHERE agent_id=?',(config['agent'],))[0]['expires_at']
            call('echo',True)
            assert operator_sql('SELECT expires_at FROM leases WHERE agent_id=?',(config['agent'],))[0]['expires_at']==expires
            operator_sql('UPDATE leases SET expires_at=0 WHERE agent_id=?',(config['agent'],))
            call('echo',False,'lease_expired');client.close()
            before=(state/'starts.txt').read_text();client=launch('/operator/config.json',True);client.proc.wait(timeout=30)
            assert client.proc.returncode!=0 and (state/'starts.txt').read_text()==before
            client.close();passed('supervised_calls_do_not_renew_and_expired_restart_refused')
            config.update(agent='container-deadline-run',renewal_mode='activity',hard_deadline_at=int(time.time())+20)
            save_config();client=launch('/operator/config.json',True)
            assert 'result' in client.rpc('initialize');call('echo',True)
            while time.time()<config['hard_deadline_at']+.1: time.sleep(.1)
            call('echo',False,'deadline_exceeded');client.close()
            before=(state/'starts.txt').read_text();client=launch('/operator/config.json',True);client.proc.wait(timeout=30)
            assert client.proc.returncode!=0 and (state/'starts.txt').read_text()==before
            client.close();passed('real_fixed_deadline_blocks_effect_and_restart_never_extends_it')
            config.update(agent='container-outage-run',hard_deadline_at=int(time.time())+600)
            save_config();client=launch('/operator/config.json',True)
            assert 'result' in client.rpc('initialize');call('echo',True)
            operator_sql('DROP TABLE leases')
            call('echo',False,'store_unavailable');client.close()
            passed('running_store_outage_is_readable_denial_without_effect')
        finally:
            for client in clients:
                if client.proc.poll() is None: client.close()
            run('docker','image','rm',fixture_image)
    return {'passed':True,'image':image,'image_id':info['Id'],'container_architecture':info['Architecture'],'engine_version':engine_version,'source_revision':json.loads((ROOT/'SOURCE.json').read_text())['engine_revision'],
            'scope':'Real stdio containers and disposable effects; no accounts, network, or model-mediated invocation',
            'checks':checks,'effect_calls':effect_calls,'operator_forced_idle_expiry':True,'real_wall_clock_deadline':True,'temporary_fixture_image_and_private_mounts_removed':True}


if __name__=='__main__':
    report=verify(sys.argv[1] if len(sys.argv)>1 else 'n11-deadbolt-docker:local')
    (ROOT/'acceptance-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
