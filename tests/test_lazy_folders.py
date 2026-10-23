from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autosecretaire import documents
from autosecretaire.app import create_app
from autosecretaire.config import defaults
from autosecretaire.engine import Engine
from autosecretaire.store import Store
from test_engine import add_mail


@pytest.fixture
def engine(tmp_path):
    store = Store(tmp_path / 'state.sqlite3')
    e = Engine(defaults(tmp_path), store)
    e.save_template(['Procédure/TJ Paris/Conclusions', 'Pièces/Client', 'Factures'])
    yield e
    store.close()


def exported(e, client, subject='Contrat'):
    add_mail(e, client, subject)
    e.scan()
    e.process()
    return next(m for m in e.state()['messages'] if m['subject'] == subject)


def test_new_client_and_retry_reserve_all_paths_without_creating_directories(engine):
    c = engine.create_client('Client')
    assert c['status'] == 'ready'
    assert c['mailbox'] in engine.list_folders()
    assert not Path(c['folder']).exists()
    engine.retry_client(c['id'])
    assert not Path(c['folder']).exists()
    state = engine.state()['clients'][0]
    assert {'Procédure', 'Procédure/TJ Paris', 'Procédure/TJ Paris/Conclusions',
            'Pièces', 'Pièces/Client', 'Factures', '00 - À classer'} == set(state['folders'])
    assert state['existing_folders'] == []
    assert engine.history(c['id'])['candidates'] == []


def test_latest_template_and_favorites_available_to_existing_client_after_restart(engine):
    c = engine.create_client('Ancien')
    engine.save_template(['Nouveau/Profond/Dossier'])
    allowed = engine.state()['clients'][0]['folders']
    assert 'Nouveau/Profond/Dossier' in allowed
    engine.favorites(c['id'], ['Nouveau/Profond/Dossier'])
    engine.apply_template(c['id'])
    resumed = Engine(engine.settings, engine.store)
    state = resumed.state()['clients'][0]
    assert {'Nouveau', 'Nouveau/Profond', 'Nouveau/Profond/Dossier', 'Factures'} <= set(state['folders'])
    assert state['favorites'] == ['Nouveau/Profond/Dossier']
    assert not Path(c['folder']).exists()


def test_export_and_classify_create_only_needed_chain_and_remove_empty_source(engine):
    c = engine.create_client('Client')
    root = Path(c['folder'])
    m = exported(engine, c)
    assert {p.name for p in root.iterdir()} == {'00 - À classer'}
    content = {d['id']: Path(d['path']).read_bytes() for d in m['documents']}
    engine.classify([m['id']], 'Procédure/TJ Paris/Conclusions')
    assert {str(p.relative_to(root)) for p in root.rglob('*') if p.is_dir()} == {
        'Procédure', 'Procédure/TJ Paris', 'Procédure/TJ Paris/Conclusions'}
    for d in engine.state()['messages'][0]['documents']:
        assert Path(d['path']).read_bytes() == content[d['id']]
        assert Path(d['path']).parent == root / 'Procédure/TJ Paris/Conclusions'
    engine.classify([m['id']], 'Factures')
    assert {p.name for p in root.iterdir()} == {'Factures'}
    state = engine.state()['clients'][0]
    assert 'Procédure/TJ Paris/Conclusions' in state['folders']
    assert state['existing_folders'] == ['Factures']
    assert engine.store.all('print') == []  # Historical mail stays unprinted.


def test_cleanup_keeps_other_documents_hidden_files_and_unrelated_empty_folders(engine):
    c = engine.create_client('Client')
    first = exported(engine, c)
    second = exported(engine, c, 'Autre')
    root = Path(c['folder'])
    (root / 'Dossier personnel vide').mkdir()
    hidden = root / '00 - À classer/.note'
    hidden.write_text('conserver')
    engine.classify([first['id']], 'Factures')
    assert all(Path(d['path']).exists() for d in second['documents'])
    engine.classify([second['id']], 'Factures')
    assert hidden.read_text() == 'conserver'
    assert (root / 'Dossier personnel vide').is_dir()


