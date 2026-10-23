import json
import sqlite3
from pathlib import Path
import pytest
from autosecretaire.supervisor import Supervisor
from autosecretaire.updates import atomic_json


def registry(runtime,value):
    db=sqlite3.connect(runtime/'registry.sqlite3');db.execute('CREATE TABLE IF NOT EXISTS sample(value TEXT)');db.execute('DELETE FROM sample');db.execute('INSERT INTO sample VALUES(?)',(value,));db.commit();db.close()

def value(runtime):
    with sqlite3.connect(runtime/'registry.sqlite3') as db:return db.execute('SELECT value FROM sample').fetchone()[0]

def test_backup_restore_and_interrupted_transaction(tmp_path):
    runtime=tmp_path/'runtime';runtime.mkdir();s=Supervisor(tmp_path/'source',runtime,[],8765)
    registry(runtime,'before');backup=s.backup_registry();registry(runtime,'after')
    previous={'root':str(s.source_root),'commit':''}
    atomic_json(s.directory/'transaction.json',{'previous':previous,'backup':str(backup)})
    s.recover()
    assert value(runtime)=='before';assert s.active()==previous
    assert not (s.directory/'transaction.json').exists()
    assert json.loads((s.directory/'status.json').read_text())['status']=='error'

def test_recovery_refuses_live_registry(tmp_path):
    import fcntl
    runtime=tmp_path/'runtime';runtime.mkdir();s=Supervisor(tmp_path/'source',runtime,[],8765)
    registry(runtime,'before');backup=s.backup_registry();registry(runtime,'live')
    atomic_json(s.directory/'transaction.json',{'previous':{'root':str(s.source_root),'commit':''},'backup':str(backup)})
    with open(runtime/'server.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(RuntimeError):s.recover()
    assert value(runtime)=='live'

def test_candidate_outside_release_root_rejected(tmp_path):
    s=Supervisor(tmp_path/'source',tmp_path/'runtime',[],8765)
    with pytest.raises(ValueError):s.candidate({'root':str(tmp_path),'commit':'a'*40})

def test_failed_candidate_restores_previous(tmp_path,monkeypatch):
    s=Supervisor(tmp_path/'source',tmp_path/'runtime',[],8765);registry(s.runtime,'before')
    previous=s.active();candidate={'root':str(tmp_path/'fake'),'commit':'a'*40}
    monkeypatch.setattr(s,'candidate',lambda x:x)
    class Child:
        def poll(self):return 1
    monkeypatch.setattr(s,'launch',lambda *a,**kw:Child())
    monkeypatch.setattr(s,'wait_ready',lambda *a:False)
    assert s.switch(candidate) is False
    assert s.active()==previous;assert value(s.runtime)=='before'
    assert json.loads((s.directory/'status.json').read_text())['status']=='error'
