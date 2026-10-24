from filing_helpers import post_classify
from fastapi.testclient import TestClient
from mailord.app import create_app
from mailord.config import defaults


def test_local_api_csrf_config_and_files(tmp_path):
    app=create_app(defaults(tmp_path),background=False)
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        state=c.get('/api/state').json();token=state['csrf_token'];headers={'X-CSRF-Token':token}
        assert c.post('/api/clients',json={'name':'Client'}).status_code==403
        assert c.post('/api/clients',json={'name':'Client'},headers={**headers,'Origin':'https://evil.test'}).status_code==403
        assert c.post('/api/clients',json={'name':'Client'},headers=headers).status_code==200
        assert c.put('/api/settings',json={'archive_root':'/tmp/elsewhere'},headers=headers).status_code==400
        assert c.put('/api/settings',json={'print_policy':'manual'},headers=headers).status_code==200
        assert 'imap_password' not in c.get('/api/state').json()['settings']
        assert c.get('/api/documents/unknown/file').status_code==404
        assert c.get('/').status_code==200


def test_host_rebinding_blocked(tmp_path):
    with TestClient(create_app(defaults(tmp_path),background=False),base_url='http://attacker.test') as c:
        assert c.get('/api/state').status_code==400


def test_second_instance_cannot_mutate_registry(tmp_path):
    import pytest
    app=create_app(defaults(tmp_path),background=False)
    with TestClient(app,base_url='http://127.0.0.1:8765'):
        engine=app.state.engine
        engine.store.put('print','inflight',{'message_id':'one','status':'submitting'})
        with pytest.raises(RuntimeError,match='déjà'):create_app(defaults(tmp_path),background=False)
        assert engine.store.get('print','inflight')['status']=='submitting'


def test_demo_seed_and_http_document_workflow(tmp_path):
    from mailord.demo import seed
    app=create_app(defaults(tmp_path),background=False)
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        seed(app.state.engine);seed(app.state.engine)
        s=c.get('/api/state').json();assert len(s['clients'])==3;assert len(s['messages'])==7
        headers={'X-CSRF-Token':s['csrf_token']};m=s['messages'][0];d=m['documents'][0]
        result=c.get('/api/documents/'+d['id']+'/file');assert result.content.startswith(b'%PDF-')
        assert result.headers['content-type']=='application/pdf'
        assert post_classify(c,headers,{'message_ids':[m['id']],'destination':'03 MAILS (PDF)'}).status_code==200
        assert c.post('/api/print',headers=headers,json={'message_ids':[m['id']]}).status_code==200
        assert next(x for x in c.get('/api/state').json()['messages'] if x['id']==m['id'])['print_status']=='simulated'
        assert c.post('/api/messages/'+m['id']+'/reprint',headers=headers,json={'confirm':False}).status_code==400
        assert c.get('/api/clients/'+m['client_id']+'/history').status_code==200
