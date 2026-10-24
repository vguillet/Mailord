"""Copy a stopped local workspace to a new path, preserving its source as backup."""
import argparse
from contextlib import ExitStack
import fcntl
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile


PATH_FIELDS = {'runtime', 'archive_root', 'folder', 'path', 'spool', 'move_to', 'target_path'}


def relocate(source: Path, destination: Path):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_dir() or destination.exists() or destination.is_relative_to(source):
        raise ValueError('Source invalide ou destination déjà présente / imbriquée.')
    if any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('Examinez les liens symboliques avant de déplacer cet espace.')
    if any((source / 'updates' / name).exists() for name in ('pending.json', 'transaction.json', 'active.json')):
        raise ValueError('Cet espace contient une bascule de version ; une migration spécifique est nécessaire.')

    def rewrite(value, key=''):
        if isinstance(value, dict): return {k: rewrite(v, k) for k, v in value.items()}
        if isinstance(value, list): return [rewrite(v, key) for v in value]
        if isinstance(value, str) and key in PATH_FIELDS:
            if value == str(source): return str(destination)
            if value.startswith(str(source) + '/'):
                return str(destination) + value[len(str(source)):]
        return value

    with ExitStack() as locks:
        for name in ('supervisor.lock', 'server.lock'):
            lock = locks.enter_context((source / name).open('a'))
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('Le service doit être à l’arrêt avant la migration.') from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.mailord-move-', dir=destination.parent))
        try:
            def ignore(directory, names):
                return [n for n in names if n in {'registry.sqlite3', 'registry.sqlite3-wal', 'registry.sqlite3-shm'}] if Path(directory) == source else []
            shutil.copytree(source, stage, dirs_exist_ok=True, ignore=ignore)
            database = source / 'registry.sqlite3'
            if database.exists():
                original = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
                target = sqlite3.connect(stage / 'registry.sqlite3')
                try:
                    original.backup(target)
                    with target:
                        for kind, ident, payload in target.execute('SELECT kind,id,payload FROM records').fetchall():
                            updated = rewrite(json.loads(payload))
                            target.execute('UPDATE records SET payload=? WHERE kind=? AND id=?', (json.dumps(updated, ensure_ascii=False), kind, ident))
                    if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise RuntimeError('Le contrôle du registre a échoué.')
                    target.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                finally:
                    target.close(); original.close()
                (stage / 'registry.sqlite3').chmod(0o600)
            stage.chmod(0o700)
            if destination.exists(): raise ValueError('La destination existe déjà.')
            stage.rename(destination)
        finally:
            if stage.exists(): shutil.rmtree(stage)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Déplacer un espace Mailord arrêté, en conservant la source.')
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(relocate(args.source, args.destination))
