import argparse
from pathlib import Path
import sys
import threading
import webbrowser
from .config import defaults


def main():
    parser=argparse.ArgumentParser(description='Auto-secrétaire — service local pour les dossiers clients')
    parser.add_argument('--data-dir',type=Path,help='Registre privé (hors dossier synchronisé)')
    parser.add_argument('--archive-root',type=Path,help='Racine des documents, peut être synchronisée')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--demo',action='store_true',help='Créer des exemples fictifs dans un espace de démonstration')
    parser.add_argument('--open',action='store_true',help='Ouvrir l’interface dans le navigateur')
    args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('Le port doit être compris entre 1024 et 65535.')
    runtime=(args.data_dir or (Path.home()/'Library/Application Support/Auto-secretaire'/('demo' if args.demo else 'data'))).expanduser().resolve()
    settings=defaults(runtime)
    if args.archive_root:settings['archive_root']=str(args.archive_root.expanduser().resolve())
    from .app import create_app
    import uvicorn
    try:app=create_app(settings)
    except (RuntimeError,OSError) as e:parser.exit(1,str(e)+'\n')
    if args.demo:
        from .demo import seed
        try:seed(app.state.engine)
        except ValueError as e:parser.exit(1,str(e)+'\n')
    url=f'http://127.0.0.1:{args.port}'
    print(f'Auto-secrétaire : {url}\nDonnées privées : {runtime}\nArrêt : Ctrl+C',flush=True)
    if args.open:threading.Timer(1.5,lambda:webbrowser.open(url)).start()
    uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning',access_log=False)


if __name__=='__main__':main()
