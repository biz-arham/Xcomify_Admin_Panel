import io,json,base64,time,csv,zipfile
from decimal import Decimal
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import select,delete
from xcomify.models import *
from xcomify.security import HASHER,seal,digest,totp_at,verify_totp
from xcomify.finance import money,order_profit,summary
from xcomify.backup import create_backup,restore_backup
from .conftest import create_store,create_order,PASSWORD

def test_setup_private_no_default_password(env):
    app,c,s,me=env
    assert me['user']['role']=='owner'
    assert me['emergency_stop'] is True
    assert c.get('/api/setup/status').json()['configured'] is True
    r=c.post('/api/setup',json={'email':'x@example.test','password':PASSWORD,'name':'Other','setup_code':s.bootstrap_token})
    assert r.status_code==409

def test_csrf_and_origin_enforced(env):
    _,c,_,_=env
    assert c.post('/api/stores',json={'name':'Bad'},headers={'X-CSRF-Token':'bad'}).status_code==403
    assert c.post('/api/stores',json={'name':'Bad'},headers={'Origin':'http://evil.test'}).status_code==403
    assert c.post('/api/stores',data='name=bad',headers={'Content-Type':'application/x-www-form-urlencoded'}).status_code==415

def test_no_public_docs_or_registration(env):
    app,c,_,_=env
    stranger=TestClient(app)
    assert stranger.get('/api/stores').status_code==401
    assert stranger.get('/docs').status_code==404
    assert stranger.get('/api/openapi').status_code==401
    assert c.get('/api/openapi').status_code==200

def test_no_secrets_in_validation_errors(env):
    _,c,_,_=env
    r=c.post('/api/auth/login',json={'password':'a-secret','email':'x','unexpected_secret':'never-log-this'})
    assert r.status_code==422
    assert 'never-log-this' not in r.text and 'a-secret' not in r.text

def test_security_headers(env):
    _,c,_,_=env
    r=c.get('/api/me')
    assert r.headers['x-frame-options']=='DENY'
    assert "script-src 'self'" in r.headers['content-security-policy']
    assert 'no-store' in r.headers['cache-control']

def test_decimal_and_missing_zero_distinct(env):
    app,c,_,_=env;st=create_store(c)
    assert create_order(c,st['id'],cost=None).status_code==200
    assert create_order(c,st['id'],oid='zero-cost',cost='0',earnings='0.30').status_code==200
    ss=c.get(f'/api/stores/{st["id"]}/summary?month=2026-10').json()
    assert ss['incomplete_orders']==1 and ss['confirmed_subtotal']=='0.30'
    assert ss['provisional_subtotal']=='12.00'
    assert ss['celebration_eligible'] is False
    assert money('0.10')+money('0.20')==Decimal('0.30')

def test_filler_excluded_by_default_and_explicit_change(env):
    _,c,_,_=env;st=create_store(c)
    create_order(c,st['id'],filler='3.00')
    ss=c.get(f'/api/stores/{st["id"]}/summary?month=2026-10').json()
    assert ss['eligible_profit']=='8.00' and ss['excluded_filler']=='3.00'
    b={k:st[k] for k in ['name','currency','marketplace','timezone','revision','status','poll_seconds','financial_approved']};b['include_filler']=True
    assert c.patch('/api/stores/'+st['id'],json=b).status_code==200
    ss=c.get(f'/api/stores/{st["id"]}/summary?month=2026-10').json()
    assert ss['eligible_profit']=='5.00'

def test_duplicate_import_order_guard(env):
    _,c,_,_=env;st=create_store(c)
    assert create_order(c,st['id']).status_code==200
    assert create_order(c,st['id']).status_code==409
    assert c.get('/api/orders').json()['total']==1

def test_same_ebay_id_two_stores_isolated(env):
    _,c,_,_=env;a=create_store(c,'One');b=create_store(c,'Two')
    assert create_order(c,a['id']).status_code==200
    assert create_order(c,b['id']).status_code==200
    assert c.get('/api/orders').json()['total']==2

def test_no_unapproved_profit(env):
    _,c,_,_=env;st=create_store(c,approved=False);create_order(c,st['id'])
    s=c.get(f'/api/stores/{st["id"]}/summary?month=2026-10').json()
    assert s['eligible_profit'] is None and not s['celebration_eligible']

def test_currency_not_merged(env):
    _,c,_,_=env;a=create_store(c,'UK','GBP');b=create_store(c,'AU','AUD')
    create_order(c,a['id']);create_order(c,b['id'])
    d=c.get('/api/overview?month=2026-10').json()
    assert {g['currency'] for g in d['groups']}=={'GBP','AUD'}
    assert all(g['profit']=='8.00' for g in d['groups'])

