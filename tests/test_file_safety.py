from pathlib import Path
import os
import pytest
from test_engine import engine, add_mail


def document(e):
    c = e.create_client('Conservation'); add_mail(e, c); e.scan(); e.process()
    m = e.state()['messages'][0]
    return c, m, m['documents'][0]


def move(e, m, d, folder='Dossiers/Signés'):
    plan = e.prepare_classify([m['id']], folder, [d['id']])
    return e.confirm_operation(plan['id'], True)


def test_confirmation_required_and_prepare_has_no_file_effect(engine):
    c, m, d = document(engine); src = Path(d['path'])
    with pytest.raises(ValueError, match='confirmation'):
        engine.classify([m['id']], 'Dossiers/Signés', [d['id']])
    plan = engine.prepare_classify([m['id']], 'Dossiers/Signés', [d['id']])
    assert src.exists() and not (Path(c['folder']) / 'Dossiers').exists()
    with pytest.raises(ValueError): engine.confirm_operation(plan['id'], False)


def test_verified_move_keeps_empty_folders_and_independent_recovery(engine):
    c, m, d = document(engine); src = Path(d['path']); data = src.read_bytes()
    move(engine, m, d)
    moved = engine.store.get('document', d['id']); dst = Path(moved['path'])
    assert not src.exists() and src.parent.is_dir() and dst.read_bytes() == data
    versions = engine.recovery_versions(d['id'])
    assert versions
    dst.write_bytes(b'changed by editor')
    assert any(Path(v['path']).read_bytes() == data for v in versions)
    assert all(Path(v['path']).stat().st_ino != dst.stat().st_ino for v in versions)


@pytest.mark.parametrize('change', ['missing', 'modified'])
def test_finder_changes_are_reported_never_repaired(engine, change):
    _, m, d = document(engine); src = Path(d['path'])
    if change == 'missing': src.rename(src.with_suffix('.outside'))
    else: src.write_bytes(b'annotated or damaged, keep me')
    engine.process()
    assert engine.store.get('message', m['id'])['status'] == 'error'
    assert (not src.exists()) if change == 'missing' else src.read_bytes() == b'annotated or damaged, keep me'


def test_stale_confirmation_and_collision_leave_source(engine):
    _, m, d = document(engine); src = Path(d['path'])
    plan = engine.prepare_classify([m['id']], 'Destination', [d['id']])
    dst = Path(plan['items'][0]['target']); dst.parent.mkdir(); dst.write_bytes(b'precious')
    with pytest.raises(ValueError): engine.confirm_operation(plan['id'], True)
    assert src.exists() and dst.read_bytes() == b'precious'


def test_restore_is_explicit_additive_and_idempotent(engine):
    _, m, d = document(engine); data = Path(d['path']).read_bytes()
    move(engine, m, d); current = engine.store.get('document', d['id'])
    src = Path(current['path']); src.write_bytes(b'edited')
    version = engine.recovery_versions(d['id'])[0]
    plan = engine.prepare_restore(d['id'], version['id'])
    result = engine.confirm_operation(plan['id'], True)
    restored = Path(engine.store.get('document', d['id'])['path'])
    assert restored != src and restored.read_bytes() == data and src.read_bytes() == b'edited'
    assert engine.confirm_operation(plan['id'], True) == result
    assert not engine.store.all('print')


def test_undo_requires_new_confirmation_and_retains_directories(engine):
    _,m,d=document(engine);move(engine,m,d)
    moved=engine.store.get('document',d['id']);path=Path(moved['path'])
    with pytest.raises(ValueError):engine.undo_filing(d['id'],moved['undo_filing']['token'])
    plan=engine.prepare_undo(d['id'],moved['undo_filing']['token'])
    assert path.exists()
    engine.confirm_operation(plan['id'],True)
    assert path.parent.is_dir() and not path.exists() and Path(d['path']).exists()
    assert not engine.store.all('print')


