"""Real HTTP and child processes, prepared revisions sharing the test interpreter.
Dependency download is exercised separately; these tests need loopback binding.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen
import pytest
from autosecretaire.updates import atomic_json

ROOT=Path(__file__).resolve().parents[1]


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True,stderr=subprocess.DEVNULL).strip()


def http(port,path,method='GET',data=None,token=''):
    request=Request(f'http://127.0.0.1:{port}{path}',method=method,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':token})
    with urlopen(request,timeout=2) as response:return json.load(response)


def wait_state(port, predicate=lambda s:True, timeout=35):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            state=http(port,'/api/state')
            if predicate(state):return state
        except (OSError,ValueError):pass
        time.sleep(.15)
    raise AssertionError('Service did not reach expected state')


@pytest.mark.parametrize('broken',[False,True])
def test_supervised_process_update_preserves_data_and_rolls_back(tmp_path,broken):
    source=tmp_path/'source';shutil.copytree(ROOT,source,ignore=shutil.ignore_patterns('.git','.venv','__pycache__','.pytest_cache','.mdse','*.egg-info'))
    # Fixture-only route invokes the same restart callback as a completed installation.
    appfile=source/'autosecretaire/app.py'
    code=appfile.read_text().replace("    @app.get('/api/health')", "    @app.post('/test-restart')\n    def test_restart():\n        restart(); return {'ok':True}\n    @app.get('/api/health')")
    appfile.write_text(code)
    git(source,'init','-b','main');git(source,'config','user.name','Test');git(source,'config','user.email','test@example.invalid');git(source,'add','autosecretaire','update.json','requirements.lock');git(source,'commit','-m','baseline')
    original=git(source,'rev-parse','HEAD')
    runtime=tmp_path/'runtime';release=runtime/'updates/releases/candidate';release.parent.mkdir(parents=True)
    subprocess.run(['git','clone','--no-local',str(source),str(release)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    git(release,'config','user.name','Test');git(release,'config','user.email','test@example.invalid')
    if broken:(release/'autosecretaire/__main__.py').write_text('raise RuntimeError("fixture startup failure")\n')
    else:(release/'marker').write_text('updated')
    git(release,'add','autosecretaire/__main__.py' if broken else 'marker');git(release,'commit','-m','candidate')
    sha=git(release,'rev-parse','HEAD')
    if sys.prefix!=sys.base_prefix:
        (release/'.venv').symlink_to(Path(sys.prefix),target_is_directory=True)
    else:
        (release/'.venv/bin').mkdir(parents=True);(release/'.venv/bin/python').symlink_to(sys.executable)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    log=open(tmp_path/'service.log','w+')
    process=subprocess.Popen([sys.executable,'-m','autosecretaire','--data-dir',os.path.relpath(runtime,source),'--port',str(port)],cwd=source,stdout=log,stderr=log,env={**os.environ,'PYTHONPATH':str(source)})
    try:
        state=wait_state(port);token=state['csrf_token']
        client=http(port,'/api/clients','POST',{'name':'Client conservé'},token)
        document=Path(client['folder'])/'preuve.pdf';document.write_bytes(b'archive unchanged')
        atomic_json(runtime/'updates/pending.json',{'root':str(release),'commit':sha})
        http(port,'/test-restart','POST',{},token)
        if broken:
            state=wait_state(port,lambda s:s['updates']['status']=='error')
            assert state['updates']['current_commit']==original
            assert 'restaurée' in state['updates']['error']
        else:
            state=wait_state(port,lambda s:s['updates']['current_commit']==sha)
            assert json.loads((runtime/'updates/active.json').read_text())['commit']==sha
        assert state['csrf_token']!=token
        assert [c['name'] for c in state['clients']]==['Client conservé']
        assert document.read_bytes()==b'archive unchanged'
        assert state['messages']==[]
        assert git(source,'rev-parse','HEAD')==original
        assert not (runtime/'updates/transaction.json').exists()
        assert list((runtime/'updates/backups').glob('*.sqlite3'))
        if not broken:
            # The stable original launcher must still select the new version next launch.
            process.terminate();process.wait(timeout=15)
            process=subprocess.Popen([sys.executable,'-m','autosecretaire','--data-dir',os.path.relpath(runtime,source),'--port',str(port)],cwd=source,stdout=log,stderr=log,env={**os.environ,'PYTHONPATH':str(source)})
            again=wait_state(port,lambda s:s['updates']['current_commit']==sha)
            assert [c['name'] for c in again['clients']]==['Client conservé']
    finally:
        process.terminate()
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()
