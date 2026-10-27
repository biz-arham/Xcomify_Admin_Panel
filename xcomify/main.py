from __future__ import annotations
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode, urlparse
import asyncio, base64, csv, hashlib, hmac, io, json, logging, secrets, threading, time
import httpx
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select, delete, update, func, or_
from sqlalchemy.exc import IntegrityError
from .config import Settings, ROOT
from .db import Database
from .models import *
from .schemas import *
from .security import *
from .finance import *
from .google import GoogleSheets, GoogleError, SCOPE, TOKEN_URL
from .sync import FIELDS,WRITABLE_FIELDS,validate_headers,mapped_records,do_sync,canonical

log=logging.getLogger('xcomify')
BOOT_LOCK=threading.Lock()

def clean_email(value):
    v=value.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v) or len(v)>254:raise HTTPException(422,'Enter a valid email address.')
    return v

def create_app(settings: Settings | None=None, database: Database | None=None):
    settings=settings or Settings.from_env();database=database or Database(settings.database_url)
    database.migrate()
    stop=asyncio.Event()
    @asynccontextmanager
    async def lifespan(app):
        task=None
        if settings.worker:
            from .worker import Worker
            worker=Worker(database,settings,lambda c:app.state.adapter_factory(c))
            async def loop():
                while not stop.is_set():
                    try:await asyncio.to_thread(worker.tick)
                    except Exception:log.exception('Worker tick failed; no request payloads are logged.')
                    try:await asyncio.wait_for(stop.wait(),timeout=2)
                    except asyncio.TimeoutError:pass
            task=asyncio.create_task(loop())
        yield
        stop.set()
        if task:await task
    app=FastAPI(title='Xcomify Central Command',version='1.0.0',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.settings=settings;app.state.database=database
    app.state.adapter_factory=lambda c:GoogleSheets(settings,c.credential)
    host=urlparse(settings.base_url).hostname
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=[host] if host else ['localhost'])

    @app.middleware('http')
    async def security_headers(request:Request,call_next):
        rid=secrets.token_hex(8)
        if request.method not in {'GET','HEAD','OPTIONS'}:
            if request.headers.get('origin')!=settings.base_url or request.headers.get('x-xcomify-request')!='1':
                return JSONResponse({'detail':'Origin or request header not allowed.'},403)
            if 'application/json' not in request.headers.get('content-type',''):
                return JSONResponse({'detail':'JSON content type required.'},415)
            size=0;parts=[]
            async for chunk in request.stream():
                size+=len(chunk)
                if size>2_500_000:return JSONResponse({'detail':'Request exceeds 2.5 MB limit.'},413)
                parts.append(chunk)
            request._body=b''.join(parts)
        try:response=await call_next(request)
        except Exception:
            log.exception('Unhandled request error id=%s path=%s',rid,request.url.path)
            response=JSONResponse({'detail':'Unexpected server error. No changes are assumed confirmed.','request_id':rid},500)
        response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer',
            'Permissions-Policy':'camera=(), microphone=(), geolocation=()',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
            'X-Request-ID':rid})
        if request.url.path.startswith('/api'):response.headers['Cache-Control']='no-store, private'
        if settings.production:response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
        return response
    @app.exception_handler(RequestValidationError)
    async def validation_error(_,exc):
        return JSONResponse({'detail':[{'loc':list(e['loc']),'msg':e['msg'],'type':e['type']} for e in exc.errors()]},422)
    @app.exception_handler(GoogleError)
    async def google_error(_,exc):return JSONResponse({'detail':str(exc),'remote_status':exc.status},502)
    @app.exception_handler(ValueError)
    async def value_error(_,exc):return JSONResponse({'detail':str(exc)},422)
    @app.exception_handler(IntegrityError)
    async def integrity_error(_,exc):return JSONResponse({'detail':'This record already exists or changed concurrently. Refresh and retry.'},409)

    def context(request:Request):
        with database.Session() as db:
            token=request.cookies.get(settings.cookie_name,'')
            ses=db.get(Session,digest(token)) if token else None
            if not ses or ses.expires_at<now() or ses.last_seen<now()-settings.idle_minutes*60:raise HTTPException(401,'Sign in to continue.')
            user=db.get(User,ses.user_id)
            if not user or not user.active:raise HTTPException(401,'Session is no longer active.')
            if request.method not in {'GET','HEAD'} and not hmac.compare_digest(request.headers.get('x-csrf-token',''),ses.csrf):
                raise HTTPException(403,'CSRF verification failed. Refresh and try again.')
            ses.last_seen=now()
            try:
                yield db,user,ses
                db.commit()
            except Exception:
                db.rollback();raise
    def login_limit(request,email):
        ip=request.client.host if request.client else 'unknown'
        keys=['ip:'+digest(ip),'account:'+digest(email)]
        with database.Session.begin() as db:
            db.execute(delete(AuthAttempt).where(AuthAttempt.at<now()-86400))
            for key in keys:
                count=db.scalar(select(func.count()).select_from(AuthAttempt).where(AuthAttempt.key==key,AuthAttempt.at>now()-900))
                if count>=(30 if key.startswith('ip:') else 12):raise HTTPException(429,'Too many attempts. Try again after 15 minutes.')
            for key in keys:db.add(AuthAttempt(key=key))
    def mfa_check(db,user,code):
        if not user.mfa_secret:return False
        counter=verify_totp(unseal(settings,user.mfa_secret),code,user.mfa_counter)
        if counter is not None:
            changed=db.execute(update(User).where(User.id==user.id,User.mfa_counter<counter).values(mfa_counter=counter))
            if changed.rowcount:return True
        hashed=digest(code.strip().upper())
        consumed=db.execute(update(RecoveryCode).where(RecoveryCode.user_id==user.id,RecoveryCode.code_hash==hashed,RecoveryCode.used_at.is_(None)).values(used_at=now()))
        if consumed.rowcount:
            audit(db,user,'auth.recovery_code_used');return True
        raise HTTPException(401,'Invalid credentials or verification code.')
    def session_create(db,user,response,request,mfa_verified=False):
        token=secrets.token_urlsafe(48)
        ses=Session(id=digest(token),user_id=user.id,csrf=secrets.token_urlsafe(32),expires_at=now()+settings.session_hours*3600,
            stepup_until=now()+600,mfa_verified=mfa_verified,user_agent=request.headers.get('user-agent','')[:200])
        db.add(ses)
        response.set_cookie(settings.cookie_name,token,max_age=settings.session_hours*3600,httponly=True,secure=settings.production,samesite='lax',path='/')
        return ses
    def user_public(user):return {'id':user.id,'name':user.name,'email':user.email,'role':user.role,'mfa_enabled':bool(user.mfa_secret),'active':user.active}
    def store_public(db,user,s):
        v={'id':s.id,'name':s.name,'marketplace':s.marketplace,'currency':s.currency,'timezone':s.timezone,'status':s.status,
            'source':s.source,'last_sync':s.last_sync,'sync_error':s.sync_error,'writes_enabled':s.writes_enabled,'revision':s.revision,
            'financial_approved':s.financial_approved,'financial_basis':s.financial_basis,'include_filler':s.include_filler,'poll_seconds':s.poll_seconds}
        if user.role=='owner':v.update(connection_id=s.connection_id,spreadsheet_id=s.spreadsheet_id,sheet_id=s.sheet_id,
            tab_name=s.tab_name,header_row=s.header_row,mapping=s.mapping,mapping_version=s.mapping_version,max_rows=s.max_rows,
            writer_contract=s.writer_contract,gates=s.gates)
        return v
    def order_public(user,o,store,details=False):
        d={'id':o.id,'store_id':o.store_id,'store':store.name,'currency':store.currency,'ebay_id':o.ebay_id,'sold_on':o.sold_on,
            'title':o.title,'tracking':o.tracking,'courier':o.courier,'status':o.status,'supplier_ref':o.supplier_ref,
            'postcode':o.postcode if details and can(user,'orders:edit') else (o.postcode[:3]+' ***' if o.postcode else ''),
            'origin':o.origin,'revision':o.revision,'observed':o.observed,'issues':o.issues,'notes':o.notes,'updated_at':o.updated_at}
        if can(user,'finance:view'):d.update(earnings=fmt(o.earnings),profit=fmt(order_profit(o,store)),financial_approved=store.financial_approved)
        if can(user,'costs:view'):d.update({k:fmt(getattr(o,k)) for k in ['cost','extra','refund','credit','filler']})
        if details and user.role=='owner':d.update(source_row=o.source_row,source_values=o.source_values,spreadsheet_id=store.spreadsheet_id,sheet_id=store.sheet_id)
        return d
    def find_order(db,user,oid,action='orders:view'):
        o=db.get(Order,oid)
        if not o or o.org_id!=user.org_id:raise HTTPException(404,'Order not found.')
        return o,store_access(db,user,o.store_id,action)
    def connection_access(db,user,cid):
        owner_only(user);c=db.get(Connection,cid)
        if not c or c.org_id!=user.org_id or not c.active:raise HTTPException(404,'Active connection not found.')
        return c
    def enqueue_sync(db,store):
        existing=db.scalar(select(Job).where(Job.store_id==store.id,Job.kind=='sync',Job.state.in_(['pending','running'])))
        if existing:return existing
        job=Job(org_id=store.org_id,store_id=store.id,kind='sync');db.add(job);db.flush();return job

    @app.get('/healthz')
    def health():return {'status':'ok'}
    @app.get('/api/setup/status')
    def setup_status():
        with database.Session() as db:return {'configured':bool(db.scalar(select(User.id).limit(1))),'demo':settings.demo,'version':'1.0.0'}
    @app.post('/api/setup')
    def setup(body:Setup,request:Request,response:Response):
        login_limit(request,'bootstrap')
        if not hmac.compare_digest(body.setup_code,settings.bootstrap_token):raise HTTPException(403,'Invalid setup code. Read it from the local launcher or secret manager.')
        password_valid(body.password);email=clean_email(body.email)
        with BOOT_LOCK,database.Session.begin() as db:
            boot=db.scalar(select(System).where(System.key=='bootstrap').with_for_update())
            if boot.value.get('complete') or db.scalar(select(User.id).limit(1)):raise HTTPException(409,'Workspace already configured.')
            org=Organization(name=body.workspace,demo=settings.demo);db.add(org);db.flush()
            user=User(org_id=org.id,name=body.name,email=email,password_hash=HASHER.hash(body.password),role='owner')
            db.add(user);db.flush();boot.value={'complete':True}
            session_create(db,user,response,request)
            audit(db,user,'workspace.created',details={'demo':settings.demo})
            if settings.demo:
                from .seed import seed_demo
                seed_demo(db,org,user)
            return {'user':user_public(user)}
    @app.post('/api/auth/login')
    def login(body:Login,request:Request,response:Response):
        email=body.email.strip().lower();login_limit(request,email)
        with database.Session.begin() as db:
            user=db.scalar(select(User).where(User.email==email))
            valid=verify_password(user.password_hash if user else DUMMY_HASH,body.password)
            if not user or not valid or not user.active:raise HTTPException(401,'Invalid credentials or verification code.')
            if user.mfa_secret and not body.code:raise HTTPException(403,'MFA_REQUIRED: Enter your authenticator or recovery code.')
            verified=mfa_check(db,user,body.code) if user.mfa_secret else False
            # Successful login invalidates any preexisting cookie session, preventing fixation.
            old=request.cookies.get(settings.cookie_name)
            if old:db.execute(delete(Session).where(Session.id==digest(old)))
            session_create(db,user,response,request,verified)
            audit(db,user,'auth.login')
            return {'user':user_public(user)}
    @app.get('/api/me')
    def me(ctx=Depends(context)):
        db,u,s=ctx;org=db.get(Organization,u.org_id)
        return {'user':user_public(u),'csrf':s.csrf,'permissions':sorted(ROLES[u.role]),'workspace':org.name,'demo':org.demo,
            'emergency_stop':org.emergency_stop,'stepup_until':s.stepup_until,'google_configured':bool(settings.google_client_id and settings.google_client_secret),
            'local_database':settings.database_url.startswith('sqlite'),'version':'1.0.0'}
    @app.post('/api/auth/logout')
    def logout(response:Response,ctx=Depends(context)):
        db,u,s=ctx;audit(db,u,'auth.logout');db.delete(s);response.delete_cookie(settings.cookie_name,path='/');return {'ok':True}
    @app.post('/api/auth/reauth')
    def reauth(body:Reauth,request:Request,ctx=Depends(context)):
        db,u,s=ctx;login_limit(request,u.email)
        if not verify_password(u.password_hash,body.password):raise HTTPException(401,'Invalid credentials or verification code.')
        s.mfa_verified=mfa_check(db,u,body.code) if u.mfa_secret else False
        s.stepup_until=now()+600;audit(db,u,'auth.step_up');return {'expires_at':s.stepup_until,'mfa_verified':s.mfa_verified}
    @app.post('/api/auth/password')
    def password_change(body:PasswordChange,request:Request,response:Response,ctx=Depends(context)):
        db,u,s=ctx;login_limit(request,u.email)
        if not verify_password(u.password_hash,body.password):raise HTTPException(401,'Invalid credentials or verification code.')
        verified=mfa_check(db,u,body.code) if u.mfa_secret else False
        password_valid(body.new_password);u.password_hash=HASHER.hash(body.new_password)
        db.execute(delete(Session).where(Session.user_id==u.id));session_create(db,u,response,request,verified)
        audit(db,u,'auth.password_changed');return {'ok':True}
    @app.post('/api/auth/mfa/setup')
    def mfa_setup(ctx=Depends(context)):
        db,u,s=ctx;stepup(s)
        if u.mfa_secret:raise HTTPException(409,'MFA is already enabled. Use the documented owner recovery process to replace it.')
        secret=base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
        u.pending_mfa=seal(settings,secret)
        return {'secret':secret,'uri':f'otpauth://totp/{quote("Xcomify:"+u.email)}?secret={secret}&issuer=Xcomify&algorithm=SHA1&digits=6&period=30'}
    @app.post('/api/auth/mfa/confirm')
    def mfa_confirm(body:Code,request:Request,ctx=Depends(context)):
        db,u,s=ctx;stepup(s);login_limit(request,u.email)
        if not u.pending_mfa:raise HTTPException(409,'Start MFA setup first.')
        counter=verify_totp(unseal(settings,u.pending_mfa),body.code)
        if counter is None:raise HTTPException(401,'Invalid authenticator code.')
        u.mfa_secret=u.pending_mfa;u.pending_mfa=None;u.mfa_counter=counter
        recovery=[secrets.token_hex(10).upper() for _ in range(8)]
        u.recovery_codes=[]
        db.execute(delete(RecoveryCode).where(RecoveryCode.user_id==u.id))
        for value in recovery:db.add(RecoveryCode(user_id=u.id,code_hash=digest(value)))
        s.mfa_verified=True;s.stepup_until=now()+600
        db.execute(delete(Session).where(Session.user_id==u.id,Session.id!=s.id))
        audit(db,u,'auth.mfa_enabled');return {'recovery_codes':recovery,'message':'Save these offline now. They are shown once.'}
    @app.get('/api/sessions')
    def sessions(ctx=Depends(context)):
        db,u,s=ctx
        return [{'id':x.id,'current':x.id==s.id,'created_at':x.created_at,'last_seen':x.last_seen,'expires_at':x.expires_at,'device':x.user_agent} for x in db.scalars(select(Session).where(Session.user_id==u.id,Session.expires_at>now()))]
    @app.post('/api/sessions/revoke-others')
    def revoke_others(ctx=Depends(context)):
        db,u,s=ctx;stepup(s);r=db.execute(delete(Session).where(Session.user_id==u.id,Session.id!=s.id));audit(db,u,'auth.other_sessions_revoked');return {'revoked':r.rowcount}

    @app.get('/api/stores')
    def stores(ctx=Depends(context)):
        db,u,s=ctx;ids=scoped_ids(db,u)
        return [store_public(db,u,x) for x in db.scalars(select(Store).where(Store.id.in_(ids)).order_by(Store.created_at))]
    @app.post('/api/stores')
    def create_store(body:StoreCreate,ctx=Depends(context)):
        db,u,s=ctx;owner_only(u)
        st=Store(org_id=u.org_id,**body.model_dump());db.add(st);db.flush();audit(db,u,'store.created',st.id)
        return store_public(db,u,st)
    @app.patch('/api/stores/{store_id}')
    def edit_store(store_id:str,body:StoreEdit,ctx=Depends(context)):
        db,u,s=ctx;owner_only(u);stepup(s);st=store_access(db,u,store_id)
        if st.revision!=body.revision:raise HTTPException(409,'Store changed. Refresh before editing.')
        if (st.currency!=body.currency or st.timezone!=body.timezone or st.include_filler!=body.include_filler) and db.scalar(select(PeriodClose).where(PeriodClose.store_id==st.id)):
            raise HTTPException(409,'Closed periods exist. Basis, currency and timezone changes require a separately reviewed migration.')
        if st.currency!=body.currency and db.scalar(select(Order.id).where(Order.store_id==st.id).limit(1)):
            raise HTTPException(409,'Cannot relabel currency on existing orders. Create a new store or migrate with explicit FX evidence.')
        for k,v in body.model_dump(exclude={'revision'}).items():setattr(st,k,v)
        st.revision+=1;st.financial_basis='business_contribution' if st.include_filler else 'operational_profit'
        if st.status!='active':st.writes_enabled=False
        db.flush();record_milestones(db,st,current_month(st),muted=True)
        audit(db,u,'store.settings_updated',st.id,details={'financial_approved':st.financial_approved,'include_filler':st.include_filler})
        return store_public(db,u,st)
    @app.get('/api/overview')
    def overview(month:str|None=None,currency:str|None=None,store_id:str|None=None,ctx=Depends(context)):
        db,u,s=ctx;ids=scoped_ids(db,u)
        if store_id:
            store_access(db,u,store_id);ids=[store_id]
        selected=list(db.scalars(select(Store).where(Store.id.in_(ids),Store.status!='archived')).all())
        if currency:selected=[x for x in selected if x.currency==currency]
        cards=[];groups={};total_orders=0;missing=0
        for st in selected:
            ss=summary(db,st,month or current_month(st));total_orders+=ss['orders'];missing+=ss['incomplete_orders']
            if can(u,'finance:view'):
                key=st.currency+':'+st.financial_basis
                g=groups.setdefault(key,{'currency':st.currency,'basis':st.financial_basis,'profit':Decimal(0),'earnings':Decimal(0),'target':Decimal(0),'targeted_profit':Decimal(0),'unknown_stores':0,'incomplete_orders':0})
                g['earnings']+=Decimal(ss['earnings']);g['incomplete_orders']+=ss['incomplete_orders']
                if ss['eligible_profit'] is None:g['unknown_stores']+=1
                else:g['profit']+=Decimal(ss['eligible_profit'])
                if Decimal(ss['target'])>0 and ss['eligible_profit'] is not None:
                    g['target']+=Decimal(ss['target']);g['targeted_profit']+=Decimal(ss['eligible_profit'])
            else:
                ss={k:v for k,v in ss.items() if k in {'store_id','store','currency','month','orders','last_sync','stale'}}
            if not can(u,'costs:view'):
                ss={k:v for k,v in ss.items() if k not in {'costs','excluded_filler'}}
            cards.append({**ss,'status':st.status,'source':st.source,'marketplace':st.marketplace,'writes_enabled':st.writes_enabled})
        grouped=[]
        for g in groups.values():
            pct=g['targeted_profit']/g['target']*100 if g['target']>0 else None
            grouped.append({**{k:(fmt(v) if isinstance(v,Decimal) else v) for k,v in g.items()},'attainment':fmt(pct)})
        return {'stores':cards,'groups':grouped,'total_orders':total_orders,'active_stores':sum(x.status=='active' for x in selected),
            'missing_cost_or_issues':missing,'generated_at':now(),'month':month,'finance_visible':can(u,'finance:view')}
    @app.get('/api/stores/{store_id}/summary')
    def store_summary(store_id:str,month:str|None=None,ctx=Depends(context)):
        db,u,s=ctx;st=store_access(db,u,store_id,'finance:view');result=summary(db,st,month or current_month(st))
        return result if can(u,'costs:view') else {k:v for k,v in result.items() if k not in {'costs','excluded_filler'}}

    @app.get('/api/orders')
    def orders(store_id:str|None=None,month:str|None=None,q:str='',attention:str|None=None,page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),ctx=Depends(context)):
        db,u,s=ctx;require(u,'orders:view');ids=scoped_ids(db,u)
        if store_id:store_access(db,u,store_id);ids=[store_id]
        query=select(Order).where(Order.store_id.in_(ids))
        if month:month_valid(month);query=query.where(Order.sold_on.like(month+'%'))
        if q:
            term='%'+q[:120].replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
            query=query.where(or_(Order.ebay_id.ilike(term,escape='\\'),Order.supplier_ref.ilike(term,escape='\\'),Order.tracking.ilike(term,escape='\\'),Order.title.ilike(term,escape='\\')))
        if attention=='tracking':query=query.where(Order.tracking=='',Order.status.notin_(['Cancelled','Refunded']))
        if attention=='cost':
            require(u,'costs:view');query=query.where(or_(Order.cost.is_(None),Order.earnings.is_(None),Order.observed==False))
        count=db.scalar(select(func.count()).select_from(query.subquery()))
        rows=db.scalars(query.order_by(Order.sold_on.desc(),Order.id).offset((page-1)*page_size).limit(page_size)).all()
        mapping={x.id:x for x in db.scalars(select(Store).where(Store.id.in_(ids)))}
        return {'total':count,'page':page,'page_size':page_size,'rows':[order_public(u,x,mapping[x.store_id]) for x in rows]}
    @app.get('/api/orders/{order_id}')
    def order_details(order_id:str,ctx=Depends(context)):
        db,u,s=ctx;o,st=find_order(db,u,order_id)
        d=order_public(u,o,st,True)
        d['pending']=[{'id':i.id,'state':i.state,'fields':list(i.proposed),'created_at':i.created_at} for i in db.scalars(select(WriteIntent).where(WriteIntent.order_id==o.id,WriteIntent.state.notin_(['confirmed','cancelled'])))]
        return d
    @app.post('/api/stores/{store_id}/orders')
    def order_add(store_id:str,body:OrderCreate,ctx=Depends(context)):
        db,u,s=ctx;st=store_access(db,u,store_id,'orders:edit')
        if st.source!='local':raise HTTPException(409,'Create rows through your existing Sheet/extension. Remote appends are intentionally disabled.')
        if db.get(PeriodClose,(st.id,body.sold_on[:7])):raise HTTPException(409,'This period is closed.')
        if not can(u,'costs:view') and (body.earnings is not None or body.cost is not None or any(Decimal(getattr(body,k)) for k in ['extra','refund','credit','filler'])):
            raise HTTPException(403,'Your role cannot enter financial fields.')
        values=body.model_dump()
        for k in MONEY_FIELDS:values[k]=money(values[k],optional=k in {'earnings','cost'})
        order=Order(org_id=u.org_id,store_id=store_id,**values);db.add(order);db.flush()
        record_milestones(db,st,body.sold_on[:7]);audit(db,u,'order.created',st.id,order.id)
        return order_public(u,order,st,True)
    @app.patch('/api/orders/{order_id}')
    def order_edit(order_id:str,body:OrderEdit,ctx=Depends(context)):
        db,u,s=ctx;o,st=find_order(db,u,order_id,'orders:edit')
        if o.revision!=body.revision:raise HTTPException(409,'Order changed. Refresh and review the latest data.')
        allowed={'sold_on','title','postcode','supplier_ref','tracking','courier','status','notes'}|MONEY_FIELDS
        if not set(body.changes)<=allowed:raise HTTPException(422,'One or more fields cannot be edited.')
        if set(body.changes)&MONEY_FIELDS:
            require(u,'costs:view');stepup(s)
        if db.get(PeriodClose,(st.id,o.sold_on[:7])):raise HTTPException(409,'This period is closed; add an authorized current-period adjustment instead.')
        values={k:getattr(o,k) for k in OrderCreate.model_fields}
        values.update(body.changes)
        for k in MONEY_FIELDS:values[k]=fmt(values[k]) if isinstance(values[k],Decimal) else values[k]
        validated=OrderCreate(**values).model_dump()
        if db.get(PeriodClose,(st.id,validated['sold_on'][:7])):raise HTTPException(409,'Destination period is closed.')
        changes={k:validated[k] for k in body.changes}
        if o.origin=='google' and set(changes)!={'notes'}:
            if len(changes)!=1:raise HTTPException(422,'Propose one mapped cell at a time to make remote outcomes unambiguous.')
            name=next(iter(changes))
            if name not in WRITABLE_FIELDS:raise HTTPException(422,'This Sheet-controlled field is read-only in this release.')
            prior=db.scalar(select(WriteIntent).where(WriteIntent.org_id==u.org_id,WriteIntent.idempotency_key==body.idempotency_key))
            if prior:
                if prior.order_id!=o.id or prior.proposed!=changes:raise HTTPException(409,'Idempotency key belongs to a different change.')
                return {'state':prior.state,'intent_id':prior.id}
            intent=WriteIntent(org_id=u.org_id,store_id=st.id,order_id=o.id,actor_id=u.id,
                base={name:o.source_values.get(name,fmt(getattr(o,name)) if name in MONEY_FIELDS else getattr(o,name))},
                proposed=changes,postcode=o.postcode,mapping_version=st.mapping_version,reason=body.reason,idempotency_key=body.idempotency_key)
            db.add(intent);db.flush();audit(db,u,'write.proposed',st.id,intent.id,{'fields':list(changes)})
            return {'state':'proposed','intent_id':intent.id,'message':'Proposal saved. No Google cell has been changed.'}
        before={k:fmt(getattr(o,k)) for k in changes if k in MONEY_FIELDS}
        for k in MONEY_FIELDS&changes.keys():changes[k]=money(changes[k],optional=k in {'earnings','cost'})
        result=db.execute(update(Order).where(Order.id==o.id,Order.revision==body.revision).values(**changes,revision=body.revision+1,updated_at=now()))
        if result.rowcount!=1:raise HTTPException(409,'Order changed concurrently. No update was applied.')
        db.flush();db.refresh(o);record_milestones(db,st,o.sold_on[:7])
        audit(db,u,'order.updated',st.id,o.id,{'fields':list(changes),'reason':body.reason,'financial_before':before,
            'financial_after':{k:fmt(v) for k,v in changes.items() if k in MONEY_FIELDS}})
        return {'state':'confirmed','order':order_public(u,o,st,True)}
    @app.post('/api/stores/{store_id}/csv-import')
    def csv_import(store_id:str,body:CSVImport,ctx=Depends(context)):
        db,u,s=ctx;st=store_access(db,u,store_id,'orders:edit');require(u,'costs:view')
        if st.source!='local':raise HTTPException(409,'CSV import is only available for local stores; existing Google workflows stay untouched.')
        rows=list(csv.DictReader(io.StringIO(body.csv_text.lstrip('\ufeff'))))
        if len(rows)>1000:raise HTTPException(422,'Import at most 1000 rows per batch.')
        parsed=[];errors=[];seen=set()
        for idx,row in enumerate(rows,2):
            try:
                obj=OrderCreate(**{k:(v if v!='' else None) for k,v in row.items() if k in OrderCreate.model_fields and (v!='' or k in {'cost','earnings'})})
                if obj.ebay_id in seen or db.scalar(select(Order.id).where(Order.store_id==st.id,Order.ebay_id==obj.ebay_id)):raise ValueError('Duplicate order ID; no overwrite.')
                if db.get(PeriodClose,(st.id,obj.sold_on[:7])):raise ValueError('Financial period is closed.')
                seen.add(obj.ebay_id);parsed.append(obj)
            except Exception as exc:errors.append({'row':idx,'error':str(exc)[:240]})
        if body.commit:
            stepup(s)
            if errors:raise HTTPException(422,{'message':'Import blocked; correct all preview errors.','errors':errors})
            for obj in parsed:
                values=obj.model_dump()
                for k in MONEY_FIELDS:values[k]=money(values[k],optional=k in {'earnings','cost'})
                db.add(Order(org_id=u.org_id,store_id=st.id,**values))
            db.flush()
            for m in {x.sold_on[:7] for x in parsed}:record_milestones(db,st,m,muted=True)
            audit(db,u,'orders.csv_import',st.id,details={'rows':len(parsed)})
        return {'valid_rows':len(parsed),'errors':errors[:100],'committed':body.commit,'preview':[x.model_dump() for x in parsed[:5]]}

    @app.post('/api/stores/{store_id}/targets')
    def target_set(store_id:str,body:TargetSet,ctx=Depends(context)):
        db,u,s=ctx;st=store_access(db,u,store_id,'targets:edit')
        if db.get(PeriodClose,(st.id,body.month)):raise HTTPException(409,'Cannot revise a target in a closed period.')
        t=db.scalar(select(Target).where(Target.store_id==st.id,Target.month==body.month))
        if t:
            if body.version!=t.version:raise HTTPException(409,'Target changed. Refresh the current version before revising.')
            old=fmt(t.amount);t.amount=money(body.amount);t.version+=1;t.updated_at=now()
        else:
            old=None;t=Target(org_id=u.org_id,store_id=st.id,month=body.month,amount=money(body.amount));db.add(t)
        db.flush();record_milestones(db,st,body.month,muted=True)
        audit(db,u,'target.revised' if old is not None else 'target.created',st.id,t.id,{'month':body.month,'old':old,'new':body.amount,'reason':body.reason})
        return summary(db,st,body.month)
    @app.get('/api/financials/entries')
    def financial_entries(store_id:str|None=None,month:str|None=None,ctx=Depends(context)):
        db,u,s=ctx;require(u,'finance:view');ids=scoped_ids(db,u)
        if store_id:store_access(db,u,store_id);ids=[store_id]
        q=select(FinancialEntry).where(FinancialEntry.store_id.in_(ids))
        if month:month_valid(month);q=q.where(FinancialEntry.recognized_on.like(month+'%'))
        return [{'id':x.id,'store_id':x.store_id,'amount':fmt(x.amount),'date':x.recognized_on,'reason':x.reason,'created_at':x.created_at} for x in db.scalars(q.order_by(FinancialEntry.created_at.desc()).limit(500))]
    @app.post('/api/stores/{store_id}/adjustments')
    def adjustment_add(store_id:str,body:Adjustment,ctx=Depends(context)):
        db,u,s=ctx;st=store_access(db,u,store_id,'finance:adjust');stepup(s)
        if db.get(PeriodClose,(st.id,body.recognized_on[:7])):raise HTTPException(409,'Choose an open recognition period.')
        exists=db.scalar(select(FinancialEntry).where(FinancialEntry.store_id==st.id,FinancialEntry.idempotency_key==body.idempotency_key))
        if exists:
            if exists.amount!=money(body.amount) or exists.reason!=body.reason or exists.recognized_on!=body.recognized_on:raise HTTPException(409,'Idempotency key conflict.')
            return {'id':exists.id,'duplicate':True}
        row=FinancialEntry(org_id=u.org_id,store_id=st.id,amount=money(body.amount),recognized_on=body.recognized_on,reason=body.reason,idempotency_key=body.idempotency_key,user_id=u.id)
        db.add(row);db.flush();record_milestones(db,st,body.recognized_on[:7]);audit(db,u,'finance.adjustment_created',st.id,row.id,{'amount':body.amount,'reason':body.reason})
        return {'id':row.id}
    @app.post('/api/stores/{store_id}/close/{month}')
    def close_period(store_id:str,month:str,body:Reason,ctx=Depends(context)):
        db,u,s=ctx;owner_only(u);stepup(s);st=store_access(db,u,store_id);ss=summary(db,st,month)
        if not ss['financial_approved'] or ss['incomplete_orders'] or ss['stale']:raise HTTPException(409,'Reconcile missing costs, source issues and freshness before closing.')
        if month>=current_month(st):raise HTTPException(409,'Only completed prior months may be closed.')
        if db.get(PeriodClose,(st.id,month)):raise HTTPException(409,'Period is already closed.')
        db.add(PeriodClose(store_id=st.id,month=month,snapshot=ss,user_id=u.id));audit(db,u,'finance.period_closed',st.id,details={'month':month,'reason':body.reason})
        return {'closed':True,'snapshot':ss}

    @app.get('/api/team')
    def team(ctx=Depends(context)):
        db,u,s=ctx
        if u.role not in {'owner','admin','manager'}:raise HTTPException(403,'Team administration is not available to this role.')
        ids=scoped_ids(db,u);q=select(User).where(User.org_id==u.org_id)
        users=db.scalars(q).all();out=[]
        for x in users:
            assigned=[a.store_id for a in db.scalars(select(Assignment).where(Assignment.user_id==x.id))]
            if u.role!='owner' and not set(assigned)&set(ids) and x.id!=u.id:continue
            out.append({**user_public(x),'stores':assigned if u.role=='owner' else [sid for sid in assigned if sid in ids]})
        return out
    @app.post('/api/team/invite')
    def invite(body:Invite,ctx=Depends(context)):
        db,u,s=ctx;owner_only(u);stepup(s);email=clean_email(body.email)
        if db.scalar(select(User.id).where(User.email==email)):raise HTTPException(409,'A user with this email already exists.')
        for sid in body.stores:store_access(db,u,sid)
        token=secrets.token_urlsafe(32)
        inv=Invitation(org_id=u.org_id,email=email,role=body.role,stores=list(set(body.stores)),token_hash=digest(token),expires_at=now()+48*3600)
        db.add(inv);db.flush();audit(db,u,'user.invited',object_id=inv.id,details={'role':body.role,'store_count':len(body.stores)})
        return {'invitation_url':settings.base_url+'/#invite='+token,'expires_at':inv.expires_at,'delivery':'Copy and privately send this single-use link; no email has been sent.'}
    @app.post('/api/invitations/accept')
    def accept_invite(body:AcceptInvite,request:Request,response:Response):
        login_limit(request,'invite');password_valid(body.password)
        with database.Session.begin() as db:
            inv=db.scalar(select(Invitation).where(Invitation.token_hash==digest(body.token)).with_for_update())
            if not inv or inv.used_at or inv.expires_at<now():raise HTTPException(400,'Invitation expired or already used.')
            changed=db.execute(update(Invitation).where(Invitation.id==inv.id,Invitation.used_at.is_(None)).values(used_at=now()))
            if changed.rowcount!=1:raise HTTPException(409,'Invitation already used.')
            user=User(org_id=inv.org_id,email=inv.email,name=body.name,role=inv.role,password_hash=HASHER.hash(body.password));db.add(user);db.flush()
            for sid in inv.stores:
                st=db.get(Store,sid)
                if st and st.org_id==inv.org_id:db.add(Assignment(user_id=user.id,store_id=sid))
            session_create(db,user,response,request);audit(db,user,'user.invitation_accepted');return {'user':user_public(user)}
    @app.patch('/api/team/{user_id}')
    def edit_user(user_id:str,body:UserEdit,ctx=Depends(context)):
        db,u,s=ctx;owner_only(u);stepup(s)
        target=db.get(User,user_id)
        if not target or target.org_id!=u.org_id:raise HTTPException(404,'User not found.')
        if target.role=='owner':raise HTTPException(403,'Owner removal or transfer requires the offline recovery procedure.')
        for sid in body.stores:store_access(db,u,sid)
        target.active=body.active;target.role=body.role
        db.execute(delete(Assignment).where(Assignment.user_id==target.id))
        for sid in set(body.stores):db.add(Assignment(user_id=target.id,store_id=sid))
        db.execute(delete(Session).where(Session.user_id==target.id))
        audit(db,u,'user.access_changed',object_id=target.id,details={'active':body.active,'role':body.role,'store_count':len(body.stores)})
        return {'user':user_public(target),'sessions_revoked':True}
    @app.get('/api/tasks')
    def tasks(ctx=Depends(context)):
        db,u,s=ctx;ids=scoped_ids(db,u)
        data=[]
        for t in db.scalars(select(Task).where(Task.store_id.in_(ids)).order_by(Task.created_at.desc()).limit(500)):
            assigned=db.get(User,t.assignee_id) if t.assignee_id else None
            data.append({'id':t.id,'store_id':t.store_id,'title':t.title,'status':t.status,'due_on':t.due_on,'assignee_id':t.assignee_id,
                'assignee':assigned.name if assigned else 'Unassigned','created_at':t.created_at})
        return data
    @app.post('/api/tasks')
    def task_add(body:TaskCreate,ctx=Depends(context)):
        db,u,s=ctx;store_access(db,u,body.store_id,'tasks:edit')
        if body.assignee_id:
            assigned=db.get(User,body.assignee_id)
            if not assigned or assigned.org_id!=u.org_id or not assigned.active:raise HTTPException(422,'Invalid task assignee.')
            store_access(db,assigned,body.store_id)
            if u.role=='operations' and assigned.id!=u.id:raise HTTPException(403,'Operations employees may create tasks for themselves only.')
        task=Task(org_id=u.org_id,created_by=u.id,**body.model_dump());db.add(task);db.flush();audit(db,u,'task.created',task.store_id,task.id)
        return {'id':task.id}
    @app.patch('/api/tasks/{task_id}')
    def task_edit(task_id:str,body:TaskEdit,ctx=Depends(context)):
        db,u,s=ctx;t=db.get(Task,task_id)
        if not t or t.org_id!=u.org_id:raise HTTPException(404,'Task not found.')
        store_access(db,u,t.store_id,'tasks:edit')
        if u.role=='operations' and t.assignee_id!=u.id and t.created_by!=u.id:raise HTTPException(403,'Only your assigned or created tasks can be changed.')
        t.status=body.status;audit(db,u,'task.status_changed',t.store_id,t.id,{'status':body.status});return {'ok':True}

    @app.get('/api/connections')
    def connections(ctx=Depends(context)):
        db,u,s=ctx;owner_only(u)
        return [{'id':c.id,'name':c.name,'scope':c.scope,'active':c.active,'created_at':c.created_at} for c in db.scalars(select(Connection).where(Connection.org_id==u.org_id))]
    @app.post('/api/google/start')
    def google_start(ctx=Depends(context)):
        db,u,s=ctx;owner_only(u);stepup(s)
        if settings.demo:raise HTTPException(403,'Google connections are disabled in the isolated demo workspace.')
        if not settings.google_client_id or not settings.google_client_secret:raise HTTPException(503,'Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the private environment first. See the Google setup guide.')
        state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        db.add(OAuthState(state_hash=digest(state),session_id=s.id,verifier=seal(settings,verifier),expires_at=now()+600))
        args={'client_id':settings.google_client_id,'redirect_uri':settings.redirect_uri,'response_type':'code','scope':SCOPE,
            'access_type':'offline','prompt':'consent select_account','state':state,'code_challenge':challenge,'code_challenge_method':'S256'}
        audit(db,u,'google.authorization_started')
        return {'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(args),
            'scope_notice':'The Sheets scope can access spreadsheets granted to the authorizing Google account. The app restricts use to configured file IDs; this is not a per-tab Google permission.'}
    @app.get('/api/google/callback')
    def google_callback(request:Request,state:str='',code:str='',error:str='',ctx=Depends(context)):
        db,u,s=ctx;owner_only(u)
        st=db.get(OAuthState,digest(state))
        if not st or st.session_id!=s.id or st.expires_at<now():raise HTTPException(400,'Invalid or expired Google authorization state.')
        verifier=unseal(settings,st.verifier);db.delete(st);db.commit()
        if error:return RedirectResponse('/#google=cancelled',303)
        if not code or len(code)>4096:raise HTTPException(400,'Google authorization did not return a valid code.')
        try:
            r=httpx.post(TOKEN_URL,data={'code':code,'client_id':settings.google_client_id,'client_secret':settings.google_client_secret,
                'redirect_uri':settings.redirect_uri,'grant_type':'authorization_code','code_verifier':verifier},timeout=30)
        except httpx.HTTPError:raise HTTPException(502,'Google token exchange failed. Start authorization again.')
        if r.status_code!=200:raise HTTPException(400,'Google code exchange failed. Verify client settings and redirect URI.')
        tokens=r.json()
        if not tokens.get('refresh_token') or SCOPE not in tokens.get('scope','').split():raise HTTPException(400,'Offline Sheets authorization was not granted. Reauthorize with consent.')
        stored={'refresh_token':tokens['refresh_token'],'access_token':tokens['access_token'],'expires_at':time.time()+tokens.get('expires_in',3600)}
        c=Connection(org_id=u.org_id,name='Google Sheets '+datetime.now(timezone.utc).strftime('%d %b %Y %H:%M'),credential=seal(settings,json.dumps(stored)),scope=tokens['scope'])
        db.add(c);db.flush();audit(db,u,'google.connected',object_id=c.id)
        return RedirectResponse('/#google=connected',303)
    @app.post('/api/connections/{connection_id}/disconnect')
    def disconnect(connection_id:str,body:Reason,ctx=Depends(context)):
        db,u,s=ctx;owner_only(u);stepup(s);c=connection_access(db,u,connection_id)
        c.active=False;c.credential='REVOKED_LOCALLY'
        for st in db.scalars(select(Store).where(Store.connection_id==c.id)):
            st.writes_enabled=False;st.sync_error='Google connection disconnected locally.'
        audit(db,u,'google.disconnected',object_id=c.id,details={'reason':body.reason})
        return {'disconnected':True,'note':'Local credentials erased. Remove the app in your Google account permissions to revoke the external grant as well.'}
    @app.get('/api/connections/{connection_id}/metadata')
    def metadata(connection_id:str,spreadsheet_id:str,ctx=Depends(context)):
        db,u,s=ctx;c=connection_access(db,u,connection_id)
        adapter=app.state.adapter_factory(c)
        try:return adapter.metadata(spreadsheet_id)
        finally:
            if isinstance(adapter,GoogleSheets):adapter.http.close()
    def mapping_snapshot(db,u,body):
        c=connection_access(db,u,body.connection_id)
        adapter=app.state.adapter_factory(c)
        try:snap=adapter.snapshot(body.spreadsheet_id,body.sheet_id,body.max_rows)
        finally:
            if isinstance(adapter,GoogleSheets):adapter.http.close()
        return snap
    @app.post('/api/stores/{store_id}/mapping-preview')
    def mapping_preview(store_id:str,body:Mapping,ctx=Depends(context)):
        db,u,s=ctx;owner_only(u);store_access(db,u,store_id)
        snap=mapping_snapshot(db,u,body)
        mock=SimpleNamespace(header_row=body.header_row,mapping={'fields':{k:v.model_dump() for k,v in body.fields.items()},'date_format':body.date_format})
        records,errors=mapped_records(mock,snap)
        return {'title':snap.title,'rows':len(snap.rows),'orders':len(records),'errors':errors[:100],
            'sample':[{k:(fmt(v) if isinstance(v,Decimal) else v) for k,v in r.items()} for r in records[:5]],
            'dynamic_formula':snap.dynamic_formula,'protected_ranges':len(snap.protected),'writes_performed':0}
    @app.post('/api/stores/{store_id}/mapping')
    def mapping_save(store_id:str,body:Mapping,ctx=Depends(context)):
        db,u,s=ctx;owner_only(u);stepup(s);st=store_access(db,u,store_id)
        if settings.demo:raise HTTPException(403,'Demo cannot connect live Sheets.')
        if db.scalar(select(Store.id).where(Store.org_id==u.org_id,Store.id!=st.id,Store.spreadsheet_id==body.spreadsheet_id,Store.sheet_id==body.sheet_id)):
            raise HTTPException(409,'This file and tab are already connected to another store. Duplicate mappings could double count orders.')
        snap=mapping_snapshot(db,u,body)
        mapping={'fields':{k:v.model_dump() for k,v in body.fields.items()},'date_format':body.date_format}
        mock=SimpleNamespace(header_row=body.header_row,mapping=mapping)
        validate_headers(mock,snap)
        st.mapping=mapping;st.mapping_version+=1;st.header_row=body.header_row;st.source='google'
        st.spreadsheet_id=body.spreadsheet_id;st.sheet_id=body.sheet_id;st.tab_name=snap.title;st.max_rows=body.max_rows
        st.connection_id=body.connection_id;st.writes_enabled=False;st.writer_contract=False;st.gates={};st.revision+=1
        st.last_sync=None;st.sync_error=None;enqueue_sync(db,st)
        audit(db,u,'mapping.saved',st.id,details={'mapping_version':st.mapping_version,'write_enabled':False})
        return {'mapped':True,'message':'Read-only import queued. Write-back remains disabled.'}
    @app.get('/api/connections/{connection_id}/sample')
    def sheet_sample(connection_id:str,spreadsheet_id:str,sheet_id:int,header_row:int=1,ctx=Depends(context)):
        db,u,s=ctx;c=connection_access(db,u,connection_id)
        if not 1<=header_row<=100:raise HTTPException(422,'Invalid header row.')
        adapter=app.state.adapter_factory(c)
        try:snap=adapter.snapshot(spreadsheet_id,sheet_id,50000)
        finally:
            if isinstance(adapter,GoogleSheets):adapter.http.close()
        headers=[{'column':i,'header':str(c.value),'formula':bool(c.formula)} for i,c in enumerate(snap.rows[header_row-1] if len(snap.rows)>=header_row else []) if str(c.value).strip()]
        return {'headers':headers,'title':snap.title,'sample':[[str(c.value) for c in r] for r in snap.rows[header_row:header_row+3]],'dynamic_formula':snap.dynamic_formula}
    @app.post('/api/stores/{store_id}/write-enable')
    def write_enable(store_id:str,body:WriteEnable,ctx=Depends(context)):
        db,u,s=ctx;owner_only(u);stepup(s,mfa=body.enabled);st=store_access(db,u,store_id)
        if body.enabled:
            if settings.demo or st.source!='google':raise HTTPException(409,'Live write-back requires a non-demo Google-connected store.')
            if not st.last_sync or st.sync_error or now()-st.last_sync>max(600,st.poll_seconds*3):raise HTTPException(409,'A fresh successful read-only reconciliation is required.')
            if not st.financial_approved:raise HTTPException(409,'Approve the financial basis first.')
            checks=body.model_dump(exclude={'enabled','reason'})
            if not all(checks.values()):raise HTTPException(409,'Complete every write-enable checklist gate first.')
            if not any(m['ownership']=='app' and k in WRITABLE_FIELDS for k,m in st.mapping.get('fields',{}).items()):raise HTTPException(409,'No application-owned writable field is configured.')
            st.writer_contract=True;st.gates={**checks,'attested_by':u.id,'attested_at':now(),'reason':body.reason}
        st.writes_enabled=body.enabled;audit(db,u,'store.write_gate_changed',st.id,details={'enabled':body.enabled,'reason':body.reason})
        return {'writes_enabled':st.writes_enabled,'global_write_stop':db.get(Organization,u.org_id).emergency_stop,
            'note':'Owner attestations are recorded; they are not an independent security certification.'}
    @app.post('/api/stores/{store_id}/sync')
    def sync_now(store_id:str,ctx=Depends(context)):
        db,u,s=ctx;st=store_access(db,u,store_id,'sync:run')
        if st.source!='google':raise HTTPException(409,'This is a local-data store, not a connected Google Sheet.')
        if st.status!='active':raise HTTPException(409,'Resume the store before syncing.')
        job=enqueue_sync(db,st);audit(db,u,'sync.requested',st.id,job.id);return {'job_id':job.id,'state':job.state}
    @app.get('/api/sync')
    def sync_status(ctx=Depends(context)):
        db,u,s=ctx;require(u,'sync:run');ids=scoped_ids(db,u)
        jobs=[{'id':j.id,'store_id':j.store_id,'kind':j.kind,'state':j.state,'attempts':j.attempts,'created_at':j.created_at,'finished_at':j.finished_at,'error':j.error,'result':j.result} for j in db.scalars(select(Job).where(Job.store_id.in_(ids)).order_by(Job.created_at.desc()).limit(100))]
        intents=[]
        for i in db.scalars(select(WriteIntent).where(WriteIntent.store_id.in_(ids)).order_by(WriteIntent.created_at.desc()).limit(100)):
            row={'id':i.id,'store_id':i.store_id,'order_id':i.order_id,'actor_id':i.actor_id,'state':i.state,'fields':list(i.proposed),'reason':i.reason,'error':i.error,'created_at':i.created_at}
            if can(u,'costs:view') or not set(i.proposed)&MONEY_FIELDS:row.update(base=i.base,proposed=i.proposed)
            intents.append(row)
        lease=db.get(Lease,'worker')
        return {'jobs':jobs,'intents':intents,'worker_alive':bool(lease and lease.expires_at>now()),'worker_expires_at':lease.expires_at if lease else None}
    def find_intent(db,u,iid,permission='orders:edit'):
        i=db.get(WriteIntent,iid)
        if not i or i.org_id!=u.org_id:raise HTTPException(404,'Change not found.')
        st=store_access(db,u,i.store_id,permission);return i,st
    @app.post('/api/write-intents/{intent_id}/approve')
    def approve_intent(intent_id:str,body:WriteApproval,ctx=Depends(context)):
        db,u,s=ctx;i,st=find_intent(db,u,intent_id,'writes:approve');stepup(s,mfa=True)
        if i.state!='proposed':raise HTTPException(409,'Only a fresh proposal can be approved. Reconcile conflicts first.')
        if u.id==i.actor_id and (u.role!='owner' or not body.owner_override):raise HTTPException(403,'Independent approval required, or an explicit owner override with reason.')
        if db.get(Organization,u.org_id).emergency_stop or not st.writes_enabled or not st.writer_contract:raise HTTPException(409,'Write-stop is active or this store has not passed write-enable gates.')
        name=next(iter(i.proposed))
        if st.mapping.get('fields',{}).get(name,{}).get('ownership')!='app':raise HTTPException(409,'This field remains Sheet-owned; preserve the extension workflow and edit in the source Sheet.')
        i.approver_id=u.id;i.state='queued';i.updated_at=now()
        job=Job(org_id=u.org_id,store_id=st.id,kind='write',payload={'intent_id':i.id});db.add(job)
        audit(db,u,'write.approved',st.id,i.id,{'owner_override':body.owner_override,'reason':body.reason})
        return {'state':'queued','message':'Queued, not yet written or confirmed.'}
    @app.post('/api/write-intents/{intent_id}/cancel')
    def cancel_intent(intent_id:str,body:Reason,ctx=Depends(context)):
        db,u,s=ctx;i,st=find_intent(db,u,intent_id)
        if i.actor_id!=u.id:require(u,'writes:approve')
        if i.state in {'submitting','verifying','confirmed'}:raise HTTPException(409,'A submitted or confirmed write cannot be recalled. Reconcile its remote outcome.')
        i.state='cancelled';i.error=body.reason;i.updated_at=now();audit(db,u,'write.cancelled',st.id,i.id,{'reason':body.reason})
        return {'state':i.state,'note':'Cancellation does not undo any previously submitted remote change.'}
    @app.post('/api/write-intents/{intent_id}/reconcile')
    def reconcile_intent(intent_id:str,ctx=Depends(context)):
        db,u,s=ctx;i,st=find_intent(db,u,intent_id,'writes:approve');stepup(s)
        if i.state not in {'outcome_unknown','conflict','failed'}:raise HTTPException(409,'Only an unresolved write can be reconciled.')
        c=connection_access(db,u,st.connection_id)
        adapter=app.state.adapter_factory(c)
        try:snap=adapter.snapshot(st.spreadsheet_id,st.sheet_id,st.max_rows)
        finally:
            if isinstance(adapter,GoogleSheets):adapter.http.close()
        fields=validate_headers(st,snap);o=db.get(Order,i.order_id)
        matches=[r for r in range(st.header_row,len(snap.rows)) if str(snap.value(r,fields['ebay_id']['column'])).strip()==o.ebay_id]
        if len(matches)!=1:raise HTTPException(409,'Unique source identity cannot be resolved.')
        row=matches[0]
        if 'postcode' in fields and norm_postcode(snap.value(row,fields['postcode']['column']))!=norm_postcode(i.postcode):raise HTTPException(409,'Source postcode changed. Make a new reviewed proposal.')
        name,val=next(iter(i.proposed.items()));current=canonical(name,snap.value(row,fields[name]['column']))
        if current==canonical(name,val):i.state='confirmed';i.error='Proposed value observed during reconciliation; no write submitted.'
        elif current==canonical(name,i.base.get(name)):i.state='proposed';i.approver_id=None;i.error='Base value observed. Fresh approval is required before another attempt.'
        else:i.state='conflict';i.error='Source differs from both base and proposal. Cancel and create a new proposal after review.'
        do_sync(db,st,snap);audit(db,u,'write.reconciled',st.id,i.id,{'outcome':i.state});return {'state':i.state,'message':i.error}

    @app.post('/api/celebrations/claim')
    def claim_celebrations(ctx=Depends(context)):
        db,u,s=ctx;require(u,'finance:view');ids=scoped_ids(db,u)
        seen=select(CelebrationSeen.notification_id).where(CelebrationSeen.user_id==u.id)
        candidates=list(db.scalars(select(Notification).where(Notification.org_id==u.org_id,
            Notification.store_id.in_(ids),Notification.id.notin_(seen),Notification.dedupe_key.like('milestone:%'),
            Notification.created_at>=now()-86400).order_by(Notification.created_at.desc()).limit(20)))
        events=[]
        for n in candidates:
            db.add(CelebrationSeen(user_id=u.id,notification_id=n.id))
            st=db.get(Store,n.store_id);parts=n.dedupe_key.split(':')
            if len(parts)!=4 or parts[2]!=current_month(st):continue
            ss=summary(db,st,parts[2]);level=int(parts[3])
            if ss['celebration_eligible'] and ss['attainment'] is not None and Decimal(ss['attainment'])>=level:
                events.append({'id':n.id,'store':st.name,'level':level,'title':n.title})
        # One short animation per claim; lower milestones remain in notification history.
        return {'events':sorted(events,key=lambda x:x['level'],reverse=True)[:1]}

    @app.get('/api/notifications')
    def notifications(ctx=Depends(context)):
        db,u,s=ctx;ids=scoped_ids(db,u)
        q=select(Notification).where(Notification.org_id==u.org_id,or_(Notification.store_id.in_(ids),Notification.store_id.is_(None) if u.role=='owner' else False))
        if not can(u,'finance:view'):q=q.where(Notification.financial==False)
        reads=set(db.scalars(select(NotificationRead.notification_id).where(NotificationRead.user_id==u.id)))
        return [{'id':n.id,'store_id':n.store_id,'title':n.title,'body':n.body,'severity':n.severity,'created_at':n.created_at,'read':n.id in reads} for n in db.scalars(q.order_by(Notification.created_at.desc()).limit(100))]
    @app.post('/api/notifications/{notification_id}/read')
    def notification_read(notification_id:str,ctx=Depends(context)):
        db,u,s=ctx;n=db.get(Notification,notification_id)
        if not n or n.org_id!=u.org_id:raise HTTPException(404,'Notification not found.')
        if n.store_id:store_access(db,u,n.store_id)
        else:owner_only(u)
        if n.financial:require(u,'finance:view')
        if not db.get(NotificationRead,(u.id,n.id)):db.add(NotificationRead(user_id=u.id,notification_id=n.id))
        return {'ok':True}
    @app.get('/api/audit')
    def audit_list(page:int=Query(1,ge=1),ctx=Depends(context)):
        db,u,s=ctx;require(u,'audit:view');ids=scoped_ids(db,u)
        q=select(Audit).where(Audit.org_id==u.org_id)
        if u.role!='owner':q=q.where(Audit.store_id.in_(ids))
        total=db.scalar(select(func.count()).select_from(q.subquery()))
        events=[]
        for a in db.scalars(q.order_by(Audit.seq.desc()).offset((page-1)*50).limit(50)):
            actor=db.get(User,a.actor_id) if a.actor_id else None
            events.append({'seq':a.seq,'store_id':a.store_id,'actor':actor.name if actor else 'System / external Sheet change','action':a.action,'object_id':a.object_id,'details':a.details,'at':a.at})
        return {'total':total,'page':page,'rows':events,'integrity':'Append-only through app APIs; not immutable against a database administrator.'}
    @app.get('/api/reports/orders.csv')
    def export_orders(store_id:str|None=None,month:str|None=None,ctx=Depends(context)):
        db,u,s=ctx;require(u,'reports:export');stepup(s);ids=scoped_ids(db,u)
        if store_id:store_access(db,u,store_id);ids=[store_id]
        q=select(Order).where(Order.store_id.in_(ids))
        if month:month_valid(month);q=q.where(Order.sold_on.like(month+'%'))
        rows=db.scalars(q.order_by(Order.sold_on).limit(10001)).all()
        if len(rows)>10000:raise HTTPException(422,'Narrow export to a month or store; maximum 10,000 records per export.')
        output=io.StringIO();writer=csv.writer(output)
        cols=['store','currency','ebay_id','sold_on','title','status','tracking','supplier_ref','earnings']
        if can(u,'costs:view'):cols+=['cost','extra','refund','credit','filler']
        cols+=['profit','financial_approved','origin','observed']
        writer.writerow(cols)
        stores={st.id:st for st in db.scalars(select(Store).where(Store.id.in_(ids)))}
        for o in rows:
            data=order_public(u,o,stores[o.store_id]);writer.writerow([safe_csv(data.get(k,'')) for k in cols])
        audit(db,u,'report.exported',store_id,details={'format':'csv','rows':len(rows),'month':month})
        return Response('\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="xcomify-orders.csv"'})
    @app.get('/api/reports/summary')
    def report_summary(month:str,ctx=Depends(context)):
        db,u,s=ctx;require(u,'reports:export');month_valid(month);ids=scoped_ids(db,u)
        return {'generated_at':now(),'month':month,'profit_definition':'Net order earnings minus product cost, extra expense and refund, plus supplier credits; filler handling is store-specific. These are operational reports, not audited accounts.',
            'stores':[summary(db,x,month) for x in db.scalars(select(Store).where(Store.id.in_(ids)))],
            'fx_policy':'Currencies are reported separately; no unapproved exchange rates are used.'}
    @app.post('/api/system/write-stop')
    def write_stop(body:Freeze,ctx=Depends(context)):
        db,u,s=ctx;owner_only(u)
        if not body.enabled:stepup(s,mfa=True)
        org=db.get(Organization,u.org_id)
        if org.demo and not body.enabled:raise HTTPException(403,'Demo workspaces permanently block outbound Google writes.')
        org.emergency_stop=body.enabled;audit(db,u,'system.write_stop_changed',details={'enabled':body.enabled,'reason':body.reason})
        return {'emergency_stop':org.emergency_stop,'note':'Already-submitted requests may still complete; reconcile in-flight work.'}
    @app.post('/api/system/backup')
    def make_backup(ctx=Depends(context)):
        db,u,s=ctx;owner_only(u);stepup(s)
        if not settings.database_url.startswith('sqlite'):raise HTTPException(409,'PostgreSQL backups use your external backup/PITR process, not this local SQLite endpoint.')
        audit(db,u,'backup.requested');db.commit()
        from .backup import create_backup
        path=create_backup(settings)
        return FileResponse(path,filename=path.name,media_type='application/octet-stream',headers={'Cache-Control':'no-store'})
    @app.get('/api/system/status')
    def system_status(ctx=Depends(context)):
        db,u,s=ctx;owner_only(u);org=db.get(Organization,u.org_id);lease=db.get(Lease,'worker')
        pending=db.scalar(select(func.count()).select_from(Job).where(Job.org_id==u.org_id,Job.state.in_(['pending','running'])))
        backup=db.get(System,'last_backup')
        return {'version':'1.0.0','database':'SQLite local edition' if settings.database_url.startswith('sqlite') else 'PostgreSQL',
            'worker_alive':bool(lease and lease.expires_at>now()),'pending_jobs':pending,'emergency_stop':org.emergency_stop,
            'google_configured':bool(settings.google_client_id and settings.google_client_secret),'demo':settings.demo,
            'last_backup':backup.value if backup else None,'public_registration':False,'same_origin_api':True,
            'release_status':'Locally tested application; live Google, PostgreSQL, extension regression and production security review require deployment validation.'}
    @app.get('/api/openapi')
    def openapi(ctx=Depends(context)):
        db,u,s=ctx;owner_only(u)
        return get_openapi(title=app.title,version=app.version,routes=app.routes)

    app.mount('/static',StaticFiles(directory=Path(__file__).parent/'static'),name='static')
    @app.get('/',include_in_schema=False)
    def index():return FileResponse(Path(__file__).parent/'static'/'index.html',headers={'Cache-Control':'no-store'})
    return app
