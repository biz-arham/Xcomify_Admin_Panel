"""Explicitly synthetic development fixtures; never silently used in production."""
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo
from .models import *
from .finance import record_milestones

def seed_demo(db,org,user):
    if not org.demo:raise ValueError('Synthetic seed requires an isolated demo organization.')
    examples=[('Prime Deal Mart','UK','GBP','Europe/London','1750',26,Decimal('38.40')),
              ('Ocean Crest','AU','AUD','Australia/Sydney','2300',22,Decimal('71.60')),
              ('Xcomify US - Demo','US','USD','America/New_York','1400',18,Decimal('59.20')),
              ('British Home - Demo','UK','GBP','Europe/London','780',20,Decimal('44.80'))]
    products=['Universal shaver replacement foil','Home organisation storage set','Garden solar path light','Compact travel umbrella','Silicone kitchen tool set','USB-C enclosure accessory','Adjustable phone stand','Weatherproof protective cover']
    for index,(name,market,currency,tz,target,n,margin) in enumerate(examples):
        month=datetime.now(ZoneInfo(tz)).strftime('%Y-%m');today=datetime.now(ZoneInfo(tz)).day
        st=Store(org_id=org.id,name=name,marketplace=market,currency=currency,timezone=tz,financial_approved=True,source='local')
        db.add(st);db.flush();db.add(Target(org_id=org.id,store_id=st.id,month=month,amount=Decimal(target)))
        for k in range(n):
            cost=Decimal('9.20')+Decimal(k%5)*Decimal('1.75')
            earnings=cost+margin+Decimal((k%7)-3)*Decimal('2.60')
            missing=index==1 and k in (4,12)
            db.add(Order(org_id=org.id,store_id=st.id,ebay_id=f'DEMO-{index+1:02d}-{100001+k}',
                sold_on=f'{month}-{1+(k%max(1,today)):02d}',title=products[k%len(products)],earnings=earnings,
                cost=None if missing else cost,extra=Decimal('0'),refund=Decimal('0'),credit=Decimal('0'),filler=Decimal('0'),
                tracking='' if k%6==0 else f'DEMO-H0-{index}{k:08d}',courier='' if k%6==0 else 'Demo carrier',
                supplier_ref=f'DEMO-AE-{index}{k:07d}',postcode='DEMO',status='Placed' if k%6==0 else 'Tracking available',
                notes='Synthetic demonstration record. Not a real order.'))
        db.flush();record_milestones(db,st,month,muted=True)
        db.add(Task(org_id=org.id,store_id=st.id,title='Review missing tracking in demo records',assignee_id=user.id,created_by=user.id,due_on=f'{month}-{today:02d}'))
    db.add(Notification(org_id=org.id,title='Isolated demonstration workspace',body='All stores, orders and amounts in this workspace are synthetic. Google connections and outbound writes are disabled.',severity='info',dedupe_key='demo-start'))
