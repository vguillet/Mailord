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


STATIC=Path(__file__).parent/'static'


def create_app(settings,background=True):
    runtime=Path(settings['runtime']);runtime.mkdir(parents=True,exist_ok=True)
    lock=open(runtime/'server.lock','a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close();raise RuntimeError('Un service utilise déjà cet espace de données.')
    try:
        store=Store(runtime/'registry.sqlite3');engine=Engine(settings,store)
    except BaseException:
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close();raise
    token=secrets.token_urlsafe(32)
    stop=threading.Event()

    def worker():
        while not stop.is_set():
            try:engine.scan();engine.process()
            except Exception as e:engine.event(engine.error_text(e),'error')
            stop.wait(engine.settings['poll_seconds'])

    @asynccontextmanager
    async def lifespan(app):
        thread=None
        if background:
            thread=threading.Thread(target=worker,daemon=True,name='archive-worker');thread.start()
        try:yield
        finally:
            stop.set()
            if thread:await asyncio.to_thread(thread.join)
            store.close()
            fcntl.flock(lock,fcntl.LOCK_UN);lock.close()

    app=FastAPI(title='Auto-secrétaire',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.engine=engine
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','[::1]'])

    @app.middleware('http')
    async def local_security(request,call_next):
        if request.method not in ('GET','HEAD','OPTIONS'):
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
    def state():return {**engine.state(),'csrf_token':token}
    @app.get('/api/folders')
    def folders():return {'folders':engine.list_folders()}
    @app.get('/api/printers')
    def printers():
        engine.printers=printing.list_printers();return {'printers':engine.printers}
    @app.post('/api/clients')
    def create(body:dict=Body(...)):return engine.create_client(required(body,'name',str),body.get('mailbox',''))
    @app.post('/api/clients/{id}/retry')
    def retry(id:str):return engine.retry_client(id)
    @app.post('/api/clients/{id}/template')
    def apply(id:str):return engine.apply_template(id)
    @app.put('/api/clients/{id}/favorites')
    def favorites(id:str,body:dict=Body(...)):return engine.favorites(id,required(body,'folders',list))
    @app.put('/api/template')
    def template(body:dict=Body(...)):return engine.save_template(required(body,'folders',list))
    @app.post('/api/sync')
    def sync():
        engine.scan();engine.process()
        if engine.sync_error:raise ValueError(engine.sync_error)
        return {'ok':True}
    @app.post('/api/process')
    def process():engine.process();return {'ok':True}
    @app.post('/api/classify')
    def classify(body:dict=Body(...)):
        engine.classify(required(body,'message_ids',list),required(body,'destination',str));return {'ok':True}
    @app.post('/api/print')
    def print_messages(body:dict=Body(...)):
        engine.print_messages(required(body,'message_ids',list));return {'ok':True}
    @app.post('/api/messages/{id}/reprint')
    def reprint(id:str,body:dict=Body(...)):
        if body.get('confirm') is not True:raise ValueError('Confirmez explicitement la nouvelle impression après vérification de la file.')
        engine.print_messages([id],reprint=True);return {'ok':True}
    @app.put('/api/documents/{id}')
    def select(id:str,body:dict=Body(...)):return engine.select_document(id,required(body,'selected',bool))
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
