from email.message import EmailMessage
from pathlib import Path
import pytest
from mailord.config import defaults
from mailord.store import Store
from mailord.engine import Engine


def mail(subject='Contrat'):
    m=EmailMessage(); m['Subject']=subject; m['From']='alice@example.test'; m['To']='bureau@example.test';m['Date']='Fri, 23 Oct 2026 10:00:00 +0200';m['Message-ID']='<'+subject+'@example.test>';m.set_content('Bonjour, voici les documents.');m.add_attachment(b'Note de rendez-vous',maintype='text',subtype='plain',filename='note.txt');return m.as_bytes()


@pytest.fixture
def engine(tmp_path):
    s=defaults(tmp_path);return Engine(s,Store(tmp_path/'state.sqlite3'))


def add_mail(e,c,subject='Contrat'):
    p=Path(e.settings['runtime'])/'mailboxes'/c['mailbox'];p.mkdir(parents=True,exist_ok=True);(p/(subject+'.eml')).write_bytes(mail(subject))


def test_provision_template_version_and_safe_additive(engine):
    c=engine.create_client('Émilie');assert c['status']=='ready'
    engine.save_template(['00 - À classer','Contrats/Signés'])
    root=Path(c['folder']);root.mkdir(exist_ok=True);(root/'preuve.txt').write_text('conserver')
    engine.apply_template(c['id']);assert 'Contrats/Signés' in engine.client_folders(c);assert not (root/'Contrats').exists();assert (root/'preuve.txt').read_text()=='conserver'
    assert engine.create_client('Émilie')['id']==c['id']
    with pytest.raises(ValueError):engine.save_template(['../escape'])


def test_scan_export_repair_and_restart_idempotent(engine):
    c=engine.create_client('Camille');add_mail(engine,c);engine.scan();engine.process()
    m=engine.state()['messages'][0];assert m['status']=='ready';assert m['historical']
    pdf=next(d for d in m['documents'] if d['kind']=='email');Path(pdf['path']).unlink()
    engine.process();assert Path(pdf['path']).is_file()
    engine.scan();assert len(engine.state()['messages'])==1
    e2=Engine(engine.settings,engine.store);e2.process();assert len(e2.state()['messages'][0]['documents'])==2


def test_classify_bulk_confined_and_no_overwrite(engine):
    c=engine.create_client('Camille');add_mail(engine,c);engine.scan();engine.process();m=engine.state()['messages'][0]
    with pytest.raises(ValueError):engine.classify([m['id']],'../escape')
    engine.classify([m['id']],'03 MAILS (PDF)');m=engine.state()['messages'][0];assert m['classification']=='classified'
    assert all('03 MAILS (PDF)' in d['path'] for d in m['documents'])
    engine.classify([m['id']],'07 FACTURES');assert len(engine.store.all('print'))==0


def test_new_mail_prints_once_and_repair_never_reprints(engine):
    c=engine.create_client('Camille');engine.scan();add_mail(engine,c);engine.scan();engine.process();m=engine.state()['messages'][0]
    engine.classify([m['id']],'03 MAILS (PDF)');assert engine.state()['messages'][0]['print_status']=='simulated'
    count=len(engine.store.all('print'));engine.process();engine.classify([m['id']],'07 FACTURES');engine.print_messages([m['id']]);assert len(engine.store.all('print'))==count
    Path(engine.state()['messages'][0]['documents'][0]['path']).write_bytes(b'broken');engine.process();assert len(engine.store.all('print'))==count


def test_history_explicit_validation(engine,tmp_path):
    c=engine.create_client('Camille');add_mail(engine,c);engine.scan();engine.process();m=engine.state()['messages'][0]
    src=Path(m['documents'][0]['path']);legacy=Path(c['folder'])/'ancien.pdf';legacy.write_bytes(src.read_bytes())
    assert any(x['path']==str(legacy) for x in engine.history(c['id'])['candidates'])
    with pytest.raises(ValueError):engine.associate(m['id'],str(tmp_path/'outside.pdf'))
    engine.associate(m['id'],str(legacy));assert engine.state()['messages'][0]['print_status']=='historical'


def test_provision_failure_resumes_same_client(engine,monkeypatch):
    original=engine.connector.create_folder
    monkeypatch.setattr(engine.connector,'create_folder',lambda name: (_ for _ in ()).throw(RuntimeError('offline')))
    c=engine.create_client('Client');assert c['status']=='error'
    monkeypatch.setattr(engine.connector,'create_folder',original)
    assert engine.retry_client(c['id'])['status']=='ready';assert len(engine.store.all('client'))==1


