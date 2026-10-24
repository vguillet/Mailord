"""Progress and reversible filing, using disposable local archives only."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mailord import printing
from mailord.app import create_app
from mailord.config import defaults
from mailord.demo import seed
from mailord.engine import Engine, digest


@pytest.fixture
def space(tmp_path):
    app = create_app(defaults(tmp_path), background=False)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        e = app.state.engine
        seed(e)
        state = client.get('/api/state').json()
        m = next(m for m in state['messages'] if len(m['documents']) == 2)
        yield e, client, {'X-CSRF-Token': state['csrf_token']}, m


def current(e, m):
    return next(x for x in e.state()['messages'] if x['id'] == m['id'])


def test_partial_print_and_latest_attempt_resolve_old_error(space, monkeypatch):
    e, _, _, m = space
    a, b = m['documents']
    e.print_document(a['id'])
    state = current(e, m)
    assert state['print_status'] == 'partial'
    assert state['print_progress']['simulated'] == 1
    assert state['print_progress']['total'] == 2
    e.print_document(b['id'])
    with monkeypatch.context() as p:
        p.setattr(printing, 'submit', lambda *a, **k: (_ for _ in ()).throw(printing.PrintError('offline')))
        e.print_document(a['id'], reprint=True)
    assert current(e, m)['print_status'] == 'error'
    e.print_document(a['id'], reprint=True)
    assert current(e, m)['print_status'] == 'simulated'
    assert len(e.store.all('print')) == 4
    assert any(p['status'] == 'error' for p in e.store.all('print'))


def test_unselected_attempts_still_need_attention_and_empty_is_not_complete(space, monkeypatch):
    e, _, _, m = space
    for d in m['documents']: e.select_document(d['id'], False)
    assert current(e, m)['print_status'] == 'not_selected'
    monkeypatch.setattr(printing, 'submit', lambda *a, **k: (_ for _ in ()).throw(printing.PrintUncertain('unknown')))
    e.print_document(m['documents'][0]['id'])
    state = current(e, m)
    assert state['print_status'] == 'uncertain'
    assert state['print_progress']['total'] == 1


def test_real_and_simulated_counts_are_distinct(space, monkeypatch):
    e, _, _, m = space
    e.print_document(m['documents'][0]['id'])
    e.settings['dry_run'] = False
    monkeypatch.setattr(printing, 'submit', lambda *a, **k: 'fake-printer-42')
    e.print_document(m['documents'][1]['id'])
    state = current(e, m)
    assert state['print_status'] == 'mixed'
    assert state['print_progress']['submitted'] == state['print_progress']['simulated'] == 1


def test_ordinary_print_does_not_retry_a_superseded_initial_failure(space, monkeypatch):
    e, _, _, m = space
    d = m['documents'][0]
    with monkeypatch.context() as p:
        p.setattr(printing, 'submit', lambda *a, **k: (_ for _ in ()).throw(printing.PrintError('offline')))
        e.print_document(d['id'])
    latest = e.print_document(d['id'], reprint=True)
    assert e.print_document(d['id'])['id'] == latest['id']
    assert len(e.store.all('print')) == 2


def test_undo_filing_restores_pending_survives_restart_and_is_idempotent(space):
    e, client, headers, m = space
    d = m['documents'][0]
    # A freshly exported document starts unfiled even if it already has a staging path.
    d['classification'] = 'pending'
    e.store.put('document', d['id'], d)
    e.classify([m['id']], '07 FACTURES', [d['id']])
    moved = e.store.get('document', d['id'])
    token = moved['undo_filing']['token']
    Engine(e.settings, e.store)
    route = f"/api/documents/{d['id']}/undo-filing"
    assert client.post(route, json={'token': token}).status_code == 403
    response = client.post(route, headers=headers, json={'token': token})
    assert response.status_code == 200
    restored = e.store.get('document', d['id'])
    assert restored['path'] == d['path'] and restored['classification'] == 'pending'
    assert digest(restored['path']) == d['sha256']
    assert not Path(moved['path']).exists()
    assert client.post(route, headers=headers, json={'token': token}).status_code == 200
    assert not e.store.all('print')
    assert not restored.get('undo_filing')


@pytest.mark.parametrize('problem', ['occupied', 'modified', 'stale', 'symlink'])
def test_undo_refuses_conflicts_without_touching_files(space, problem):
    e, client, headers, m = space
    d = m['documents'][0]
    e.classify([m['id']], '07 FACTURES', [d['id']])
    moved = e.store.get('document', d['id'])
    token = moved['undo_filing']['token']
    old = Path(d['path']); old.parent.mkdir(parents=True, exist_ok=True)
    if problem == 'occupied': old.write_bytes(b'keep this')
    if problem == 'modified': Path(moved['path']).write_bytes(b'edited by user')
    if problem == 'stale': token = 'outdated'
    if problem == 'symlink': old.symlink_to(moved['path'])
    before = Path(moved['path']).read_bytes()
    response = client.post(f"/api/documents/{d['id']}/undo-filing", headers=headers, json={'token': token})
    assert response.status_code == 400
    assert Path(moved['path']).read_bytes() == before
    if problem == 'occupied': assert old.read_bytes() == b'keep this'
    assert not e.store.all('print')


def test_interrupted_undo_recovers_pending_state_without_printing(space, monkeypatch):
    e, _, _, m = space
    d = m['documents'][0];d['classification'] = 'pending';e.store.put('document', d['id'], d)
    e.classify([m['id']], '07 FACTURES', [d['id']])
    token = e.store.get('document', d['id'])['undo_filing']['token']
    with monkeypatch.context() as p:
        p.setattr(e, '_publish', lambda *a, **k: (_ for _ in ()).throw(OSError('interruption')))
        with pytest.raises(ValueError): e.undo_filing(d['id'], token)
    assert e.store.get('document', d['id']).get('move_to')
    Engine(e.settings, e.store)
    restored = e.store.get('document', d['id'])
    assert restored['path'] == d['path'] and restored['classification'] == 'pending'
    assert not restored.get('move_to') and not e.store.all('print')


def test_ordinary_retry_uses_latest_failed_intent_not_an_older_generation(space, monkeypatch):
    e, _, _, m = space
    d = m['documents'][0]
    e.print_document(d['id'])
    with monkeypatch.context() as p:
        p.setattr(printing, 'submit', lambda *a, **k: (_ for _ in ()).throw(printing.PrintError('offline')))
        failed = e.print_document(d['id'], reprint=True)
    retried = e.print_document(d['id'])
    assert retried['id'] == failed['id'] and retried['status'] == 'simulated'
    assert len(e.store.all('print')) == 2


def test_undo_to_classified_location_does_not_activate_automatic_print(space):
    e, _, _, m = space
    stored = e.store.get('message', m['id'])
    stored['historical'] = False
    e.store.put('message', m['id'], stored)
    e.settings['print_policy'] = 'manual'
    e.classify([m['id']], '05 PIÈCES/Pièces client')
    d = e.store.get('document', m['documents'][0]['id'])
    e.classify([m['id']], '07 FACTURES', [d['id']])
    token = e.store.get('document', d['id'])['undo_filing']['token']
    e.settings['print_policy'] = 'after_classify'
    restored = e.undo_filing(d['id'], token)
    e.process()
    assert restored['path'] == d['path'] and restored['classification'] == 'classified'
    assert not e.store.all('print')
