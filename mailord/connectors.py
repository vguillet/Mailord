"""Mailbox adapters. Reads never change read flags; credentials are never persisted.

Apple Mail uses its published scripting dictionary, through JavaScript for
Automation, not Mail's private database. Hardware integration remains an
installation-time check; unit tests use isolated files and mocked transports.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesHeaderParser
import imaplib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
from typing import Protocol


class ConnectorError(RuntimeError):
    """Actionable connection, mailbox or source error, safe to show in the UI."""


@dataclass(frozen=True)
class SourceMessage:
    source_id: str
    received_at: str
    message_id: str = ''


class Connector(Protocol):
    def list_folders(self) -> list[str]: ...
    def create_folder(self, name: str) -> str: ...
    def list_messages(self, folder: str) -> list[SourceMessage]: ...
    def fetch(self, folder: str, source_id: str) -> bytes: ...


def _folder(name: str) -> str:
    if (not isinstance(name, str) or not name or name.startswith('/')
            or '\\' in name or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or any(part in ('', '.', '..') for part in name.split('/'))):
        raise ConnectorError('Nom de dossier invalide. Utilisez des noms séparés par / sans .. .')
    return name


class DemoConnector:
    """A directory per mailbox, containing .eml files (no network or Mail access)."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, folder: str) -> Path:
        path = (self.root / _folder(folder)).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ConnectorError('Le dossier sort de la boîte de démonstration.')
        return path

    def list_folders(self) -> list[str]:
        return sorted(path.relative_to(self.root).as_posix()
                      for path in self.root.rglob('*')
                      if path.is_dir() and not path.is_symlink()
                      and path.resolve().is_relative_to(self.root))

    def create_folder(self, name: str) -> str:
        try:
            self._path(name).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConnectorError('Impossible de créer le dossier de démonstration.') from exc
        return name

    def list_messages(self, folder: str) -> list[SourceMessage]:
        directory = self._path(folder)
        if not directory.is_dir():
            raise ConnectorError('Dossier de démonstration introuvable.')
        result = []
        try:
            for path in sorted(directory.iterdir()):
                if path.suffix.lower() != '.eml' or not path.is_file() or path.is_symlink():
                    continue
                headers = BytesHeaderParser(policy=policy.default).parsebytes(path.read_bytes())
                received = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
                result.append(SourceMessage(path.name, received, str(headers.get('Message-ID', ''))))
        except OSError as exc:
            raise ConnectorError('Impossible de lire la boîte de démonstration.') from exc
        return result

    def fetch(self, folder: str, source_id: str) -> bytes:
        directory = self._path(folder)
        if not source_id or source_id in ('.', '..') or '/' in source_id or '\\' in source_id:
            raise ConnectorError('Identifiant de message invalide.')
        path = directory / source_id
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ConnectorError('Le message sort de la boîte de démonstration.')
        try:
            return path.read_bytes()
        except OSError as exc:
            raise ConnectorError('Message de démonstration introuvable ou inaccessible.') from exc


def encode_mailbox(value: str) -> str:
    """IMAP4rev1 modified UTF-7 (RFC 3501 §5.1.3)."""
    result, pending = [], []

    def flush():
        if pending:
            data = ''.join(pending).encode('utf-16-be')
            result.append('&' + base64.b64encode(data).decode('ascii').rstrip('=').replace('/', ',') + '-')
            pending.clear()

    for char in value:
        if ' ' <= char <= '~':
            flush()
            result.append('&-' if char == '&' else char)
        else:
            pending.append(char)
    flush()
    return ''.join(result)


def decode_mailbox(value: str | bytes) -> str:
    if isinstance(value, bytes):
        value = value.decode('ascii')

    def decode(match):
        part = match.group(1)
        if not part:
            return '&'
        encoded = part.replace(',', '/')
        encoded += '=' * (-len(encoded) % 4)
        return base64.b64decode(encoded, validate=True).decode('utf-16-be')

    try:
        return re.sub(r'&([^-]*)-', decode, value)
    except (ValueError, UnicodeError) as exc:
        raise ConnectorError('Nom de dossier IMAP invalide.') from exc


def _quote(value: str) -> str:
    if any(ord(char) < 32 for char in value):
        raise ConnectorError('Nom de dossier IMAP invalide.')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _unquote(value: str) -> str:
    if value.startswith('"') and value.endswith('"'):
        return re.sub(r'\\(.)', r'\1', value[1:-1])
    return value


def _checked(result, operation: str):
    status, data = result
    if status != 'OK':
        raise ConnectorError(f'Le serveur IMAP a refusé l’opération : {operation}.')
    return data or []