def test_target_zero_negative_overachievement(env):
    _,c,_,_=env;st=create_store(c);create_order(c,st['id'],earnings='10',cost='20')
    r=c.post(f'/api/stores/{st["id"]}/targets',json={'month':'2026-10','amount':'0','reason':'No active target'})
    assert r.status_code==200 and r.json()['attainment'] is None
    version=r.json()['target_version']
    r=c.post(f'/api/stores/{st["id"]}/targets',json={'month':'2026-10','amount':'5','version':version,'reason':'Set an active target'})
    assert r.json()['attainment']=='-200.00'
    assert c.post(f'/api/stores/{st["id"]}/targets',json={'month':'2026-10','amount':'-1','version':2,'reason':'Invalid target'}).status_code==422
    create_order(c,st['id'],oid='second',earnings='30',cost='0')
    r=c.get(f'/api/stores/{st["id"]}/summary?month=2026-10')
    assert r.json()['attainment']=='400.00'

def test_target_revisions_dont_spam_and_updates_versioned(env):
    app,c,_,_=env;st=create_store(c);create_order(c,st['id'])
    r=c.post(f'/api/stores/{st["id"]}/targets',json={'month':'2026-10','amount':'5','reason':'Set a target'})
    assert r.status_code==200
    assert c.get('/api/notifications').json()==[]
    r=c.post(f'/api/stores/{st["id"]}/targets',json={'month':'2026-10','amount':'4','version':1,'reason':'Reduce target'})
    assert r.status_code==200
    assert c.get('/api/notifications').json()==[]
    assert c.post(f'/api/stores/{st["id"]}/targets',json={'month':'2026-10','amount':'3','version':1,'reason':'Stale revision'}).status_code==409

def test_refund_credit_adjustment_and_idempotency(env):
    _,c,_,_=env;st=create_store(c);create_order(c,st['id'],earnings='30',cost='10',refund='4',credit='2',extra='3')
    body={'amount':'-5','recognized_on':'2026-10-15','reason':'One additional expense','idempotency_key':'unique-key-12345'}
    r=c.post(f'/api/stores/{st["id"]}/adjustments',json=body);assert r.status_code==200,r.text
    assert c.post(f'/api/stores/{st["id"]}/adjustments',json=body).json()['duplicate'] is True
    conflict={**body,'amount':'-6'}
    assert c.post(f'/api/stores/{st["id"]}/adjustments',json=conflict).status_code==409
    assert c.get(f'/api/stores/{st["id"]}/summary?month=2026-10').json()['eligible_profit']=='10.00'

def test_financial_edit_optimistic_revision(env):
    _,c,_,_=env;st=create_store(c);o=create_order(c,st['id']).json()
    b={'revision':o['revision'],'changes':{'cost':'5.00'},'reason':'Correct purchase cost','idempotency_key':'test-update-123'}
    assert c.patch('/api/orders/'+o['id'],json=b).status_code==200
    assert c.patch('/api/orders/'+o['id'],json=b).status_code==409

def test_csv_preview_no_mutation_atomic_duplicates(env):
    _,c,_,_=env;st=create_store(c)
    content='ebay_id,sold_on,title,earnings,cost\n00123,2026-10-10,Title,12.00,4.00\n'
    r=c.post(f'/api/stores/{st["id"]}/csv-import',json={'csv_text':content,'commit':False})
    assert r.json()['valid_rows']==1 and c.get('/api/orders').json()['total']==0
    assert c.post(f'/api/stores/{st["id"]}/csv-import',json={'csv_text':content,'commit':True}).status_code==200
    assert c.get('/api/orders').json()['rows'][0]['ebay_id']=='00123'
    assert c.post(f'/api/stores/{st["id"]}/csv-import',json={'csv_text':content,'commit':True}).status_code==422

def test_formula_injection_escaped_in_csv(env):
    _,c,_,_=env;st=create_store(c);create_order(c,st['id'],title='=HYPERLINK("https://evil.test")')
    r=c.get('/api/reports/orders.csv');assert r.status_code==200
    rows=list(csv.DictReader(io.StringIO(r.text.lstrip('\ufeff'))))
    assert rows[0]['title'].startswith("'=")

def create_employee(app,c,store_ids,role='operations',email='employee@example.test'):
    r=c.post('/api/team/invite',json={'email':email,'role':role,'stores':store_ids});assert r.status_code==200,r.text
    token=r.json()['invitation_url'].split('#invite=')[1]
    employee=TestClient(app);employee.headers.update({'Origin':'http://testserver','X-Xcomify-Request':'1'})
    accepted=employee.post('/api/invitations/accept',json={'token':token,'name':'Employee','password':PASSWORD})
    assert accepted.status_code==200,accepted.text
    me=employee.get('/api/me').json();employee.headers['X-CSRF-Token']=me['csrf']
    return employee,me,token

