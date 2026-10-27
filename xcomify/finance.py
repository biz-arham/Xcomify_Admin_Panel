from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import calendar, re
from sqlalchemy import select
from .models import Order, FinancialEntry, Target, Milestone, Notification, PeriodClose, now

ZERO=Decimal('0')
MONEY_FIELDS={'earnings','cost','extra','refund','credit','filler'}

def money(value, optional=False):
    if value is None or str(value).strip()=='':
        if optional: return None
        raise ValueError('A monetary value is required; blank is not zero.')
    s=str(value).strip()
    if not re.fullmatch(r'-?\d{1,16}(\.\d{1,4})?',s): raise ValueError('Use a plain decimal amount, for example 12.50 (no symbols or separators).')
    d=Decimal(s)
    if not d.is_finite() or abs(d)>Decimal('999999999999.99'): raise ValueError('Amount out of range.')
    return d.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
def fmt(value): return None if value is None else format(value.quantize(Decimal('.01'),rounding=ROUND_HALF_UP),'f')
def norm_postcode(value): return re.sub(r'\s+','',str(value)).upper()
def current_month(store): return datetime.now(ZoneInfo(store.timezone)).strftime('%Y-%m')
def date_valid(value):
    try: return date.fromisoformat(str(value)).isoformat()
    except ValueError: raise ValueError('Date must be YYYY-MM-DD.')
def month_valid(month):
    if not re.fullmatch(r'\d{4}-\d{2}',month): raise ValueError('Month must be YYYY-MM.')
    date.fromisoformat(month+'-01')
    return month

def order_profit(order, store):
    if order.earnings is None or order.cost is None or order.issues or not order.observed: return None
    return order.earnings-order.cost-order.extra-order.refund+order.credit-(order.filler if store.include_filler else ZERO)

def summary(db,store,month):
    month_valid(month)
    closed=db.get(PeriodClose,(store.id,month))
    if closed:
        # Preserve the approved closing snapshot despite later source corrections.
        return {**closed.snapshot,'closed':True,'celebration_eligible':False}
    orders=list(db.scalars(select(Order).where(Order.store_id==store.id,Order.sold_on.like(month+'%'))).all())
    confirmed=ZERO; provisional=ZERO; complete=0; missing=0; earnings=ZERO; costs=ZERO; filler=ZERO; trends={}
    for o in orders:
        p=order_profit(o,store)
        earnings+=o.earnings or ZERO
        costs+=o.cost or ZERO
        filler+=o.filler
        if p is None:
            missing+=1
            if o.earnings is not None:
                provisional+=o.earnings-(o.cost or ZERO)-o.extra-o.refund+o.credit-(o.filler if store.include_filler else ZERO)
        else:
            confirmed+=p; complete+=1
            trends[o.sold_on]=trends.get(o.sold_on,ZERO)+p
    adjustments=ZERO
    for e in db.scalars(select(FinancialEntry).where(FinancialEntry.store_id==store.id,FinancialEntry.recognized_on.like(month+'%'))):
        adjustments+=e.amount
        trends[e.recognized_on]=trends.get(e.recognized_on,ZERO)+e.amount
    confirmed+=adjustments
    target=db.scalar(select(Target).where(Target.store_id==store.id,Target.month==month))
    target_amount=target.amount if target else ZERO
    actual=confirmed if store.financial_approved else None
    percent=(actual/target_amount*100) if actual is not None and target_amount>0 else None
    local_today=datetime.now(ZoneInfo(store.timezone)).date()
    start=date.fromisoformat(month+'-01'); days=calendar.monthrange(start.year,start.month)[1]
    end=date(start.year,start.month,days)
    completed_days=max(0,min(days,(local_today-start).days))
    remaining_days=max(0,days-completed_days)
    completed_profit=sum((v for k,v in trends.items() if date.fromisoformat(k)<local_today),ZERO)
    projection=completed_profit/Decimal(completed_days)*days if completed_days>=3 else None
    remaining=max(target_amount-(actual or ZERO),ZERO) if target_amount>0 and actual is not None else None
    stale=store.source=='google' and (not store.last_sync or now()-store.last_sync>max(600,store.poll_seconds*3))
    return {'store_id':store.id,'store':store.name,'currency':store.currency,'basis':store.financial_basis,'month':month,
        'orders':len(orders),'complete_orders':complete,'incomplete_orders':missing,'earnings':fmt(earnings),'costs':fmt(costs),
        'confirmed_subtotal':fmt(confirmed),'provisional_subtotal':fmt(provisional),'eligible_profit':fmt(actual),
        'excluded_filler':fmt(ZERO if store.include_filler else filler),'adjustments':fmt(adjustments),
        'target':fmt(target_amount),'target_id':target.id if target else None,'target_version':target.version if target else None,
        'attainment':fmt(percent),'remaining':fmt(remaining),'overachievement':fmt(max((actual or ZERO)-target_amount,ZERO)) if target_amount>0 and actual is not None else None,
        'coverage':round(complete/len(orders)*100,1) if orders else 100,
        'celebration_eligible':bool(store.financial_approved and not missing and not stale and store.status=='active'),
        'stale':stale,'last_sync':store.last_sync,'financial_approved':store.financial_approved,
        'days_completed':completed_days,'days_remaining_including_today':remaining_days,
        'required_daily_profit':fmt(remaining/remaining_days) if remaining is not None and remaining_days else None,
        'projected_profit':fmt(projection) if store.financial_approved else None,
        'projection_method':'Observed profit per completed local day; minimum three completed days; no probability estimate.',
        'daily':[{'date':k,'profit':fmt(v)} for k,v in sorted(trends.items())],
        'closed':bool(db.get(PeriodClose,(store.id,month)))}

def record_milestones(db,store,month,muted=False):
    s=summary(db,store,month)
    if not s['celebration_eligible'] or s['attainment'] is None: return
    attained=Decimal(s['attainment'])
    for level in [25,50,75,90,100]:
        if attained<level: continue
        existing=db.scalar(select(Milestone).where(Milestone.store_id==store.id,Milestone.month==month,Milestone.level==level))
        if existing: continue
        db.add(Milestone(store_id=store.id,month=month,level=level,target_version=s['target_version'],muted=muted))
        if not muted:
            key=f'milestone:{store.id}:{month}:{level}'
            if not db.scalar(select(Notification.id).where(Notification.org_id==store.org_id,Notification.dedupe_key==key)):
                db.add(Notification(org_id=store.org_id,store_id=store.id,title=f'{store.name} reached {level}%',
                    body=f'{month} profit target milestone. Current progress can change after refunds or corrections.',
                    severity='success',financial=True,dedupe_key=key))
