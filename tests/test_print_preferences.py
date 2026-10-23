from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from autosecretaire import printing
from autosecretaire.app import create_app
from autosecretaire.config import defaults
from autosecretaire.engine import Engine
from autosecretaire.store import Store


@pytest.fixture
def engine(tmp_path):
    store=Store(tmp_path/'registry.sqlite3')
    engine=Engine(defaults(tmp_path),store)
    yield engine
    store.close()


def message(engine):
    c=engine.create_client('Cliente');engine.scan()
    mail=EmailMessage();mail['Subject']='Documents';mail['From']='a@example.test';mail.set_content('Bonjour')
    mail.add_attachment(b'Une note',maintype='text',subtype='plain',filename='note.txt')
    mail.add_attachment(b'format non pris en charge',maintype='application',subtype='msword',filename='contrat.doc')
    path=engine.runtime/'mailboxes'/c['mailbox']/'mail.eml';path.write_bytes(mail.as_bytes())
    engine.scan();engine.process();return engine.state()['messages'][0]


def test_preferences_api_persist_and_old_configuration_defaults(tmp_path):
    store=Store(tmp_path/'registry.sqlite3');store.put('settings','main',{'print_policy':'manual'});store.close()
    with TestClient(create_app(defaults(tmp_path),background=False),base_url='http://127.0.0.1') as c:
        s=c.get('/api/state').json();assert s['settings']['print_sides']=='printer';assert s['settings']['print_color_mode']=='printer'
        h={'X-CSRF-Token':s['csrf_token']}
        r=c.put('/api/settings',headers=h,json={'print_sides':'two-sided-long-edge','print_color_mode':'monochrome'})
        assert r.status_code==200
        r=c.put('/api/settings',headers=h,json={'print_sides':'invalide','print_color_mode':'color'})
        assert r.status_code==400
        assert c.get('/api/state').json()['settings']['print_color_mode']=='monochrome'
    with TestClient(create_app(defaults(tmp_path),background=False),base_url='http://127.0.0.1') as c:
        s=c.get('/api/state').json()['settings'];assert s['print_sides']=='two-sided-long-edge';assert s['print_color_mode']=='monochrome'


@pytest.mark.parametrize('field,value',[('print_sides',[]),('print_sides',None),('print_sides','-o something'),('print_color_mode',True),('print_color_mode',{}),('print_color_mode','ColorModel=RGB')])
def test_invalid_preferences_leave_settings_untouched(engine,field,value):
    before=engine.settings.copy()
    with pytest.raises(ValueError):engine.update_settings({field:value})
    assert engine.settings==before


@pytest.mark.parametrize('sides,color',[('one-sided','monochrome'),('two-sided-long-edge','color'),('two-sided-short-edge','monochrome')])
def test_explicit_options_reach_cups_as_separate_arguments(tmp_path,monkeypatch,sides,color):
    p=tmp_path/'document.pdf';p.write_bytes(b'%PDF test');calls=[]
    def run(args,**kw):
        calls.append(args)
        return SimpleNamespace(returncode=0,stdout='' if args[0].endswith('lpoptions') else 'request id is Bureau-42',stderr='')
    monkeypatch.setattr(printing.subprocess,'run',run)
    assert printing.submit(p,'Bureau',sides=sides,color_mode=color)=='Bureau-42'
    cmd=calls[-1];assert cmd==['/usr/bin/lp','-d','Bureau','-o','sides='+sides,'-o','print-color-mode='+color,'--',str(p)]


def test_announced_legacy_driver_options_are_forwarded(tmp_path,monkeypatch):
    p=tmp_path/'x.pdf';p.write_bytes(b'x');calls=[]
    def run(args,**kw):
        calls.append(args)
        return SimpleNamespace(returncode=0,stdout='ColorModel/Color Mode: *RGB Gray\nDuplex/Two sided: *None DuplexNoTumble DuplexTumble\n' if args[0].endswith('lpoptions') else 'request id is Bureau-1',stderr='')
    monkeypatch.setattr(printing.subprocess,'run',run)
    printing.submit(p,'Bureau',sides='two-sided-long-edge',color_mode='monochrome')
    assert 'ColorModel=Gray' in calls[-1];assert 'Duplex=DuplexNoTumble' in calls[-1]


def test_known_unsupported_option_fails_before_submitting(tmp_path,monkeypatch):
    p=tmp_path/'x.pdf';p.write_bytes(b'x');calls=[]
    def run(args,**kw):
        calls.append(args);return SimpleNamespace(returncode=0,stdout='ColorModel/Mode: *Gray\nDuplex/Mode: *None\n',stderr='')
    monkeypatch.setattr(printing.subprocess,'run',run)
    with pytest.raises(printing.PrintError):printing.submit(p,'Bureau',color_mode='color')
    with pytest.raises(printing.PrintError):printing.submit(p,'Bureau',sides='two-sided-short-edge')
    assert all(c[0]=='/usr/bin/lpoptions' for c in calls)


