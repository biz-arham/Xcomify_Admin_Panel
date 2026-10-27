"""Deterministic adapter tests. These do not claim live Google validation."""
import copy,uuid,json,time
from decimal import Decimal
import pytest,httpx
from sqlalchemy import select
from xcomify.models import *
from xcomify.google import Cell,Snapshot,GoogleSheets,GoogleError,writable
from xcomify.security import seal
from xcomify.sync import do_sync,mapped_records,execute_intent,parse_date
from xcomify.finance import summary
from xcomify.worker import Worker
from .conftest import create_store,create_order
from .test_application import create_employee

FIELDS=['ebay_id','sold_on','earnings','cost','postcode','tracking']
HEADERS=['eBay Order','Sold','Net earnings','Purchase cost','Postcode','Tracking']
def snapshot(rows=None):
    data=rows if rows is not None else [['01-12345-67890','2026-10-10','12.00','4.00','AB1 2CD','']]
    return Snapshot('test_spreadsheet',1,'Existing orders',[[Cell(v,str(v)) for v in HEADERS]]+[[Cell(v,str(v)) for v in r] for r in data])

class FakeSheets:
    def __init__(self,snap=None):self.snap=snap or snapshot();self.writes=[];self.fail_write=False;self.read_count=0;self.hook=None;self.verify_fail=False
    def snapshot(self,*args):
        self.read_count+=1
        if self.hook:self.hook()
        if self.verify_fail and self.read_count>1:raise GoogleError('Read-back unavailable.',503)
        return copy.deepcopy(self.snap)
    def write_cell(self,spreadsheet_id,sheet_id,row,col,value,is_money=False):
        self.writes.append((row,col,value))
        self.snap.rows[row][col]=Cell(value,str(value))
        if self.fail_write:raise GoogleError('Timeout after remote success.',ambiguous=True)

@pytest.fixture
def remote(env):
    app,c,settings,me=env;st=create_store(c)
    with app.state.database.Session.begin() as db:
        store=db.get(Store,st['id']);store.source='google';store.spreadsheet_id='test_spreadsheet';store.sheet_id=1
        store.mapping={'date_format':'day_first','fields':{n:{'column':i,'header':HEADERS[i],'ownership':'app' if n=='tracking' else 'sheet'} for i,n in enumerate(FIELDS)}}
        con=Connection(org_id=store.org_id,credential=seal(settings,json.dumps({'access_token':'synthetic-not-real','expires_at':time.time()+3600})),scope='synthetic test')
        db.add(con);db.flush();store.connection_id=con.id;store.next_sync=now()+10000
        store.writes_enabled=True;store.writer_contract=True
        db.get(Organization,store.org_id).emergency_stop=False
        db.get(User,me['user']['id']).mfa_secret=seal(settings,'SYNTHETIC-TEST-ONLY')
        do_sync(db,store,snapshot())
    return env,st['id']

def intent(db,sid,uid,value='LR000123456GB'):
    st=db.get(Store,sid);o=db.scalar(select(Order).where(Order.store_id==sid))
    i=WriteIntent(org_id=st.org_id,store_id=sid,order_id=o.id,actor_id=uid,approver_id=uid,base={'tracking':o.tracking},proposed={'tracking':value},postcode=o.postcode,mapping_version=st.mapping_version,state='queued',reason='Approved isolated test',idempotency_key=str(uuid.uuid4()))
    db.add(i);db.commit();return i

def test_repeated_import_is_idempotent(remote):
    (app,c,settings,me),sid=remote
    with app.state.database.Session.begin() as db:
        r=do_sync(db,db.get(Store,sid),snapshot());assert r['created']==0 and r['unchanged']==1
        assert len(list(db.scalars(select(Order).where(Order.store_id==sid))))==1

def test_google_zero_cost_missing_cost_and_source_format(remote):
    (app,c,_,_),sid=remote
    with app.state.database.Session.begin() as db:
        st=db.get(Store,sid)
        do_sync(db,st,snapshot([['000001','2026-10-10','1.00','0','AB1','000000'],['000002','2026-10-11','2.00','','AB2','']]))
        rows=list(db.scalars(select(Order).where(Order.store_id==sid,Order.observed==True)))
        assert rows[0].ebay_id=='000001' and rows[0].tracking=='000000' and rows[0].cost==Decimal('0')
        assert rows[1].cost is None

