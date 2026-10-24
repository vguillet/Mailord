"""Durable, serial orchestration. Files stay ordinary Finder documents."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .config import DEFAULT_FOLDERS, DEFAULT_EMAIL_FOLDER
from .connectors import make_connector
from . import documents, printing


def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return uuid.uuid4().hex
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(value):
    if not isinstance(value,str) or not value.strip() or value.startswith(('/', '~')) or '\\' in value or '\x00' in value:
        raise ValueError('Chemin de dossier invalide.')
    parts=value.split('/')
    if any(p in ('','.', '..') or p.strip()!=p or ':' in p or any(ord(c)<32 for c in p) for p in parts):
        raise ValueError('Utilisez des noms de dossiers simples, sans ../ ni chemin absolu.')
    if any(len(p.encode())>200 for p in parts):raise ValueError('Nom de dossier trop long.')
    return '/'.join(parts)


def within(root,path):
    root=Path(root).resolve();original=Path(path).absolute()
    for component in [original,*original.parents]:
        if component==root:break
        if component.is_symlink():raise ValueError('Lien symbolique refusé : choisissez un fichier ou dossier ordinaire.')
    p=original.resolve()
    if p==root or not p.is_relative_to(root):raise ValueError('Le chemin doit rester dans le dossier autorisé.')
    return p


class Engine:
    def __init__(self, settings, store, connector=None, recover=True):
        self.store=store;self.lock=threading.RLock()
        self.settings={**settings,**(store.get('settings','main') or {})};self.settings.pop('id',None)
        self.runtime=Path(settings['runtime']).resolve();self.runtime.mkdir(parents=True,exist_ok=True);self.runtime.chmod(0o700)
        for name in ['spool','staging','quarantine','print']:(self.runtime/name).mkdir(exist_ok=True)
        self.root=Path(self.settings['archive_root']).expanduser().resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.connector=connector or make_connector(self.settings,self.runtime)
        self.folders=[];self.printers=[];self.last_scan='';self.sync_error=''
        if not self.store.all('template'):self.save_template(DEFAULT_FOLDERS)
        if recover:self.recover()

    def recover(self):
        # A crash after persisting the intent cannot prove whether CUPS received it.
        for p in self.store.all('print'):
            if p['status']=='submitting':p['status']='uncertain';p['error']='Service interrompu pendant la soumission. Vérifiez la file de l’imprimante.';self.store.put('print',p['id'],p)
        self._recover_moves()

    def error_text(self,e):
        text=str(e)[:600]
        secret=os.environ.get(self.settings.get('imap_password_env',''), '')
        return text.replace(secret,'[secret masqué]') if secret else text

    def event(self,text,level='info'):
        self.store.put('event',uid(),{'date':now(),'message':text,'level':level})
        events=self.store.all('event')
        for x in events[:-200]:self.store.delete('event',x['id'])

    def template(self):
        t=self.store.all('template')[-1]
        t.setdefault('initial_folders',[DEFAULT_EMAIL_FOLDER] if DEFAULT_EMAIL_FOLDER in t['folders'] else [])
        return t

    def save_template(self,folders,initial_folders=None,email_folder=None):
        with self.lock:
            if not isinstance(folders,list) or not 1<=len(folders)<=250:raise ValueError('Le modèle doit contenir de 1 à 250 dossiers.')
            cleaned=[relative(x) for x in folders]
            if len({x.casefold() for x in cleaned})!=len(cleaned):raise ValueError('Deux dossiers portent le même nom.')
            previous=self.template() if self.store.all('template') else {'email_folder':DEFAULT_EMAIL_FOLDER,'initial_folders':[DEFAULT_EMAIL_FOLDER]}
            # Retain the old API option as metadata only; it never routes documents.
            mail=relative(previous.get('email_folder',DEFAULT_EMAIL_FOLDER) if email_folder is None else email_folder)
            allowed=set(cleaned)
            for p in cleaned:
                parts=p.split('/');allowed.update('/'.join(parts[:i]) for i in range(1,len(parts)))
            if email_folder is not None and mail not in allowed:raise ValueError('Le dossier indiqué doit appartenir au modèle.')
            selected=[p for p in previous['initial_folders'] if p in allowed] if initial_folders is None else initial_folders
            if not isinstance(selected,list):raise ValueError('Présélection de dossiers invalide.')
            selected=list(dict.fromkeys(relative(p) for p in selected))
            if any(p not in allowed for p in selected):raise ValueError('Un dossier présélectionné est absent du modèle.')
            if len({p.casefold() for p in cleaned})!=len(cleaned):raise ValueError('Deux dossiers portent le même nom.')
            t={'version':len(self.store.all('template'))+1,'folders':cleaned,'initial_folders':selected,'email_folder':mail,'created_at':now()};id=uid();self.store.put('template',id,t);return self.store.get('template',id)

    def client(self,id):
        c=self.store.get('client',id)
        if not c:raise KeyError('Client introuvable.')
        within(self.root,c['folder']);return c

    def existing_folders(self,c):
        root=within(self.root,c['folder'])
        paths=set()
        if root.exists():
            for p in root.rglob('*'):
                if p.is_dir():
                    try:within(root,p)
                    except ValueError:continue
                    paths.add(str(p.relative_to(root)))
        return sorted(paths,key=str.casefold)

    def client_folders(self,c,existing=None):
        paths=set(c.get('folders',[])) | set(c.get('initial_folders',[])) | set(self.template()['folders']) | {'00 - À classer'}
        paths.update(self.existing_folders(c) if existing is None else existing)
        # A template can store only leaves; every ancestor is also a destination.
        for name in list(paths):
            parts=name.split('/')
            paths.update('/'.join(parts[:i]) for i in range(1,len(parts)))
        return sorted(paths,key=str.casefold)

    def create_client(self,name,mailbox='',initial_folders=None):
        with self.lock:
            selected=[] if initial_folders is None else initial_folders
            if not isinstance(selected,list):raise ValueError('Sélection de dossiers invalide.')
            selected=list(dict.fromkeys(relative(p) for p in selected))
            allowed=set(self.template()['folders'])
            for p in list(allowed):
                parts=p.split('/');allowed.update('/'.join(parts[:i]) for i in range(1,len(parts)))
            if any(p not in allowed for p in selected):raise ValueError('Choisissez les dossiers à créer dans le modèle courant.')
            name=relative(name.strip())
            if '/' in name:raise ValueError('Le nom du client ne peut pas contenir /.')
            for c in self.store.all('client'):
                if c['name'].casefold()==name.casefold():
                    c['initial_folders']=list(dict.fromkeys(c.get('initial_folders',[])+selected))
                    self.store.put('client',c['id'],c)
                    return self.retry_client(c['id'])
            if initial_folders is None:selected=self.template()['initial_folders']
            folder_name=self.settings.get('client_folder_pattern','{name}').replace('{name}',name);relative(folder_name)
            if '/' in folder_name:raise ValueError('Le modèle de nom client ne doit pas créer de chemin imbriqué.')
            folder=within(self.root,self.root/folder_name)
            if any(Path(c['folder']).name.casefold()==folder_name.casefold() for c in self.store.all('client')):raise ValueError('Ce dossier est déjà associé à un client.')
            mailbox=mailbox.strip() or name
            if any(c['mailbox']==mailbox for c in self.store.all('client')):raise ValueError('Cette boîte est déjà associée à un autre client.')
            c={'name':name,'mailbox':mailbox,'folder':str(folder),'status':'provisioning','error':'','template_version':self.template()['version'],'folders':self.template()['folders'],'initial_folders':selected,'favorites':[],'initialized':False}
            id=uid();self.store.put('client',id,c);return self.retry_client(id)

    def retry_client(self,id):
        with self.lock:
            c=self.client(id)
            try:
                root=within(self.root,c['folder'])
                if root.exists() and not root.is_dir():raise ValueError('Le chemin du client est occupé par un fichier.')
                self.connector.create_folder(c['mailbox'])
                for p in c.get('initial_folders',[]):
                    within(root,root/relative(p)).mkdir(parents=True,exist_ok=True)
                c.update(status='ready',error='')
            except Exception as e:c.update(status='error',error=self.error_text(e))
            self.store.put('client',id,c);return self.client(id)

    def apply_template(self,id):
        with self.lock:
            c=self.client(id);t=self.template()
            c['folders']=sorted(set(c['folders']+t['folders']));c['template_version']=t['version'];self.store.put('client',id,c);return c

    def favorites(self,id,folders):
        with self.lock:
            c=self.client(id);allowed=self.client_folders(c)
            if any(p not in allowed for p in folders):raise ValueError('Un favori ne correspond à aucun dossier.')
            c['favorites']=list(dict.fromkeys(folders));self.store.put('client',id,c);return c

    def star_client(self,id,starred):
        with self.lock:
            if type(starred)!=bool:raise ValueError('Étoile invalide.')
            c=self.client(id);c['starred']=starred;self.store.put('client',id,c);return c

    def list_folders(self):
        with self.lock:self.folders=self.connector.list_folders();return self.folders

    def scan(self):
        with self.lock:
            self.sync_error=''
            try:self.list_folders()
            except Exception as e:self.sync_error=self.error_text(e);self.event(self.sync_error,'error');return
            for c in self.store.all('client'):
                if c['status']!='ready':continue
                try:
                    sources=self.connector.list_messages(c['mailbox'])
                    for source in sources:
                        # Re-fetch only when unknown; rescan includes read and moved messages.
                        source_key=f"{c['mailbox']}\0{source.source_id}"
                        known=next((m for m in self.store.all('message') if source_key in m.get('sources',[])),None)
                        if known:continue
                        raw=self.connector.fetch(c['mailbox'],source.source_id)
                        parsed=documents.parse_message(raw,source.received_at)
                        identity=hashlib.sha256(raw).hexdigest();existing=self.store.get('message',identity)
                        if existing:
                            existing.setdefault('sources',[]).append(source_key);self.store.put('message',identity,existing)
                            if existing['client_id']!=c['id']:self.event('Message déjà suivi chez un autre client : '+parsed['subject'],'warning')
                            continue
                        spool=self.runtime/'spool'/(identity+'.eml');tmp=spool.with_suffix('.tmp');tmp.write_bytes(raw);tmp.replace(spool)
                        m={'client_id':c['id'],'subject':parsed['subject'],'sender':parsed['sender'],'recipients':parsed['recipients'],'body':parsed['body'],'date':str(parsed['date']),'received_at':source.received_at or now(),'status':'queued','classification':'pending','destination':'00 - À classer','print_status':'historical' if not c.get('initialized') else 'pending','historical':not c.get('initialized'),'error':'','sources':[source_key],'spool':str(spool),'discovered_at':now()}
                        m.update(filing_version=3,classification_auto_print=True)
                        self.store.put('message',identity,m);self._queue(identity)
                    c['initialized']=True;c['error']='';self.store.put('client',c['id'],c)
                except Exception as e:
                    c['error']=self.error_text(e);self.store.put('client',c['id'],c);self.sync_error=c['error'];self.event(c['name']+' : '+c['error'],'error')
            self.last_scan=now();self.store.put('meta','scan',{'date':self.last_scan,'error':self.sync_error})

    def _queue(self,id):self.store.put('job',id,{'message_id':id,'status':'queued','error':''})

    def _docs(self,id):return [d for d in self.store.all('document') if d['message_id']==id]

    def _healthy(self,d):
        try:
            p=within(self.root,d['path'])
            return p.is_file() and digest(p)==d['sha256'] and (d['kind']!='email' or documents.valid_pdf(p))
        except (ValueError,OSError):return False

    def _target(self,root,name,id,sha,reserved=()):
        target=within(root,root/name)
        # Case-insensitive collision handling also works on case-sensitive development disks.
        occupied={p.name.casefold():p for p in root.iterdir()} if root.exists() else {}
        found=occupied.get(target.name.casefold())
        if found is not None:target=found
        if target.exists() or str(target).casefold() in reserved:
            target=within(root,root/(Path(name).stem+' - '+id[:10]+Path(name).suffix))
            index=2
            while target.exists() or str(target).casefold() in reserved:
                target=within(root,root/(Path(name).stem+' - '+id[:10]+f' ({index})'+Path(name).suffix));index+=1
        return target

    def _prune_empty(self,root,directory):
        # rmdir never removes content (including hidden files), and no tree walk
        # is performed: only ancestors of the directory involved are considered.
        try:
            root=Path(root)
            if root!=self.root:root=within(self.root,root)
            path=within(self.root,directory)
            if not path.is_relative_to(root):return
            protected=set()
            for c in self.store.all('client'):
                for selected in c.get('initial_folders',[]):
                    keep=within(self.root,Path(c['folder'])/relative(selected))
                    while keep!=self.root:
                        protected.add(str(keep).casefold());keep=keep.parent
            while path!=root:
                if str(path).casefold() in protected:return
                path.rmdir()
                path=path.parent
        except (OSError,ValueError):pass

    def _publish(self,source,target):
        target=within(self.root,target)
        # Write complete data before linking into a synced directory; linking never overwrites.
        temporary=target.parent/('.auto-'+uid()+'.tmp')
        try:
            target.parent.mkdir(parents=True,exist_ok=True)
            with open(temporary,'xb') as f:
                f.write(Path(source).read_bytes());f.flush();os.fsync(f.fileno())
            os.link(temporary,target)
        finally:
            temporary.unlink(missing_ok=True)
            self._prune_empty(self.root,target.parent)

    def _prepare_filing(self,m):
        if m.get('filing_version')==3:return
        # Old shared move intents must finish before adapting their final paths.
        if m.get('move_destination'):raise ValueError('Classement précédent incomplet. Relancez le contrôle.')
        root=Path(self.client(m['client_id'])['folder'])
        with self.store.transaction():
            for d in self._docs(m['id']):
                d.setdefault('destination',str(Path(d['path']).parent.relative_to(root)))
                d.setdefault('classification',m['classification'])
                self.store.put('document',d['id'],d)
            m.update(filing_version=3,classification_auto_print=m.get('classification_auto_print',m['classification']=='classified'))
            m.pop('email_destination',None)
            self.store.put('message',m['id'],m)

    def _refresh_classification(self,id):
        m=self.store.get('message',id);ds=self._docs(id)
        if m.get('filing_version') not in (2,3) or m['status']!='ready' or not ds:return
        tracked=ds if m['filing_version']==3 else [d for d in ds if d['kind']=='attachment']
        complete=all(d.get('classification')=='classified' and not d.get('move_to') for d in tracked)
        m['classification']='classified' if complete else 'pending'
        destinations={d.get('destination','00 - À classer') for d in tracked}
        m['destination']=next(iter(destinations)) if len(destinations)==1 else ''
        self.store.put('message',id,m)

    def process(self):
        with self.lock:
            self._recover_moves()
            for m in self.store.all('message'):
                try:
                    self._prepare_filing(m)
                    ds=self._docs(m['id'])
                    if m['status']!='ready' or not ds or not all(self._healthy(d) for d in ds):
                        self.store.put('job',m['id'],{'message_id':m['id'],'status':'running','error':''})
                        c=self.client(m['client_id']);root=Path(c['folder'])
                        stage=self.runtime/'staging'/uid();stage.mkdir()
                        exports=documents.export_message(Path(m['spool']).read_bytes(),stage,received_at=m['received_at'],date_source=self.settings['date_source'],prefix_format=self.settings['prefix_format'],identity=m['id'])
                        for index,x in enumerate(exports):
                            did=m['id']+f'-{index}';d=self.store.get('document',did)
                            if d and self._healthy(d):continue
                            if d:
                                target=within(self.root,d['path'])
                                if target.exists():
                                    quarantine=self.runtime/'quarantine'/(uid()+'-'+target.name);shutil.copy2(target,quarantine);target.unlink()
                            else:
                                destination='00 - À classer'
                                dest=within(root,root/relative(destination))
                                target=self._target(dest,Path(x['path']).name,did,x['sha256'])
                                d={**x,'message_id':m['id'],'path':str(target),'name':target.name,'destination':destination,
                                   'classification':'pending',
                                   'selected':x['kind']=='email' or (self.settings.get('print_attachments',True) and x['printable'] and not x.get('inline',False))}
                                self.store.put('document',did,d)
                            self._publish(x['path'],target);d.update(path=str(target),name=target.name,sha256=digest(target));self.store.put('document',did,d)
                        shutil.rmtree(stage);m.update(status='ready',error='');self.store.put('message',m['id'],m)
                        self.store.put('job',m['id'],{'message_id':m['id'],'status':'done','error':''})
                    self._refresh_classification(m['id'])
                except Exception as e:
                    m.update(status='error',error=self.error_text(e));self.store.put('message',m['id'],m)
                    self.store.put('job',m['id'],{'message_id':m['id'],'status':'error','error':m['error']})

            for current in self.store.all('message'):
                policy=self.settings['print_policy']
                eligible=policy=='after_export' or (policy=='after_classify' and current['classification']=='classified' and current.get('classification_auto_print',True))
                if eligible and current['status']=='ready' and not current['historical']:
                    try:self.print_messages([current['id']],retry_failed=False)
                    except Exception as e:self.event(self.error_text(e),'error')

    def _recover_moves(self):
        for d in self.store.all('document'):
            if not d.get('move_to'):continue
            try:
                src=within(self.root,d['path']);dst=within(self.root,d['move_to'])
                if not dst.exists():self._publish(src,dst)
                if digest(dst)!=d['sha256']:raise ValueError('Destination modifiée pendant le classement ; reprise suspendue.')
                if src.exists() and src!=dst:
                    if digest(src)!=d['sha256']:raise ValueError('Source modifiée pendant le classement ; original conservé.')
                    src.unlink()
                if src.parent!=dst.parent:self._prune_empty(self.root,src.parent)
                d.update(path=str(dst),name=dst.name);d.pop('move_to')
                if 'move_destination' in d:
                    d['destination']=d.pop('move_destination');d['classification']=d.pop('move_classification','classified')
                self.store.put('document',d['id'],d)
            except (OSError,ValueError) as e:self.event(self.error_text(e),'error')
        for m in self.store.all('message'):
            # Compatibility with intents recorded by the previous shared filing workflow.
            if m.get('move_destination') and not any(d.get('move_to') for d in self._docs(m['id'])):
                m['destination']=m.pop('move_destination');m['classification']='classified';self.store.put('message',m['id'],m)
            self._refresh_classification(m['id'])

    def classify(self,ids,destination,document_ids=None):
        with self.lock:
            destination=relative(destination);ms=self._messages(ids)
            if len({m['client_id'] for m in ms})!=1:raise ValueError('Sélectionnez des messages du même client.')
            if any(m['status']!='ready' for m in ms):raise ValueError('Attendez que tous les documents soient exportés.')
            c=self.client(ms[0]['client_id']);root=Path(c['folder']);dest=within(root,root/destination)
            all_docs=[d for m in ms for d in self._docs(m['id'])]
            if any(d.get('move_to') for d in all_docs):raise ValueError('Classement incomplet. Relancez le contrôle avant un nouveau classement.')
            available={d['id']:d for d in all_docs}
            if document_ids is None:ds=list(available.values())
            else:
                if not isinstance(document_ids,list) or any(not isinstance(i,str) for i in document_ids):raise ValueError('Sélection de documents invalide.')
                if any(i not in available for i in document_ids):raise ValueError('Sélectionnez uniquement les documents des mails choisis.')
                ds=[available[i] for i in dict.fromkeys(document_ids)]
            if not ds:raise ValueError('Aucun document à classer.')
            if any(not self._healthy(d) for d in ds):raise ValueError('Un fichier manque ou a changé. Lancez le contrôle avant classement.')
            for m in ms:self._prepare_filing(m)
            ds=[self.store.get('document',d['id']) for d in ds]
            reserved=set()
            with self.store.transaction():
                for d in ds:
                    src=within(root,d['path'])
                    target=src if src.parent==dest else self._target(dest,src.name,d['id'],d['sha256'],reserved)
                    reserved.add(str(target).casefold())
                    if target!=src or d.get('classification')!='classified':
                        d['undo_filing']={'token':uid(),'path':str(src),'destination':d['destination'],
                                          'classification':d['classification'],'target_path':str(target)}
                        d.pop('undo_applied',None)
                    d.update(move_to=str(target),move_destination=destination);self.store.put('document',d['id'],d)
                for m in ms:
                    m['classification_auto_print']=True;self.store.put('message',m['id'],m)
            self._recover_moves()
            if any(self.store.get('document',d['id']).get('move_to') for d in ds):raise ValueError('Classement incomplet. Consultez le journal et relancez le contrôle.')
            printable_ids=[m['id'] for m in ms if not m['historical'] and self.store.get('message',m['id'])['classification']=='classified']
            if self.settings['print_policy']=='after_classify' and printable_ids:
                self.print_messages(printable_ids,retry_failed=False)

    def undo_filing(self,id,token):
        with self.lock:
            d=self.store.get('document',id)
            if not d:raise KeyError('Document introuvable.')
            if d.get('move_to'):raise ValueError('Déplacement incomplet. Relancez le contrôle avant de réessayer.')
            if token and d.get('undo_applied')==token:return d
            undo=d.get('undo_filing')
            if not undo or not token or undo['token']!=token:raise ValueError('Ce classement ne peut plus être annulé. Actualisez la page.')
            if d['path']!=undo['target_path'] or not self._healthy(d):raise ValueError('Le fichier manque ou a changé. Lancez le contrôle avant annulation.')
            m=self._messages([d['message_id']])[0]
            root=Path(self.client(m['client_id'])['folder'])
            src=within(root,d['path']);target=within(root,undo['path'])
            if target!=src and target.exists():raise ValueError('Un fichier occupe déjà l’ancien emplacement. Aucun fichier n’a été remplacé.')
            with self.store.transaction():
                d.update(move_to=str(target),move_destination=undo['destination'],move_classification=undo['classification'],undo_applied=token)
                d.pop('undo_filing');self.store.put('document',id,d)
                m['classification_auto_print']=False;self.store.put('message',m['id'],m)
            self._recover_moves()
            result=self.store.get('document',id)
            if result.get('move_to'):raise ValueError('Annulation à reprendre. Relancez le contrôle des fichiers.')
            return result

    def _messages(self,ids):
        if not isinstance(ids,list) or not ids:raise ValueError('Sélectionnez au moins un message.')
        ms=[self.store.get('message',i) for i in dict.fromkeys(ids)]
        if any(m is None for m in ms):raise KeyError('Message introuvable.')
        return ms

    def print_document(self,id,reprint=False):
        with self.lock:
            d=self.store.get('document',id)
            if not d:raise KeyError('Document introuvable.')
            if not d['printable']:raise ValueError('Ce format ne peut pas être imprimé ici. Ouvrez-le dans son application.')
            return self.print_messages([d['message_id']],reprint=reprint,document_ids={id})[0]

    def print_messages(self,ids,reprint=False,retry_failed=True,*,document_ids=None):
        with self.lock:
            results=[]
            for m in self._messages(ids):
                if m['status']!='ready':raise ValueError('Les documents doivent être exportés avant impression.')
                generation=uid() if reprint else 'initial'
                for d in self._docs(m['id']):
                    if document_ids is not None:
                        if d['id'] not in document_ids:continue
                    elif not d.get('selected'):continue
                    if not d['printable']:continue
                    pid=d['id']+'-'+generation
                    if not reprint:
                        own=[p for p in self.store.all('print') if p['document_id']==d['id']]
                        # A confirmed reprint supersedes the initial intent, including its failures.
                        if own:pid=own[-1]['id']
                    previous=self.store.get('print',pid)
                    if previous and not (previous['status']=='preparing' or (previous['status']=='error' and retry_failed)):
                        results.append(previous);continue
                    if not self._healthy(d):raise ValueError('Fichier manquant ou modifié ; effectuez un contrôle.')
                    options={'sides':self.settings.get('print_sides','printer'),'color_mode':self.settings.get('print_color_mode','printer')}
                    p={'message_id':m['id'],'document_id':d['id'],'status':'preparing','created_at':now(),'error':'','job_id':'',
                       'options':options,'printer':self.settings['printer'],'dry_run':self.settings['dry_run']}
                    # A prepared but not submitted intent keeps its original settings on resume.
                    if previous and previous['status']=='preparing':
                        for key in ('options','printer','dry_run','created_at'):
                            if key in previous:p[key]=previous[key]
                    self.store.put('print',pid,p)
                    try:
                        printable=documents.convert_for_print(Path(d['path']),self.runtime/'print')
                        p['status']='submitting';self.store.put('print',pid,p)
                        job=printing.submit(printable,p['printer'],dry_run=p['dry_run'],**p['options'])
                        p.update(status='simulated' if p['dry_run'] else 'submitted',job_id=job)
                    except printing.PrintUncertain as e:p.update(status='uncertain',error=self.error_text(e))
                    except printing.PrintError as e:p.update(status='error',error=self.error_text(e))
                    except Exception as e:p.update(status='uncertain' if p['status']=='submitting' else 'error',error=self.error_text(e))
                    self.store.put('print',pid,p)
                    results.append(self.store.get('print',pid))
                m['print_status']=self.print_status(m);self.store.put('message',m['id'],m)
            return results

    def print_progress(self,m):
        latest={p['document_id']:p for p in self.store.all('print') if p['message_id']==m['id']}
        progress=dict.fromkeys(['total','submitted','simulated','pending','error','uncertain','preparing','submitting'],0)
        for d in self._docs(m['id']):
            if not d['printable'] or not (d.get('selected') or d['id'] in latest):continue
            status=latest.get(d['id'],{}).get('status','pending')
            if status not in progress:status='uncertain'
            progress['total']+=1;progress[status]+=1
        return progress

    def print_status(self,m,progress=None):
        p=self.print_progress(m) if progress is None else progress
        if not p['total']:return 'not_selected'
        for status in ['uncertain','error','submitting','preparing']:
            if p[status]:return status
        complete=p['submitted']+p['simulated']
        if complete and complete<p['total']:return 'partial'
        if p['submitted'] and p['simulated']:return 'mixed'
        if complete:return 'submitted' if p['submitted'] else 'simulated'
        return 'historical' if m['historical'] else 'pending'

    def select_document(self,id,selected):
        with self.lock:
            d=self.store.get('document',id)
            if not d:raise KeyError('Document introuvable.')
            if type(selected)!=bool:raise ValueError('Sélection invalide.')
            d['selected']=selected;self.store.put('document',id,d);return d

    def history(self,id):
        c=self.client(id);root=Path(c['folder']);known={d['path'] for d in self.store.all('document')};items=[]
        for p in root.rglob('*'):
            if p.suffix.lower()=='.pdf' and p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root) and str(p) not in known:
                items.append({'path':str(p),'name':str(p.relative_to(root)),'size':p.stat().st_size})
        return {'candidates':items,'note':'Choisissez un message et vérifiez le PDF avant association. Aucune impression automatique.'}

    def associate(self,id,path):
        with self.lock:
            m=self._messages([id])[0];c=self.client(m['client_id']);p=within(Path(c['folder']),path)
            if not documents.valid_pdf(p):raise ValueError('Le fichier sélectionné n’est pas un PDF valide.')
            if any(d['path']==str(p) and d['message_id']!=id for d in self.store.all('document')):raise ValueError('Ce fichier est déjà associé à un autre message.')
            d=next((x for x in self._docs(id) if x['kind']=='email'),None) or {'id':id+'-0','message_id':id,'kind':'email','inline':False,'selected':True,'printable':True,'original_name':m['subject']+'.pdf'}
            if d.get('move_to'):raise ValueError('Déplacement du PDF incomplet. Relancez le contrôle avant association.')
            d.update(path=str(p),name=p.name,sha256=digest(p),destination=str(p.parent.relative_to(Path(c['folder']))),classification='classified');self.store.put('document',d['id'],d)
            m.update(historical=True,print_status='historical');self.store.put('message',id,m)
            self._refresh_classification(id)

    def update_settings(self,values):
        with self.lock:
            allowed=set(self.settings)-{'runtime','id','timezone'}
            if set(values)-allowed:raise ValueError('Réglage inconnu.')
            s={**self.settings,**values}
            if s['connector'] not in ['demo','imap','apple_mail'] or s['print_policy'] not in ['manual','after_classify','after_export']:raise ValueError('Mode invalide.')
            if s['prefix_format'] not in ['%Y-%m-%d','%Y%m%d'] or s['date_source'] not in ['received','sent']:raise ValueError('Format de date invalide.')
            if type(s['poll_seconds']) is not int or not 15<=s['poll_seconds']<=3600:raise ValueError('Intervalle : 15 à 3600 secondes.')
            if type(s['imap_port']) is not int or not 1<=s['imap_port']<=65535:raise ValueError('Port IMAP invalide.')
            for k in ['dry_run','print_attachments']:
                if type(s[k]) is not bool:raise ValueError('Valeur booléenne attendue.')
            try:printing.validate_options(s['print_sides'],s['print_color_mode'])
            except printing.PrintError as e:raise ValueError(str(e)) from e
            pattern=s['client_folder_pattern']
            if pattern.count('{name}')!=1 or '/' in pattern or '\\' in pattern or '{' in pattern.replace('{name}',''):raise ValueError('Le nom client doit contenir {name} une fois, sans séparateurs.')
            relative(pattern.replace('{name}','Client'))
            immutable=['archive_root','connector','mail_account','imap_host','imap_port','imap_user']
            if self.store.all('client') and any(s[k]!=self.settings[k] for k in immutable):raise ValueError('Des clients sont déjà suivis. Créez un nouvel espace de données pour changer de racine ou de connexion.')
            if s['connector']=='demo' and not s['dry_run']:raise ValueError('La démonstration utilise une impression simulée.')
            root=Path(s['archive_root']).expanduser()
            if not root.is_absolute():raise ValueError('Choisissez un chemin absolu pour les archives.')
            root.mkdir(parents=True,exist_ok=True);s['archive_root']=str(root.resolve())
            connector=make_connector(s,self.runtime)
            self.store.put('settings','main',s);self.settings=s;self.root=root.resolve();self.connector=connector;return s

    def state(self):
        with self.lock:
            clients=self.store.all('client')
            for c in clients:
                c.setdefault('starred',False)
                c['existing_folders']=self.existing_folders(c)
                c['folders']=self.client_folders(c,c['existing_folders'])
            messages=self.store.all('message')
            for m in messages:
                m['documents']=self._docs(m['id']);m['print_progress']=self.print_progress(m)
                m['print_status']=self.print_status(m,m['print_progress'])
                m['print_jobs']=[p for p in self.store.all('print') if p['message_id']==m['id']]
                m.pop('spool',None);m.pop('sources',None)
            meta=self.store.get('meta','scan') or {}
            return dict(clients=clients,messages=sorted(messages,key=lambda m:m['date'],reverse=True),settings=self.settings,template=self.template(),templates=self.store.all('template'),jobs=self.store.all('job'),events=self.store.all('event')[-40:][::-1],folders=self.folders,printers=self.printers,last_scan=meta.get('date',''),sync_error=meta.get('error',''),stats={'clients':len(clients),'messages':len(messages),'pending':sum(m['classification']=='pending' for m in messages),'errors':sum(m['status']=='error' for m in messages)})