def test_simulation_has_no_system_calls_but_validates_options(tmp_path,monkeypatch):
    p=tmp_path/'x.pdf';p.write_bytes(b'x')
    monkeypatch.setattr(printing.subprocess,'run',lambda *a,**kw:pytest.fail('system called'))
    assert printing.submit(p,'',True,sides='two-sided-long-edge',color_mode='monochrome').startswith('simulated-')
    with pytest.raises(printing.PrintError):printing.submit(p,'',True,color_mode='invalid')


def test_both_mail_and_supported_attachment_receive_options_without_duplicate(engine,monkeypatch):
    m=message(engine);calls=[]
    def submit(path,printer,dry_run=False,**options):calls.append(options);return 'simulated-1'
    monkeypatch.setattr(printing,'submit',submit)
    engine.update_settings({'print_sides':'two-sided-long-edge','print_color_mode':'monochrome'})
    engine.classify([m['id']],'03 - Documents')
    assert calls==[{'sides':'two-sided-long-edge','color_mode':'monochrome'}]*2
    records=engine.store.all('print');assert len(records)==2
    assert all(p['options']==calls[0] for p in records)
    assert all(p['dry_run'] is True for p in records)
    engine.update_settings({'print_color_mode':'color','print_sides':'one-sided'})
    engine.print_messages([m['id']]);engine.process();assert len(calls)==2
    engine.print_messages([m['id']],reprint=True)
    assert calls[2:]==[{'sides':'one-sided','color_mode':'color'}]*2
    assert engine.store.get('print',records[0]['id'])['options']['color_mode']=='monochrome'


def test_attachment_toggle_is_default_and_per_document_selection_controls_existing(engine,monkeypatch):
    engine.update_settings({'print_attachments':False});m=message(engine)
    email=next(d for d in m['documents'] if d['kind']=='email')
    attachment=next(d for d in m['documents'] if d['original_name']=='note.txt')
    assert email['selected'] and not attachment['selected']
    calls=[];monkeypatch.setattr(printing,'submit',lambda *a,**kw:calls.append(kw) or 'simulated-1')
    engine.select_document(email['id'],False);engine.select_document(attachment['id'],True)
    engine.print_messages([m['id']]);assert len(calls)==1
    assert engine.store.all('print')[0]['document_id']==attachment['id']


def test_preparing_intent_keeps_options_after_settings_change(engine,monkeypatch):
    m=message(engine);email=next(d for d in m['documents'] if d['kind']=='email')
    for d in m['documents']:engine.select_document(d['id'],d['id']==email['id'])
    opts={'sides':'two-sided-short-edge','color_mode':'monochrome'}
    engine.store.put('print',email['id']+'-initial',{'message_id':m['id'],'document_id':email['id'],'status':'preparing','options':opts,'printer':'Ancienne','dry_run':True,'created_at':'before'})
    engine.update_settings({'print_color_mode':'color','printer':'Nouvelle'})
    calls=[];monkeypatch.setattr(printing,'submit',lambda *a,**kw:calls.append((a,kw)) or 'simulated-1')
    engine.print_messages([m['id']]);assert calls[0][0][1]=='Ancienne';assert calls[0][1]=={'dry_run':True,**opts}


def test_unavailable_driver_description_uses_standard_options(tmp_path,monkeypatch):
    p=tmp_path/'x.pdf';p.write_bytes(b'x');calls=[]
    def run(args,**kw):
        calls.append(args)
        if args[0].endswith('lpoptions'):raise FileNotFoundError('no description')
        return SimpleNamespace(returncode=0,stdout='request id is Bureau-1',stderr='')
    monkeypatch.setattr(printing.subprocess,'run',run)
    assert printing.submit(p,'Bureau',color_mode='monochrome')=='Bureau-1'
    assert 'print-color-mode=monochrome' in calls[-1]


def test_confirmed_failure_retry_uses_new_choices(engine,monkeypatch):
    m=message(engine)
    for d in m['documents']:engine.select_document(d['id'],d['kind']=='email')
    attempts=[]
    def submit(path,printer,dry_run=False,**options):
        attempts.append(options)
        if len(attempts)==1:raise printing.PrintError('Mode refusé avant soumission')
        return 'simulated-1'
    monkeypatch.setattr(printing,'submit',submit)
    engine.update_settings({'print_color_mode':'color'});engine.print_messages([m['id']])
    engine.update_settings({'print_color_mode':'monochrome'});engine.print_messages([m['id']])
    assert [a['color_mode'] for a in attempts]==['color','monochrome']
    assert len(engine.store.all('print'))==1
