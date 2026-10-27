"""Safe source import and one-cell outbound write state machine."""
from collections import defaultdict
from datetime import date,datetime,timedelta
from decimal import Decimal
import re
from sqlalchemy import select
from fastapi import HTTPException
from .models import *
from .finance import money,fmt,norm_postcode,record_milestones,current_month,MONEY_FIELDS
from .security import audit,can,store_access
from .google import GoogleError,writable

FIELDS={'ebay_id','sold_on','title','earnings','cost','extra','refund','credit','filler','supplier_ref','tracking','courier','postcode','status'}
WRITABLE_FIELDS={'cost','extra','refund','credit','filler','supplier_ref','tracking','courier','status'}

def parse_date(value,mode):
    if isinstance(value,(int,float)):
        return (date(1899,12,30)+timedelta(days=int(value))).isoformat()
    s=str(value).strip()
    s=re.sub(r'^Sold\s+','',s,flags=re.I)
    formats=['%Y-%m-%d','%d %b %Y','%d %B %Y']
    formats+=['%d/%m/%Y','%d-%m-%Y'] if mode=='day_first' else ['%m/%d/%Y','%m-%d-%Y'] if mode=='month_first' else []
    for f in formats:
        try:return datetime.strptime(s,f).date().isoformat()
        except ValueError:pass
    raise ValueError('Unrecognized sold date; select the correct date format.')

def validate_headers(store,snapshot):
    fields=store.mapping.get('fields',{})
    if not {'ebay_id','sold_on','earnings','cost'}<=set(fields): raise ValueError('Mapping requires eBay ID, sold date, net earnings and supplier cost.')
    if len({m['column'] for m in fields.values()})!=len(fields): raise ValueError('Each field must map to a distinct column.')
    for name,m in fields.items():
        if name not in FIELDS: raise ValueError('Unsupported mapped field.')
        if str(snapshot.value(store.header_row-1,m['column'])).strip()!=m['header']:
            raise ValueError(f'Header changed for {name}; writes are paused until mapping is reapproved.')
    return fields

def mapped_records(store,snapshot):
    fields=validate_headers(store,snapshot)
    grouped=defaultdict(list); errors=[]
    for index in range(store.header_row,len(snapshot.rows)):
        identity_cell=snapshot.cell(index,fields['ebay_id']['column'])
        ebay=str(identity_cell.value).strip()
        if not ebay:
            if any(str(snapshot.value(index,m['column'])).strip() for m in fields.values()):
                errors.append({'row':index+1,'error':'Non-empty row has no eBay order ID. Review totals or excluded sections before live use.'})
            continue
        if ebay==fields['ebay_id']['header']:
            errors.append({'row':index+1,'error':'Repeated header detected.'});continue
        if isinstance(identity_cell.value,(int,float)):
            if abs(identity_cell.value)>=10**15:
                errors.append({'row':index+1,'error':'Numeric order ID may have lost precision. Store source IDs as text.'});continue
            ebay=identity_cell.formatted or str(identity_cell.value)
        if len(ebay)>100: errors.append({'row':index+1,'error':'Invalid eBay order ID length.'});continue
        rec={'ebay_id':ebay,'source_row':index+1,'issues':[],'source_values':{}}
        for name,m in fields.items():
            c=snapshot.cell(index,m['column']); val=c.value
            if c.error: rec['issues'].append(f'{name}: formula error')
            try:
                if name in MONEY_FIELDS:
                    if val is None or str(val).strip()=='':
                        rec[name]=None if name in {'earnings','cost'} else Decimal(0)
                        if name not in {'earnings','cost'}: rec['issues'].append(f'{name}: mapped amount is blank')
                    else: rec[name]=money(str(val),optional=True)
                    if rec[name] is not None and rec[name]<0 and name!='earnings': rec['issues'].append(f'{name}: negative deduction requires review')
                elif name=='sold_on': rec[name]=parse_date(val,store.mapping.get('date_format','day_first'))
                else: rec[name]=str(val).strip()
                rec['source_values'][name]=fmt(rec[name]) if name in MONEY_FIELDS else rec[name]
            except (ValueError,OverflowError):
                rec['issues'].append(f'{name}: invalid value')
                rec[name]=None if name in MONEY_FIELDS else ''
                rec['source_values'][name]=str(val)[:200]
        # Invalid dates cannot safely enter a monthly target period.
        if not rec.get('sold_on'):
            errors.append({'row':index+1,'error':'Invalid sold date; row quarantined.'});continue
        for field in ['supplier_ref','tracking','courier','postcode','title']:
            rec.setdefault(field,'')
        rec.setdefault('status','Unknown')
        for f in ['extra','refund','credit','filler']:
            if rec.get(f) is None: rec[f]=Decimal(0)
        grouped[ebay].append(rec)
    output=[]
    for ebay,recs in grouped.items():
        rec=recs[0]
        if len(recs)>1:
            rec['issues'].append(f'Duplicate/multi-item source rows ({len(recs)}); revenue counted once and excluded from eligible profit until reviewed.')
            errors.append({'row':rec['source_row'],'error':f'Duplicate eBay ID {ebay}: reconcile parent and line allocation.'})
        output.append(rec)
    return output,errors

