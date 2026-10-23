import json
import ssl
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from autosecretaire.connectors import (
    AppleMailConnector, ConnectorError, DemoConnector, IMAPConnector,
    SourceMessage, decode_mailbox, encode_mailbox, make_connector,
)

RAW = b'From: client@example.test\r\nMessage-ID: <one@example.test>\r\nSubject: Bonjour\r\n\r\nTexte\r\n'


def test_demo_discovers_nested_folders_and_reads_without_changing_message(tmp_path):
    connector = DemoConnector(tmp_path)
    assert connector.create_folder('Clients/Andr\u00e9 & fils') == 'Clients/Andr\u00e9 & fils'
    connector.create_folder('Clients/Andr\u00e9 & fils')
    path = tmp_path / 'Clients/Andr\u00e9 & fils/one.eml'
    path.write_bytes(RAW)
    before = path.stat().st_mtime_ns
    assert connector.list_folders() == ['Clients', 'Clients/Andr\u00e9 & fils']
    found = connector.list_messages('Clients/Andr\u00e9 & fils')
    assert len(found) == 1
    assert isinstance(found[0], SourceMessage)
    assert found[0].message_id == '<one@example.test>'
    assert datetime.fromisoformat(found[0].received_at).tzinfo is not None
    assert connector.fetch('Clients/Andr\u00e9 & fils', found[0].source_id) == RAW
    assert path.stat().st_mtime_ns == before


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'a/../b', 'a//b', '.', '', 'a\\b', 'a\nb'])
def test_demo_rejects_paths_outside_named_folder(tmp_path, name):
    with pytest.raises(ConnectorError):
        DemoConnector(tmp_path).create_folder(name)


def test_demo_rejects_symlink_file_and_folder_escape(tmp_path):
    root = tmp_path / 'root'
    connector = DemoConnector(root)
    connector.create_folder('Client')
    outside = tmp_path / 'outside.eml'
    outside.write_bytes(RAW)
    (root / 'Client' / 'escape.eml').symlink_to(outside)
    with pytest.raises(ConnectorError):
        connector.fetch('Client', 'escape.eml')
    (root / 'outside').symlink_to(tmp_path, target_is_directory=True)
    assert 'outside' not in connector.list_folders()


@pytest.mark.parametrize('name', ['Clients/Andr\u00e9 & fils', '台北/日本語', 'a"b\\c', 'simple'])
def test_imap_modified_utf7_roundtrip(name):
    encoded = encode_mailbox(name)
    encoded.encode('ascii')
    assert decode_mailbox(encoded) == name
    assert encode_mailbox('&') == '&-'


class FakeIMAP:
    def __init__(self):
        self.calls = []
        self.folders = [b'(\\HasChildren) "." "Clients"', b'(\\HasNoChildren) "." "Clients.Andr&AOk- &- fils"']
        self.uidvalidity = b'77'
        self.bad_search = False

    def login(self, user, password):
        self.calls.append(('login', user, password))
        return 'OK', []

    def logout(self):
        self.calls.append(('logout',))
        return 'BYE', []

    def list(self, *args):
        self.calls.append(('list', *args))
        return 'OK', self.folders

    def create(self, folder):
        self.calls.append(('create', folder))
        self.folders.append(b'(\\HasNoChildren) "." ' + folder.encode())
        return 'OK', []

    def select(self, folder, readonly=False):
        self.calls.append(('select', folder, readonly))
        return 'OK', [b'1']

    def response(self, name):
        return name, [self.uidvalidity]

    def uid(self, action, *args):
        self.calls.append(('uid', action, *args))
        if action.upper() == 'SEARCH':
            return ('NO', [b'failure']) if self.bad_search else ('OK', [b'42'])
        if 'HEADER.FIELDS' in args[-1]:
            return 'OK', [(b'1 (UID 42 INTERNALDATE "23-Oct-2026 09:31:00 +0200" BODY[HEADER.FIELDS (MESSAGE-ID)] {36}', b'Message-ID: <one@example.test>\r\n\r\n'), b')']
        return 'OK', [(b'1 (UID 42 BODY[] {90}', RAW), b')']


@pytest.fixture
def imap_setup(monkeypatch):
    fake = FakeIMAP()
    options = {}

    def connect(host, port, **kwargs):
        options.update(host=host, port=port, **kwargs)
        return fake

    monkeypatch.setattr('autosecretaire.connectors.imaplib.IMAP4_SSL', connect)
    monkeypatch.setenv('TEST_MAIL_PASSWORD', 'secret-do-not-log')
    connector = IMAPConnector({'imap_host': 'imap.example.test', 'imap_port': 993,
                              'imap_user': 'test@example.test', 'imap_password_env': 'TEST_MAIL_PASSWORD'})
    return connector, fake, options


def test_imap_list_unicode_and_nested_create_idempotent(imap_setup):
    connector, fake, options = imap_setup
    assert connector.list_folders() == ['Clients', 'Clients/Andr\u00e9 & fils']
    assert connector.create_folder('Clients/Andr\u00e9 & fils') == 'Clients/Andr\u00e9 & fils'
    assert not [call for call in fake.calls if call[0] == 'create']
    connector.create_folder('Clients/Andr\u00e9 & fils/2026')
    assert ('create', '"Clients.Andr&AOk- &- fils.2026"') in fake.calls
    assert options['ssl_context'].check_hostname
    assert options['ssl_context'].verify_mode == ssl.CERT_REQUIRED


