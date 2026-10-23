"""Update UI state/session regressions, without network or a running real updater."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'autosecretaire/static/app.js'
NODE = shutil.which('node')


def js(body):
    if not NODE:
        pytest.skip('Node is needed for browser logic tests')
    source = f"const ui=require({json.dumps(str(SCRIPT))});\n(async()=>{{{body}}})().then(value=>console.log(JSON.stringify(value))).catch(e=>{{console.error(e);process.exit(1)}});"
    result = subprocess.run([NODE, '-e', source], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


@pytest.mark.parametrize('status', ['checking', 'installing', 'restarting'])
def test_active_update_disables_mutations(status):
    result = js(f'return ui.updateView({{status:{json.dumps(status)}, repository:"https://example.org/project.git", available_commit:"abc", managed:true}});')
    assert result['busy'] is True
    assert result['canInstall'] is False
    assert result['canCheck'] is False


def test_install_requires_available_commit_and_managed_launcher():
    assert js('return [false,true].map(managed=>ui.updateView({status:"available",managed,available_commit:"abc"}).canInstall);') == [False, True]
    assert js('return ui.updateView({status:"available",managed:true}).canInstall;') is False


def test_restart_outage_is_explained_without_claiming_success():
    result = js('return ui.updateView({status:"restarting",managed:true},{offline:true});')
    assert result['title'] == 'Reconnexion à votre espace…'
    assert result['canInstall'] is False
    assert result['canCheck'] is False
    assert result['tone'] != 'success'
    stalled = js('return ui.updateView({status:"restarting"},{offline:true,stalled:true});')
    assert stalled['tone'] == 'error'
    assert 'plus de temps' in stalled['title']


def test_error_keeps_explicit_check_available():
    result = js('return ui.updateView({status:"error",repository:"https://example.org/project.git"});')
    assert result['canCheck'] is True
    assert result['canInstall'] is False
    assert result['tone'] == 'error'


def test_csrf_rejection_renews_then_retries_exactly_once():
    result = js('''
      const seen=[]; let renewals=0;
      const result=await ui.sessionRequest('/api/updates/install',
        {method:'POST',headers:{'X-CSRF-Token':'old'},body:JSON.stringify({commit:'requested'})},
        async()=>{renewals++;return 'fresh';},
        async(path,options)=>{seen.push({path,token:options.headers['X-CSRF-Token'],body:options.body});return {status:seen.length===1?403:200};});
      return {status:result.status,seen,renewals};
    ''')
    assert result['status'] == 200
    assert result['renewals'] == 1
    assert [request['token'] for request in result['seen']] == ['old', 'fresh']
    assert all(request['path'] == '/api/updates/install' for request in result['seen'])
    assert all(json.loads(request['body']) == {'commit': 'requested'} for request in result['seen'])


def test_second_csrf_rejection_is_not_retried_forever():
    result = js('''
      let requests=0, renewals=0;
      const result=await ui.sessionRequest('/api/updates/check',{method:'POST',headers:{}},
      async()=>{renewals++;return 'fresh';},async()=>{requests++;return {status:403};});
      return {requests,renewals,status:result.status};
    ''')
    assert result == {'requests': 2, 'renewals': 1, 'status': 403}


def test_lost_install_response_never_resubmits_installation():
    result = js('''
      let requests=0,renewals=0;
      try { await ui.sessionRequest('/api/updates/install',{method:'POST',headers:{}},
        async()=>{renewals++;return 'fresh';},async()=>{requests++;throw new TypeError('worker restarted');});
      } catch(e) { return {requests,renewals,error:e.message}; }
    ''')
    assert result == {'requests': 1, 'renewals': 0, 'error': 'worker restarted'}


def test_reads_do_not_trigger_session_retry():
    result = js('''
      let renewals=0,requests=0;
      await ui.sessionRequest('/api/updates',{method:'GET',headers:{}},
        async()=>{renewals++;return 'fresh';},async()=>{requests++;return {status:403};});
      return {renewals,requests};
    ''')
    assert result == {'renewals': 0, 'requests': 1}


def test_exact_requested_version_reloads_once_and_clears_intent():
    result = js('''
      const before={target:'requested',startedAt:1,accepted:true};
      const first=ui.updateRecovery({status:'updated',current_commit:'requested'},before,100);
      const second=ui.updateRecovery({status:'updated',current_commit:'requested'},first.intent,200);
      return {first,second};
    ''')
    assert result['first'] == {'intent': None, 'reload': True}
    assert result['second'] == {'intent': None, 'reload': False}


def test_failed_preparation_keeps_page_and_form():
    assert js("return ui.updateRecovery({status:'error'},{target:'requested',startedAt:1,accepted:true},100);") == {'intent': None, 'reload': False}


def test_rollback_after_restart_reloads_previous_frontend_once():
    assert js("return ui.updateRecovery({status:'error',current_commit:'previous'},{target:'requested',startedAt:1,accepted:true,sawRestart:true},100);") == {'intent': None, 'reload': True}


def test_lost_request_with_no_job_unlocks_without_resubmitting():
    result = js("return ui.updateRecovery({status:'available',current_commit:'previous'},{target:'requested',startedAt:1,accepted:false,hadDisconnection:true},20000);")
    assert result['intent'] is None
    assert result['reload'] is False
    assert 'Aucune installation' in result['notice']


def test_frontend_has_explicit_controls_and_persistent_recovery():
    script = SCRIPT.read_text()
    html = (ROOT / 'autosecretaire/static/index.html').read_text()
    assert 'data-action="updates"' in html
    assert 'id="update-banner"' in html
    assert "api('/api/updates/install', 'POST', {commit})" in script
    assert "sessionStorage.setItem('autosecretaire.update'" in script
    assert "sessionStorage.removeItem('autosecretaire.update')" in script
    assert 'window.location.reload()' in script
    assert 'section id="update-status-panel"' in script
    assert "const fresh = await api('/api/state')" in script