def test_multi_item_duplicate_quarantines_not_double_revenue(remote):
    (app,c,_,_),sid=remote
    with app.state.database.Session.begin() as db:
        st=db.get(Store,sid);s=snapshot();s.rows.append(copy.deepcopy(s.rows[1]));r=do_sync(db,st,s)
        ss=summary(db,st,'2026-10');assert ss['earnings']=='12.00' and ss['incomplete_orders']==1
        assert ss['eligible_profit']=='0.00' and not st.writes_enabled and r['errors']

def test_header_change_detected(remote):
    (app,c,_,_),sid=remote
    with app.state.database.Session() as db:
        s=snapshot();s.rows[0][3]=Cell('Changed')
        with pytest.raises(ValueError,match='Header changed'):mapped_records(db.get(Store,sid),s)

def test_complete_absence_not_deletion(remote):
    (app,c,_,_),sid=remote
    with app.state.database.Session.begin() as db:
        do_sync(db,db.get(Store,sid),snapshot([]));o=db.scalar(select(Order).where(Order.store_id==sid))
        assert o is not None and not o.observed and o.cost==Decimal('4')

def test_sorted_rows_relocated_before_cell_write(remote):
    (app,c,settings,me),sid=remote
    s=snapshot([['OTHER','2026-10-12','1','0','XX',''],['01-12345-67890','2026-10-10','12.00','4.00','AB1 2CD','']]);adapter=FakeSheets(s)
    with app.state.database.Session() as db:
        i=intent(db,sid,me['user']['id']);r=execute_intent(db,settings,i,adapter)
        assert r['state']=='confirmed' and adapter.writes==[(2,5,'LR000123456GB')]
        assert db.get(Order,i.order_id).tracking=='LR000123456GB'

def test_same_value_no_remote_duplicate(remote):
    (app,c,settings,me),sid=remote;adapter=FakeSheets();adapter.snap.rows[1][5]=Cell('LR000123456GB')
    with app.state.database.Session() as db:
        i=intent(db,sid,me['user']['id']);r=execute_intent(db,settings,i,adapter)
        assert r['state']=='confirmed' and adapter.writes==[] and db.get(Order,i.order_id).tracking=='LR000123456GB'

def test_three_way_conflict_no_overwrite(remote):
    (app,c,settings,me),sid=remote;adapter=FakeSheets();adapter.snap.rows[1][5]=Cell('EXTERNAL-CHANGE')
    with app.state.database.Session() as db:
        i=intent(db,sid,me['user']['id']);r=execute_intent(db,settings,i,adapter)
        assert r['state']=='conflict' and not adapter.writes

@pytest.mark.parametrize('kind',['postcode','duplicate','formula','array','protected','merged','header'])
def test_unsafe_target_blocks_write(remote,kind):
    (app,c,settings,me),sid=remote;adapter=FakeSheets();s=adapter.snap
    if kind=='postcode':s.rows[1][4]=Cell('WRONG')
    if kind=='duplicate':s.rows.append(copy.deepcopy(s.rows[1]))
    if kind=='formula':s.rows[1][5]=Cell('',formula='=A1')
    if kind=='array':s.dynamic_formula=True
    if kind=='protected':s.protected=[{'range':{'sheetId':1,'startColumnIndex':5,'endColumnIndex':6},'warningOnly':True}]
    if kind=='merged':s.merges=[{'sheetId':1,'startRowIndex':1,'endRowIndex':2,'startColumnIndex':5,'endColumnIndex':7}]
    if kind=='header':s.rows[0][5]=Cell('New header')
    with app.state.database.Session() as db:
        i=intent(db,sid,me['user']['id']);r=execute_intent(db,settings,i,adapter)
        assert r['state']=='conflict' and not adapter.writes

@pytest.mark.parametrize('control',['emergency','paused','mapping','disabled_user','sheet_owned','lease'])
def test_runtime_gates_before_write(remote,control):
    (app,c,settings,me),sid=remote;adapter=FakeSheets()
    with app.state.database.Session() as db:
        i=intent(db,sid,me['user']['id']);st=db.get(Store,sid)
        if control=='emergency':db.get(Organization,st.org_id).emergency_stop=True
        if control=='paused':st.status='paused'
        if control=='mapping':st.mapping_version+=1
        if control=='disabled_user':db.get(User,i.actor_id).active=False
        if control=='sheet_owned':m=copy.deepcopy(st.mapping);m['fields']['tracking']['ownership']='sheet';st.mapping=m
        db.commit()
        r=execute_intent(db,settings,i,adapter,lambda:control!='lease')
        assert r['state'] in {'cancelled','conflict'} and not adapter.writes

