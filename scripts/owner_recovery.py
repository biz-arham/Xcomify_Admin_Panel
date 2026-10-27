"""OFFLINE OWNER RECOVERY. Requires filesystem/database access. Stop all servers first.
This is not an HTTP endpoint. It resets only an existing owner, freezes outbound
writes, revokes all workspace sessions and cancels queued work for review.
"""
from pathlib import Path
import sys,getpass
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from sqlalchemy import select,delete
from xcomify.config import Settings
from xcomify.db import Database
from xcomify.models import User,Session,Organization,Store,Job,WriteIntent,OAuthState,RecoveryCode
from xcomify.security import HASHER,password_valid,audit

def main():
    settings=Settings.from_env();dbase=Database(settings.database_url)
    print('Stop every Xcomify server and worker before continuing. This is an offline privileged recovery operation.')
    if input('Type RECOVER OWNER to continue: ').strip()!='RECOVER OWNER':raise SystemExit('Cancelled.')
    email=input('Existing owner email: ').strip().lower()
    password=getpass.getpass('New password (14+ characters): ')
    if password!=getpass.getpass('Repeat new password: '):raise SystemExit('Passwords do not match.')
    password_valid(password)
    with dbase.Session.begin() as db:
        user=db.scalar(select(User).where(User.email==email,User.role=='owner'))
        if not user:raise SystemExit('No matching existing owner. No changes made.')
        user.password_hash=HASHER.hash(password);user.active=True;user.mfa_secret=None;user.pending_mfa=None;user.recovery_codes=[];user.mfa_counter=-1
        db.execute(delete(RecoveryCode).where(RecoveryCode.user_id==user.id))
        org=db.get(Organization,user.org_id);org.emergency_stop=True
        for st in db.scalars(select(Store).where(Store.org_id==org.id)):st.writes_enabled=False;st.writer_contract=False
        for i in db.scalars(select(WriteIntent).where(WriteIntent.org_id==org.id,WriteIntent.state.in_(['queued','validating','submitting','verifying']))):i.state='outcome_unknown';i.error='Owner recovery: remote reconciliation required.'
        for j in db.scalars(select(Job).where(Job.org_id==org.id,Job.state.in_(['pending','running']))):j.state='cancelled';j.error='Owner recovery: explicit review required.'
        ids=list(db.scalars(select(User.id).where(User.org_id==org.id)))
        session_ids=list(db.scalars(select(Session.id).where(Session.user_id.in_(ids))))
        db.execute(delete(OAuthState).where(OAuthState.session_id.in_(session_ids)))
        db.execute(delete(Session).where(Session.user_id.in_(ids)))
        audit(db,user,'owner.offline_recovery',details={'writes_frozen':True,'all_sessions_revoked':True})
    dbase.close();print('Owner reset. Sign in, re-enroll MFA, reconcile source state and explicitly re-enable approved writes.')
if __name__=='__main__':main()
