"""Conservative CUPS submission. A spool result never proves paper was printed."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import uuid


class PrintError(RuntimeError):
    """Confirmed local validation failure or explicit scheduler rejection."""


class PrintUncertain(PrintError):
    """Submission may have reached the scheduler; MUST NOT be retried implicitly."""


def _environment():
    # Fix locale for CUPS diagnostics and job-id parsing.
    return dict(os.environ, LC_ALL='C', LANG='C')


def _printer_name(value: str) -> bool:
    return bool(value and not value.startswith('-') and not re.search(r'[\s/#\x00-\x1f\x7f]', value))


def submit(path: Path, printer: str, dry_run: bool = False) -> str:
    path = Path(path).resolve()
    if not path.is_file():
        raise PrintError('Le document à imprimer est absent.')
    if dry_run:
        return 'simulated-' + uuid.uuid4().hex
    if not isinstance(printer, str) or not _printer_name(printer):
        raise PrintError('Choisissez une imprimante configurée valide.')
    try:
        result = subprocess.run(['/usr/bin/lp', '-d', printer, '--', str(path)],
                                capture_output=True, text=True, encoding='utf-8', errors='replace',
                                env=_environment(), timeout=30, check=False)
    except subprocess.TimeoutExpired as exc:
        raise PrintUncertain('Délai d’impression dépassé : vérifiez la file avant de réimprimer.') from exc
    except (FileNotFoundError, PermissionError) as exc:
        raise PrintError('La commande d’impression macOS est indisponible.') from exc
    except OSError as exc:
        raise PrintUncertain('Résultat de l’envoi inconnu : vérifiez la file avant de réimprimer.') from exc
    match = re.search(r'\brequest id is ([^\s/]+-\d+)\b', result.stdout)
    if match:
        # Positive scheduler receipt remains valid even if a later diagnostic failed.
        return match.group(1)
    detail = (result.stderr or result.stdout).strip()
    confirmed_rejections = ('printer or class does not exist', 'unknown destination',
                            'no such file or directory', 'unable to open file',
                            'not accepting jobs', 'unsupported document-format',
                            'client-error-document-format-not-supported', 'client-error-not-authorized',
                            'client-error-forbidden')
    if result.returncode and any(text in detail.lower() for text in confirmed_rejections):
        raise PrintError('Impression refusée : ' + detail[:300])
    raise PrintUncertain('Soumission non confirmée : vérifiez la file avant de réimprimer.'
                         + (' ' + detail[:300] if detail else ''))


def _query(arguments: list[str]):
    try:
        return subprocess.run(['/usr/bin/lpstat', *arguments], capture_output=True,
                              text=True, encoding='utf-8', errors='replace', env=_environment(),
                              timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def status(job_id: str) -> str:
    if not isinstance(job_id, str) or not re.fullmatch(r'[^\s/]+-\d+', job_id):
        return 'unknown'
    for selector, value in [('not-completed', 'submitted'), ('completed', 'completed')]:
        result = _query(['-W', selector, '-o'])
        if result is None or result.returncode:
            return 'unknown'
        if any(line.split() and line.split()[0] == job_id for line in result.stdout.splitlines()):
            return value
    # Absence can mean purged history, a different spooler or never submitted.
    return 'unknown'


def list_printers() -> list[str]:
    result = _query(['-e'])
    if result is None or result.returncode:
        return []
    return sorted({name.strip() for name in result.stdout.splitlines() if _printer_name(name.strip())})
