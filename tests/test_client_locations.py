from filing_helpers import classify, undo, post_classify
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mailord.app import create_app
from mailord.config import defaults
from mailord.engine import Engine
from mailord.store import Store
from test_engine import add_mail


@pytest.fixture
def engine(tmp_path):
    store = Store(tmp_path / 'state.sqlite3')
    e = Engine(defaults(tmp_path), store)
    yield e
    store.close()


def test_browse_existing_parents_is_read_only_and_one_level(engine, tmp_path):
    (engine.root / 'Affaires/2026').mkdir(parents=True)
    (engine.root / 'Z vide').mkdir()
    (engine.root / 'note.txt').write_text('conserver')
    (engine.root / '.cache').mkdir()
    (engine.root / 'raccourci').symlink_to(tmp_path, target_is_directory=True)
    before = sorted(str(p) for p in engine.root.rglob('*'))
    listing = engine.client_locations()
    assert listing['parent_folder'] == ''
    assert listing['archive_root'] == str(engine.root)
    assert listing['parent_token']
    assert [p['path'] for p in listing['folders']] == ['Affaires', 'Z vide']
    children = engine.client_locations('Affaires')
    assert [p['path'] for p in children['folders']] == ['Affaires/2026']
    assert sorted(str(p) for p in engine.root.rglob('*')) == before
    assert engine.store.all('client') == []


def test_nested_client_and_initial_folders_survive_restart_and_filing(engine):
    (engine.root / 'Affaires/2026').mkdir(parents=True)
    engine.save_template(['Courriers', 'Pièces/Signées'], initial_folders=[])
    c = engine.create_client('Émilie', initial_folders=['Courriers'], parent_folder='Affaires/2026')
    assert c['status'] == 'ready'
    assert Path(c['folder']) == engine.root / 'Affaires/2026/Émilie'
    assert (Path(c['folder']) / 'Courriers').is_dir()
    assert not (Path(c['folder']) / 'Pièces').exists()
    e2 = Engine(engine.settings, engine.store)
    assert e2.create_client('Émilie')['folder'] == c['folder']
    add_mail(e2, c)
    e2.scan(); e2.process()
    m = e2.state()['messages'][0]
    classify(e2, [m['id']], 'Pièces/Signées')
    assert all(Path(d['path']).is_relative_to(Path(c['folder']) / 'Pièces/Signées') for d in e2.state()['messages'][0]['documents'])
    assert not (engine.root / 'Émilie').exists()


def test_root_default_and_empty_initial_selection_stay_lazy(engine):
    c = engine.create_client('Racine', initial_folders=[], parent_folder='')
    assert c['folder'] == str(engine.root / 'Racine')
    assert c['status'] == 'ready'
    assert not Path(c['folder']).exists()


def test_existing_client_directory_is_reused_additively(engine):
    target = engine.root / 'Affaires/Cliente'
    target.mkdir(parents=True)
    (target / 'note.txt').write_text('ne pas toucher')
    c = engine.create_client('Cliente', parent_folder='Affaires')
    assert c['status'] == 'ready'
    assert c['folder'] == str(target)
    assert (target / 'note.txt').read_text() == 'ne pas toucher'


@pytest.mark.parametrize('parent', ['../ailleurs', '/tmp', '~', 'A/../B', 'Absent', 'Fichier'])
def test_invalid_parent_rejected_before_any_effect(engine, parent):
    (engine.root / 'Fichier').write_text('conserver')
    with pytest.raises(ValueError):
        engine.create_client('Refus', parent_folder=parent)
    assert engine.store.all('client') == []
    assert engine.connector.list_folders() == []
    assert (engine.root / 'Fichier').read_text() == 'conserver'


def test_symlink_and_client_subtrees_cannot_be_parents(engine, tmp_path):
    (engine.root / 'Lien').symlink_to(tmp_path, target_is_directory=True)
    c = engine.create_client('Déjà suivi')
    for parent in ['Lien', 'Déjà suivi', 'Déjà suivi/02 CORRESPONDANCES']:
        with pytest.raises(ValueError):
            engine.create_client('Autre', parent_folder=parent)
    row = next(p for p in engine.client_locations()['folders'] if p['path'] == 'Déjà suivi')
    assert row['disabled'] is True
    assert row['reason']
    assert len(engine.store.all('client')) == 1
    assert not (tmp_path / 'Autre').exists()