def test_imap_searches_all_uses_uidvalidity_and_never_marks_read(imap_setup):
    connector, fake, _ = imap_setup
    messages = connector.list_messages('Clients/Andr\u00e9 & fils')
    assert messages == [SourceMessage('77:42', '2026-10-23T09:31:00+02:00', '<one@example.test>')]
    assert connector.fetch('Clients/Andr\u00e9 & fils', '77:42') == RAW
    assert ('uid', 'SEARCH', None, 'ALL') in fake.calls
    assert all(call[-1] is True for call in fake.calls if call[0] == 'select')
    assert any('BODY.PEEK[]' in str(call) for call in fake.calls)
    assert not any('STORE' in str(call) for call in fake.calls)


def test_imap_uidvalidity_change_does_not_fetch_different_message(imap_setup):
    connector, fake, _ = imap_setup
    fake.uidvalidity = b'88'
    with pytest.raises(ConnectorError, match='identit'):
        connector.fetch('Clients/Andr\u00e9 & fils', '77:42')
    assert not [call for call in fake.calls if call[:2] == ('uid', 'FETCH')]


def test_imap_failed_response_not_an_empty_mailbox(imap_setup):
    connector, fake, _ = imap_setup
    fake.bad_search = True
    with pytest.raises(ConnectorError):
        connector.list_messages('Clients')
    assert fake.calls[-1] == ('logout',)


def test_imap_requires_secret_before_network(monkeypatch):
    monkeypatch.delenv('TEST_MAIL_PASSWORD', raising=False)
    monkeypatch.setattr('autosecretaire.connectors.imaplib.IMAP4_SSL', lambda *a, **k: pytest.fail('network called'))
    with pytest.raises(ConnectorError, match='TEST_MAIL_PASSWORD'):
        IMAPConnector({'imap_user': 'test', 'imap_password_env': 'TEST_MAIL_PASSWORD'}).list_folders()


def test_imap_literal_list_response(imap_setup):
    connector, fake, _ = imap_setup
    fake.folders = [(b'(\\HasNoChildren) "/" {12}', b'Client Alpha')]
    assert connector.list_folders() == ['Client Alpha']


def test_apple_mail_payload_not_interpolated_into_script(monkeypatch):
    calls = []
    folder = 'Client "x"; do shell script "bad"'
    responses = [[folder, folder + '/2026'], folder,
                 [{'source_id': '123', 'received_at': '2026-10-23T07:31:00.000Z', 'message_id': '<one@example.test>'}],
                 RAW.decode()]

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(responses.pop(0)), stderr='')

    monkeypatch.setattr('autosecretaire.connectors.subprocess.run', run)
    connector = AppleMailConnector('Orange')
    assert connector.list_folders() == [folder, folder + '/2026']
    assert connector.create_folder(folder) == folder
    messages = connector.list_messages(folder)
    assert messages[0].source_id == '123'
    assert connector.fetch(folder, '123') == RAW
    command, kwargs = calls[-1]
    assert command[:3] == ['/usr/bin/osascript', '-l', 'JavaScript']
    assert folder not in command[4]
    assert json.loads(command[-1]) == {'action': 'fetch', 'account': 'Orange', 'folder': folder, 'source_id': '123'}
    assert not kwargs.get('shell', False)


def test_apple_mail_reports_denied_permission_and_bad_json(monkeypatch):
    monkeypatch.setattr('autosecretaire.connectors.subprocess.run', lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='Not authorized (-1743)'))
    with pytest.raises(ConnectorError, match='Automatisation'):
        AppleMailConnector('').list_folders()
    monkeypatch.setattr('autosecretaire.connectors.subprocess.run', lambda *a, **k: SimpleNamespace(returncode=0, stdout='nonsense', stderr=''))
    with pytest.raises(ConnectorError):
        AppleMailConnector('').list_folders()


def test_connector_factory_no_connection_on_construction(tmp_path):
    assert isinstance(make_connector({'connector': 'demo'}, tmp_path), DemoConnector)
    assert isinstance(make_connector({'connector': 'imap'}, tmp_path), IMAPConnector)
    assert isinstance(make_connector({'connector': 'apple_mail', 'mail_account': ''}, tmp_path), AppleMailConnector)
    with pytest.raises(ConnectorError):
        make_connector({'connector': 'unknown'}, tmp_path)


def test_imap_uid_after_literal_is_recognized(imap_setup):
    connector, fake, _ = imap_setup
    old_uid = fake.uid

    def uid(action, *args):
        if action.upper() == 'SEARCH':
            return old_uid(action, *args)
        if 'HEADER.FIELDS' in args[-1]:
            return 'OK', [(b'1 (INTERNALDATE "23-Oct-2026 09:31:00 +0200" BODY[HEADER.FIELDS (MESSAGE-ID)] {36}', b'Message-ID: <one@example.test>\r\n\r\n'), b' UID 42)']
        return 'OK', [(b'1 (BODY[] {90}', RAW), b' UID 42)']

    fake.uid = uid
    assert connector.list_messages('Clients')[0].source_id == '77:42'
    assert connector.fetch('Clients', '77:42') == RAW


def test_imap_rejects_reserved_server_delimiter_in_new_component(imap_setup):
    connector, fake, _ = imap_setup
    with pytest.raises(ConnectorError, match='séparateur'):
        connector.create_folder('Clients/Acme.sarl')
    assert not [call for call in fake.calls if call[0] == 'create']


def test_imap_flat_namespace_cannot_create_nested_folder(imap_setup):
    connector, fake, _ = imap_setup
    fake.folders = [b'(\\HasNoChildren) NIL "Clients"']
    with pytest.raises(ConnectorError, match='sous-dossiers'):
        connector.create_folder('Clients/Nouveau')


def test_apple_mail_timeout_is_visible(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 120)

    monkeypatch.setattr('autosecretaire.connectors.subprocess.run', timeout)
    with pytest.raises(ConnectorError, match='répond pas'):
        AppleMailConnector('').list_folders()
