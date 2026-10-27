"""Encrypted local backups and explicit offline read-only restoration."""
from pathlib import Path
from datetime import datetime,timezone
import io,json,os,secrets,sqlite3,zipfile,hashlib
from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url
from .models import now

def create_backup(settings):
    if not settings.database_url.startswith('sqlite'):raise ValueError('Use the documented PostgreSQL backup/PITR runbook.')
    from .db import Database
    from .models import System
    directory=settings.data_dir/'backups';directory.mkdir(mode=0o700,exist_ok=True)
    keyfile=settings.data_dir/'backup-recovery.key'
    if not keyfile.exists():
        fd=os.open(keyfile,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as f:f.write(Fernet.generate_key())
    database=Path(make_url(settings.database_url).database)
    temp=directory/('snapshot-'+secrets.token_hex(6)+'.db')
    try:
        with sqlite3.connect(str(database)) as src,sqlite3.connect(str(temp)) as dst:src.backup(dst)
        payload=temp.read_bytes();blob=io.BytesIO()
        manifest={'format':1,'created_at':now(),'database_sha256':hashlib.sha256(payload).hexdigest(),'encryption_key':settings.encryption_key}
        with zipfile.ZipFile(blob,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('database.sqlite',payload);z.writestr('manifest.json',json.dumps(manifest))
        encrypted=Fernet(keyfile.read_bytes().strip()).encrypt(blob.getvalue())
        path=directory/('xcomify-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3)+'.xcbak')
        path.write_bytes(encrypted);os.chmod(path,0o600)
        db=Database(settings.database_url)
        with db.Session.begin() as session:
            state=session.get(System,'last_backup')
            value={'at':now(),'filename':path.name,'encrypted':True,'restore_tested':False}
            if state:state.value=value
            else:session.add(System(key='last_backup',value=value))
        db.close();return path
    finally:
        if temp.exists():temp.unlink()

def restore_backup(backup_path,key_path,destination):
    """Only restores into a NEW directory. Never overwrites a running workspace."""
    dest=Path(destination)
    if dest.exists() and any(dest.iterdir()):raise ValueError('Restore destination must be empty; stop the app and use a new directory.')
    content=Fernet(Path(key_path).read_bytes().strip()).decrypt(Path(backup_path).read_bytes())
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        if set(z.namelist())!={'database.sqlite','manifest.json'}:raise ValueError('Unexpected backup contents.')
        payload=z.read('database.sqlite');manifest=json.loads(z.read('manifest.json'))
    if manifest.get('format')!=1 or hashlib.sha256(payload).hexdigest()!=manifest['database_sha256']:raise ValueError('Invalid backup integrity.')
    dest.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=dest/'xcomify.db';path.write_bytes(payload);os.chmod(path,0o600)
    with sqlite3.connect(path) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Restored database failed integrity check.')
        db.execute('UPDATE organizations SET emergency_stop=1')
        db.execute('UPDATE stores SET writes_enabled=0,writer_contract=0,last_sync=NULL,sync_error=?',('Restored workspace: read-only reconciliation and new write approval required.',))
        db.execute("UPDATE write_intents SET state='outcome_unknown',error='Restored backup; remote outcome must be reconciled' WHERE state IN ('queued','validating','submitting','verifying')")
        db.execute("UPDATE jobs SET state='cancelled',error='Restored backup: queued work must be explicitly resubmitted' WHERE state IN ('pending','running')")
        db.execute('DELETE FROM sessions');db.execute('DELETE FROM oauth_states');db.execute('DELETE FROM leases')
    key=dest/'xcomify_encryption_key';key.write_text(manifest['encryption_key']);os.chmod(key,0o600)
    boot=dest/'xcomify_bootstrap_token';boot.write_text(secrets.token_urlsafe(32));os.chmod(boot,0o600)
    return path
