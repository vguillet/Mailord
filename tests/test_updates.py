import json
import subprocess
from pathlib import Path
import pytest
from autosecretaire.updates import UpdateManager, UpdateError, atomic_json, validate_source


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True,stderr=subprocess.DEVNULL).strip()

@pytest.fixture
def repository(tmp_path):
    root=tmp_path/'origin';root.mkdir();git(root,'init','-b','main');git(root,'config','user.email','test@example.invalid');git(root,'config','user.name','Test')
    (root/'update.json').write_text('{"update_protocol":1,"data_schema":1}')
    (root/'requirements.lock').write_text('')
    (root/'autosecretaire').mkdir();(root/'autosecretaire/__main__.py').write_text('')
    git(root,'add','update.json','requirements.lock','autosecretaire/__main__.py');git(root,'commit','-m','initial')
    return root

@pytest.mark.parametrize('url,branch', [('ext::evil','main'),('https://user:secret@example.com/a','main'),('http://example.com/a','main'),('https://example.com/a','--upload-pack=x'),('https://example.com/a','a..b'),('https://example.com/a','main\n')])
def test_source_validation(url,branch):
    with pytest.raises(ValueError):validate_source(url,branch)

def test_sources_accept_https_and_ssh():
    for url in ['https://github.com/owner/repo.git','git@github.com:owner/repo.git','ssh://git@github.com/owner/repo.git']:
        assert validate_source(url,'releases/stable')==(url,'releases/stable')

def manager(tmp_path,repo,**kw):
    return UpdateManager(tmp_path/'runtime',repo,allow_local=True,**kw)

def test_check_exact_commit_and_current(tmp_path,repository):
    m=manager(tmp_path,repository);assert m.state()['status']=='unconfigured'
    m.configure(str(repository),'main');m.check()
    assert m.state()['status']=='current'
    (repository/'new').write_text('new');git(repository,'add','new');git(repository,'commit','-m','new')
    m.check();s=m.state();assert s['status']=='available';assert s['available_commit']==git(repository,'rev-parse','HEAD')
    assert s['current_commit']!=s['available_commit']

def test_prepare_isolated_pinned_and_does_not_replace_data(tmp_path,repository):
    called=[];m=manager(tmp_path,repository,restart=lambda:called.append(True))
    m.configure(str(repository),'main')
    old=git(repository,'rev-parse','HEAD');(repository/'new').write_text('new');git(repository,'add','new');git(repository,'commit','-m','new');m.check();sha=m.state()['available_commit']
    # Newer commits must not silently replace the version the user selected.
    (repository/'new').write_text('latest');git(repository,'commit','-am','later')
    (m.runtime/'document.pdf').write_text('keep')
    m.prepare_environment=lambda release: (release/'.venv').mkdir()
    m.install(sha)
    pending=json.loads((m.directory/'pending.json').read_text());release=Path(pending['root'])
    assert git(release,'rev-parse','HEAD')==sha
    assert (release/'new').read_text()=='new'
    assert (repository/'new').read_text()=='latest'
    assert (m.runtime/'document.pdf').read_text()=='keep'
    assert m.current_commit==old and called==[True]
    assert m.state()['status']=='restarting'

def test_failed_install_leaves_current_and_retries(tmp_path,repository):
    m=manager(tmp_path,repository,restart=lambda:None);m.configure(str(repository),'main')
    (repository/'new').write_text('new');git(repository,'add','new');git(repository,'commit','-m','new');m.check();sha=m.state()['available_commit']
    def fail(path):raise UpdateError('Installation impossible.')
    m.prepare_environment=fail;m.install(sha)
    assert m.state()['status']=='error';assert not (m.directory/'pending.json').exists()
    m.check();assert m.state()['status']=='available'

def test_no_restart_and_stale_commit_rejected(tmp_path,repository):
    m=manager(tmp_path,repository);m.configure(str(repository),'main');m.check()
    with pytest.raises(ValueError):m.install_async('a'*40)

def test_incompatible_release_refused(tmp_path,repository):
    m=manager(tmp_path,repository,restart=lambda:None);m.configure(str(repository),'main')
    (repository/'update.json').write_text('{"update_protocol":2,"data_schema":1}');git(repository,'commit','-am','incompatible');m.check();m.install(m.state()['available_commit'])
    assert m.state()['status']=='error';assert 'compatible' in m.state()['error']

def test_network_error_sanitized(tmp_path,repository,monkeypatch):
    m=manager(tmp_path,repository);m.configure(str(tmp_path/'absent'),'main');m.check()
    assert m.state()['status']=='error';assert str(tmp_path) not in m.state()['error']

def test_atomic_json(tmp_path):
    p=tmp_path/'state.json';atomic_json(p,{'ok':True});assert json.loads(p.read_text())=={'ok':True}
