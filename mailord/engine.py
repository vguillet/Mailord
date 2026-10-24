"""Durable, serial orchestration. Files stay ordinary Finder documents."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import threading
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .config import DEFAULT_FOLDERS, DEFAULT_EMAIL_FOLDER
from .connectors import make_connector
from . import documents, printing, file_safety


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
        self.root=Path(self.settings['archive_root']).expanduser().resolve()
        if not self.store.all('client') and not self.store.get('meta','archive_identity'):self.root.mkdir(parents=True,exist_ok=True)
        if not self.store.get('meta','archive_identity') and self.root.is_dir():
            self.store.put('meta','archive_identity',{'identity':file_safety.identity(self.root)})
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

    def _client_overlap(self,path,contains=False,exclude=None):
        def parts(p):return tuple(unicodedata.normalize('NFC',x).casefold() for x in Path(p).parts)
        target=parts(path)
        for c in self.store.all('client'):
            if c['id']==exclude:continue
            existing=parts(c['folder'])
            if target[:len(existing)]==existing or (contains and existing[:len(target)]==target):return c
        return None

    def _client_parent(self,parent_folder='',parent_token=None):
        if not isinstance(parent_folder,str):raise ValueError('Emplacement du client invalide.')
        if self.root.is_symlink() or not self.root.is_dir():raise ValueError('La racine Mailord est indisponible. Vérifiez son emplacement.')
        path=self.root if parent_folder=='' else within(self.root,self.root/relative(parent_folder))
        if any(p.startswith('.') for p in Path(parent_folder).parts):raise ValueError('Choisissez un dossier visible dans la racine Mailord.')
        if self.runtime.is_relative_to(self.root) and path.is_relative_to(self.runtime):raise ValueError('L’espace technique de Mailord ne peut pas accueillir de client.')
        if self._client_overlap(path):raise ValueError('Ce dossier appartient déjà à un client. Choisissez un dossier de regroupement ou la racine.')
        if not path.is_dir():raise ValueError('Le dossier choisi est introuvable ou inaccessible. Actualisez les emplacements.')
        stat=path.stat();token=f'{stat.st_dev}:{stat.st_ino}'
        if parent_token is not None and parent_token!=token:raise ValueError('Le dossier choisi a changé. Actualisez les emplacements et choisissez-le à nouveau.')
        return path,token

    def client_locations(self,parent_folder=''):
        """Browse one existing level without creating folders or following links."""
        with self.lock:
            parent,token=self._client_parent(parent_folder)
            folders=[]
            try:
                for p in sorted(parent.iterdir(),key=lambda x:x.name.casefold()):
                    if p.name.startswith('.') or p.is_symlink() or not p.is_dir():continue
                    try:relative(p.name);within(self.root,p)
                    except ValueError:continue
                    if self.runtime.is_relative_to(self.root) and p.is_relative_to(self.runtime):continue
                    owner=self._client_overlap(p)
                    folders.append({'name':p.name,'path':p.relative_to(self.root).as_posix(),
                                    'disabled':bool(owner),'reason':'Dossier client déjà associé' if owner else ''})
            except OSError as e:raise ValueError('Impossible de lire ce dossier. Vérifiez son accès puis actualisez.') from e
            return {'archive_root':str(self.root),'parent_folder':parent_folder,'parent_token':token,'folders':folders}

    def create_client(self,name,mailbox='',initial_folders=None,parent_folder=None,parent_token=None):
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
                    if parent_folder is not None:
                        parent,_=self._client_parent(parent_folder,parent_token)
                        if parent!=Path(c['folder']).parent:raise ValueError('Ce client existe déjà à un autre emplacement. Sa création ne peut pas le déplacer.')
                    c['initial_folders']=list(dict.fromkeys(c.get('initial_folders',[])+selected))
                    self.store.put('client',c['id'],c)
                    return self.retry_client(c['id'])
            if initial_folders is None:selected=self.template()['initial_folders']
            folder_name=self.settings.get('client_folder_pattern','{name}').replace('{name}',name);relative(folder_name)
            if '/' in folder_name:raise ValueError('Le modèle de nom client ne doit pas créer de chemin imbriqué.')
            parent,token=self._client_parent('' if parent_folder is None else parent_folder,parent_token)
            folder=within(self.root,parent/folder_name)
            if self._client_overlap(folder,contains=True):raise ValueError('Ce dossier est déjà associé à un client ou contient un client. Choisissez un autre nom.')
            if folder.exists() and not folder.is_dir():raise ValueError('Le chemin du client est occupé par un fichier.')
            mailbox=mailbox.strip() or name
            if any(c['mailbox']==mailbox for c in self.store.all('client')):raise ValueError('Cette boîte est déjà associée à un autre client.')
            c={'name':name,'mailbox':mailbox,'folder':str(folder),'parent_token':token,'status':'provisioning','error':'','template_version':self.template()['version'],'folders':self.template()['folders'],'initial_folders':selected,'favorites':[],'initialized':False}
            id=uid();self.store.put('client',id,c);return self.retry_client(id)

    def retry_client(self,id):
        with self.lock:
            c=self.client(id)
            try:
                root=within(self.root,c['folder'])
                self._check_client_root(c)
                parent_folder='' if root.parent==self.root else root.parent.relative_to(self.root).as_posix()
                _,token=self._client_parent(parent_folder,c.get('parent_token'))
                if root.exists() and not root.is_dir():raise ValueError('Le chemin du client est occupé par un fichier.')
                self.connector.create_folder(c['mailbox'])
                self._client_parent(parent_folder,token)
                root=within(self.root,c['folder'])
                for p in c.get('initial_folders',[]):
                    within(root,root/relative(p)).mkdir(parents=True,exist_ok=True)
                if root.is_dir():c['folder_identity']=file_safety.identity(root)
                c.update(status='ready',error='')
            except Exception as e:c.update(status='error',error=self.error_text(e))
            self.store.put('client',id,c);return self.store.get('client',id)

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
                        spool=self.runtime/'spool'/(identity+'.eml')
                        if os.path.lexists(spool):
                            if spool.is_symlink() or not spool.is_file() or digest(spool)!=identity:raise ValueError('Copie originale du mail différente ou incomplète : aucun remplacement automatique.')
                        else:
                            with spool.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
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

    def _publish(self,source,target):
        self._assert_root()
        file_safety.publish(source,within(self.root,target),self.root)

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
                    self._assert_root()
                    self._check_client_root(self.client(m['client_id']))
                    ds=self._docs(m['id'])
                    for d in ds:
                        if d.get('file_error') or d.get('move_to') or not self._healthy(d):
                            d['file_error']=d.get('file_error') or 'Fichier absent ou modifié. Aucun remplacement automatique ; consultez Récupération.'
                            self.store.put('document',d['id'],d)
                            raise ValueError(d['file_error'])
                        if not any(v['document_id']==d['id'] and v['status']=='verified' and v['sha256']==d['sha256'] for v in self.store.all('file_version')):
                            self._save_version(d,d['path'],'Première protection')
                    if m['status']!='ready' or not ds or not all(self._healthy(d) for d in ds):
                        self.store.put('job',m['id'],{'message_id':m['id'],'status':'running','error':''})
                        c=self.client(m['client_id']);root=Path(c['folder'])
                        stage=self.runtime/'staging'/uid();stage.mkdir()
                        exports=documents.export_message(Path(m['spool']).read_bytes(),stage,received_at=m['received_at'],date_source=self.settings['date_source'],prefix_format=self.settings['prefix_format'],identity=m['id'])
                        m['expected_documents']=len(exports);self.store.put('message',m['id'],m)
                        for index,x in enumerate(exports):
                            did=m['id']+f'-{index}';d=self.store.get('document',did)
                            if d and self._healthy(d):continue
                            if d:raise ValueError('Fichier suivi absent ou modifié : récupération explicite requise.')
                            else:
                                destination='00 - À classer'
                                dest=within(root,root/relative(destination))
                                target=self._target(dest,Path(x['path']).name,did,x['sha256'])
                                d={**x,'message_id':m['id'],'path':str(target),'name':target.name,'destination':destination,
                                   'classification':'pending',
                                   'selected':x['kind']=='email' or (self.settings.get('print_attachments',True) and x['printable'] and not x.get('inline',False))}
                                self.store.put('document',did,d)
                                d['id']=did
                            self._save_version(d,x['path'],'Export initial')
                            self._publish(x['path'],target);d.update(path=str(target),name=target.name,sha256=digest(target));self.store.put('document',did,d)
                        c['folder_identity']=file_safety.identity(root);self.store.put('client',c['id'],c)
                        m.update(status='ready',error='');self.store.put('message',m['id'],m)
                        self.store.put('job',m['id'],{'message_id':m['id'],'status':'done','error':''})
                    self._refresh_classification(m['id'])
                except Exception as e:
                    m.update(status='error',error=self.error_text(e));self.store.put('message',m['id'],m)
                    self.store.put('job',m['id'],{'message_id':m['id'],'status':'error','error':m['error']})

            for current in self.store.all('message'):
                policy=self.settings['print_policy']
                eligible=policy=='after_export' and current.get('classification_auto_print',True)
                if eligible and current['status']=='ready' and not current['historical']:
                    try:self.print_messages([current['id']],retry_failed=False)
                    except Exception as e:self.event(self.error_text(e),'error')

    def _check_client_root(self,c):
        if c.get('folder_identity') and file_safety.identity(c['folder'])!=c['folder_identity']:
            raise ValueError('Le dossier client a été remplacé. Aucun fichier ne sera créé ici.')
        if not Path(c['folder']).exists() and (c.get('folder_identity') or any(m['client_id']==c['id'] and self._docs(m['id']) for m in self.store.all('message'))):
            raise ValueError('Le dossier client manque. Aucun dossier ne sera recréé automatiquement.')

    def _assert_root(self):
        expected=self.store.get('meta','archive_identity')
        if not expected or file_safety.identity(self.root)!=expected['identity']:
            raise ValueError('La racine des archives manque ou a été remplacée. Aucun dossier ne sera recréé automatiquement.')

    def _recovery_root(self):
        self._assert_root()
        recovery=self.runtime/'recovery'
        if recovery.is_relative_to(self.root):
            raise ValueError('L’espace de récupération doit être situé hors du dossier des archives synchronisées.')
        with file_safety.directory(recovery,True,self.runtime):pass
        return recovery

    def _revision(self,d):
        return {k:d.get(k) for k in ('path','sha256','destination','classification','undo_filing','file_revision','move_to')}

    def _save_version(self,d,source,reason):
        recovery=self._recovery_root();version_id=uid();path=recovery/version_id/'snapshot'
        original=file_safety.fingerprint(source)
        version={'document_id':d['id'],'path':str(path),'source_path':str(source),'name':d['name'],
                 'created_at':now(),'reason':reason,'sha256':original['sha256'],'status':'copying'}
        self.store.put('file_version',version_id,version)
        copied=file_safety.copy_verified(source,path,recovery,original)
        version.update(status='verified',fingerprint=copied)
        self.store.put('file_version',version_id,version)
        return self.store.get('file_version',version_id)

    def recovery_versions(self,id):
        if not self.store.get('document',id):raise KeyError('Document introuvable.')
        result=[]
        for v in self.store.all('file_version'):
            if v['document_id']!=id:continue
            v['available']=False
            try:
                p=within(self.runtime/'recovery',v['path'])
                if v['status']=='verified':v['available']=file_safety.fingerprint(p)==v['fingerprint']
            except (OSError,ValueError):pass
            result.append(v)
        return result[::-1]

    def _record_retained(self,op):
        for item in op['items']:
            if not item.get('retained'):continue
            vid=op['id']+'-'+item['document_id']+'-original'
            if self.store.get('file_version',vid):continue
            try:
                p=within(self.runtime/'recovery',item['retained']);fp=file_safety.fingerprint(p)
                self.store.put('file_version',vid,{'document_id':item['document_id'],'path':str(p),'source_path':item['source'],'name':item['name'],'created_at':now(),'reason':'Original conservé après déplacement','sha256':fp['sha256'],'fingerprint':fp,'status':'verified'})
            except (OSError,ValueError):pass

    def _recover_moves(self):
        # An interrupted transfer is evidence to inspect, never permission to unlink.
        for op in self.store.all('file_operation'):
            self._record_retained(op)
            if op['status']=='running':
                op.update(status='interrupted',error='Opération interrompue. Les copies sont conservées ; consultez Récupération.')
                self.store.put('file_operation',op['id'],op)
                for item in op['items']:
                    d=self.store.get('document',item['document_id'])
                    d['file_error']=op['error'];self.store.put('document',d['id'],d)
        for d in self.store.all('document'):
            if d.get('move_to'):
                if not any(v['document_id']==d['id'] and v['status']=='verified' for v in self.store.all('file_version')):
                    try:self._save_version(d,within(self.root,d['path']),'Avant revue de l’ancien déplacement')
                    except (OSError,ValueError):pass
                d['file_error']='Ancien déplacement incomplet : aucune reprise automatique. Consultez Récupération et vérifiez les deux emplacements.'
                self.store.put('document',d['id'],d)

    def _make_plan(self,action,items):
        self._assert_root();recovery=self.runtime/'recovery'
        if recovery.is_relative_to(self.root):raise ValueError('La récupération doit être hors du dossier des archives.')
        file_safety.require_local(self.runtime)
        runtime_identity=file_safety.identity(self.runtime)
        for item in items:
            source=Path(item['source']);target=Path(item['target'])
            file_safety.require_local(source.parent)
            item['source_fingerprint']=file_safety.fingerprint(source)
            item['anchors']=file_safety.anchors(self.root,target.parent)
            item['runtime_identity']=runtime_identity
            if action!='restore' and item['source_fingerprint']['device']!=runtime_identity[0]:
                raise ValueError('Déplacement entre volumes refusé : conservez les archives et la récupération sur le même volume.')
            if target!=source:
                ancestor=target.parent
                while not ancestor.exists():ancestor=ancestor.parent
                file_safety.require_local(ancestor)
                if file_safety.identity(ancestor)[0]!=runtime_identity[0]:raise ValueError('Destination sur un autre volume : déplacement protégé indisponible.')
            item['revision']=self._revision(self.store.get('document',item['document_id']))
        op={'action':action,'items':items,'status':'awaiting_confirmation','created_at':now(),'expires_at':time.time()+600,'error':''}
        id=uid();self.store.put('file_operation',id,op);return self.store.get('file_operation',id)

    def prepare_classify(self,ids,destination,document_ids=None):
        with self.lock:
            destination=relative(destination);ms=self._messages(ids)
            if len({m['client_id'] for m in ms})!=1:raise ValueError('Sélectionnez des messages du même client.')
            if any(m['status']!='ready' for m in ms):raise ValueError('Vérifiez les documents avant le classement.')
            root=Path(self.client(ms[0]['client_id'])['folder']);dest=within(root,root/destination)
            available={d['id']:d for m in ms for d in self._docs(m['id'])}
            if document_ids is not None and (not isinstance(document_ids,list) or any(not isinstance(i,str) or i not in available for i in document_ids)):
                raise ValueError('Sélectionnez uniquement les documents des mails choisis.')
            ds=[available[i] for i in dict.fromkeys(document_ids if document_ids is not None else available)]
            if not ds:raise ValueError('Aucun document à classer.')
            if any(d.get('move_to') or d.get('file_error') or not self._healthy(d) for d in ds):raise ValueError('Un fichier manque, a changé ou nécessite une récupération. Vérifiez-le avant classement.')
            for m in ms:self._prepare_filing(m)
            items=[];reserved=set()
            for d in ds:
                d=self.store.get('document',d['id']);src=within(root,d['path'])
                target=src if src.parent==dest else self._target(dest,src.name,d['id'],d['sha256'],reserved)
                reserved.add(str(target).casefold())
                items.append(dict(document_id=d['id'],name=d['name'],source=str(src),target=str(target),destination=destination,classification='classified'))
            return self._make_plan('classify',items)

    def prepare_undo(self,id,token):
        with self.lock:
            d=self.store.get('document',id)
            if not d:raise KeyError('Document introuvable.')
            undo=d.get('undo_filing')
            if not undo or not token or undo['token']!=token:raise ValueError('Ce classement ne peut plus être annulé. Actualisez la page.')
            if d.get('move_to') or d.get('file_error') or d['path']!=undo['target_path'] or not self._healthy(d):raise ValueError('Le fichier manque ou a changé. Consultez Récupération.')
            root=Path(self.client(self.store.get('message',d['message_id'])['client_id'])['folder'])
            target=within(root,undo['path']);src=within(root,d['path'])
            if target!=src and os.path.lexists(target):raise ValueError('L’ancien emplacement est occupé. Aucun remplacement autorisé.')
            return self._make_plan('undo',[dict(document_id=id,name=d['name'],source=str(src),target=str(target),destination=undo['destination'],classification=undo['classification'],undo_token=token)])

    def prepare_restore(self,id,version_id):
        with self.lock:
            d=self.store.get('document',id)
            if not d:raise KeyError('Document introuvable.')
            version=next((v for v in self.recovery_versions(id) if v['id']==version_id and v['available']),None)
            if not version:raise ValueError('Cette copie est absente ou modifiée. Elle ne peut pas être restaurée.')
            root=Path(self.client(self.store.get('message',d['message_id'])['client_id'])['folder'])
            # Do not recreate a folder which Finder removed. Use the existing client root.
            with file_safety.directory(root):pass
            name=Path(d['name']);name=name.stem+' - récupéré '+uid()[:8]+name.suffix
            target=self._target(root,name,id,version['sha256'])
            return self._make_plan('restore',[dict(document_id=id,name=d['name'],source=version['path'],target=str(target),destination='.',classification='pending',version_id=version_id)])

    def classify(self,ids,destination,document_ids=None):
        raise ValueError('Une confirmation du déplacement est obligatoire. Préparez puis confirmez l’opération.')

    def undo_filing(self,id,token):
        raise ValueError('Une confirmation de l’annulation est obligatoire. Préparez puis confirmez l’opération.')

    def confirm_operation(self,id,confirmed=False):
        with self.lock:
            if confirmed is not True:raise ValueError('Une confirmation explicite est obligatoire.')
            op=self.store.get('file_operation',id)
            if not op:raise ValueError('Confirmation inconnue.')
            if op['status']=='completed':return op
            if op['status']!='awaiting_confirmation':raise ValueError('Cette tentative est terminée ou interrompue. Vérifiez les fichiers puis préparez une nouvelle opération.')
            if time.time()>op['expires_at']:raise ValueError('Confirmation expirée. Choisissez à nouveau la destination.')
            self._assert_root()
            # Validate the entire batch before any document effect.
            for item in op['items']:
                d=self.store.get('document',item['document_id'])
                if self._revision(d)!=item['revision']:raise ValueError('Le document a changé depuis la préparation. Actualisez la page.')
                file_safety.check_anchors(item['anchors'])
                if file_safety.identity(self.runtime)!=item['runtime_identity']:raise ValueError('L’espace de récupération a changé.')
                if file_safety.fingerprint(item['source'])!=item['source_fingerprint']:raise ValueError('La source a changé depuis la préparation.')
                target=Path(item['target'])
                if str(target)!=item['source'] and target.parent.exists():
                    with file_safety.directory(target.parent) as parent:file_safety.require_free(parent,target.name)
            op['id']=id
            op.update(status='running',confirmed_at=now());self.store.put('file_operation',id,op)
            try:
                for item in op['items']:
                    d=self.store.get('document',item['document_id']);src=Path(item['source']);dst=Path(item['target'])
                    if op['action']!='restore':
                        version=self._save_version(d,src,'Avant '+('annulation' if op['action']=='undo' else 'classement'))
                        item['version_id']=version['id'];item['snapshot']=version['path']
                    else:version=self.store.get('file_version',item['version_id'])
                    item['phase']='snapshot_verified';self.store.put('file_operation',id,op)
                    file_safety.check_anchors(item['anchors'])
                    if src!=dst:
                        item['temporary']=str(dst.parent/('.mailord-'+uid()+'.tmp'))
                        item['retained']=str(Path(version['path']).parent/('original-'+uid())) if op['action']!='restore' else ''
                        item['phase']='publishing';self.store.put('file_operation',id,op)
                        final=file_safety.publish(version['path'],dst,self.root,version['fingerprint'],item['temporary'])
                        item['published_fingerprint']=final;item['phase']='destination_verified';self.store.put('file_operation',id,op)
                        if op['action']!='restore':
                            file_safety.check_anchors(item['anchors'])
                            if file_safety.fingerprint(dst)!=final:raise ValueError('La destination a changé. Original conservé.')
                            item['phase']='retiring';self.store.put('file_operation',id,op)
                            file_safety.retire(src,item['retained'],item['source_fingerprint'])
                            item['phase']='source_retained';self.store.put('file_operation',id,op)
                        if file_safety.fingerprint(dst)!=final:raise ValueError('Destination modifiée. Consultez les copies de récupération.')
                    else:final=file_safety.fingerprint(dst)
                    if op['action']=='classify':
                        d['undo_filing']={'token':uid(),'path':d['path'],'destination':d.get('destination','00 - À classer'),'classification':d.get('classification','pending'),'target_path':str(dst)}
                    else:d.pop('undo_filing',None)
                    d.update(path=str(dst),name=dst.name,sha256=final['sha256'],destination=item['destination'],classification=item['classification'],file_revision=uid())
                    d.pop('file_error',None);d.pop('move_to',None);d.pop('move_destination',None);d.pop('move_classification',None)
                    item['phase']='committed'
                    with self.store.transaction():
                        self.store.put('document',d['id'],d)
                        m=self.store.get('message',d['message_id']);m['classification_auto_print']=False
                        if len(self._docs(m['id']))>=m.get('expected_documents',0) and all(self._healthy(x) and not x.get('file_error') for x in self._docs(m['id'])):m.update(status='ready',error='')
                        self.store.put('message',m['id'],m);self.store.put('file_operation',id,op)
                    self._refresh_classification(m['id'])
                self._record_retained(op)
                op.update(status='completed',completed_at=now());self.store.put('file_operation',id,op)
            except Exception as e:
                self._record_retained(op)
                op.update(status='conflict',error=self.error_text(e));self.store.put('file_operation',id,op)
                for item in op['items']:
                    if item.get('phase')=='committed':continue
                    d=self.store.get('document',item['document_id']);d['file_error']='Opération suspendue : '+op['error']+' Consultez Récupération.';self.store.put('document',d['id'],d)
                raise ValueError('Opération suspendue. Aucun écrasement ni suppression. '+op['error']) from e
            return self.store.get('file_operation',id)

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
            self._save_version({**d,'name':p.name},p,'PDF associé explicitement')
            d.pop('file_error',None)
            d.update(path=str(p),name=p.name,file_revision=uid(),sha256=digest(p),destination=str(p.parent.relative_to(Path(c['folder']))),classification='classified');self.store.put('document',d['id'],d)
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
            self.store.put('settings','main',s);self.settings=s;self.root=root.resolve();self.store.put('meta','archive_identity',{'identity':file_safety.identity(self.root)});self.connector=connector;return s

    def state(self):
        with self.lock:
            clients=self.store.all('client')
            for c in clients:
                c.setdefault('starred',False)
                c['existing_folders']=self.existing_folders(c)
                c['folders']=self.client_folders(c,c['existing_folders'])
            messages=self.store.all('message')
            for m in messages:
                m['documents']=self._docs(m['id'])
                for d in m['documents']:d['recovery_count']=sum(v['document_id']==d['id'] and v['status']=='verified' for v in self.store.all('file_version'))
                m['print_progress']=self.print_progress(m)
                m['print_status']=self.print_status(m,m['print_progress'])
                m['print_jobs']=[p for p in self.store.all('print') if p['message_id']==m['id']]
                m.pop('spool',None);m.pop('sources',None)
            meta=self.store.get('meta','scan') or {}
            return dict(clients=clients,messages=sorted(messages,key=lambda m:m['date'],reverse=True),settings=self.settings,template=self.template(),templates=self.store.all('template'),jobs=self.store.all('job'),events=self.store.all('event')[-40:][::-1],folders=self.folders,printers=self.printers,last_scan=meta.get('date',''),sync_error=meta.get('error',''),stats={'clients':len(clients),'messages':len(messages),'pending':sum(m['classification']=='pending' for m in messages),'errors':sum(m['status']=='error' for m in messages)})