def _internal_date(metadata: bytes) -> str:
    match = re.search(rb'INTERNALDATE "\s*(\d+)-([A-Za-z]{3})-(\d{4}) (\d\d):(\d\d):(\d\d) ([+-])(\d\d)(\d\d)"', metadata)
    if not match:
        return ''
    day, month, year, hour, minute, second, sign, offh, offm = match.groups()
    months = {name: i for i, name in enumerate(
        [b'Jan', b'Feb', b'Mar', b'Apr', b'May', b'Jun', b'Jul', b'Aug', b'Sep', b'Oct', b'Nov', b'Dec'], 1)}
    try:
        offset = timedelta(hours=int(offh), minutes=int(offm)) * (-1 if sign == b'-' else 1)
        date = datetime(int(year), months[month.title()], int(day), int(hour), int(minute), int(second), tzinfo=timezone(offset))
        return date.isoformat()
    except (ValueError, KeyError) as exc:
        raise ConnectorError('Date de réception IMAP invalide.') from exc


def _fetch_literals(data):
    """Join FETCH metadata before/after a literal; servers choose item order."""
    metadata, literal = None, None
    for item in data:
        if isinstance(item, tuple):
            if metadata is not None:
                yield metadata, literal
            metadata, literal = item
        elif isinstance(item, bytes) and metadata is not None:
            metadata += b' ' + item
    if metadata is not None:
        yield metadata, literal


