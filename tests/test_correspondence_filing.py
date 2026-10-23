from email.message import EmailMessage
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autosecretaire.app import create_app
from autosecretaire.config import defaults
from autosecretaire.engine import Engine, digest
from autosecretaire.store import Store
from test_engine import add_mail


@pytest.fixture
def engine(tmp_path):
    store = Store(tmp_path / 'state.sqlite3')
    yield Engine(defaults(tmp_path), store)
    store.close()


def receive(e, c, count=2, new=False):
    if new:
        e.scan()
    msg = EmailMessage()
    msg['Subject'] = 'Deux pièces'
    msg['From'] = 'client@example.test'
    msg['To'] = 'cabinet@example.test'
    msg.set_content('Bonjour')
    for i in range(count):
        msg.add_attachment(f'Pièce {i}'.encode(), maintype='text', subtype='plain', filename=f'piece-{i}.txt')
    (e.runtime / 'mailboxes' / c['mailbox'] / 'mail.eml').write_bytes(msg.as_bytes())
    e.scan(); e.process()
    return e.state()['messages'][0]


def attachments(m):
    return [d for d in m['documents'] if d['kind'] == 'attachment']


def test_default_choices_and_explicit_opt_out_survive_restart(engine):
    assert engine.template()['initial_folders'] == ['02 CORRESPONDANCES']
    c = engine.create_client('Défaut')
    assert c['initial_folders'] == ['02 CORRESPONDANCES']
    assert engine.existing_folders(c) == ['02 CORRESPONDANCES']
    empty = engine.create_client('Sans dossier', initial_folders=[])
    assert not Path(empty['folder']).exists()
    t = engine.save_template(['Correspondances', 'Pièces/Signées'], initial_folders=['Pièces/Signées'], email_folder='Correspondances')
    resumed = Engine(engine.settings, engine.store)
    assert resumed.template() == t
    assert resumed.create_client('Défaut')['initial_folders'] == ['02 CORRESPONDANCES']
    other = resumed.create_client('Nouveau')
    assert resumed.existing_folders(other) == ['Pièces', 'Pièces/Signées']
    assert not (Path(other['folder']) / 'Correspondances').exists()


@pytest.mark.parametrize('options', [{'initial_folders': ['inconnu']}, {'initial_folders': '02 CORRESPONDANCES'}, {'email_folder': '../escape'}, {'email_folder': 'Absent'}])
def test_invalid_template_options_are_atomic(engine, options):
    before = engine.template()
    with pytest.raises(ValueError):
        engine.save_template(before['folders'], **options)
    assert engine.template() == before


def test_export_routes_mail_even_if_correspondence_unchecked(engine):
    c = engine.create_client('Client', initial_folders=[])
    m = receive(engine, c)
    email = next(d for d in m['documents'] if d['kind'] == 'email')
    assert Path(email['path']).parent == Path(c['folder']) / '02 CORRESPONDANCES'
    assert all(d['destination'] == '00 - À classer' and d['classification'] == 'pending' for d in attachments(m))
    assert m['classification'] == 'pending'


def test_independent_attachment_destinations_and_print_after_all(engine):
    c = engine.create_client('Client')
    m = receive(engine, c, new=True)
    a, b = attachments(m)
    email = next(d for d in m['documents'] if d['kind'] == 'email')
    original = {d['id']: digest(d['path']) for d in m['documents']}
    engine.classify([m['id']], '07 FACTURES', document_ids=[a['id']])
    partial = engine.state()['messages'][0]
    assert partial['classification'] == 'pending'
    assert engine.store.all('print') == []
    assert engine.store.get('document', b['id'])['path'] == b['path']
    engine.classify([m['id']], '05 PIÈCES/Pièces client', document_ids=[b['id']])
    current = engine.state()['messages'][0]
    assert current['classification'] == 'classified'
    assert {d['destination'] for d in attachments(current)} == {'07 FACTURES', '05 PIÈCES/Pièces client'}
    assert engine.store.get('document', email['id'])['path'] == email['path']
    assert len(engine.store.all('print')) == 3
    Path(engine.store.get('document', a['id'])['path']).unlink()
    engine.process()
    assert {d['id']: digest(d['path']) for d in engine.state()['messages'][0]['documents']} == original
    engine.classify([m['id']], '08 NOTES INTERNES')
    assert engine.store.get('document', email['id'])['path'] == email['path']
    assert len(engine.store.all('print')) == 3