def test_cannot_create_ancestor_of_a_reserved_client(engine):
    (engine.root / 'Groupe').mkdir()
    engine.create_client('Premier', initial_folders=[], parent_folder='Groupe')
    with pytest.raises(ValueError):
        engine.create_client('Groupe', initial_folders=[])
    assert len(engine.store.all('client')) == 1


def test_same_name_at_another_parent_is_not_a_move(engine):
    (engine.root / 'Affaires').mkdir()
    c = engine.create_client('Client', parent_folder='Affaires')
    before = engine.client(c['id'])
    with pytest.raises(ValueError):
        engine.create_client('Client', parent_folder='', initial_folders=[])
    assert engine.client(c['id']) == before
    assert engine.create_client('client', parent_folder='Affaires')['id'] == c['id']


def test_stale_parent_identity_and_missing_parent_fail_closed(engine):
    parent = engine.root / 'Affaires'
    parent.mkdir()
    token = engine.client_locations('Affaires')['parent_token']
    parent.rename(engine.root / 'Déplacé')
    parent.mkdir()
    with pytest.raises(ValueError):
        engine.create_client('Client', parent_folder='Affaires', parent_token=token)
    assert engine.store.all('client') == []


def test_retry_does_not_recreate_a_missing_parent(engine, monkeypatch):
    parent = engine.root / 'Affaires'
    parent.mkdir()
    original = engine.connector.create_folder
    def offline(_):
        raise RuntimeError('hors ligne')
    monkeypatch.setattr(engine.connector, 'create_folder', offline)
    c = engine.create_client('Client', parent_folder='Affaires')
    assert c['status'] == 'error'
    parent.rename(engine.root / 'Déplacé')
    monkeypatch.setattr(engine.connector, 'create_folder', original)
    result = engine.retry_client(c['id'])
    assert result['status'] == 'error'
    assert not parent.exists()
    assert engine.connector.list_folders() == []


def test_api_locations_create_and_invalid_type(tmp_path):
    app = create_app(defaults(tmp_path), background=False)
    root = app.state.engine.root
    (root / 'Années/2026').mkdir(parents=True)
    with TestClient(app, base_url='http://127.0.0.1:8765') as c:
        listing = c.get('/api/client-locations', params={'parent_folder': 'Années/2026'})
        assert listing.status_code == 200
        headers = {'X-CSRF-Token': c.get('/api/state').json()['csrf_token']}
        payload = {'name': 'Cliente', 'parent_folder': 'Années/2026', 'parent_token': listing.json()['parent_token']}
        assert c.post('/api/clients', json=payload).status_code == 403
        result = c.post('/api/clients', json=payload, headers=headers)
        assert result.status_code == 200
        assert result.json()['folder'] == str(root / 'Années/2026/Cliente')
        for parent in [None, [], 42, '../outside', 'Absent']:
            assert c.post('/api/clients', json={'name': 'Refus', 'parent_folder': parent}, headers=headers).status_code == 400
        assert c.get('/api/client-locations', params={'parent_folder': '../outside'}).status_code == 400


def test_client_target_becoming_a_link_during_mailbox_creation_stops(engine, tmp_path, monkeypatch):
    outside = tmp_path / 'outside'
    outside.mkdir()
    def replace_target(_):
        (engine.root / 'Client').symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(engine.connector, 'create_folder', replace_target)
    c = engine.create_client('Client')
    assert c['status'] == 'error'
    assert list(outside.iterdir()) == []


def test_parent_disappearing_during_mailbox_creation_is_not_recreated(engine, monkeypatch):
    parent = engine.root / 'Affaires'
    parent.mkdir()
    def move_parent(_):
        parent.rename(engine.root / 'Déplacé')
    monkeypatch.setattr(engine.connector, 'create_folder', move_parent)
    c = engine.create_client('Client', parent_folder='Affaires')
    assert c['status'] == 'error'
    assert not parent.exists()


def test_runtime_inside_archive_is_not_a_client_parent(tmp_path):
    s = defaults(tmp_path / 'Technique')
    s['archive_root'] = str(tmp_path)
    store = Store(tmp_path / 'registry.sqlite3')
    try:
        e = Engine(s, store)
        assert all(p['name'] != 'Technique' for p in e.client_locations()['folders'])
        with pytest.raises(ValueError):
            e.create_client('Client', parent_folder='Technique/spool')
    finally:
        store.close()