def test_failed_export_or_missing_source_does_not_create_destination(engine, monkeypatch):
    c = engine.create_client('Client')
    add_mail(engine, c)
    engine.scan()
    with monkeypatch.context() as patch:
        patch.setattr(documents, 'export_message', lambda *a, **k: (_ for _ in ()).throw(ValueError('rendu impossible')))
        engine.process()
    assert not Path(c['folder']).exists()
    engine.process()
    m = engine.state()['messages'][0]
    Path(m['documents'][0]['path']).unlink()
    with pytest.raises(ValueError):
        engine.classify([m['id']], 'Procédure/TJ Paris/Conclusions')
    assert not (Path(c['folder']) / 'Procédure').exists()
    engine.process()
    assert all(Path(d['path']).exists() for d in engine.state()['messages'][0]['documents'])


def test_symlink_destination_cannot_create_outside_client(engine, tmp_path):
    c = engine.create_client('Client')
    m = exported(engine, c)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (Path(c['folder']) / 'Procédure').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        engine.classify([m['id']], 'Procédure/TJ Paris/Conclusions')
    assert list(outside.iterdir()) == []
    assert all(Path(d['path']).exists() for d in m['documents'])


def test_interrupted_classification_recovers_missing_branch_and_cleans_source(engine, monkeypatch):
    c = engine.create_client('Client')
    m = exported(engine, c)
    with monkeypatch.context() as patch:
        patch.setattr(engine, '_recover_moves', lambda: None)
        with pytest.raises(ValueError, match='incomplet'):
            engine.classify([m['id']], 'Procédure/TJ Paris/Conclusions')
    assert not (Path(c['folder']) / 'Procédure').exists()
    resumed = Engine(engine.settings, engine.store)
    current = resumed.state()['messages'][0]
    assert current['classification'] == 'classified'
    assert all(Path(d['path']).parent == Path(c['folder']) / 'Procédure/TJ Paris/Conclusions'
               and Path(d['path']).exists() for d in current['documents'])
    assert not (Path(c['folder']) / '00 - À classer').exists()
    assert resumed.store.all('print') == []


def test_failed_publication_cleans_empty_target_but_can_resume(engine, monkeypatch):
    c = engine.create_client('Client')
    m = exported(engine, c)
    with monkeypatch.context() as patch:
        patch.setattr('autosecretaire.engine.os.link', lambda *a: (_ for _ in ()).throw(OSError('disque occupé')))
        with pytest.raises(ValueError, match='incomplet'):
            engine.classify([m['id']], 'Procédure/TJ Paris/Conclusions')
    assert not (Path(c['folder']) / 'Procédure').exists()
    assert all(Path(d['path']).exists() for d in m['documents'])
    engine.process()
    assert engine.state()['messages'][0]['classification'] == 'classified'
    assert not (Path(c['folder']) / '00 - À classer').exists()


def test_state_api_exposes_virtual_and_existing_paths_without_writes(tmp_path):
    app = create_app(defaults(tmp_path), background=False)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        token = client.get('/api/state').json()['csrf_token']
        headers = {'X-CSRF-Token': token}
        c = client.post('/api/clients', headers=headers, json={'name': 'Client'}).json()
        client.put('/api/template', headers=headers, json={'folders': ['Récent/Enfant']})
        state = client.get('/api/state').json()['clients'][0]
        assert {'Récent', 'Récent/Enfant'} <= set(state['folders'])
        assert state['existing_folders'] == []
        assert not Path(c['folder']).exists()


def test_existing_folder_names_do_not_break_catalogue(engine):
    c = engine.create_client('Client')
    root = Path(c['folder'])
    personal = root / ' Dossier importé '
    personal.mkdir(parents=True)
    (personal / 'preuve.txt').write_text('conserver')
    state = engine.state()['clients'][0]
    assert ' Dossier importé ' in state['existing_folders']
    assert 'Factures' in state['folders']
    assert not (root / 'Factures').exists()


