"""Durable database queue and elected persistent worker. No browser dependency."""
import logging, random, secrets, time, json
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .models import *
from .google import GoogleSheets,GoogleError
from .sync import do_sync,execute_intent
from .security import audit,seal
from .finance import current_month

log=logging.getLogger('xcomify.worker')
class Worker:
    def __init__(self,database,settings,adapter_factory=None):
        self.database=database;self.settings=settings;self.owner=secrets.token_hex(24)
        self.adapter_factory=adapter_factory or (lambda c:GoogleSheets(settings,c.credential))
    def lease(self):
        with self.database.Session.begin() as db:
            lease=db.get(Lease,'worker')
            if not lease:
                try:
                    db.add(Lease(key='worker',owner=self.owner,expires_at=now()+180));db.flush();return True
                except IntegrityError:return False
            result=db.execute(update(Lease).where(Lease.key=='worker',((Lease.owner==self.owner)|(Lease.expires_at<now()))).values(owner=self.owner,expires_at=now()+180))
            return result.rowcount==1
    def lease_valid(self):
        with self.database.Session() as db:
            lease=db.get(Lease,'worker');return bool(lease and lease.owner==self.owner and lease.expires_at>now())
    def tick(self):
        if not self.lease():return
        with self.database.Session.begin() as db:
            # Unknown remote outcomes are never blindly replayed after a crash.
            for j in db.scalars(select(Job).where(Job.state=='running',Job.started_at<now()-240)):
                if j.kind=='write':
                    i=db.get(WriteIntent,j.payload.get('intent_id'))
                    if i and i.state in {'submitting','verifying'}:
                        i.state='outcome_unknown';i.error='Worker interrupted after submission; reconcile remote state.'
                        j.state='outcome_unknown';j.error=i.error
                    elif i and i.state=='confirmed':j.state='succeeded'
                    else:
                        j.state='failed'
                        if i and i.state not in {'cancelled','confirmed'}:i.state='proposed';i.approver_id=None;i.error='Interrupted before confirmed submission; fresh approval required.'
                else:j.state='pending';j.available_at=now()+10
            for st in db.scalars(select(Store).where(Store.source=='google',Store.status=='active',Store.next_sync<=now())):
                c=db.get(Connection,st.connection_id) if st.connection_id else None
                if not c or not c.active:continue
                exists=db.scalar(select(Job.id).where(Job.store_id==st.id,Job.kind=='sync',Job.state.in_(['pending','running'])))
                if not exists:db.add(Job(org_id=st.org_id,store_id=st.id,kind='sync'))
                st.next_sync=now()+st.poll_seconds+random.randint(0,15)
            job=db.scalar(select(Job).where(Job.state=='pending',Job.available_at<=now()).order_by(Job.available_at,Job.created_at).limit(1))
            if not job:return
            changed=db.execute(update(Job).where(Job.id==job.id,Job.state=='pending').values(state='running',started_at=now(),attempts=job.attempts+1))
            if changed.rowcount!=1:return
            job_id=job.id
        self.run(job_id)
    def run(self,job_id):
        adapter=None
        with self.database.Session() as db:
            job=db.get(Job,job_id);st=db.get(Store,job.store_id)
            try:
                if not st or st.status!='active':raise ValueError('Store paused, archived or unavailable.')
                c=db.get(Connection,st.connection_id) if st.connection_id else None
                if not c or not c.active:raise ValueError('Google connection is unavailable.')
                adapter=self.adapter_factory(c)
                if job.kind=='sync':
                    snapshot=adapter.snapshot(st.spreadsheet_id,st.sheet_id,st.max_rows)
                    if not self.lease_valid():raise ValueError('Worker lease expired during read; retry after reconciliation.')
                    result=do_sync(db,st,snapshot)
                    job.result=result;job.state='succeeded'
                elif job.kind=='write':
                    intent=db.get(WriteIntent,job.payload.get('intent_id'))
                    if not intent or intent.state!='queued':
                        job.state='cancelled';job.error='Intent no longer queued.'
                    else:
                        result=execute_intent(db,self.settings,intent,adapter,self.lease_valid)
                        job.result=result;job.state='succeeded' if result['state']=='confirmed' else result['state']
                else:raise ValueError('Unknown job type.')
                if isinstance(adapter,GoogleSheets) and c.active:
                    db.execute(update(Connection).where(Connection.id==c.id,Connection.active==True).values(credential=seal(self.settings,json.dumps(adapter.tokens))))
                job.finished_at=now();db.commit()
            except GoogleError as exc:
                db.rollback();job=db.get(Job,job_id);st=db.get(Store,job.store_id)
                if job.kind=='sync' and job.attempts<5 and (exc.status in {0,429} or exc.status>=500):
                    job.state='pending';job.available_at=now()+min(900,2**job.attempts*10)+random.randint(1,10)
                else:job.state='failed';job.finished_at=now()
                job.error=str(exc)
                if st:st.sync_error=str(exc)
                if job.kind=='write':
                    intent=db.get(WriteIntent,job.payload.get('intent_id'))
                    if intent and intent.state not in {'confirmed','cancelled'}:
                        intent.state='outcome_unknown' if intent.state in {'submitting','verifying'} else 'failed';intent.error=str(exc)
                db.commit()
            except Exception as exc:
                db.rollback();job=db.get(Job,job_id);st=db.get(Store,job.store_id)
                message=str(exc) if isinstance(exc,ValueError) else 'Worker operation failed. Review server diagnostics without replaying writes.'
                job.state='failed';job.error=message;job.finished_at=now()
                if st:st.sync_error=message;st.writes_enabled=False
                if job.kind=='write':
                    intent=db.get(WriteIntent,job.payload.get('intent_id'))
                    if intent and intent.state not in {'confirmed','cancelled'}:
                        intent.state='outcome_unknown' if intent.state in {'submitting','verifying'} else 'failed';intent.error=message
                if st:audit(db,None,'worker.failed',st.id,job.id,{'kind':job.kind},org_id=st.org_id)
                db.commit()
                if not isinstance(exc,ValueError):log.exception('Worker failure job=%s',job_id)
            finally:
                if isinstance(adapter,GoogleSheets):adapter.http.close()

def main():
    from .config import Settings
    from .db import Database
    s=Settings.from_env();db=Database(s.database_url);db.migrate();w=Worker(db,s)
    print('Xcomify durable worker started. Keep this server process running for background sync.')
    while True:
        try:w.tick()
        except KeyboardInterrupt:break
        except Exception:log.exception('Worker loop failed')
        time.sleep(2)
if __name__=='__main__':main()