def test_store_permissions_and_financial_redaction(env):
    app,c,_,_=env;a=create_store(c,'Allowed');b=create_store(c,'Hidden')
    oa=create_order(c,a['id']).json();ob=create_order(c,b['id']).json()
    emp,_,_=create_employee(app,c,[a['id']])
    assert len(emp.get('/api/stores').json())==1
    rows=emp.get('/api/orders').json()['rows'];assert len(rows)==1
    assert 'cost' not in rows[0] and 'earnings' not in rows[0] and 'profit' not in rows[0]
    assert emp.get('/api/orders/'+ob['id']).status_code==404
    assert emp.get('/api/reports/orders.csv').status_code==403
    assert emp.get('/api/overview').json()['groups']==[]
    assert emp.get('/api/stores/'+a['id']+'/summary').status_code==403
    r=emp.patch('/api/orders/'+oa['id'],json={'revision':1,'changes':{'cost':'0'},'reason':'Unsafe cost update','idempotency_key':'employee-write-key'})
    assert r.status_code==403
    emp.close()

def test_two_tenant_direct_id_isolation(env):
    app,c,_,_=env;st=create_store(c);o=create_order(c,st['id']).json()
    with app.state.database.Session.begin() as db:
        org=Organization(name='Other');db.add(org);db.flush()
        u=User(org_id=org.id,email='other@example.test',name='Other owner',role='owner',password_hash=HASHER.hash(PASSWORD));db.add(u)
    other=TestClient(app);other.headers.update({'Origin':'http://testserver','X-Xcomify-Request':'1'})
    assert other.post('/api/auth/login',json={'email':'other@example.test','password':PASSWORD}).status_code==200
    me=other.get('/api/me').json();other.headers['X-CSRF-Token']=me['csrf']
    assert other.get('/api/stores').json()==[]
    assert other.get('/api/orders/'+o['id']).status_code==404
    assert other.get('/api/orders?store_id='+st['id']).status_code==404
    assert other.get('/api/audit').json()['total']==1
    other.close()

def test_invite_one_time_and_deactivation_revokes(env):
    app,c,_,_=env;st=create_store(c);emp,me,token=create_employee(app,c,[st['id']])
    assert c.post('/api/invitations/accept',json={'token':token,'name':'Replay','password':PASSWORD}).status_code==400
    assert c.patch('/api/team/'+me['user']['id'],json={'active':False,'role':'operations','stores':[]}).status_code==200
    assert emp.get('/api/me').status_code==401
    emp.close()

