from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autosecretaire.app import create_app
from autosecretaire.config import defaults
from autosecretaire.engine import Engine, digest
from autosecretaire.store import Store
from test_correspondence_filing import receive


@pytest.fixture
def engine(tmp_path):
    store = Store(tmp_path / 'state.sqlite3')
    yield Engine(defaults(tmp_path), store)
    store.close()


def test_all_new_documents_wait_for_manual_filing(engine):
    c = engine.create_client('Client', initial_folders=[])
    m = receive(engine, c, new=True)
    assert all(d['destination'] == '00 - À classer' and d['classification'] == 'pending' for d in m['documents'])
    assert not (Path(c['folder']) / '02 CORRESPONDANCES').exists()
    assert m['classification'] == 'pending'
    assert engine.store.all('print') == []
    email, *pieces = m['documents']
    engine.classify([m['id']], '03 MAILS (PDF)', document_ids=[email['id']])
    current = engine.state()['messages'][0]
    assert current['classification'] == 'pending'
    assert all(engine.store.get('document', d['id'])['path'] == d['path'] for d in pieces)
    engine.classify([m['id']], '05 PIÈCES/Pièces client', document_ids=[d['id'] for d in pieces])
    current = engine.state()['messages'][0]
    assert current['classification'] == 'classified'
    assert len(engine.store.all('print')) == 3
    pdf = engine.store.get('document', email['id'])
    Path(pdf['path']).unlink();engine.process()
    assert engine.store.get('document', email['id'])['path'] == pdf['path']
    assert digest(pdf['path']) == email['sha256']
    assert len(engine.store.all('print')) == 3


def test_mail_without_attachment_waits_for_its_own_destination(engine):
    c = engine.create_client('Client')
    m = receive(engine, c, count=0, new=True)
    assert m['classification'] == 'pending'
    assert engine.store.all('print') == []
    engine.classify([m['id']], '08 NOTES INTERNES')
    assert engine.state()['messages'][0]['classification'] == 'classified'
    assert len(engine.store.all('print')) == 1
    engine.process()
    assert engine.state()['messages'][0]['documents'][0]['destination'] == '08 NOTES INTERNES'


def test_old_fixed_pdf_stays_put_but_can_be_reclassified(engine):
    c = engine.create_client('Client')
    m = receive(engine, c)
    email = m['documents'][0]
    target = Path(c['folder']) / '02 CORRESPONDANCES' / email['name']
    if Path(email['path']) != target:Path(email['path']).rename(target)
    d = engine.store.get('document', email['id']);d.update(path=str(target), destination='02 CORRESPONDANCES', classification='classified')
    engine.store.put('document', d['id'], d)
    record = engine.store.get('message', m['id']);record.update(filing_version=2,email_destination='02 CORRESPONDANCES')
    engine.store.put('message', m['id'], record)
    engine.process()
    assert engine.store.get('document', d['id'])['path'] == str(target)
    engine.classify([m['id']], '03 MAILS (PDF)', document_ids=[d['id']])
    engine.process()
    pdf = engine.store.get('document', d['id'])
    assert pdf['destination'] == '03 MAILS (PDF)'
    assert digest(pdf['path']) == d['sha256']
    assert engine.store.all('print') == []


def test_interrupted_pdf_filing_resumes_without_filing_attachments(engine, monkeypatch):
    c = engine.create_client('Client')
    m = receive(engine, c)
    email, *pieces = m['documents']
    with monkeypatch.context() as patch:
        patch.setattr(engine, '_recover_moves', lambda: None)
        with pytest.raises(ValueError, match='incomplet'):
            engine.classify([m['id']], 'Procédure/Actes', document_ids=[email['id']])
    resumed = Engine(engine.settings, engine.store);resumed.process()
    assert resumed.store.get('document', email['id'])['destination'] == 'Procédure/Actes'
    assert all(resumed.store.get('document', d['id'])['path'] == d['path'] for d in pieces)
    assert resumed.state()['messages'][0]['classification'] == 'pending'


def test_template_no_longer_imposes_a_correspondence_folder(engine):
    t = engine.save_template(['Dossiers/Actes'], initial_folders=[])
    assert t['folders'] == ['Dossiers/Actes']
    assert engine.template()['folders'] == t['folders']
    c = engine.create_client('Client')
    m = receive(engine, c, count=0)
    assert m['documents'][0]['destination'] == '00 - À classer'
    assert engine.existing_folders(c) == ['00 - À classer']


def test_api_accepts_email_document_selection(tmp_path):
    app = create_app(defaults(tmp_path), background=False)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        headers = {'X-CSRF-Token': client.get('/api/state').json()['csrf_token']}
        c = client.post('/api/clients', headers=headers, json={'name':'Client'}).json()
        m = receive(app.state.engine, c)
        email, *pieces = m['documents']
        result = client.post('/api/classify', headers=headers, json={'message_ids':[m['id']], 'document_ids':[email['id']], 'destination':'03 MAILS (PDF)'})
        assert result.status_code == 200
        current = client.get('/api/state').json()['messages'][0]
        assert current['classification'] == 'pending'
        assert current['documents'][0]['destination'] == '03 MAILS (PDF)'
        assert all(app.state.engine.store.get('document', d['id'])['path'] == d['path'] for d in pieces)