def do_sync(db,store,snapshot):
    records,errors=mapped_records(store,snapshot)
    first=store.last_sync is None; created=0; updated=0; unchanged=0; seen=set()
    for rec in records:
        existing=db.scalar(select(Order).where(Order.store_id==store.id,Order.ebay_id==rec['ebay_id']))
        seen.add(rec['ebay_id'])
        if existing and existing.origin!='google':
            errors.append({'row':rec['source_row'],'error':'Local order collides with imported order; no overwrite.'});continue
        if existing and db.get(PeriodClose,(store.id,existing.sold_on[:7])):
            if existing.source_values!=rec['source_values']:
                existing.issues=list(set(existing.issues+['Source changed in closed period; authorized reconciliation required.']))
                errors.append({'row':rec['source_row'],'error':'Closed period changed; stored financial data preserved.'})
            continue
        if not existing:
            existing=Order(org_id=store.org_id,store_id=store.id,ebay_id=rec['ebay_id'],sold_on=rec['sold_on'],origin='google')
            db.add(existing);created+=1
        elif existing.source_values==rec['source_values'] and existing.issues==rec['issues'] and existing.observed:
            existing.source_row=rec['source_row'];unchanged+=1;continue
        else:updated+=1
        for key,val in rec.items():
            if key in FIELDS|{'source_row','source_values','issues'}: setattr(existing,key,val)
        existing.observed=True;existing.revision=(existing.revision or 0)+1;existing.updated_at=now()
    # A complete scan marks absence without deleting, refunding, or erasing history.
    for old in db.scalars(select(Order).where(Order.store_id==store.id,Order.origin=='google')):
        if old.ebay_id not in seen: old.observed=False
    store.last_sync=now();store.tab_name=snapshot.title
    store.sync_error=(f'{len(errors)} source issue(s); inspect sync results before write-enable.' if errors else None)
    if errors: store.writes_enabled=False
    db.flush()
    record_milestones(db,store,current_month(store),muted=first)
    if errors:
        key=f'sync-issues:{store.id}:{store.mapping_version}'
        if not db.scalar(select(Notification.id).where(Notification.org_id==store.org_id,Notification.dedupe_key==key)):
            db.add(Notification(org_id=store.org_id,store_id=store.id,title='Sheet reconciliation needs review',
                body=f'{len(errors)} source issue(s) in {store.name}. Outbound writes have been paused.',severity='warning',dedupe_key=key))
    audit(db,None,'sync.completed',store.id,details={'created':created,'updated':updated,'unchanged':unchanged,'issues':len(errors)},org_id=store.org_id)
    return {'created':created,'updated':updated,'unchanged':unchanged,'scanned_rows':len(snapshot.rows),'errors':errors[:100]}

def canonical(name,value):
    if name in MONEY_FIELDS:
        try:return fmt(money(value,optional=True))
        except ValueError:return str(value)
    return str(value or '').strip()