def test_mail_without_attachment_is_already_filed(engine):
    c = engine.create_client('Client', initial_folders=[])
    m = receive(engine, c, count=0, new=True)
    assert m['classification'] == 'classified'
    assert len(engine.store.all('print')) == 1
    assert not (Path(c['folder']) / '00 - À classer').exists()
    with pytest.raises(ValueError, match='pièce jointe'):
        engine.classify([m['id']], '07 FACTURES')


def test_rejected_document_selection_leaves_all_files_in_place(engine):
    c = engine.create_client('Client')
    m = receive(engine, c)
    email = next(d for d in m['documents'] if d['kind'] == 'email')
    for ids in [[], [email['id']], ['inconnu'], 'invalid']:
        with pytest.raises((ValueError, KeyError)):
            engine.classify([m['id']], 'Destination/Absente', document_ids=ids)
    assert all(Path(d['path']).exists() for d in m['documents'])
    assert not (Path(c['folder']) / 'Destination').exists()


def test_partial_attachment_move_resumes_without_filing_other_pieces(engine, monkeypatch):
    c = engine.create_client('Client')
    m = receive(engine, c)
    a, b = attachments(m)
    with monkeypatch.context() as patch:
        patch.setattr(engine, '_recover_moves', lambda: None)
        with pytest.raises(ValueError, match='incomplet'):
            engine.classify([m['id']], '07 FACTURES', document_ids=[a['id']])
    resumed = Engine(engine.settings, engine.store)
    current = resumed.state()['messages'][0]
    assert current['classification'] == 'pending'
    assert resumed.store.get('document', a['id'])['destination'] == '07 FACTURES'
    assert resumed.store.get('document', b['id'])['path'] == b['path']
    assert resumed.store.all('print') == []


def test_legacy_pdf_moves_without_changing_attachments_or_printing(engine):
    c = engine.create_client('Client')
    m = receive(engine, c, count=0)
    d = m['documents'][0]
    old = Path(c['folder']) / 'Ancien' / d['name']
    old.parent.mkdir(); Path(d['path']).rename(old)
    record = engine.store.get('document', d['id']);record.update(path=str(old));record.pop('destination', None);record.pop('classification', None)
    engine.store.put('document', d['id'], record)
    record = engine.store.get('message', m['id']);record.update(destination='Ancien', classification='pending', historical=False)
    for key in ['filing_version', 'email_destination', 'classification_auto_print']:record.pop(key, None)
    engine.store.put('message', m['id'], record)
    engine.process()
    current = engine.state()['messages'][0]
    assert Path(current['documents'][0]['path']).parent == Path(c['folder']) / '02 CORRESPONDANCES'
    assert digest(current['documents'][0]['path']) == d['sha256']
    assert not old.exists()
    assert engine.store.all('print') == []


def test_api_defaults_opt_out_template_and_document_selection(tmp_path):
    app = create_app(defaults(tmp_path), background=False)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        headers = {'X-CSRF-Token': client.get('/api/state').json()['csrf_token']}
        assert client.post('/api/clients', headers=headers, json={'name':'Défaut'}).json()['initial_folders'] == ['02 CORRESPONDANCES']
        c = client.post('/api/clients', headers=headers, json={'name':'Sans', 'initial_folders':[]}).json()
        assert c['initial_folders'] == []
        response = client.put('/api/template', headers=headers, json={'folders':['Correspondances','Pièces'], 'initial_folders':['Pièces'], 'email_folder':'Correspondances'})
        assert response.status_code == 200
        assert response.json()['initial_folders'] == ['Pièces']
        m = receive(app.state.engine, c)
        a, b = attachments(m)
        response = client.post('/api/classify', headers=headers, json={'message_ids':[m['id']], 'destination':'Pièces', 'document_ids':[a['id']]})
        assert response.status_code == 200
        assert app.state.engine.store.get('document', b['id'])['destination'] == '00 - À classer'
        assert client.post('/api/classify', headers=headers, json={'message_ids':[m['id']], 'destination':'Pièces', 'document_ids':None}).status_code == 400


