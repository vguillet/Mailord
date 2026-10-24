"""Generate an opt-in macOS LaunchAgent; never enables it implicitly."""
import argparse
import plistlib
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser(description='Préparer le démarrage automatique Mailord')
    p.add_argument('--data-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path.home()/'Library/LaunchAgents/fr.mailord.local.plist')
    p.add_argument('--port',type=int,default=8765)
    args=p.parse_args();root=Path(__file__).resolve().parents[1];python=root/'.venv/bin/python'
    if not python.exists():p.error('Exécutez d’abord scripts/install-macos.sh.')
    if not 1024<=args.port<=65535:p.error('Port invalide.')
    runtime=args.data_dir.expanduser().resolve();runtime.mkdir(parents=True,exist_ok=True);runtime.chmod(0o700)
    target=args.output.expanduser();target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():p.error('Le fichier existe déjà ; examinez-le avant de le remplacer.')
    value={'Label':'fr.mailord.local','ProgramArguments':[str(python),'-m','mailord','--data-dir',str(runtime),'--port',str(args.port)],'WorkingDirectory':str(root),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,'StandardOutPath':str(runtime/'service.log'),'StandardErrorPath':str(runtime/'service-error.log')}
    with target.open('xb') as f:plistlib.dump(value,f)
    target.chmod(0o600);print(target)


if __name__=='__main__':main()
