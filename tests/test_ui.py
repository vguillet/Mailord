"""UI contract and dangerous-input regressions; live flows are checked in the browser."""
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / 'autosecretaire' / 'static'
NODE = shutil.which('node')


def js(expression):
    if not NODE:
        pytest.skip('Node is needed for the browser transformation checks')
    script = f"const ui = require({json.dumps(str(STATIC / 'app.js'))});\nconsole.log(JSON.stringify({expression}));"
    result = subprocess.run([NODE, '-e', script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_script_syntax():
    if not NODE:
        pytest.skip('Node is needed for the JS syntax check')
    subprocess.run([NODE, '--check', str(STATIC / 'app.js')], check=True, capture_output=True)


def test_mail_data_is_escaped_as_text():
    assert js('ui.escape(\'<img src=x onerror="alert(1)">&\\\'\')') == '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&amp;&#39;'


def test_template_nested_paths_include_parents_once():
    assert js('ui.withParents(["01 - Dossier/Sous-dossier", "01 - Dossier", "02 - Factures"])') == [
        '01 - Dossier', '01 - Dossier/Sous-dossier', '02 - Factures'
    ]


def test_template_tree_keeps_descendants_with_their_parent():
    assert js('ui.withParents(["A/Z", "A - copie", "A/B"])') == [
        'A', 'A/B', 'A/Z', 'A - copie'
    ]


def test_template_reparent_preserves_descendants():
    assert js('ui.changeBranch(["A", "A/B", "A/B/C", "Z"], "A/B", "Z/B")') == [
        'A', 'Z', 'Z/B', 'Z/B/C'
    ]


def test_template_duplicate_preserves_original_branch():
    assert js('ui.changeBranch(["A", "A/B"], "A", "A - copie", true)') == [
        'A', 'A/B', 'A - copie', 'A - copie/B'
    ]


@pytest.mark.parametrize('target', ['A/B/C', 'Z'])
def test_template_rejects_cycles_and_overwrites(target):
    assert js(f'(() => {{ try {{ ui.changeBranch(["A", "A/B", "Z"], "A", {json.dumps(target)}); return false; }} catch (e) {{ return true; }} }})()') is True


@pytest.mark.parametrize('path', ['../client', '/absolute', 'a/../b', 'a//b', 'a\\b', '', 'a\x00b'])
def test_template_rejects_unsafe_paths(path):
    assert js(f'(() => {{ try {{ ui.checkedFolder({json.dumps(path)}); return false; }} catch (e) {{ return true; }} }})()') is True


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.tags = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        self.tags.append((tag, attrs))


def test_shell_is_local_french_and_accessible():
    page = PageParser()
    page.feed((STATIC / 'index.html').read_text())
    assert len(page.ids) == len(set(page.ids)), 'Duplicate IDs break accessible controls'
    assert ('html', {'lang': 'fr'}) in page.tags
    assert any(tag == 'dialog' and attrs.get('aria-labelledby') == 'modal-title' for tag, attrs in page.tags)
    assert any(attrs.get('aria-live') == 'polite' for _, attrs in page.tags)
    assert all(not attrs.get('src', '').startswith(('http://', 'https://', '//')) for _, attrs in page.tags)
    assert any(tag == 'script' and attrs.get('src') == '/static/app.js' for tag, attrs in page.tags)


def test_client_uses_document_ids_and_csrf_contract():
    source = (STATIC / 'app.js').read_text()
    assert "headers['X-CSRF-Token'] = model.state.csrf_token" in source
    assert "credentials: 'same-origin'" in source
    assert '/api/documents/${encodeURIComponent(id)}/file' in source
    assert not re.search(r'(?:src|href)=[^\n]*\$\{(?:doc|d)\.path\}', source)
    assert 'confirm: true' in source  # A reprint is separate from ordinary printing.


def test_filing_tree_collapses_branches_but_keeps_parents_selectable():
    folders = ['Pièces/Client/Signées', 'Pièces', 'Pièces/Client', 'Factures']
    data = json.dumps(folders)
    assert [r['path'] for r in js(f'ui.folderEntries({data}, "", [])')] == ['Factures', 'Pièces']
    expanded = js(f'ui.folderEntries({data}, "", ["Pièces"])')
    assert [r['path'] for r in expanded] == ['Factures', 'Pièces', 'Pièces/Client']
    assert expanded[-1]['hasChildren'] is True


def test_filing_search_finds_collapsed_destinations_and_preserves_ancestors():
    result = js('ui.folderEntries(["Procédure", "Procédure/TJ Paris", "Procédure/TJ Paris/Expertise", "Pièces"], "expertise", [])')
    assert [r['path'] for r in result] == ['Procédure', 'Procédure/TJ Paris', 'Procédure/TJ Paris/Expertise']
    assert js('ui.folderEntries(["Pièces", "Pièces/Signées"], "pieces/signees", [])')[-1]['path'] == 'Pièces/Signées'
    assert js('ui.folderEntries(["Pièces"], "introuvable", [])') == []


def test_starred_clients_first_then_french_alphabetical_order():
    data = [{"id": "a", "name": "Albert"}, {"id": "z", "name": "Zoé", "starred": True}, {"id": "e", "name": "Émilie", "starred": True}, {"id": "b", "name": "Bruno", "starred": False}]
    assert [c['id'] for c in js(f'ui.sortClients({json.dumps(data)})')] == ['e', 'z', 'a', 'b']


def test_print_control_uses_only_its_document_jobs():
    doc = {'id': 'attachment', 'printable': True}
    other = [{'document_id': 'email', 'status': 'submitted'}]
    result = js(f'ui.documentPrintView({json.dumps(doc)}, {json.dumps(other)})')
    assert result['reprint'] is False and result['label'] == 'Imprimer'
    jobs = other + [{'document_id': 'attachment', 'status': 'uncertain', 'error': 'À vérifier'}]
    result = js(f'ui.documentPrintView({json.dumps(doc)}, {json.dumps(jobs)})')
    assert result['reprint'] is True and result['tone'] == 'error'
    assert js('ui.documentPrintView({id:"word", printable:false}, [])')['disabled'] is True


def test_message_search_includes_document_names_and_destinations_without_accents():
    message = {'subject': 'Bonjour', 'documents': [{'original_name': 'Échéancier.pdf', 'name': '2026-10-24 - Échéancier.pdf', 'destination': 'Procédure/TJ Paris'}]}
    data = json.dumps(message)
    for query in ['echeancier', '2026-10-24', 'procedure/tj paris']:
        assert js(f'ui.messageMatches({data}, {json.dumps(query)}, "Camille")') is True
    assert js(f'ui.messageMatches({data}, "introuvable", "Camille")') is False
    assert js('ui.messageMatches({}, "", "")') is True


@pytest.mark.parametrize(('progress', 'status', 'labels'), [
    ({'total': 2, 'pending': 2}, 'pending', ['À imprimer · 2/2']),
    ({'total': 2, 'pending': 1, 'submitted': 1}, 'partial', ['À imprimer · 1/2', 'Transmis à l’imprimante · 1/2']),
    ({'total': 2, 'simulated': 2}, 'simulated', ['Simulation · 2/2']),
    ({'total': 2, 'submitted': 1, 'simulated': 1}, 'mixed', ['Transmis à l’imprimante · 1/2', 'Simulation · 1/2']),
    ({'total': 1, 'submitting': 1}, 'submitting', ['Impression en cours · 1/1']),
    ({'total': 0}, 'not_selected', ['Aucun document à imprimer']),
    ({'total': 0}, 'uncertain', ['Aucun document à imprimer', 'Impression à vérifier']),
    ({'total': 1, 'error': 1}, 'error', ['Impression à vérifier']),
])
def test_print_badges_distinguish_pending_submitted_simulated_and_uncertain(progress, status, labels):
    message = {'status': 'ready', 'print_progress': progress, 'print_status': status}
    badges = js(f'ui.messagePrintBadges({json.dumps(message)})')
    assert [badge['label'] for badge in badges] == labels
    if status in ('error', 'uncertain'):
        assert badges[-1]['tone'] == 'error'


def test_print_badges_wait_for_export():
    assert js('ui.messagePrintBadges({status:"queued"})') == []
