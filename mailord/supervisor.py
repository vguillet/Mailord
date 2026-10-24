"""Stable, standard-library launcher. Never executes from a replaced checkout."""
from __future__ import annotations
import fcntl
import json
import os
import secrets
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError
from .updates import atomic_json, read_json, validate_release, git, SHA, UpdateError


class Supervisor:
    def __init__(self, source_root, runtime, arguments, port):
        self.source_root = Path(source_root).resolve()
        self.runtime = Path(runtime).resolve(); self.runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory = self.runtime/'updates'; self.directory.mkdir(exist_ok=True, mode=0o700)
        self.arguments = list(arguments); self.port = port
        self.child = None; self.stopping = False; self.token = ''

    def active(self):
        active = read_json(self.directory/'active.json')
        if active: return active
        try: commit = git('rev-parse', 'HEAD', cwd=self.source_root)
        except UpdateError: commit = ''
        return {'root': str(self.source_root), 'commit': commit}

    @contextmanager
    def registry_stopped(self):
        with open(self.runtime/'server.lock', 'a') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('Un service utilise encore les données. Fermez-le avant de relancer l’application.') from exc
            try: yield
            finally: fcntl.flock(lock, fcntl.LOCK_UN)

    def backup_registry(self):
        with self.registry_stopped():
            source = self.runtime/'registry.sqlite3'
            if not source.exists(): return None
            backups = self.directory/'backups'; backups.mkdir(exist_ok=True, mode=0o700)
            target = backups/(uuid.uuid4().hex+'.sqlite3')
            with sqlite3.connect(source) as db, sqlite3.connect(target) as backup: db.backup(backup)
            target.chmod(0o600)
            return target

    def recover(self):
        transaction = read_json(self.directory/'transaction.json')
        if not transaction: return
        with self.registry_stopped():
            backup = transaction.get('backup')
            if backup:
                path = Path(backup).resolve()
                if path.parent != (self.directory/'backups').resolve() or not path.is_file():
                    raise RuntimeError('Sauvegarde de mise à jour introuvable. Aucune donnée n’a été remplacée.')
                # SQLite's backup API handles existing WAL files without deleting user files.
                with sqlite3.connect(path) as old, sqlite3.connect(self.runtime/'registry.sqlite3') as current: old.backup(current)
            atomic_json(self.directory/'active.json', transaction['previous'])
            self.error('La nouvelle version n’a pas démarré. La version précédente a été restaurée.')
            (self.directory/'pending.json').unlink(missing_ok=True)
            (self.directory/'transaction.json').unlink()

    def error(self, message):
        state = read_json(self.directory/'status.json')
        state.update(status='error', error=message, progress='')
        atomic_json(self.directory/'status.json', state)

    def candidate(self, value):
        if not isinstance(value, dict) or not SHA.fullmatch(str(value.get('commit', ''))): raise ValueError('Version non identifiable.')
        root = Path(value.get('root', '')).resolve()
        if root.parent != (self.directory/'releases').resolve() or root.is_symlink(): raise ValueError('Dossier de version invalide.')
        validate_release(root)
        if not (root/'.venv/bin/python').is_file(): raise ValueError('Environnement de la version manquant.')
        if git('rev-parse', 'HEAD', cwd=root)!=value['commit']: raise ValueError('Version modifiée depuis sa préparation.')
        return {'root': str(root), 'commit': value['commit']}

    def launch(self, active, *, probation=False):
        root = Path(active['root'])
        if root.resolve()!=self.source_root: active=self.candidate(active)
        python = root/'.venv/bin/python'
        executable = str(python) if python.is_file() else sys.executable
        self.token = secrets.token_urlsafe(32)
        env = dict(os.environ, MAILORD_MANAGED='1', MAILORD_HEALTH_TOKEN=self.token,
                   MAILORD_PROBATION='1' if probation else '0', PYTHONPATH=str(root))
        self.child = subprocess.Popen([executable, '-m', 'mailord', '--worker', *self.arguments], cwd=root, env=env)
        return self.child

    def request(self, path, method='GET'):
        req = Request(f'http://127.0.0.1:{self.port}{path}', method=method, headers={'X-Supervisor-Token': self.token})
        with urlopen(req, timeout=2) as response: return json.load(response)

    def wait_ready(self, child, timeout=45):
        until = time.monotonic()+timeout
        while time.monotonic()<until and not self.stopping and child.poll() is None:
            try:
                if self.request('/api/health').get('ready'): return True
            except (OSError, URLError, ValueError): pass
            time.sleep(.2)
        return False

    def stop_child(self):
        if self.child and self.child.poll() is None:
            self.child.terminate()
            # The archive/print worker must drain. No forced kill that could duplicate printing.
            self.child.wait()

    def switch(self, pending):
        try:
            candidate = self.candidate(pending)
            previous = self.active()
            backup = self.backup_registry()
            atomic_json(self.directory/'transaction.json', {'previous': previous, 'candidate': candidate, 'backup': str(backup) if backup else None})
            self.child = self.launch(candidate, probation=True)
            if not self.wait_ready(self.child):
                self.stop_child(); self.recover(); return False
            # Commit before activating: after this point user work must never be rolled back.
            atomic_json(self.directory/'active.json', candidate)
            (self.directory/'pending.json').unlink(missing_ok=True)
            (self.directory/'transaction.json').unlink()
            try: self.request('/api/activate', 'POST')
            except (OSError, URLError, ValueError):
                # Activation may have succeeded despite a lost response. Restart the accepted
                # revision normally, preserving all data rather than undoing possible work.
                self.stop_child(); self.launch(candidate)
            state = read_json(self.directory/'status.json')
            state.update(status='updated', error='', progress='Mise à jour installée.', available_commit=candidate['commit'])
            atomic_json(self.directory/'status.json', state)
            return True
        except (OSError, ValueError, RuntimeError, UpdateError):
            self.stop_child()
            if (self.directory/'transaction.json').exists(): self.recover()
            else:
                self.error('La bascule est impossible. La version actuelle est conservée.')
                (self.directory/'pending.json').unlink(missing_ok=True)
            return False

    def run(self):
        with open(self.runtime/'supervisor.lock', 'a') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise RuntimeError('Un lanceur utilise déjà cet espace de données.')
            # Recover only when no worker can write the registry.
            self.recover()
            previous_handlers = {}
            def stop(signum, frame):
                self.stopping=True
                if self.child and self.child.poll() is None: self.child.terminate()
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous_handlers[sig]=signal.signal(sig, stop)
            try:
                # An interrupted preparation can leave a durable, approved pending version.
                pending = read_json(self.directory/'pending.json')
                if (not pending or not self.switch(pending)) and not self.stopping: self.launch(self.active())
                while not self.stopping:
                    code = self.child.wait()
                    if self.stopping: return 0
                    pending = read_json(self.directory/'pending.json')
                    if code!=0 or not pending: return code
                    if not self.switch(pending) and not self.stopping: self.launch(self.active())
                return 0
            finally:
                self.stop_child()
                for sig, handler in previous_handlers.items(): signal.signal(sig, handler)