class IMAPConnector:
    """TLS-verified IMAP; source ids combine UIDVALIDITY and UID."""

    def __init__(self, settings: dict):
        self.settings = dict(settings)

    @contextmanager
    def _connection(self):
        secret_name = self.settings.get('imap_password_env', 'MAILORD_IMAP_PASSWORD')
        password = os.environ.get(secret_name, '')
        if not password:
            raise ConnectorError(f'Mot de passe absent : configurez la variable {secret_name}.')
        if not self.settings.get('imap_user'):
            raise ConnectorError('Renseignez l’identifiant du compte IMAP.')
        connection = None
        try:
            connection = imaplib.IMAP4_SSL(self.settings.get('imap_host', 'imap.orange.fr'),
                                          int(self.settings.get('imap_port', 993)),
                                          ssl_context=ssl.create_default_context(), timeout=30)
            _checked(connection.login(self.settings['imap_user'], password), 'authentification')
            yield connection
        except (OSError, imaplib.IMAP4.error) as exc:
            # Server exception text can contain login arguments or private data.
            raise ConnectorError('Connexion IMAP impossible. Vérifiez le réseau, le serveur et les identifiants.') from exc
        finally:
            if connection is not None:
                try:
                    connection.logout()  # Never CLOSE/EXPUNGE a mailbox.
                except (OSError, imaplib.IMAP4.error):
                    pass

    def _catalog(self, connection):
        data = _checked(connection.list('""', '"*"'), 'liste des dossiers')
        if not data or data == [None]:
            data = _checked(connection.list('""', '""'), 'séparateur des dossiers')
        folders = {}
        delimiters = []
        for row in data:
            if row is None:
                continue
            literal = row[1] if isinstance(row, tuple) else None
            header = row[0] if isinstance(row, tuple) else row
            match = re.match(rb'^\([^)]*\)\s+(NIL|"(?:[^"\\]|\\.)*")\s+(.+)$', header)
            if not match:
                raise ConnectorError('Réponse IMAP de dossiers non reconnue.')
            raw_delimiter, raw_name = match.groups()
            delimiter = None if raw_delimiter == b'NIL' else _unquote(raw_delimiter.decode('ascii'))
            delimiters.append(delimiter)
            try:
                encoded_name = literal.decode('ascii') if literal is not None else _unquote(raw_name.decode('ascii'))
                name = decode_mailbox(encoded_name)
            except (UnicodeError, ValueError) as exc:
                raise ConnectorError('Nom de dossier IMAP non reconnu.') from exc
            if not name:
                continue
            canonical = name.replace(delimiter, '/') if delimiter else name
            _folder(canonical)
            if canonical in folders and folders[canonical][0] != name:
                raise ConnectorError('Deux dossiers IMAP ont le même chemin apparent.')
            folders[canonical] = (name, delimiter)
        return folders, (delimiters[0] if delimiters else '/')

    def list_folders(self) -> list[str]:
        with self._connection() as connection:
            folders, _ = self._catalog(connection)
            return sorted(folders)

    def create_folder(self, name: str) -> str:
        _folder(name)
        with self._connection() as connection:
            folders, delimiter = self._catalog(connection)
            for i in range(1, len(name.split('/')) + 1):
                canonical = '/'.join(name.split('/')[:i])
                if canonical in folders:
                    continue
                parent = canonical.rpartition('/')[0]
                part = canonical.rsplit('/', 1)[-1]
                if parent in folders:
                    parent_native, delimiter = folders[parent]
                    if delimiter is None:
                        raise ConnectorError('Ce serveur ne permet pas de sous-dossiers.')
                    native = parent_native + delimiter + part
                else:
                    native = canonical
                if delimiter and delimiter != '/' and delimiter in part:
                    raise ConnectorError(f'Le nom contient le séparateur réservé du serveur : {delimiter}')
                result = connection.create(_quote(encode_mailbox(native)))
                if result[0] != 'OK':
                    # Another process may just have created it; only accept proved existence.
                    existing, _ = self._catalog(connection)
                    if canonical not in existing:
                        _checked(result, 'création du dossier')
                folders[canonical] = (native, delimiter)
        return name

    def _select(self, connection, folder: str) -> str:
        _folder(folder)
        folders, _ = self._catalog(connection)
        if folder not in folders:
            raise ConnectorError('Dossier IMAP introuvable. Actualisez la liste des dossiers.')
        native, _ = folders[folder]
        _checked(connection.select(_quote(encode_mailbox(native)), readonly=True), 'lecture du dossier')
        _, response = connection.response('UIDVALIDITY')
        validity = (response or [b''])[0]
        if isinstance(validity, bytes):
            validity = validity.decode('ascii')
        if not validity or not str(validity).isdigit():
            raise ConnectorError('Le serveur ne fournit pas l’identité stable du dossier (UIDVALIDITY).')
        return str(validity)

    def list_messages(self, folder: str) -> list[SourceMessage]:
        with self._connection() as connection:
            validity = self._select(connection, folder)
            search = _checked(connection.uid('SEARCH', None, 'ALL'), 'recherche des messages')
            uids = (search[0] or b'').split() if search else []
            if any(not uid.isdigit() for uid in uids):
                raise ConnectorError('Liste de messages IMAP invalide.')
            result = []
            for offset in range(0, len(uids), 100):
                batch = uids[offset:offset + 100]
                data = _checked(connection.uid('FETCH', b','.join(batch).decode('ascii'),
                                                '(UID INTERNALDATE BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])'),
                                'lecture des en-têtes')
                found = {}
                for metadata, headers in _fetch_literals(data):
                    match = re.search(rb'\bUID (\d+)\b', metadata)
                    if not match:
                        raise ConnectorError('Réponse IMAP sans identité de message.')
                    uid = match.group(1)
                    parsed = BytesHeaderParser(policy=policy.default).parsebytes(headers)
                    found[uid] = SourceMessage(f'{validity}:{uid.decode()}', _internal_date(metadata),
                                               str(parsed.get('Message-ID', '')))
                if any(uid not in found for uid in batch):
                    raise ConnectorError('Un message a disparu pendant la lecture. Relancez la synchronisation.')
                result.extend(found[uid] for uid in batch)
            return result

    def fetch(self, folder: str, source_id: str) -> bytes:
        if not re.fullmatch(r'\d+:\d+', source_id):
            raise ConnectorError('Identifiant IMAP invalide.')
        expected_validity, uid = source_id.split(':')
        with self._connection() as connection:
            if self._select(connection, folder) != expected_validity:
                raise ConnectorError('L’identité du dossier a changé. Relancez la synchronisation.')
            data = _checked(connection.uid('FETCH', uid, '(UID BODY.PEEK[])'), 'téléchargement du message')
            for metadata, content in _fetch_literals(data):
                match = re.search(rb'\bUID (\d+)\b', metadata)
                if match and match.group(1).decode() == uid and isinstance(content, bytes) and content:
                    return content
            raise ConnectorError('Message IMAP absent ou incomplet. Relancez la synchronisation.')