def test_cancel_during_read_is_not_submitted(remote):
    (app,c,settings,me),sid=remote;adapter=FakeSheets()
    with app.state.database.Session() as db:
        i=intent(db,sid,me['user']['id']);iid=i.id
        def cancel():
            with app.state.database.Session.begin() as other:other.get(WriteIntent,iid).state='cancelled'
        adapter.hook=cancel
        r=execute_intent(db,settings,i,adapter);assert r['state']=='cancelled' and not adapter.writes

def test_timeout_after_success_never_replays(remote):
    (app,c,settings,me),sid=remote;adapter=FakeSheets();adapter.fail_write=True
    with app.state.database.Session() as db:
        i=intent(db,sid,me['user']['id']);r=execute_intent(db,settings,i,adapter)
        assert r['state']=='outcome_unknown' and len(adapter.writes)==1
        assert db.get(Order,i.order_id).tracking==''

def test_verification_failure_is_unknown(remote):
    (app,c,settings,me),sid=remote;adapter=FakeSheets();adapter.verify_fail=True
    with app.state.database.Session() as db:
        i=intent(db,sid,me['user']['id']);r=execute_intent(db,settings,i,adapter)
        assert r['state']=='outcome_unknown' and len(adapter.writes)==1

def test_worker_sync_persists_result(remote):
    (app,c,settings,me),sid=remote;adapter=FakeSheets()
    with app.state.database.Session.begin() as db:db.add(Job(org_id=db.get(Store,sid).org_id,store_id=sid,kind='sync'))
    worker=Worker(app.state.database,settings,lambda _:adapter);worker.tick()
    with app.state.database.Session() as db:
        j=db.scalar(select(Job).where(Job.store_id==sid));assert j.state=='succeeded' and j.result['unchanged']==1

def test_interrupted_remote_job_is_not_blindly_replayed(remote):
    (app,c,settings,me),sid=remote
    with app.state.database.Session() as db:
        i=intent(db,sid,me['user']['id']);i.state='submitting'
        db.add(Job(org_id=i.org_id,store_id=sid,kind='write',state='running',started_at=now()-300,payload={'intent_id':i.id}));db.commit();iid=i.id
    worker=Worker(app.state.database,settings,lambda _:FakeSheets());worker.tick()
    with app.state.database.Session() as db:assert db.get(WriteIntent,iid).state=='outcome_unknown'

def test_google_write_contract_one_cell_text_no_formula(env):
    _,_,settings,_=env;captured=[]
    def respond(req):captured.append(req);return httpx.Response(200,json={'replies':[{}]})
    tokens=seal(settings,json.dumps({'access_token':'TEST-NOT-REAL','expires_at':time.time()+3600}))
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        adapter=GoogleSheets(settings,tokens,client);adapter.write_cell('test',7,18,11,'=DANGEROUS()',False)
    body=json.loads(captured[0].content);request=body['requests'][0]['updateCells']
    assert request['fields']=='userEnteredValue'
    assert request['start']=={'sheetId':7,'rowIndex':18,'columnIndex':11}
    assert request['rows'][0]['values'][0]['userEnteredValue']=={'stringValue':'=DANGEROUS()'}

def test_viewer_cost_fields_redacted_from_summaries(env):
    app,c,_,_=env;st=create_store(c);create_order(c,st['id']);viewer,_,_=create_employee(app,c,[st['id']],role='viewer')
    assert 'costs' not in viewer.get('/api/overview?month=2026-10').json()['stores'][0]
    assert 'costs' not in viewer.get('/api/stores/'+st['id']+'/summary?month=2026-10').json()
    viewer.close()

def test_closed_period_snapshot_survives_source_issue(env):
    app,c,_,me=env;st=create_store(c);create_order(c,st['id'],sold_on='2025-01-05')
    assert c.post('/api/stores/'+st['id']+'/close/2025-01',json={'reason':'Reconciled and verified month'}).status_code==200
    with app.state.database.Session.begin() as db:
        o=db.scalar(select(Order).where(Order.store_id==st['id']));o.issues=['External correction requires review'];o.observed=False
    s=c.get('/api/stores/'+st['id']+'/summary?month=2025-01').json();assert s['closed'] and s['eligible_profit']=='8.00'

def test_date_serial_and_user_formats():
    assert parse_date(46205,'day_first')=='2026-07-02'
    assert parse_date('Sold 27 Oct 2026','day_first')=='2026-10-27'
    assert parse_date('03/04/2026','day_first')=='2026-04-03'
    assert parse_date('03/04/2026','month_first')=='2026-03-04'
