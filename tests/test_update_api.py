from fastapi.testclient import TestClient
from mailord.app import create_app
from mailord.config import defaults
from mailord.store import Store


def test_update_api_security_and_configuration(tmp_path):
    app=create_app(defaults(tmp_path),background=False)
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        s=c.get('/api/state').json();assert s['updates']['status']=='unconfigured'
        assert not s['updates']['managed']
        h={'X-CSRF-Token':s['csrf_token']}
        assert c.put('/api/updates/config',json={'repository':'https://github.com/example/project.git','branch':'main'}).status_code==403
        assert c.put('/api/updates/config',headers=h,json={'repository':'https://github.com/example/project.git','branch':'main'}).status_code==200
        assert c.get('/api/updates').json()['branch']=='main'
        assert c.post('/api/updates/install',headers=h,json={'commit':'a'*40}).status_code==400
        assert c.put('/api/updates/config',headers=h,json={'repository':'ext::bad','branch':'main'}).status_code==400
        assert c.post('/api/updates/check',headers={**h,'Origin':'https://evil.test'}).status_code==403
        assert c.get('/api/health').status_code==403


def test_probation_prohibits_recovery_and_all_business_access(tmp_path):
    store=Store(tmp_path/'registry.sqlite3');store.put('print','p',{'status':'submitting'});store.close()
    app=create_app(defaults(tmp_path),background=False,probation=True,health_token='private-token')
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        assert app.state.engine.store.get('print','p')['status']=='submitting'
        assert c.get('/api/state').status_code==503
        assert c.post('/api/clients',json={'name':'Forbidden'}).status_code==503
        assert c.get('/api/health').status_code==403
        assert c.get('/api/health',headers={'X-Supervisor-Token':'private-token'}).json()['ready']
        assert c.post('/api/activate',headers={'X-Supervisor-Token':'wrong'}).status_code==403
        assert c.post('/api/activate',headers={'X-Supervisor-Token':'private-token'}).status_code==200
        assert c.get('/api/state').status_code==200
        assert app.state.engine.store.get('print','p')['status']=='uncertain'
        assert c.post('/api/activate',headers={'X-Supervisor-Token':'private-token'}).status_code==200