@pytest.mark.parametrize('fault',['copy_failure','corrupt_copy','publication_race','source_edit','destination_lost','source_swap'])
def test_faults_never_destroy_a_surviving_version(engine,monkeypatch,fault):
    from mailord import file_safety as fs
    _,m,d=document(engine);src=Path(d['path']);original=src.read_bytes()
    plan=engine.prepare_classify([m['id']],'Faults/Target',[d['id']]);dst=Path(plan['items'][0]['target'])
    if fault=='copy_failure':
        monkeypatch.setattr(fs,'copy_verified',lambda *a,**k: (_ for _ in ()).throw(OSError(28,'disque plein')))
    elif fault=='corrupt_copy':
        actual=fs.fingerprint_fd;ino=src.stat().st_ino
        def corrupted(fd):
            fp=actual(fd)
            if fp['inode']!=ino:fp['sha256']='wrong'
            return fp
        monkeypatch.setattr(fs,'fingerprint_fd',corrupted)
    elif fault=='publication_race':
        actual=fs.exclusive_rename
        def collision(sp,s,tp,t):
            if t==dst.name:dst.write_bytes(b'foreign document')
            return actual(sp,s,tp,t)
        monkeypatch.setattr(fs,'exclusive_rename',collision)
    elif fault=='source_edit':
        actual=fs.publish
        def editing(*args,**kwargs):
            result=actual(*args,**kwargs);src.write_bytes(b'new edit');return result
        monkeypatch.setattr(fs,'publish',editing)
    elif fault=='destination_lost':
        actual=fs.retire
        def losing(*args,**kwargs):
            dst.unlink();return actual(*args,**kwargs)
        monkeypatch.setattr(fs,'retire',losing)
    else:
        actual=fs.exclusive_rename
        def swapping(sp,s,tp,t):
            if s==src.name:
                replacement=src.with_name('replacement');replacement.write_bytes(b'new edit');os.replace(replacement,src)
            return actual(sp,s,tp,t)
        monkeypatch.setattr(fs,'exclusive_rename',swapping)
    with pytest.raises(ValueError):engine.confirm_operation(plan['id'],True)
    # Inspect physical files, not just optimistic registry flags.
    contents=[p.read_bytes() for p in engine.runtime.rglob('*') if p.is_file() and not p.is_symlink()]
    assert original in contents
    assert src.parent.is_dir()
    if fault in ('source_edit','source_swap'):assert b'new edit' in contents
    if fault=='publication_race':assert dst.read_bytes()==b'foreign document'
    if fault in ('copy_failure','corrupt_copy','publication_race','source_edit'):assert src.exists()
    assert engine.store.get('file_operation',plan['id'])['status']=='conflict'
    assert not engine.store.all('print')


@pytest.mark.parametrize('phase',['snapshot_verified','publishing','destination_verified','retiring','source_retained','committed'])
def test_crash_journal_preserves_copies_without_auto_resume(engine,monkeypatch,phase):
    from mailord.engine import Engine
    _,m,d=document(engine);original=Path(d['path']).read_bytes()
    plan=engine.prepare_classify([m['id']],'Crash/Target',[d['id']]);put=engine.store.put
    class PowerLoss(BaseException):pass
    def interrupt(kind,id,data):
        put(kind,id,data)
        if kind=='file_operation' and data.get('status')=='running' and any(i.get('phase')==phase for i in data['items']):raise PowerLoss()
    with monkeypatch.context() as patch:
        patch.setattr(engine.store,'put',interrupt)
        with pytest.raises(PowerLoss):engine.confirm_operation(plan['id'],True)
    paths={str(p) for p in engine.root.rglob('*')}
    resumed=Engine(engine.settings,engine.store);resumed.process()
    assert paths=={str(p) for p in engine.root.rglob('*')}
    assert resumed.store.get('file_operation',plan['id'])['status']=='interrupted'
    assert any(v['available'] and Path(v['path']).read_bytes()==original for v in resumed.recovery_versions(d['id']))
    assert not resumed.store.all('print')


def test_expired_and_changed_source_plans_do_nothing(engine,monkeypatch):
    from mailord import engine as module
    _,m,d=document(engine);src=Path(d['path'])
    plan=engine.prepare_classify([m['id']],'Expired',[d['id']])
    with monkeypatch.context() as patch:
        patch.setattr(module.time,'time',lambda:plan['expires_at']+1)
        with pytest.raises(ValueError,match='expirée'):engine.confirm_operation(plan['id'],True)
    src.write_bytes(b'edited')
    with pytest.raises(ValueError,match='source a changé'):engine.confirm_operation(plan['id'],True)
    assert src.read_bytes()==b'edited' and not Path(plan['items'][0]['target']).exists()


def test_parent_replacement_and_symlink_are_rejected(engine):
    _,m,d=document(engine);parent=Path(d['path']).parent.parent/'Chosen';parent.mkdir()
    plan=engine.prepare_classify([m['id']],'Chosen',[d['id']])
    old=parent.with_name('renamed');parent.rename(old);parent.mkdir()
    with pytest.raises(ValueError):engine.confirm_operation(plan['id'],True)
    assert Path(d['path']).exists() and not list(parent.iterdir())
    link=parent/'link';link.symlink_to(old,target_is_directory=True)
    with pytest.raises(ValueError):engine.prepare_classify([m['id']],'Chosen/link',[d['id']])