def execute_intent(db,settings,intent,adapter,lease_check=lambda:True):
    store=db.get(Store,intent.store_id);org=db.get(Organization,intent.org_id)
    actor=db.get(User,intent.actor_id);approver=db.get(User,intent.approver_id) if intent.approver_id else None
    def fail(state,message):
        intent.state=state;intent.error=message;intent.updated_at=now();db.commit();return {'state':state,'message':message}
    if settings.demo or org.demo: return fail('failed','Demo workspaces cannot write to Google.')
    if not actor or not actor.active or not approver or not approver.active:return fail('cancelled','Actor or approver access was revoked.')
    try:
        store_access(db,actor,store.id,'orders:edit');store_access(db,approver,store.id,'writes:approve')
    except HTTPException:return fail('cancelled','Current store permission does not permit this queued write.')
    if not approver.mfa_secret:return fail('cancelled','Approver MFA is no longer active.')
    if org.emergency_stop or store.status!='active' or not store.writes_enabled or not store.writer_contract:
        return fail('cancelled','Write-stop, inactive store, or missing single-writer approval.')
    if store.mapping_version!=intent.mapping_version:return fail('conflict','Mapping changed after this proposal.')
    if len(intent.proposed)!=1:return fail('failed','This release submits exactly one cell per approved intent.')
    name,value=next(iter(intent.proposed.items()));mapping=store.mapping.get('fields',{}).get(name)
    if name not in WRITABLE_FIELDS or not mapping or mapping['ownership']!='app':return fail('conflict','Field is Sheet-owned or not approved for application writes.')
    order=db.get(Order,intent.order_id)
    if db.get(PeriodClose,(store.id,order.sold_on[:7])):return fail('conflict','Financial period is closed.')
    intent.state='validating';db.commit()
    snap=adapter.snapshot(store.spreadsheet_id,store.sheet_id,store.max_rows)
    try:fields=validate_headers(store,snap)
    except ValueError as e:
        store.writes_enabled=False;return fail('conflict',str(e))
    matches=[ri for ri in range(store.header_row,len(snap.rows)) if str(snap.value(ri,fields['ebay_id']['column'])).strip()==order.ebay_id]
    if len(matches)!=1:return fail('conflict','Order identity is absent or duplicated. No cell was written.')
    row=matches[0];col=mapping['column']
    if 'postcode' in fields:
        observed=norm_postcode(snap.value(row,fields['postcode']['column']))
        if observed!=norm_postcode(intent.postcode):return fail('conflict','Postcode changed or does not match; no write.')
    current=canonical(name,snap.value(row,col));proposed=canonical(name,value);base=canonical(name,intent.base.get(name))
    if current==proposed:
        do_sync(db,store,snap)
        return fail('confirmed','Proposed value already observed; no duplicate write sent.')
    if current!=base:return fail('conflict','The Sheet value changed since the proposal. Review instead of overwriting.')
    ok,reason=writable(snap,row,col)
    if not ok:return fail('conflict',reason)
    # Recheck live controls and privileges after the potentially long read.
    db.expire_all();org=db.get(Organization,intent.org_id);store=db.get(Store,intent.store_id)
    actor=db.get(User,intent.actor_id);approver=db.get(User,intent.approver_id)
    if intent.state!='validating':
        return {'state':intent.state,'message':'Intent changed during validation; no remote write submitted.'}
    if not lease_check() or org.emergency_stop or not store.writes_enabled or store.status!='active' or store.mapping_version!=intent.mapping_version:
        return fail('cancelled','Lease, configuration, or emergency control changed before submission.')
    try:
        if not actor.active or not approver.active or not approver.mfa_secret:raise HTTPException(403)
        store_access(db,actor,store.id,'orders:edit');store_access(db,approver,store.id,'writes:approve')
    except HTTPException:return fail('cancelled','Authorization changed before submission.')
    intent.state='submitting';db.commit()
    try:adapter.write_cell(store.spreadsheet_id,store.sheet_id,row,col,value,name in MONEY_FIELDS)
    except GoogleError as exc:
        return fail('outcome_unknown' if exc.ambiguous else 'failed',str(exc))
    intent.state='verifying';db.commit()
    try:
        verified=adapter.snapshot(store.spreadsheet_id,store.sheet_id,store.max_rows)
        validate_headers(store,verified)
        matches=[ri for ri in range(store.header_row,len(verified.rows)) if str(verified.value(ri,fields['ebay_id']['column'])).strip()==order.ebay_id]
        if len(matches)!=1:return fail('outcome_unknown','Remote request returned, but unique identity could not be verified.')
        vr=matches[0]
        if 'postcode' in fields and norm_postcode(verified.value(vr,fields['postcode']['column']))!=norm_postcode(intent.postcode):
            return fail('outcome_unknown','Identity postcode changed during verification.')
        if canonical(name,verified.value(vr,col))!=proposed:return fail('conflict','Read-back differs from proposed value; manual review required.')
        do_sync(db,store,verified)
        audit(db,None,'write.verified',store.id,intent.id,{'field':name,'approval':intent.approver_id},org_id=store.org_id)
        return fail('confirmed','Value and identity observed after write. Independent future edits remain possible.')
    except (GoogleError,ValueError):return fail('outcome_unknown','Remote write submitted; verification failed. Reconcile before any retry.')
