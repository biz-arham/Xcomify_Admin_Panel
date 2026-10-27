from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .finance import money, date_valid, month_valid
import re

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Login(Strict):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256, min_length=1)
    code: str = Field(default='', max_length=80)
class Setup(Login):
    name: str = Field(min_length=2,max_length=120)
    workspace: str = Field(default='Xcomify',min_length=2,max_length=120)
    setup_code: str = Field(min_length=20,max_length=200)
class Reauth(Strict):
    password: str = Field(min_length=1,max_length=256)
    code: str = Field(default='',max_length=80)
class Code(Strict):
    code: str = Field(min_length=6,max_length=80)
class PasswordChange(Reauth):
    new_password: str = Field(min_length=14,max_length=256)
class Invite(Strict):
    email: str = Field(min_length=3,max_length=254)
    role: Literal['admin','manager','operations','finance','viewer']='operations'
    stores: list[str]=Field(default_factory=list,max_length=100)
class AcceptInvite(Strict):
    token: str = Field(min_length=20,max_length=200)
    name: str = Field(min_length=2,max_length=120)
    password: str = Field(min_length=14,max_length=256)
class UserEdit(Strict):
    active: bool
    role: Literal['admin','manager','operations','finance','viewer']
    stores: list[str]=Field(default_factory=list,max_length=100)
class StoreCreate(Strict):
    name: str=Field(min_length=2,max_length=120)
    marketplace: Literal['UK','AU','US','DE','CA','Other']='UK'
    currency: Literal['GBP','AUD','USD','EUR','CAD']='GBP'
    timezone: str='Europe/London'
    @field_validator('timezone')
    @classmethod
    def tz(cls,v):
        try: ZoneInfo(v)
        except (ZoneInfoNotFoundError,ValueError): raise ValueError('Choose a valid IANA timezone.')
        return v
class StoreEdit(StoreCreate):
    revision: int=Field(ge=1)
    status: Literal['active','paused','archived']='active'
    financial_approved: bool=False
    include_filler: bool=False
    poll_seconds: int=Field(default=120,ge=60,le=3600)
class OrderCreate(Strict):
    ebay_id: str=Field(min_length=1,max_length=100)
    sold_on: str
    title: str=Field(default='',max_length=2000)
    earnings: str | None=None
    cost: str | None=None
    extra: str='0'
    refund: str='0'
    credit: str='0'
    filler: str='0'
    supplier_ref: str=Field(default='',max_length=150)
    tracking: str=Field(default='',max_length=200)
    courier: str=Field(default='',max_length=100)
    postcode: str=Field(default='',max_length=30)
    status: str=Field(default='New',max_length=50)
    notes: str=Field(default='',max_length=4000)
    @field_validator('sold_on')
    @classmethod
    def d(cls,v): return date_valid(v)
    @field_validator('earnings','cost','extra','refund','credit','filler')
    @classmethod
    def amount(cls,v,info):
        n=money(v,optional=info.field_name in {'earnings','cost'})
        if n is not None and n<0 and info.field_name!='earnings': raise ValueError('Cost, expenses, refunds and credits must not be negative.')
        return None if n is None else str(n)
class OrderEdit(Strict):
    revision: int=Field(ge=1)
    changes: dict=Field(min_length=1,max_length=15)
    reason: str=Field(min_length=4,max_length=1000)
    idempotency_key: str=Field(min_length=8,max_length=100)
class TargetSet(Strict):
    month: str
    amount: str
    version: int | None=None
    reason: str=Field(min_length=4,max_length=500)
    @field_validator('month')
    @classmethod
    def m(cls,v): return month_valid(v)
    @field_validator('amount')
    @classmethod
    def a(cls,v):
        n=money(v)
        if n<0: raise ValueError('Target cannot be negative.')
        return str(n)
class Adjustment(Strict):
    amount: str
    recognized_on: str
    reason: str=Field(min_length=8,max_length=1000)
    idempotency_key: str=Field(min_length=8,max_length=100)
    @field_validator('amount')
    @classmethod
    def a(cls,v): return str(money(v))
    @field_validator('recognized_on')
    @classmethod
    def d(cls,v): return date_valid(v)
class TaskCreate(Strict):
    store_id: str
    title: str=Field(min_length=3,max_length=200)
    assignee_id: str | None=None
    due_on: str | None=None
    @field_validator('due_on')
    @classmethod
    def d(cls,v): return date_valid(v) if v else None
class TaskEdit(Strict):
    status: Literal['open','in_progress','done']
class Reason(Strict):
    reason: str=Field(min_length=8,max_length=1000)
class WriteApproval(Reason):
    owner_override: bool=False
class Freeze(Reason):
    enabled: bool=True
class MapField(Strict):
    column: int=Field(ge=0,le=100)
    header: str=Field(min_length=1,max_length=200)
    ownership: Literal['sheet','app','computed']='sheet'
class Mapping(Strict):
    connection_id: str
    spreadsheet_id: str=Field(pattern=r'^[A-Za-z0-9_-]{20,180}$')
    sheet_id: int=Field(ge=0)
    header_row: int=Field(ge=1,le=100)
    fields: dict[str,MapField]=Field(min_length=2,max_length=20)
    date_format: Literal['iso','day_first','month_first']='day_first'
    max_rows: int=Field(default=10000,ge=100,le=50000)
class WriteEnable(Reason):
    enabled: bool
    single_writer_confirmed: bool=False
    mapping_verified: bool=False
    private_sharing_verified: bool=False
    test_sheet_write_verified: bool=False
    extension_regression_verified: bool=False
    restore_verified: bool=False
    limited_rollout_approved: bool=False
class CSVImport(Strict):
    csv_text: str=Field(max_length=2_000_000)
    commit: bool=False