def test_uncertain_submission_never_auto_retries(engine,monkeypatch):
    from mailord import printing
    c=engine.create_client('Client');engine.scan();add_mail(engine,c);engine.scan();engine.process();m=engine.state()['messages'][0]
    monkeypatch.setattr(printing,'submit',lambda *a,**k: (_ for _ in ()).throw(printing.PrintUncertain('timeout')))
    engine.print_messages([m['id']]);assert engine.state()['messages'][0]['print_status']=='uncertain'
    before=len(engine.store.all('print'));engine.print_messages([m['id']]);assert len(engine.store.all('print'))==before


def test_repair_does_not_follow_replaced_symlink(engine):
    c=engine.create_client('Camille');add_mail(engine,c);engine.scan();engine.process();m=engine.state()['messages'][0]
    tracked=Path(m['documents'][0]['path']);other=Path(c['folder'])/'important.pdf';other.write_bytes(b'precious');tracked.unlink();tracked.symlink_to(other)
    engine.process();assert other.read_bytes()==b'precious';assert tracked.is_symlink();assert engine.state()['messages'][0]['status']=='error'


def test_preparing_print_resumes_without_new_generation(engine):
    c=engine.create_client('Camille');engine.scan();add_mail(engine,c);engine.scan();engine.process();m=engine.state()['messages'][0];d=m['documents'][0]
    pid=d['id']+'-initial';engine.store.put('print',pid,{'message_id':m['id'],'document_id':d['id'],'status':'preparing','error':'','job_id':''})
    engine.print_messages([m['id']]);assert engine.store.get('print',pid)['status']=='simulated'


def test_same_name_existing_destination_is_preserved(engine):
    c=engine.create_client('Camille');add_mail(engine,c);engine.scan();engine.process();m=engine.state()['messages'][0]
    target=Path(c['folder'])/'03 MAILS (PDF)'/next(d for d in m['documents'] if d['kind']=='attachment')['name'];target.parent.mkdir();target.write_bytes(b'precious')
    engine.classify([m['id']],'03 MAILS (PDF)');assert target.read_bytes()==b'precious'
    assert next(d for d in engine.state()['messages'][0]['documents'] if d['kind']=='attachment')['path']!=str(target)


def test_resume_partial_move_intent(engine):
    c=engine.create_client('Camille');add_mail(engine,c);engine.scan();engine.process();m=engine.state()['messages'][0];d=next(d for d in m['documents'] if d['kind']=='attachment')
    dst=Path(c['folder'])/'03 MAILS (PDF)'/d['name'];dst.parent.mkdir();dst.write_bytes(Path(d['path']).read_bytes())
    record=engine.store.get('document',d['id']);record['move_to']=str(dst);engine.store.put('document',d['id'],record)
    engine.process();assert not Path(d['path']).exists();assert engine.store.get('document',d['id'])['path']==str(dst)


def test_retry_failed_print_only(engine,monkeypatch):
    from mailord import printing
    c=engine.create_client('Camille');engine.scan();add_mail(engine,c);engine.scan();engine.process();m=engine.state()['messages'][0]
    actual=printing.submit;calls=[]
    def first(path,printer,dry_run=False,**options):
        calls.append(str(path))
        if len(calls)==1:raise printing.PrintError('printer not accepting')
        return actual(path,printer,dry_run,**options)
    monkeypatch.setattr(printing,'submit',first);engine.print_messages([m['id']]);assert len(calls)==2
    engine.print_messages([m['id']]);assert len(calls)==3;assert engine.state()['messages'][0]['print_status']=='simulated'


def test_crash_submitting_is_uncertain(engine):
    engine.store.put('print','inflight',{'status':'submitting','message_id':'one','document_id':'one'})
    Engine(engine.settings,engine.store)
    assert engine.store.get('print','inflight')['status']=='uncertain'


def test_print_failure_exposes_actionable_details(engine,monkeypatch):
    from mailord import printing
    c=engine.create_client('Camille');engine.scan();add_mail(engine,c);engine.scan();engine.process();m=engine.state()['messages'][0]
    monkeypatch.setattr(printing,'submit',lambda *a,**k: (_ for _ in ()).throw(printing.PrintError('Imprimante hors ligne')))
    engine.print_messages([m['id']]);m=engine.state()['messages'][0]
    assert m['print_jobs'][0]['error']=='Imprimante hors ligne'
    assert m['print_jobs'][0]['document_id']==m['documents'][0]['id']
