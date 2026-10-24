import subprocess
from types import SimpleNamespace

import pytest

from mailord import printing


@pytest.fixture
def document(tmp_path):
    path = tmp_path / 'facture $exemple; test.pdf'
    path.write_bytes(b'%PDF-1.4\nfixture')
    return path


def test_dry_run_never_calls_printer(monkeypatch, document):
    monkeypatch.setattr(printing.subprocess, 'run', lambda *a, **k: pytest.fail('printer called'))
    assert printing.submit(document, '', dry_run=True).startswith('simulated-')


def test_submit_uses_arguments_and_retains_spool_id(monkeypatch, document):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout='request id is Office-Laser-42 (1 file(s))\n', stderr='')

    monkeypatch.setattr(printing.subprocess, 'run', run)
    assert printing.submit(document, 'Office-Laser') == 'Office-Laser-42'
    command, kwargs = calls[0]
    assert command == ['/usr/bin/lp', '-d', 'Office-Laser', '--', str(document.resolve())]
    assert kwargs['env']['LC_ALL'] == 'C'
    assert not kwargs.get('shell', False)


@pytest.mark.parametrize('printer', ['', '-h attacker', 'Office/../../x', 'a\nb'])
def test_invalid_printer_never_submits(monkeypatch, document, printer):
    monkeypatch.setattr(printing.subprocess, 'run', lambda *a, **k: pytest.fail('printer called'))
    with pytest.raises(printing.PrintError):
        printing.submit(document, printer)


def test_missing_file_rejected_before_submitting(monkeypatch, tmp_path):
    monkeypatch.setattr(printing.subprocess, 'run', lambda *a, **k: pytest.fail('printer called'))
    with pytest.raises(printing.PrintError):
        printing.submit(tmp_path / 'missing.pdf', 'Office')


def test_timeout_and_ambiguous_success_are_uncertain(monkeypatch, document):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 30)

    monkeypatch.setattr(printing.subprocess, 'run', timeout)
    with pytest.raises(printing.PrintUncertain):
        printing.submit(document, 'Office')
    monkeypatch.setattr(printing.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout='', stderr=''))
    with pytest.raises(printing.PrintUncertain):
        printing.submit(document, 'Office')


def test_explicit_rejection_is_error_but_network_failure_is_uncertain(monkeypatch, document):
    monkeypatch.setattr(printing.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='lp: Error - The printer or class does not exist.'))
    with pytest.raises(printing.PrintError) as error:
        printing.submit(document, 'Office')
    assert not isinstance(error.value, printing.PrintUncertain)
    monkeypatch.setattr(printing.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='lp: server disconnected'))
    with pytest.raises(printing.PrintUncertain):
        printing.submit(document, 'Office')


def test_job_status_requires_positive_spool_evidence(monkeypatch):
    outputs = ['Office-42 user 1024 today\n', '', 'Office-42 user 1024 today\n', '', '']
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=outputs.pop(0), stderr='')

    monkeypatch.setattr(printing.subprocess, 'run', run)
    assert printing.status('Office-42') == 'submitted'
    assert printing.status('Office-42') == 'completed'
    assert printing.status('Office-42') == 'unknown'
    assert calls[0] == ['/usr/bin/lpstat', '-W', 'not-completed', '-o']
    assert calls[2] == ['/usr/bin/lpstat', '-W', 'completed', '-o']


def test_list_printers(monkeypatch):
    monkeypatch.setattr(printing.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout='Office\nOffice\nDesk\n', stderr=''))
    assert printing.list_printers() == ['Desk', 'Office']


def test_spool_unavailable_does_not_claim_completion(monkeypatch):
    def absent(*a, **k):
        raise FileNotFoundError('lpstat unavailable')

    monkeypatch.setattr(printing.subprocess, 'run', absent)
    assert printing.status('Office-42') == 'unknown'
    assert printing.list_printers() == []