def test_bulk_same_names_never_share_a_target(engine):
    c = engine.create_client('Client')
    add_mail(engine, c, 'Premier');add_mail(engine, c, 'Second')
    engine.scan();engine.process()
    ms = engine.state()['messages']
    before = {d['id']: d['sha256'] for m in ms for d in attachments(m)}
    engine.classify([m['id'] for m in ms], '07 FACTURES')
    docs = [d for m in engine.state()['messages'] for d in attachments(m)]
    assert len({d['path'].casefold() for d in docs}) == 2
    assert {d['id']: digest(d['path']) for d in docs} == before


def test_pending_move_cannot_be_overwritten(engine, monkeypatch):
    c = engine.create_client('Client')
    m = receive(engine, c)
    a = attachments(m)[0]
    with monkeypatch.context() as patch:
        patch.setattr(engine, '_recover_moves', lambda: None)
        with pytest.raises(ValueError, match='incomplet'):
            engine.classify([m['id']], '07 FACTURES', document_ids=[a['id']])
    intent = engine.store.get('document', a['id'])['move_to']
    with pytest.raises(ValueError, match='incomplet'):
        engine.classify([m['id']], 'Autre', document_ids=[a['id']])
    assert engine.store.get('document', a['id'])['move_to'] == intent
    engine.process()
    assert engine.store.get('document', a['id'])['path'] == intent


def test_old_template_read_is_pure_and_new_defaults_do_not_create_old_client_folders(engine):
    c = engine.create_client('Client', initial_folders=[])
    t = engine.store.all('template')[-1]
    t.pop('initial_folders');t.pop('email_folder')
    engine.store.put('template', t['id'], t)
    before = engine.store.all('template')
    assert engine.template()['initial_folders'] == ['02 CORRESPONDANCES']
    assert engine.store.all('template') == before
    engine.retry_client(c['id'])
    assert not Path(c['folder']).exists()


def test_legacy_adaptation_preserves_filed_attachments_and_print_intents(engine, monkeypatch):
    c = engine.create_client('Client')
    m = receive(engine, c, new=True)
    engine.classify([m['id']], '07 FACTURES')
    current = engine.state()['messages'][0]
    original_attachments = {d['id']: (d['path'], digest(d['path'])) for d in attachments(current)}
    prints = engine.store.all('print')
    d = next(d for d in current['documents'] if d['kind'] == 'email')
    old = Path(c['folder']) / '07 FACTURES' / d['name']
    Path(d['path']).rename(old)
    record = engine.store.get('document', d['id']);record['path'] = str(old)
    engine.store.put('document', d['id'], record)
    record = engine.store.get('message', m['id']);record.pop('filing_version');record['destination']='07 FACTURES'
    engine.store.put('message', m['id'], record)
    with monkeypatch.context() as patch:
        patch.setattr('autosecretaire.engine.os.link', lambda *a: (_ for _ in ()).throw(OSError('disque occupé')))
        engine.process()
    assert old.exists()
    resumed = Engine(engine.settings, engine.store);resumed.process()
    assert not old.exists()
    assert engine.store.all('print') == prints
    assert {d['id']: (d['path'], digest(d['path'])) for d in attachments(engine.state()['messages'][0])} == original_attachments


def test_associating_a_pdf_does_not_mark_pending_attachments_filed(engine):
    c = engine.create_client('Client')
    m = receive(engine, c)
    email = next(d for d in m['documents'] if d['kind'] == 'email')
    legacy = Path(c['folder']) / 'ancien.pdf'
    legacy.write_bytes(Path(email['path']).read_bytes())
    engine.associate(m['id'], str(legacy))
    current = engine.state()['messages'][0]
    assert current['classification'] == 'pending'
    assert next(d for d in current['documents'] if d['kind'] == 'email')['destination'] == '.'
    engine.process()
    current = engine.state()['messages'][0]
    assert next(d for d in current['documents'] if d['kind'] == 'email')['destination'] == '02 CORRESPONDANCES'
    assert all(d['classification'] == 'pending' for d in attachments(current))
    assert engine.store.all('print') == []
