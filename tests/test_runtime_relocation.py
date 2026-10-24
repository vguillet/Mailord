import fcntl
from pathlib import Path

import pytest

from mailord.store import Store
from scripts.relocate_runtime import relocate


def test_relocation_keeps_originals_ids_external_paths_and_print_history(tmp_path):
    source = tmp_path / 'before'
    destination = tmp_path / 'after'
    store = Store(source / 'registry.sqlite3')
    archive = source / 'Archives' / 'Client' / 'mail.pdf'
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b'original PDF bytes')
    store.put('document', 'doc-1', {'path': str(archive), 'body': str(source),
        'undo_filing': {'path': str(source / 'Archives' / 'previous.pdf')}, 'selected': False})
    store.put('job', 'print-1', {'status': 'submitted', 'path': '/external/document.pdf'})
    store.put('client', 'client-1', {'folder': str(source) + '-other/client', 'starred': True})
    store.close()
    before = (source / 'registry.sqlite3').read_bytes()
    relocate(source, destination)
    moved = Store(destination / 'registry.sqlite3')
    doc = moved.get('document', 'doc-1')
    assert Path(doc['path']).read_bytes() == archive.read_bytes()
    assert doc['body'] == str(source)
    assert doc['undo_filing']['path'] == str(destination / 'Archives' / 'previous.pdf')
    assert doc['selected'] is False
    assert moved.get('job', 'print-1')['status'] == 'submitted'
    assert moved.get('job', 'print-1')['path'] == '/external/document.pdf'
    assert moved.get('client', 'client-1')['starred'] is True
    assert moved.get('client', 'client-1')['folder'] == str(source) + '-other/client'
    moved.close()
    assert (source / 'registry.sqlite3').read_bytes() == before


@pytest.mark.parametrize('lock_name', ['server.lock', 'supervisor.lock'])
def test_relocation_refuses_running_service(tmp_path, lock_name):
    source = tmp_path / 'before'; source.mkdir()
    with (source / lock_name).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match='arrêt'):
            relocate(source, tmp_path / 'after')
    assert not (tmp_path / 'after').exists()


def test_relocation_refuses_overwrite_nested_destination_and_symlinks(tmp_path):
    source = tmp_path / 'before'; source.mkdir()
    occupied = tmp_path / 'occupied'; occupied.mkdir()
    (occupied / 'keep').write_text('keep')
    with pytest.raises(ValueError): relocate(source, occupied)
    with pytest.raises(ValueError): relocate(source, source / 'nested')
    (source / 'link').symlink_to(occupied, target_is_directory=True)
    with pytest.raises(ValueError): relocate(source, tmp_path / 'after')
    assert (occupied / 'keep').read_text() == 'keep'
    assert not (tmp_path / 'after').exists()
