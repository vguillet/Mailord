"""Create fictional examples only inside a fresh demo workspace."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import os
from pathlib import Path
from .documents import _pdf_bytes


def seed(engine):
    if engine.settings['connector']!='demo':raise ValueError('La démonstration exige un espace de données dédié.')
    if engine.store.get('meta','demo-seeded'):return
    clients=[engine.create_client(n) for n in ['Camille Moreau','Atelier Beaumont','Sophie Laurent']]
    subjects=[['Documents pour notre rendez-vous','Contrat signé — projet rénovation','Votre facture du mois'],['Devis et calendrier prévisionnel','Compte rendu de notre échange'],['Justificatif de domicile','Confirmation du rendez-vous']]
    for n,c in enumerate(clients):
        for i,subject in enumerate(subjects[n]):
            stamp=datetime.now(timezone.utc)-timedelta(days=(n*2+i+1))
            msg=EmailMessage();msg['From']=f"{c['name']} <client{n+1}@example.test>";msg['To']='Votre cabinet <cabinet@example.test>';msg['Subject']=subject;msg['Message-ID']=f'<demo-{n}-{i}@example.test>';msg['Date']=stamp
            msg.set_content(f"Bonjour,\n\nVous trouverez ci-joint les éléments évoqués lors de notre échange.\nMerci de les ajouter à mon dossier. Je reste à votre disposition pour toute précision.\n\nBien cordialement,\n{c['name']}\n\nCeci est un exemple fictif pour découvrir Auto-secrétaire.")
            if i==0:msg.add_attachment(b'Liste des documents\n- Justificatif\n- Contrat signe\n',maintype='text',subtype='plain',filename='Liste des documents.txt')
            if i==1:msg.add_attachment(_pdf_bytes({'subject':'Document de démonstration','body':'Exemple fictif sans valeur contractuelle.','sender':c['name'],'recipients':'Votre cabinet','date':stamp.isoformat()}),maintype='application',subtype='pdf',filename='Contrat signé.pdf')
            p=Path(engine.settings['runtime'])/'mailboxes'/c['mailbox']/f'{i+1}.eml';p.write_bytes(msg.as_bytes());os.utime(p,(stamp.timestamp(),stamp.timestamp()))
    engine.scan();engine.process()
    ms=engine.state()['messages'];first=next(m for m in ms if m['client_id']==clients[0]['id']);engine.classify([first['id']],'03 MAILS (PDF)')
    engine.store.put('meta','demo-seeded',{'created':datetime.now(timezone.utc).isoformat()})
