import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from xcomify.config import Settings
from xcomify.main import create_app
from xcomify.models import Store, User, Organization
from sqlalchemy import select

PASSWORD='correct-horse-battery-staple-63!'
@pytest.fixture
def env(tmp_path):
    settings=Settings(tmp_path,f'sqlite:///{tmp_path / "test.db"}',Fernet.generate_key().decode(),'test-bootstrap-code-with-enough-entropy',base_url='http://testserver',worker=False)
    app=create_app(settings)
    client=TestClient(app)
    client.headers.update({'Origin':'http://testserver','X-Xcomify-Request':'1'})
    r=client.post('/api/setup',json={'email':'owner@example.test','password':PASSWORD,'name':'Test Owner','setup_code':settings.bootstrap_token})
    assert r.status_code==200,r.text
    me=client.get('/api/me').json();client.headers['X-CSRF-Token']=me['csrf']
    yield app,client,settings,me
    client.close();app.state.database.close()

def create_store(client,name='Store A',currency='GBP',approved=True):
    r=client.post('/api/stores',json={'name':name,'currency':currency,'marketplace':'UK','timezone':'Europe/London'})
    assert r.status_code==200,r.text
    st=r.json()
    if approved:
        payload={k:st[k] for k in ['name','currency','marketplace','timezone','revision','status','include_filler','poll_seconds']}
        payload['financial_approved']=True
        r=client.patch('/api/stores/'+st['id'],json=payload);assert r.status_code==200,r.text;st=r.json()
    return st

def create_order(client,sid,oid='01-12345-67890',cost='4.00',earnings='12.00',**kw):
    payload={'ebay_id':oid,'sold_on':'2026-10-10','title':'Test product','earnings':earnings,'cost':cost,**kw}
    return client.post('/api/stores/'+sid+'/orders',json=payload)
