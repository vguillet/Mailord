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


PRINT_SIDES = ('printer', 'one-sided', 'two-sided-long-edge', 'two-sided-short-edge')
PRINT_COLOR_MODES = ('printer', 'monochrome', 'color')


def validate_options(sides='printer', color_mode='printer'):
    if not isinstance(sides, str) or sides not in PRINT_SIDES:
        raise PrintError('Choisissez un mode recto ou recto verso valide.')
    if not isinstance(color_mode, str) or color_mode not in PRINT_COLOR_MODES:
        raise PrintError('Choisissez un mode couleur valide.')


def _driver_choices(printer):
    """Read available PPD options only; never change the Mac's printer defaults."""
    try:
        result = subprocess.run(['/usr/bin/lpoptions', '-p', printer, '-l'],
                                capture_output=True, text=True, encoding='utf-8', errors='replace',
                                env=_environment(), timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode:
        return {}
    choices = {}
    for line in result.stdout.splitlines():
        label, separator, values = line.partition(':')
        key = label.split('/', 1)[0].strip()
        if separator and key in ('ColorModel', 'Duplex'):
            choices[key] = {value.lstrip('*') for value in values.split()}
    return choices


def _job_options(printer, sides, color_mode):
    options = []
    if sides != 'printer':
        options += ['-o', 'sides=' + sides]
    if color_mode != 'printer':
        options += ['-o', 'print-color-mode=' + color_mode]
    if not options:
        return options
    choices = _driver_choices(printer)
    if sides != 'printer' and choices.get('Duplex'):
        value = {'one-sided': 'None', 'two-sided-long-edge': 'DuplexNoTumble',
                 'two-sided-short-edge': 'DuplexTumble'}[sides]
        if value not in choices['Duplex']:
            raise PrintError('Ce mode recto verso n’est pas proposé par le pilote de cette imprimante. Choisissez un autre mode dans les réglages.')
        options += ['-o', 'Duplex=' + value]
    if color_mode != 'printer' and choices.get('ColorModel'):
        aliases = ('Gray', 'Grayscale', 'DeviceGray', 'KGray', 'CMYGray', 'FastGray') if color_mode == 'monochrome' else ('RGB', 'CMYK', 'Color', 'DeviceRGB', 'DeviceCMYK', 'CMY')
        value = next((candidate for candidate in aliases if candidate in choices['ColorModel']), None)
        if value is None:
            raise PrintError('Ce mode couleur n’est pas reconnu parmi les options du pilote. Choisissez « Réglage de l’imprimante » ou un autre mode.')
        options += ['-o', 'ColorModel=' + value]
    return options


def submit(path: Path, printer: str, dry_run: bool = False, *, sides: str = "printer", color_mode: str = "printer") -> str:
    validate_options(sides, color_mode)
    path = Path(path).resolve()
    if not path.is_file():
        raise PrintError('Le document à imprimer est absent.')
    if dry_run:
        return 'simulated-' + uuid.uuid4().hex
    if not isinstance(printer, str) or not _printer_name(printer):
        raise PrintError('Choisissez une imprimante configurée valide.')
    options = _job_options(printer, sides, color_mode)
    try:
        result = subprocess.run(['/usr/bin/lp', '-d', printer, *options, '--', str(path)],
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
