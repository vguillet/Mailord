"""Loopback-only web application and local API."""
import asyncio
import fcntl
import mimetypes
import secrets
import subprocess
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Body, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .engine import Engine, within
from .store import Store
from . import printing
from .updates import UpdateManager


STATIC=Path(__file__).parent/'static'


def create_app(settings,background=True,*,restart=None,probation=False,health_token=""):
    active=not probation
    thread=None
    activation_lock=threading.Lock()
    runtime=Path(settings['runtime']);runtime.mkdir(parents=True,exist_ok=True)
    lock=open(runtime/'server.lock','a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close();raise RuntimeError('Un service utilise déjà cet espace de données.')
    try:
        store=Store(runtime/'registry.sqlite3');engine=Engine(settings,store,recover=not probation)
        updates=UpdateManager(runtime,Path(__file__).resolve().parents[1],restart=restart)
    except BaseException:
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close();raise
    token=secrets.token_urlsafe(32)
    stop=threading.Event()

    def worker():
        while not stop.is_set():
            try:engine.scan();engine.process()
            except Exception as e:engine.event(engine.error_text(e),'error')
            stop.wait(engine.settings['poll_seconds'])

    def start_workers():
        nonlocal thread
        if background and thread is None:
            thread=threading.Thread(target=worker,daemon=True,name='archive-worker');thread.start()
            updates.start_periodic()

    @asynccontextmanager
    async def lifespan(app):
        if active:start_workers()
        try:yield
        finally:
            stop.set()
            if thread:await asyncio.to_thread(thread.join)
            await asyncio.to_thread(updates.close)
            store.close()
            fcntl.flock(lock,fcntl.LOCK_UN);lock.close()

    app=FastAPI(title='Mailord',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.engine=engine
    app.state.updates=updates
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','[::1]'])

    @app.middleware('http')
    async def local_security(request,call_next):
        private=request.url.path in ('/api/health','/api/activate')
        if private:
            if not health_token or not secrets.compare_digest(request.headers.get('x-supervisor-token',''),health_token):
                return JSONResponse({'detail':'Accès réservé au lanceur.'},403)
        elif not active:
            return JSONResponse({'detail':'Mise à jour en cours. Reconnexion automatique…'},503)
        if not private and request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('origin')
            if origin:
                parsed=urlsplit(origin)
                if parsed.scheme not in ('http','https') or parsed.netloc!=request.headers.get('host'):
                    return JSONResponse({'detail':'Cette action doit venir de l’interface locale.'},403)
            if not secrets.compare_digest(request.headers.get('x-csrf-token',''),token):return JSONResponse({'detail':'Session expirée. Rechargez la page.'},403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; object-src 'none'; frame-ancestors 'self'"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request,e):return JSONResponse({'detail':engine.error_text(e)},400)
    @app.exception_handler(KeyError)
    async def missing(request,e):return JSONResponse({'detail':str(e).strip("'")},404)
    @app.exception_handler(Exception)
    async def failed(request,e):return JSONResponse({'detail':engine.error_text(e) or 'Opération impossible. Consultez le journal.'},503)

    def required(body,key,kind):
        if key not in body or type(body[key]) is not kind:raise ValueError('Champ invalide : '+key)
        return body[key]

    @app.get('/')
    def index():return FileResponse(STATIC/'index.html')
    @app.get('/api/state')
    def state():return {**engine.state(),'csrf_token':token,'updates':updates.state()}
    @app.get('/api/health')
    def health():return {'ready':True,'active':active}
    @app.post('/api/activate')
    def activate():
        nonlocal active
        with activation_lock:
            if not active:
                engine.recover()
                updates._set(status='updated',error='',progress='Mise à jour installée.')
                active=True
                start_workers()
        return {'active':True}
    @app.get('/api/updates')
    def update_state():return updates.state()
    @app.put('/api/updates/config')
    def update_config(body:dict=Body(...)):
        return updates.configure(required(body,'repository',str),required(body,'branch',str))
    @app.post('/api/updates/check')
    def update_check():return updates.check_async()
    @app.post('/api/updates/install')
    def update_install(body:dict=Body(...)):return updates.install_async(required(body,'commit',str))
    @app.get('/api/folders')
    def folders():return {'folders':engine.list_folders()}
    @app.get('/api/client-locations')
    def client_locations(parent_folder:str=''):return engine.client_locations(parent_folder)
    @app.get('/api/printers')
    def printers():
        engine.printers=printing.list_printers();return {'printers':engine.printers}
    @app.post('/api/clients')
    def create(body:dict=Body(...)):
        return engine.create_client(required(body,'name',str),required(body,'mailbox',str) if 'mailbox' in body else '',
                                    required(body,'initial_folders',list) if 'initial_folders' in body else None,
                                    required(body,'parent_folder',str) if 'parent_folder' in body else None,
                                    required(body,'parent_token',str) if 'parent_token' in body else None)
    @app.post('/api/clients/{id}/retry')
    def retry(id:str):return engine.retry_client(id)
    @app.post('/api/clients/{id}/template')
    def apply(id:str):return engine.apply_template(id)
    @app.put('/api/clients/{id}/favorites')
    def favorites(id:str,body:dict=Body(...)):return engine.favorites(id,required(body,'folders',list))
    @app.put('/api/clients/{id}/star')
    def star_client(id:str,body:dict=Body(...)):return engine.star_client(id,required(body,'starred',bool))
    @app.put('/api/template')
    def template(body:dict=Body(...)):
        return engine.save_template(required(body,'folders',list),
                                    required(body,'initial_folders',list) if 'initial_folders' in body else None,
                                    required(body,'email_folder',str) if 'email_folder' in body else None)
    @app.post('/api/sync')
    def sync():
        engine.scan();engine.process()
        if engine.sync_error:raise ValueError(engine.sync_error)
        return {'ok':True}
    @app.post('/api/process')
    def process():engine.process();return {'ok':True}
    @app.post('/api/classify/prepare')
    def prepare_classify(body:dict=Body(...)):
        return engine.prepare_classify(required(body,'message_ids',list),required(body,'destination',str),
                                       required(body,'document_ids',list) if 'document_ids' in body else None)
    @app.post('/api/file-operations/{id}/confirm')
    def confirm_operation(id:str,body:dict=Body(...)):
        return engine.confirm_operation(id,body.get('confirm'))
    @app.post('/api/documents/{id}/undo-filing/prepare')
    def prepare_undo(id:str,body:dict=Body(...)):
        return engine.prepare_undo(id,required(body,'token',str))
    @app.get('/api/documents/{id}/recovery')
    def recovery(id:str):
        return {'versions':engine.recovery_versions(id),'operations':[o for o in engine.store.all('file_operation') if o['status']!='awaiting_confirmation' and any(i['document_id']==id for i in o['items'])]}
    @app.post('/api/documents/{id}/restore/prepare')
    def prepare_restore(id:str,body:dict=Body(...)):
        return engine.prepare_restore(id,required(body,'version_id',str))
    @app.post('/api/documents/{id}/recovery/reveal')
    def reveal_recovery(id:str):
        versions=engine.recovery_versions(id)
        if not versions:raise ValueError('Aucune copie conservée pour ce document.')
        subprocess.run(['/usr/bin/open',str(engine._recovery_root())],check=True,timeout=10)
        return {'ok':True}
    @app.post('/api/classify')
    def classify(body:dict=Body(...)):
        engine.classify(required(body,'message_ids',list),required(body,'destination',str),
                        required(body,'document_ids',list) if 'document_ids' in body else None);return {'ok':True}
    @app.post('/api/print')
    def print_messages(body:dict=Body(...)):
        engine.print_messages(required(body,'message_ids',list));return {'ok':True}
    @app.post('/api/messages/{id}/reprint')
    def reprint(id:str,body:dict=Body(...)):
        if body.get('confirm') is not True:raise ValueError('Confirmez explicitement la nouvelle impression après vérification de la file.')
        engine.print_messages([id],reprint=True);return {'ok':True}
    @app.put('/api/documents/{id}')
    def select(id:str,body:dict=Body(...)):return engine.select_document(id,required(body,'selected',bool))
    @app.post('/api/documents/{id}/undo-filing')
    def undo_filing(id:str,body:dict=Body(...)):return engine.undo_filing(id,required(body,'token',str))
    @app.post('/api/documents/{id}/print')
    def print_document(id:str):return engine.print_document(id)
    @app.post('/api/documents/{id}/reprint')
    def reprint_document(id:str,body:dict=Body(...)):
        if body.get('confirm') is not True:raise ValueError('Confirmez explicitement la nouvelle impression après vérification de la file.')
        return engine.print_document(id,reprint=True)
    def document_path(id):
        d=store.get('document',id)
        if not d:raise KeyError('Document introuvable.')
        p=within(engine.root,d['path'])
        if not p.is_file():raise KeyError('Fichier absent. Lancez le contrôle des archives.')
        return p
    @app.get('/api/documents/{id}/file')
    def file(id:str,download:bool=False):
        p=document_path(id);mime=mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
        inline=mime in ('application/pdf','image/png','image/jpeg','image/gif','image/webp') and not download
        return FileResponse(p,media_type=mime,filename=p.name,content_disposition_type='inline' if inline else 'attachment')
    @app.post('/api/documents/{id}/reveal')
    def reveal(id:str):
        p=document_path(id)
        subprocess.run(['/usr/bin/open','-R',str(p)],check=True,timeout=10);return {'ok':True}
    @app.get('/api/clients/{id}/history')
    def history(id:str):return engine.history(id)
    @app.post('/api/history/associate')
    def associate(body:dict=Body(...)):
        engine.associate(required(body,'message_id',str),required(body,'path',str));return {'ok':True}
    @app.put('/api/settings')
    def settings_put(body:dict=Body(...)):return engine.update_settings(body)
    app.mount('/static',StaticFiles(directory=STATIC),name='static')
    return app
