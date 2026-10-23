from pathlib import Path

DEFAULT_FOLDERS = ['00 - À classer', '01 - Administratif', '02 - Correspondance', '03 - Documents', '04 - Facturation']


def defaults(runtime: Path):
    return dict(runtime=str(runtime.resolve()), archive_root=str((runtime / 'Archives').resolve()), connector='demo',
                mail_account='', imap_host='imap.orange.fr', imap_port=993, imap_user='',
                imap_password_env='AUTOSECRETAIRE_IMAP_PASSWORD', print_policy='after_classify',
                printer='', dry_run=True, poll_seconds=60, date_source='received', prefix_format='%Y-%m-%d',
                timezone='Europe/Paris', client_folder_pattern='{name}', print_attachments=True)
