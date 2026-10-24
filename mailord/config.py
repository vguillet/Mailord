from pathlib import Path

DEFAULT_EMAIL_FOLDER = '02 CORRESPONDANCES'

# Initial model only: saved template versions remain the user's own configuration.
# Parenthetical abbreviations and asterisks in the source are filing guidance,
# not directory names. The jurisdiction branch is edited before provisioning.
DEFAULT_FOLDERS = [
    '00 - À classer',
    '01 CONSULTATIONS',
    '02 CORRESPONDANCES',
    '02 CORRESPONDANCES/Avocat',
    '02 CORRESPONDANCES/Notaire',
    "02 CORRESPONDANCES/Tribunal ou cour d'appel",
    '02 CORRESPONDANCES/Administrations',
    '02 CORRESPONDANCES/Clients',
    '02 CORRESPONDANCES/Huissiers - Commissaires de justice',
    '02 CORRESPONDANCES/Divers',
    '03 MAILS (PDF)',
    '04 PROCÉDURE',
    '04 PROCÉDURE/LO et MED',
    '04 PROCÉDURE/[JURIDICTION + lieu]',
    '04 PROCÉDURE/[JURIDICTION + lieu]/01 CONCLUSIONS',
    '04 PROCÉDURE/[JURIDICTION + lieu]/01 bis CONCLUSIONS ADV',
    '04 PROCÉDURE/[JURIDICTION + lieu]/02 REQUÊTES',
    '04 PROCÉDURE/[JURIDICTION + lieu]/03 ASSIGNATIONS',
    '04 PROCÉDURE/[JURIDICTION + lieu]/04 SOMMATIONS',
    '04 PROCÉDURE/[JURIDICTION + lieu]/05 DOSSIER DE PLAIDOIRIES',
    '04 PROCÉDURE/[JURIDICTION + lieu]/06 BORDEREAUX DE COMMUNICATION DE PIÈCES',
    '04 PROCÉDURE/[JURIDICTION + lieu]/07 CONSTITUTIONS',
    '04 PROCÉDURE/[JURIDICTION + lieu]/08 JUGEMENTS - ORDONNANCES - ARRÊTS',
    '04 PROCÉDURE/[JURIDICTION + lieu]/09 SIGNIFICATIONS À AVOCAT',
    "04 PROCÉDURE/[JURIDICTION + lieu]/10 ACTES D'HUISSIER - CJ",
    '04 PROCÉDURE/[JURIDICTION + lieu]/11 EXPERTISE',
    '04 PROCÉDURE/[JURIDICTION + lieu]/12 NOTAIRE',
    '04 PROCÉDURE/[JURIDICTION + lieu]/13 LETTRES AU JUGE',
    '05 PIÈCES',
    '05 PIÈCES/Pièces client',
    '05 PIÈCES/Pièces adverses',
    '05 PIÈCES/Pièces reçues du client - à trier',
    '06 PROJETS ET VERSIONS DÉFINITIVES',
    '06 PROJETS ET VERSIONS DÉFINITIVES/Projets',
    '06 PROJETS ET VERSIONS DÉFINITIVES/Versions définitives',
    '07 FACTURES',
    '08 NOTES INTERNES',
]


def defaults(runtime: Path):
    return dict(runtime=str(runtime.resolve()), archive_root=str((runtime / 'Archives').resolve()), connector='demo',
                mail_account='', imap_host='imap.orange.fr', imap_port=993, imap_user='',
                imap_password_env='MAILORD_IMAP_PASSWORD', print_policy='manual',
                printer='', dry_run=True, print_sides='printer', print_color_mode='printer', poll_seconds=60, date_source='received', prefix_format='%Y-%m-%d',
                timezone='Europe/Paris', client_folder_pattern='{name}', print_attachments=True)