def test_corrupt_recovery_is_not_restorable(engine):
    _,m,d=document(engine);v=engine.recovery_versions(d['id'])[0]
    Path(v['path']).write_bytes(b'corrupted')
    with pytest.raises(ValueError):engine.prepare_restore(d['id'],v['id'])
    assert Path(d['path']).exists()


def test_legacy_intent_and_missing_archive_root_are_never_recreated(engine):
    from mailord.engine import Engine
    _,m,d=document(engine);dst=Path(d['path']).with_name('legacy.pdf');dst.write_bytes(Path(d['path']).read_bytes())
    saved=engine.store.get('document',d['id']);saved['move_to']=str(dst);engine.store.put('document',d['id'],saved)
    engine.process();assert dst.exists() and Path(d['path']).exists()
    old=engine.root.with_name('Finder moved root');engine.root.rename(old)
    resumed=Engine(engine.settings,engine.store);resumed.process()
    assert not engine.root.exists() and old.exists()


def test_macos_metadata_and_no_hardlinked_snapshot(engine):
    import sys,subprocess
    if sys.platform!='darwin':pytest.skip('macOS metadata')
    from mailord import file_safety as fs
    _,m,d=document(engine);src=Path(d['path']);src.chmod(0o640)
    subprocess.run(['/usr/bin/xattr','-w','com.mailord.test','tags-and-resource-metadata',str(src)],check=True)
    subprocess.run(['/bin/chmod','+a','everyone allow read',str(src)],check=True)
    os.utime(src,ns=(1234567890000000000,1234567890000000000))
    original=fs.fingerprint(src);assert original['acl'] and original['xattrs']
    move(engine,m,d);target=Path(engine.store.get('document',d['id'])['path'])
    assert fs.content(fs.fingerprint(target))==fs.content(original)
    assert any(fs.content(fs.fingerprint(v['path']))==fs.content(original) for v in engine.recovery_versions(d['id']) if v['available'])


def test_confirmation_api_cannot_be_bypassed(tmp_path):
    from fastapi.testclient import TestClient
    from mailord.app import create_app
    from mailord.config import defaults
    app=create_app(defaults(tmp_path),background=False)
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        e=app.state.engine;_,m,d=document(e)
        headers={'X-CSRF-Token':client.get('/api/state').json()['csrf_token']}
        body={'message_ids':[m['id']],'document_ids':[d['id']],'destination':'API'}
        assert client.post('/api/classify',headers=headers,json=body).status_code==400
        plan=client.post('/api/classify/prepare',headers=headers,json=body).json()
        url='/api/file-operations/'+plan['id']+'/confirm'
        assert client.post(url,json={'confirm':True}).status_code==403
        assert client.post(url,headers=headers,json={'confirm':'true'}).status_code==400
        assert Path(d['path']).exists()
        assert client.post(url,headers=headers,json={'confirm':True}).status_code==200
        assert client.post(url,headers=headers,json={'confirm':True}).status_code==200


def test_missing_client_directory_not_recreated_for_new_mail(engine):
    c,m,d=document(engine);folder=Path(c['folder']);saved=folder.with_name('Moved in Finder');folder.rename(saved)
    add_mail(engine,c,'New mail');engine.scan();engine.process()
    assert saved.exists() and not folder.exists()
    assert all(m['status']=='error' for m in engine.store.all('message'))


def test_unsupported_volume_refused_before_copy(engine,monkeypatch):
    from mailord import file_safety as fs
    _,m,d=document(engine);before=len(engine.store.all('file_version'))
    monkeypatch.setattr(fs,'require_local',lambda p: (_ for _ in ()).throw(ValueError('Volume réseau refusé')))
    with pytest.raises(ValueError):engine.prepare_classify([m['id']],'Network',[d['id']])
    assert Path(d['path']).exists() and len(engine.store.all('file_version'))==before


def test_runtime_relocation_refuses_unhandled_recovery_journal(engine,tmp_path):
    from scripts.relocate_runtime import relocate
    _,m,d=document(engine);destination=tmp_path.parent/(tmp_path.name+'-copy')
    # Production uses registry.sqlite3; this fixture uses state.sqlite3.
    import sqlite3
    with sqlite3.connect(engine.runtime/'registry.sqlite3') as db:engine.store.db.backup(db)
    with pytest.raises(ValueError,match='journal de conservation'):relocate(engine.runtime,destination)
    assert not destination.exists() and Path(d['path']).exists()