# All user input travels as a JSON argv value, never as executable source.
# Mail.sdef: mailbox.mailboxes, mailbox.messages, message.id/date received/
# message id/source. No readStatus write, UI selection, send or database access.
APPLE_MAIL_SCRIPT = r'''
function run(argv) {
    const request = JSON.parse(argv[0]);
    const mail = Application("Mail");
    let root = mail;
    if (request.account) {
        const accounts = mail.accounts.whose({name: request.account})();
        if (accounts.length !== 1) throw new Error("Compte Mail introuvable ou ambigu.");
        root = accounts[0];
    }
    function child(parent, name, create) {
        const matches = parent.mailboxes.whose({name: name})();
        if (matches.length > 1) throw new Error("Dossier Mail ambigu : " + name);
        if (matches.length) return matches[0];
        if (!create) throw new Error("Dossier Mail introuvable : " + name);
        const box = mail.Mailbox({name: name});
        parent.mailboxes.push(box);
        const created = parent.mailboxes.whose({name: name})();
        if (created.length !== 1) throw new Error("Création du dossier Mail non confirmée.");
        return created[0];
    }
    function resolve(path, create) {
        let parent = root;
        path.split("/").forEach(function(name) { parent = child(parent, name, create); });
        return parent;
    }
    if (request.action === "list_folders") {
        const paths = [];
        function visit(parent, prefix, depth) {
            if (depth > 64 || paths.length > 100000) throw new Error("Arborescence Mail trop profonde.");
            parent.mailboxes().forEach(function(box) {
                const name = box.name();
                if (name.indexOf("/") >= 0) throw new Error("Nom Mail contenant / non représentable.");
                const path = prefix ? prefix + "/" + name : name;
                paths.push(path);
                visit(box, path, depth + 1);
            });
        }
        visit(root, "", 0);
        return JSON.stringify(paths.sort());
    }
    if (request.action === "create_folder") {
        resolve(request.folder, true);
        return JSON.stringify(request.folder);
    }
    const box = resolve(request.folder, false);
    if (request.action === "list_messages") {
        return JSON.stringify(box.messages().map(function(message) {
            const date = message.dateReceived();
            return {source_id: String(message.id()),
                    received_at: date ? date.toISOString() : "",
                    message_id: String(message.messageId() || "")};
        }));
    }
    if (request.action === "fetch") {
        const matches = box.messages.whose({id: Number(request.source_id)})();
        if (matches.length !== 1) throw new Error("Message Mail introuvable.");
        const source = matches[0].source();
        if (!source) throw new Error("Source Mail indisponible : téléchargez le message dans Mail.");
        return JSON.stringify(source);
    }
    throw new Error("Action inconnue.");
}
'''


class AppleMailConnector:
    def __init__(self, account: str = ''):
        self.account = account

    def _call(self, action: str, **arguments):
        payload = json.dumps(dict(action=action, account=self.account, **arguments), ensure_ascii=False)
        try:
            response = subprocess.run(['/usr/bin/osascript', '-l', 'JavaScript', '-e', APPLE_MAIL_SCRIPT, payload],
                                      capture_output=True, text=True, encoding='utf-8', timeout=120, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ConnectorError('Apple Mail ne répond pas. Vérifiez son ouverture et l’autorisation Automatisation.') from exc
        except OSError as exc:
            raise ConnectorError('Apple Mail nécessite une exécution native sur macOS avec osascript.') from exc
        if response.returncode:
            if '-1743' in response.stderr or 'not authorized' in response.stderr.lower():
                raise ConnectorError('Autorisez Apple Mail dans Réglages système > Confidentialité et sécurité > Automatisation.')
            raise ConnectorError('Échec Apple Mail : ' + response.stderr.strip()[:400])
        try:
            return json.loads(response.stdout)
        except (ValueError, TypeError) as exc:
            raise ConnectorError('Réponse Apple Mail non reconnue.') from exc

    def list_folders(self) -> list[str]:
        result = self._call('list_folders')
        if not isinstance(result, list) or any(not isinstance(name, str) for name in result):
            raise ConnectorError('Liste des dossiers Apple Mail invalide.')
        return sorted(_folder(name) for name in result)

    def create_folder(self, name: str) -> str:
        _folder(name)
        result = self._call('create_folder', folder=name)
        if result != name:
            raise ConnectorError('Création du dossier Apple Mail non confirmée.')
        return name

    def list_messages(self, folder: str) -> list[SourceMessage]:
        result = self._call('list_messages', folder=_folder(folder))
        if not isinstance(result, list):
            raise ConnectorError('Liste des messages Apple Mail invalide.')
        try:
            messages = [SourceMessage(str(row['source_id']), str(row.get('received_at', '')),
                                      str(row.get('message_id', ''))) for row in result]
            if any(not re.fullmatch(r'\d+', message.source_id) for message in messages):
                raise ValueError('id')
            return messages
        except (KeyError, TypeError, ValueError) as exc:
            raise ConnectorError('Identité de message Apple Mail invalide.') from exc

    def fetch(self, folder: str, source_id: str) -> bytes:
        if not re.fullmatch(r'\d+', source_id):
            raise ConnectorError('Identifiant Apple Mail invalide.')
        source = self._call('fetch', folder=_folder(folder), source_id=source_id)
        if not isinstance(source, str) or not source:
            raise ConnectorError('Source Apple Mail vide ou invalide.')
        return source.encode('utf-8')


def make_connector(settings: dict, runtime: Path) -> Connector:
    kind = settings.get('connector', 'demo')
    if kind == 'demo':
        return DemoConnector(Path(runtime) / 'mailboxes')
    if kind == 'imap':
        return IMAPConnector(settings)
    if kind == 'apple_mail':
        return AppleMailConnector(settings.get('mail_account', ''))
    raise ConnectorError('Connecteur inconnu.')
