"""Use an explicit test catalog and empty configs; never import/reset user catalogs."""
import json
from pathlib import Path
import sys
import tempfile
from acceptance import Client, ROOT, run


def verify(catalog=None, cli=None):
    with tempfile.TemporaryDirectory(prefix='n11-docker-gateway-') as temporary:
        work=Path(temporary)
        if catalog is None:
            catalog=work/'catalog.json'
            catalog.write_text(json.dumps({'version':2,'name':'n11-deadbolt-isolated-test',
                'registry':{'deadbolt':{'title':'DeadBolt','type':'server',
                'description':'Disposable local setup validation',
                'image':'n11-deadbolt-docker:local','tools':[]}}}))
        else:
            catalog=Path(catalog).resolve()
        assert catalog.is_file()
        for name in ['config.yaml','registry.yaml','tools.yaml']:
            (work/name).write_text('{}\n')
        (work/'secrets.env').write_text('')
        prefix=[str(Path(cli).resolve())] if cli else ['docker','mcp']
        command=prefix+['gateway','run','--catalog',str(catalog),
                 '--config',str(work/'config.yaml'),'--registry',str(work/'registry.yaml'),
                 '--tools-config',str(work/'tools.yaml'),'--secrets',str(work/'secrets.env'),
                 '--servers','deadbolt','--watch=false','--log-calls=false','--transport','stdio']
        client=Client(command)
        try:
            assert 'result' in client.rpc('initialize')
            tools=client.rpc('tools/list')['result']['tools']
            assert sorted(t['name'] for t in tools)==['deadbolt_check_bundle','deadbolt_get_integration_guide']
            assert all(t.get('annotations',{}).get('readOnlyHint') for t in tools)
            check=client.rpc('tools/call',{'name':'deadbolt_check_bundle','arguments':{}})['result']
            assert not check.get('isError')
            data=check.get('structuredContent') or json.loads(check['content'][0]['text'])
            assert data['checksum_matches'] and data['active_protection'] is False
            guide=client.rpc('tools/call',{'name':'deadbolt_get_integration_guide','arguments':{'route':'stdio_client'}})['result']
            assert not guide.get('isError')
            assert 'error' in client.rpc('tools/call',{'name':'kill','arguments':{}})
        finally:
            client.close()
        return {'passed':True,'gateway_version':run(*prefix,'version').strip(),
                'catalog':str(catalog),'tools':[t['name'] for t in tools],
                'engine_target':data['target'],'checksum_matches':data['checksum_matches'],
                'active_protection':False,'scope':'Official Docker MCP Gateway with explicit local test catalog and empty configs/secrets; no model session',
                'global_catalogs_or_profiles_changed':False}


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--cli':
        report=verify(cli=sys.argv[2])
    else:
        report=verify(sys.argv[1] if len(sys.argv)>1 else None)
    (ROOT/'gateway-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
