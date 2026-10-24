"""Small transaction-safe local registry. Keep outside cloud-synced folders."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA busy_timeout=5000')
        self.db.execute('CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT, payload TEXT NOT NULL, PRIMARY KEY(kind,id))')

    def all(self, kind):
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM records WHERE kind=? ORDER BY rowid', (kind,))]

    def get(self, kind, id):
        with self.lock:
            r = self.db.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind,id)).fetchone()
            return json.loads(r[0]) if r else None

    def put(self, kind, id, payload):
        with self.lock:
            self.db.execute('INSERT INTO records VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload', (kind,id,json.dumps({**payload, 'id':id},ensure_ascii=False)))

    def delete(self, kind, id):
        with self.lock:
            self.db.execute('DELETE FROM records WHERE kind=? AND id=?',(kind,id))

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise

    def close(self):
        self.db.close()
