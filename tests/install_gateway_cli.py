"""CI-only official Docker CLI download, pinned by version and release checksum."""
import hashlib
import io
from pathlib import Path
import platform
import sys
import tarfile
from urllib.request import urlopen

ARCHIVES={
    'x86_64':('amd64','de2c5f21fb92ed6cc993cd7150abb8d67d96bac3ab2a4df24962823516ee7bff'),
    'aarch64':('arm64','712cc619deec0c2490a0bf8d1072733b0da7c48b3d4919299c8caad8657e4c46'),
}
assert platform.system()=='Linux', 'This helper is only for Linux CI; use Docker Desktop locally'
arch,expected=ARCHIVES[platform.machine()]
url='https://github.com/docker/mcp-gateway/releases/download/v0.42.0/docker-mcp-linux-'+arch+'.tar.gz'
with urlopen(url,timeout=60) as response:
    archive=response.read(150*1024*1024)
assert len(archive)<150*1024*1024 and hashlib.sha256(archive).hexdigest()==expected
with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
    members=[m for m in tar.getmembers() if m.isfile() and Path(m.name).name=='docker-mcp']
    assert len(members)==1
    destination=Path(sys.argv[1]).resolve()
    destination.write_bytes(tar.extractfile(members[0]).read())
    destination.chmod(0o755)
print('Verified official Docker MCP Gateway v0.42.0 for '+arch)