def test_initial_selection_creates_only_chosen_folders_and_parents(engine):
    chosen = ['Procédure/TJ Paris/Conclusions', 'Pièces']
    c = engine.create_client('Client', initial_folders=chosen)
    root = Path(c['folder'])
    assert c['status'] == 'ready'
    assert c['initial_folders'] == chosen
    assert {str(p.relative_to(root)) for p in root.rglob('*')} == {
        'Procédure', 'Procédure/TJ Paris', 'Procédure/TJ Paris/Conclusions', 'Pièces'}
    assert not (root / 'Pièces/Client').exists()  # Checking a parent does not select its children.
    assert 'Factures' in engine.state()['clients'][0]['folders']


def test_initial_selection_survives_retry_template_change_and_emptying(engine):
    c = engine.create_client('Client', initial_folders=['Procédure/TJ Paris/Conclusions'])
    root = Path(c['folder'])
    engine.save_template(['Nouveau'])
    resumed = Engine(engine.settings, engine.store)
    resumed.retry_client(c['id'])
    m = exported(resumed, c)
    resumed.classify([m['id']], 'Procédure/TJ Paris/Conclusions')
    resumed.classify([m['id']], 'Nouveau')
    assert list((root / 'Procédure/TJ Paris/Conclusions').iterdir()) == []
    assert not (root / '00 - À classer').exists()
    assert 'Procédure/TJ Paris/Conclusions' in resumed.state()['clients'][0]['folders']


def test_initial_selection_resumes_after_partial_creation(engine, monkeypatch):
    original = Path.mkdir
    def interrupted(path, *args, **kwargs):
        if path.name == 'Pièces':
            raise OSError('interruption')
        return original(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'mkdir', interrupted)
        c = engine.create_client('Client', initial_folders=['Factures', 'Pièces'])
    assert c['status'] == 'error'
    assert c['initial_folders'] == ['Factures', 'Pièces']
    proof = Path(c['folder']) / 'Factures/preuve.txt'
    proof.write_text('conserver')
    resumed = Engine(engine.settings, engine.store)
    c = resumed.retry_client(c['id'])
    assert c['status'] == 'ready'
    assert (Path(c['folder']) / 'Pièces').is_dir()
    assert not (Path(c['folder']) / 'Pièces/Client').exists()
    assert proof.read_text() == 'conserver'


@pytest.mark.parametrize('selection', ['Factures', [None], ['Inconnu'], ['../Factures'], ['/Factures']])
def test_invalid_initial_selection_has_no_side_effects(engine, selection):
    before = engine.list_folders()
    with pytest.raises(ValueError):
        engine.create_client('Client', initial_folders=selection)
    assert engine.store.all('client') == []
    assert engine.list_folders() == before
    assert list(engine.root.iterdir()) == []


def test_resubmitting_client_adds_choices_without_erasing_existing_ones(engine):
    c = engine.create_client('Client', initial_folders=['Factures'])
    proof = Path(c['folder']) / 'Factures/preuve.txt'
    proof.write_text('conserver')
    updated = engine.create_client('client', initial_folders=['Pièces', 'Pièces'])
    assert updated['id'] == c['id']
    assert set(updated['initial_folders']) == {'Factures', 'Pièces'}
    assert len(engine.store.all('client')) == 1
    assert proof.read_text() == 'conserver'
    assert engine.create_client('Client')['initial_folders'] == updated['initial_folders']


def test_initial_selection_api_validates_payload_and_exposes_created_paths(tmp_path):
    app = create_app(defaults(tmp_path), background=False)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        headers = {'X-CSRF-Token': client.get('/api/state').json()['csrf_token']}
        client.put('/api/template', headers=headers, json={'folders': ['Parent/Enfant', 'Autre']})
        for invalid in [None, 'Parent', ['Inconnu'], [False]]:
            response = client.post('/api/clients', headers=headers, json={'name': 'Invalide', 'initial_folders': invalid})
            assert response.status_code == 400
        assert client.get('/api/state').json()['clients'] == []
        response = client.post('/api/clients', headers=headers, json={'name': 'Client', 'initial_folders': ['Parent']})
        assert response.status_code == 200
        state = client.get('/api/state').json()['clients'][0]
        assert state['initial_folders'] == ['Parent']
        assert state['existing_folders'] == ['Parent']
        assert {'Parent/Enfant', 'Autre'} <= set(state['folders'])
