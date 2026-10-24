"""Prepare trusted Git revisions without modifying the running checkout or user data."""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

SHA = re.compile(r'^[0-9a-f]{40}$')
BUSY = {'checking', 'installing', 'restarting'}


class UpdateError(RuntimeError):
    pass


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with open(temporary, 'x', encoding='utf-8') as stream:
            os.chmod(temporary, 0o600)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(path)
        fd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path, default=None):
    try: return json.loads(Path(path).read_text())
    except FileNotFoundError: return {} if default is None else default


def command(args, *, cwd=None, timeout=90):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_SSH_COMMAND='ssh -oBatchMode=yes -oConnectTimeout=15', PIP_NO_INPUT='1', PIP_DISABLE_PIP_VERSION_CHECK='1')
    # Do not leak passwords, URLs with credentials or raw transport output to the UI.
    try:
        result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError('Commande indisponible ou délai dépassé. Vérifiez Git, Python et la connexion.') from exc
    if result.returncode:
        raise UpdateError('Opération impossible. Vérifiez le dépôt, la branche, la connexion et les autorisations Git du Mac.')
    return result.stdout.strip()


def git(*args, cwd=None, timeout=90):
    return command(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.ext.allow=never', *args], cwd=cwd, timeout=timeout)


def validate_source(repository, branch, *, allow_local=False):
    if not isinstance(repository, str) or not isinstance(branch, str):
        raise ValueError('Dépôt et branche requis.')
    if not repository or repository != repository.strip() or any(ord(c) < 32 for c in repository):
        raise ValueError('Adresse de dépôt invalide.')
    parsed = urlsplit(repository)
    https = parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
    ssh = parsed.scheme == 'ssh' and parsed.hostname and not parsed.password and parsed.username in (None, 'git')
    scp = bool(re.fullmatch(r'git@[a-zA-Z0-9.-]+:[a-zA-Z0-9_./-]+', repository))
    local = allow_local and Path(repository).is_absolute()
    if not (https or ssh or scp or local) or parsed.query or parsed.fragment:
        raise ValueError('Utilisez une adresse HTTPS sans identifiant ni jeton, ou SSH (git@…).')
    if not branch or branch != branch.strip() or branch.startswith('-') or any(ord(c) < 32 for c in branch):
        raise ValueError('Nom de branche invalide.')
    try: git('check-ref-format', '--branch', branch)
    except UpdateError as exc: raise ValueError('Nom de branche invalide.') from exc
    return repository, branch


def validate_release(root):
    root = Path(root)
    try:
        manifest = read_json(root/'update.json')
        if manifest != {'update_protocol': 1, 'data_schema': 1}:
            raise ValueError()
        for name in ('update.json', 'requirements.lock', 'mailord/__main__.py'):
            path = root/name
            if not path.is_file() or path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
                raise ValueError()
    except (ValueError, OSError) as exc:
        raise UpdateError('Cette version n’est pas compatible avec les mises à jour automatiques (protocole ou données).') from exc


class UpdateManager:
    def __init__(self, runtime, source_root, restart=None, *, allow_local=False):
        self.runtime = Path(runtime).resolve()
        self.source_root = Path(source_root).resolve()
        self.directory = self.runtime/'updates'; self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.restart = restart; self.allow_local = allow_local
        self.lock = threading.RLock(); self.thread = None; self.closed = threading.Event()
        try: self.current_commit = git('rev-parse', 'HEAD', cwd=self.source_root)
        except UpdateError: self.current_commit = ''
        self.config = read_json(self.directory/'config.json')
        if not self.config:
            try:
                url = git('remote', 'get-url', 'origin', cwd=self.source_root)
                branch = git('symbolic-ref', '--short', 'HEAD', cwd=self.source_root)
                url, branch = validate_source(url, branch, allow_local=allow_local)
                self.config = {'repository': url, 'branch': branch}
                atomic_json(self.directory/'config.json', self.config)
            except (UpdateError, ValueError): pass
        self.value = read_json(self.directory/'status.json')
        if self.value.get('status') in BUSY:
            self.value.update(status='error', error='La mise à jour a été interrompue. Vérifiez à nouveau pour reprendre.', progress='')
        self.value.setdefault('status', 'idle' if self.config else 'unconfigured')
        self.value.setdefault('available_commit', '')
        self.value.setdefault('checked_at', '')
        self.value.setdefault('error', '')
        self.value.setdefault('progress', '')
        self._save()

    def _save(self):
        atomic_json(self.directory/'status.json', self.value)

    def _set(self, **values):
        with self.lock:
            self.value.update(values); self._save()

    def state(self):
        with self.lock:
            return {**self.value, 'repository': self.config.get('repository', ''), 'branch': self.config.get('branch', 'main'), 'current_commit': self.current_commit, 'managed': self.restart is not None}

    def _idle(self):
        if self.value['status'] in BUSY or (self.thread and self.thread.is_alive()):
            raise ValueError('Une opération de mise à jour est déjà en cours.')
        if self.closed.is_set(): raise ValueError('Le service est en cours d’arrêt.')

    def configure(self, repository, branch):
        repository, branch = validate_source(repository, branch, allow_local=self.allow_local)
        with self.lock:
            self._idle()
            self.config = {'repository': repository, 'branch': branch}
            atomic_json(self.directory/'config.json', self.config)
            self._set(status='idle', error='', available_commit='', checked_at='', progress='')
            return self.state()

    def _start(self, kind, function, *args):
        with self.lock:
            self._idle()
            if not self.config: raise ValueError('Configurez d’abord le dépôt des mises à jour.')
            self._set(status=kind, error='', progress='Recherche de version…' if kind=='checking' else 'Préparation de la mise à jour…')
            self.thread = threading.Thread(target=function, args=args, daemon=True, name='application-update')
            self.thread.start()
            return self.state()

    def check_async(self):
        return self._start('checking', self.check)

    def check(self):
        try:
            ref = 'refs/heads/' + self.config['branch']
            output = git('ls-remote', '--exit-code', '--heads', '--', self.config['repository'], ref)
            matches = [line.split()[0] for line in output.splitlines() if len(line.split())==2 and line.split()[1]==ref]
            if len(matches)!=1 or not SHA.fullmatch(matches[0]): raise UpdateError('La branche ne fournit pas de version identifiable.')
            sha = matches[0]
            self._set(status='current' if sha==self.current_commit else 'available', available_commit=sha, checked_at=datetime.now(timezone.utc).isoformat(), error='', progress='')
        except (UpdateError, KeyError, OSError) as exc:
            self._set(status='error', error=str(exc) if isinstance(exc, UpdateError) else 'Vérification impossible. Vérifiez la configuration du dépôt.', progress='')

    def install_async(self, commit):
        with self.lock:
            if not self.restart: raise ValueError('Relancez l’application avec son lanceur habituel pour activer les mises à jour.')
            if not isinstance(commit, str) or not SHA.fullmatch(commit) or commit!=self.value.get('available_commit') or commit==self.current_commit:
                raise ValueError('Version indisponible ou périmée. Vérifiez les mises à jour à nouveau.')
            return self._start('installing', self.install, commit)

    def prepare_environment(self, release):
        self._set(progress='Installation des dépendances dans un environnement séparé…')
        command([sys.executable, '-m', 'venv', str(release/'.venv')], timeout=180)
        python = str(release/'.venv/bin/python')
        command([python, '-m', 'pip', 'install', '--requirement', str(release/'requirements.lock')], cwd=release, timeout=900)
        # The launch uses source directly; no executable project packaging hooks are needed.
        self._set(progress='Vérification du démarrage…')
        command([python, '-c', 'import mailord.app; import mailord.__main__'], cwd=release, timeout=60)

    def install(self, commit):
        release = self.directory/'releases'/(str(commit)+'-'+uuid.uuid4().hex[:8])
        try:
            if not SHA.fullmatch(str(commit)) or commit!=self.value.get('available_commit'):
                raise UpdateError('Version périmée. Vérifiez à nouveau.')
            release.parent.mkdir(exist_ok=True)
            self._set(status='installing', error='', progress='Téléchargement de la version sélectionnée…')
            git('init', str(release))
            git('fetch', '--depth=1', '--no-tags', '--', self.config['repository'], commit, cwd=release, timeout=180)
            git('checkout', '--detach', 'FETCH_HEAD', cwd=release)
            if git('rev-parse', 'HEAD', cwd=release)!=commit: raise UpdateError('La version reçue ne correspond pas à la version choisie.')
            validate_release(release)
            self.prepare_environment(release)
            if self.closed.is_set(): raise UpdateError('Installation interrompue par l’arrêt du service. Vérifiez à nouveau.')
            atomic_json(self.directory/'pending.json', {'root': str(release), 'commit': commit})
            self._set(status='restarting', progress='Redémarrage et contrôle de la nouvelle version…')
            if self.restart: self.restart()
        except Exception as exc:
            self._set(status='error', progress='', error=str(exc) if isinstance(exc, UpdateError) else 'Installation impossible. La version actuelle est conservée.')
            # Retain failed release for inspection; never remove user data or the running source.

    def start_periodic(self):
        def loop():
            # Preserve a rollback/interruption diagnosis until a deliberate recheck.
            if self.value['status']=='error' and self.closed.wait(3600): return
            while not self.closed.is_set():
                try:
                    if self.config and self.value['status'] not in BUSY: self.check_async()
                except ValueError: pass
                if self.closed.wait(3600): break
        self.scheduler = threading.Thread(target=loop, daemon=True, name='update-check'); self.scheduler.start()

    def close(self):
        self.closed.set()
        if self.thread and self.thread is not threading.current_thread(): self.thread.join()
