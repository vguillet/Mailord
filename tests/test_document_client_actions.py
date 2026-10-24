"""Document print scope and durable client stars, through the local API."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mailord import printing
from mailord.app import create_app
from mailord.config import defaults
from mailord.demo import seed


@pytest.fixture
def space(tmp_path):
    app = create_app(defaults(tmp_path), background=False)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        seed(app.state.engine)
        state = client.get('/api/state').json()
        yield client, app.state.engine, {'X-CSRF-Token': state['csrf_token']}, state


def attachment(state):
    return next(d for m in state['messages'] for d in m['documents'] if d['kind'] != 'email' and d['printable'])


def test_one_document_ignores_checkboxes_and_preserves_other_documents(space):
    client, engine, headers, state = space
    doc = attachment(state)
    engine.select_document(doc['id'], False)
    engine.update_settings({'print_sides': 'two-sided-long-edge', 'print_color_mode': 'monochrome'})
    before = engine.store.all('document')
    result = client.post(f"/api/documents/{doc['id']}/print", headers=headers, json={})
    assert result.status_code == 200
    job = result.json()
    assert job['document_id'] == doc['id'] and job['status'] == 'simulated'
    assert job['options'] == {'sides': 'two-sided-long-edge', 'color_mode': 'monochrome'}
    assert engine.store.all('document') == before
    assert len(engine.store.all('print')) == 1
    assert client.post(f"/api/documents/{doc['id']}/print", headers=headers, json={}).json()['id'] == job['id']
    assert len(engine.store.all('print')) == 1
    email = next(d for d in before if d['message_id'] == doc['message_id'] and d['kind'] == 'email')
    assert client.post(f"/api/documents/{email['id']}/print", headers=headers, json={}).status_code == 200
    assert {p['document_id'] for p in engine.store.all('print')} == {email['id'], doc['id']}


def test_document_reprint_requires_confirmation_and_stays_scoped(space):
    client, engine, headers, state = space
    doc = attachment(state)
    route = f"/api/documents/{doc['id']}"
    client.post(route + '/print', headers=headers, json={})
    for body in [{}, {'confirm': False}, {'confirm': 'true'}]:
        assert client.post(route + '/reprint', headers=headers, json=body).status_code == 400
    result = client.post(route + '/reprint', headers=headers, json={'confirm': True})
    assert result.status_code == 200 and result.json()['status'] == 'simulated'
    assert len(engine.store.all('print')) == 2
    assert {p['document_id'] for p in engine.store.all('print')} == {doc['id']}
    client.post(route + '/print', headers=headers, json={})
    assert len(engine.store.all('print')) == 2


def test_uncertain_print_does_not_submit_again_implicitly(space, monkeypatch):
    client, engine, headers, state = space
    doc = attachment(state)
    calls = []
    def submit(*args, **kwargs):
        calls.append(kwargs)
        raise printing.PrintUncertain('Résultat à vérifier')
    monkeypatch.setattr(printing, 'submit', submit)
    route = f"/api/documents/{doc['id']}"
    first = client.post(route + '/print', headers=headers, json={}).json()
    assert first['status'] == 'uncertain'
    assert client.post(route + '/print', headers=headers, json={}).json()['id'] == first['id']
    assert len(calls) == 1
    assert client.post(route + '/reprint', headers=headers, json={'confirm': True}).json()['status'] == 'uncertain'
    assert len(calls) == 2


def test_certain_failure_retries_only_the_failed_document(space, monkeypatch):
    client, engine, headers, state = space
    doc = attachment(state)
    calls = []
    def submit(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise printing.PrintError('Imprimante indisponible')
        return 'simulated-ok'
    monkeypatch.setattr(printing, 'submit', submit)
    route = f"/api/documents/{doc['id']}/print"
    first = client.post(route, headers=headers, json={}).json()
    assert first['status'] == 'error' and first['error'] == 'Imprimante indisponible'
    second = client.post(route, headers=headers, json={}).json()
    assert second['status'] == 'simulated' and second['id'] == first['id']
    assert len(calls) == 2 and len(engine.store.all('print')) == 1


@pytest.mark.parametrize('problem', ['unsupported', 'missing', 'modified', 'not_ready'])
def test_invalid_document_is_never_submitted(space, problem):
    client, engine, headers, state = space
    doc = attachment(state)
    if problem == 'unsupported':
        doc['printable'] = False
        engine.store.put('document', doc['id'], doc)
    elif problem == 'missing':
        Path(doc['path']).unlink()
    elif problem == 'modified':
        Path(doc['path']).write_text('changed')
    else:
        message = engine.store.get('message', doc['message_id'])
        message['status'] = 'queued'
        engine.store.put('message', message['id'], message)
    assert client.post(f"/api/documents/{doc['id']}/print", headers=headers, json={}).status_code == 400
    assert not engine.store.all('print')


def test_document_print_and_star_routes_protected(space):
    client, engine, headers, state = space
    doc = attachment(state)
    assert client.post(f"/api/documents/{doc['id']}/print", json={}).status_code == 403
    assert client.post('/api/documents/unknown/print', headers=headers, json={}).status_code == 404
    assert client.put(f"/api/clients/{state['clients'][0]['id']}/star", json={'starred': True}).status_code == 403
    assert client.put('/api/clients/unknown/star', headers=headers, json={'starred': True}).status_code == 404


def test_client_star_persists_without_altering_folder_favorites_or_archives(tmp_path):
    settings = defaults(tmp_path)
    app = create_app(settings, background=False)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        seed(app.state.engine)
        state = client.get('/api/state').json()
        headers = {'X-CSRF-Token': state['csrf_token']}
        c = state['clients'][0]
        assert c['starred'] is False
        app.state.engine.favorites(c['id'], ['02 CORRESPONDANCES'])
        before = app.state.engine.store.all('document')
        route = f"/api/clients/{c['id']}/star"
        assert client.put(route, headers=headers, json={'starred': True}).json()['starred'] is True
        for body in [{}, {'starred': 'true'}, {'starred': 1}, {'starred': None}]:
            assert client.put(route, headers=headers, json=body).status_code == 400
        assert app.state.engine.store.all('document') == before
        assert not app.state.engine.store.all('print')
    with TestClient(create_app(settings, background=False), base_url='http://127.0.0.1:8765') as client:
        state = client.get('/api/state').json()
        current = next(x for x in state['clients'] if x['id'] == c['id'])
        assert current['starred'] is True and current['favorites'] == ['02 CORRESPONDANCES']
        headers = {'X-CSRF-Token': state['csrf_token']}
        assert client.put(route, headers=headers, json={'starred': False}).json()['starred'] is False
        assert client.get('/api/state').json()['clients'][0]['starred'] is False