def test_mfa_and_code_replay(env):
    app,c,_,_=env
    setup=c.post('/api/auth/mfa/setup',json={}).json();secret=setup['secret'];code=totp_at(secret,int(time.time()//30))
    r=c.post('/api/auth/mfa/confirm',json={'code':code});assert r.status_code==200,r.text
    assert len(r.json()['recovery_codes'])==8
    assert c.get('/api/me').json()['user']['mfa_enabled'] is True
    c.post('/api/auth/logout',json={})
    r=c.post('/api/auth/login',json={'email':'owner@example.test','password':PASSWORD,'code':code})
    assert r.status_code==401
    # A one-use recovery code can establish a new MFA-verified session.
    rec=app.state.database

def test_rfc6238_totp_known_vector():
    secret=base64.b32encode(b'12345678901234567890').decode()
    assert totp_at(secret,1)=='287082' # RFC 6238 SHA1, 8-digit output truncated to 6 digits.
    assert verify_totp(secret,'287082',timestamp=59)==1
    assert verify_totp(secret,'287082',last_counter=1,timestamp=59) is None

def test_session_cookie_not_in_local_json_and_logout(env):
    _,c,_,_=env
    data=c.get('/api/me').json();assert 'session_token' not in data
    assert c.post('/api/auth/logout',json={}).status_code==200
    assert c.get('/api/me').status_code==401

def test_mfa_needed_to_clear_stop(env):
    _,c,_,_=env
    r=c.post('/api/system/write-stop',json={'enabled':False,'reason':'Attempt without MFA'})
    assert r.status_code==428

def test_connection_secret_never_serialized(env):
    app,c,s,me=env
    with app.state.database.Session.begin() as db:
        user=db.get(User,me['user']['id']);db.add(Connection(org_id=user.org_id,name='Private',credential=seal(s,json.dumps({'refresh_token':'SUPER_SECRET'})),scope='scope'))
    r=c.get('/api/connections');assert r.status_code==200
    assert 'SUPER_SECRET' not in r.text and 'credential' not in r.text

def test_backup_restores_read_only_revokes_sessions(env,tmp_path):
    app,c,s,me=env;st=create_store(c);create_order(c,st['id'])
    path=create_backup(s);assert path.read_bytes().startswith(b'gAAAA')
    restored=restore_backup(path,s.data_dir/'backup-recovery.key',tmp_path/'restored')
    import sqlite3
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT count(*) FROM orders').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM sessions').fetchone()[0]==0
        assert db.execute('SELECT emergency_stop FROM organizations').fetchone()[0]==1
        assert db.execute('SELECT writes_enabled FROM stores').fetchone()[0]==0

def test_closed_period_rejects_direct_edit(env):
    _,c,_,_=env;st=create_store(c);o=create_order(c,st['id'],sold_on='2025-01-10').json()
    r=c.post(f'/api/stores/{st["id"]}/close/2025-01',json={'reason':'Monthly reconciliation completed'})
    assert r.status_code==200,r.text
    r=c.patch('/api/orders/'+o['id'],json={'revision':1,'changes':{'cost':'3'},'reason':'Wrong historical edit','idempotency_key':'closed-edit-key'})
    assert r.status_code==409

def test_cannot_relabel_existing_currency(env):
    _,c,_,_=env;st=create_store(c);create_order(c,st['id'])
    body={k:st[k] for k in ['name','marketplace','timezone','revision','status','financial_approved','include_filler','poll_seconds']};body['currency']='AUD'
    assert c.patch('/api/stores/'+st['id'],json=body).status_code==409

def test_celebration_claim_is_persisted_once_and_refund_safe(env):
    app,c,_,_=env;st=create_store(c)
    month=__import__('datetime').date.today().strftime('%Y-%m')
    assert c.post('/api/stores/'+st['id']+'/targets',json={'month':month,'amount':'5','reason':'Fresh test target'}).status_code==200
    o=create_order(c,st['id'],sold_on=month+'-01').json()
    r=c.post('/api/celebrations/claim',json={});assert r.status_code==200,r.text
    assert len(r.json()['events'])==1 and r.json()['events'][0]['level']==100
    assert c.post('/api/celebrations/claim',json={}).json()['events']==[]
    assert c.patch('/api/orders/'+o['id'],json={'revision':o['revision'],'changes':{'refund':'8'},'reason':'Refund regression check','idempotency_key':'refund-test-celebration'}).status_code==200
    assert c.post('/api/celebrations/claim',json={}).json()['events']==[]

def test_demo_cannot_inherit_real_database(monkeypatch,tmp_path):
    from xcomify.config import Settings
    monkeypatch.setenv('XCOMIFY_DEMO','true');monkeypatch.setenv('XCOMIFY_ENV','local')
    monkeypatch.setenv('XCOMIFY_DEMO_DATA_DIR',str(tmp_path/'demo'))
    monkeypatch.setenv('XCOMIFY_DATA_DIR',str(tmp_path/'real'))
    monkeypatch.setenv('DATABASE_URL','sqlite:////do-not-use/real.db')
    s=Settings.from_env()
    assert s.demo and s.database_url.endswith('/demo/xcomify-demo.db')
    assert not (tmp_path/'real').exists()

def test_newer_schema_refused(env):
    app,_,_,_=env
    with app.state.database.Session.begin() as db:db.add(Version(version=2))
    import pytest
    with pytest.raises(RuntimeError,match='newer'):app.state.database.migrate()

def test_mfa_recovery_code_consumed_atomically_once(env):
    app,c,_,_=env
    setup=c.post('/api/auth/mfa/setup',json={}).json();code=totp_at(setup['secret'],int(time.time()//30))
    enabled=c.post('/api/auth/mfa/confirm',json={'code':code});assert enabled.status_code==200
    recovery=enabled.json()['recovery_codes'][0]
    assert c.post('/api/auth/logout',json={}).status_code==200
    first=c.post('/api/auth/login',json={'email':'owner@example.test','password':PASSWORD,'code':recovery});assert first.status_code==200,first.text
    c.headers['X-CSRF-Token']=c.get('/api/me').json()['csrf']
    assert c.post('/api/auth/logout',json={}).status_code==200
    second=c.post('/api/auth/login',json={'email':'owner@example.test','password':PASSWORD,'code':recovery});assert second.status_code==401

def test_unauthorized_viewer_cannot_claim_other_store_milestone(env):
    app,c,_,_=env;a=create_store(c,'Allowed');b=create_store(c,'Other')
    month=__import__('datetime').date.today().strftime('%Y-%m')
    c.post('/api/stores/'+b['id']+'/targets',json={'month':month,'amount':'5','reason':'Private store milestone'})
    create_order(c,b['id'],sold_on=month+'-01')
    viewer,_,_=create_employee(app,c,[a['id']],role='viewer')
    assert viewer.post('/api/celebrations/claim',json={}).json()['events']==[]
    viewer.close()
