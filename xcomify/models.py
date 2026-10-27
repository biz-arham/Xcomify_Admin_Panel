"""Portable relational schema. Monetary values stay exact on SQLite and PostgreSQL."""
from decimal import Decimal
from datetime import datetime, timezone
import uuid
from sqlalchemy import String, Text, Integer, Boolean, JSON, ForeignKey, UniqueConstraint, Index, Numeric
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def uid(): return str(uuid.uuid4())
def now(): return int(datetime.now(timezone.utc).timestamp())

class Money(TypeDecorator):
    impl = Text
    cache_ok = True
    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(Numeric(22, 4) if dialect.name == 'postgresql' else Text())
    def process_bind_param(self, value, dialect):
        if value is None: return None
        val = Decimal(str(value))
        return val if dialect.name == 'postgresql' else format(val, 'f')
    def process_result_value(self, value, dialect): return None if value is None else Decimal(str(value))

class Base(DeclarativeBase): pass
class Version(Base):
    __tablename__='schema_versions'
    version: Mapped[int] = mapped_column(primary_key=True)
    applied_at: Mapped[int] = mapped_column(default=now)
class System(Base):
    __tablename__='system'
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
class Organization(Base):
    __tablename__='organizations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    emergency_stop: Mapped[bool] = mapped_column(Boolean, default=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(default=now)
class User(Base):
    __tablename__='users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30), default='viewer')
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_secret: Mapped[str | None] = mapped_column(Text)
    pending_mfa: Mapped[str | None] = mapped_column(Text)
    mfa_counter: Mapped[int] = mapped_column(Integer, default=-1)
    recovery_codes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[int] = mapped_column(default=now)
class RecoveryCode(Base):
    __tablename__='recovery_codes'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    used_at: Mapped[int | None] = mapped_column(Integer)
class Session(Base):
    __tablename__='sessions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    csrf: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[int] = mapped_column(default=now)
    expires_at: Mapped[int] = mapped_column(Integer)
    last_seen: Mapped[int] = mapped_column(default=now)
    stepup_until: Mapped[int] = mapped_column(Integer, default=0)
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    user_agent: Mapped[str] = mapped_column(String(200), default='')
class AuthAttempt(Base):
    __tablename__='auth_attempts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    key: Mapped[str] = mapped_column(String(80), index=True)
    at: Mapped[int] = mapped_column(Integer, default=now, index=True)
class Assignment(Base):
    __tablename__='assignments'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey('stores.id'), primary_key=True)
class Invitation(Base):
    __tablename__='invitations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'))
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(30))
    stores: Mapped[list] = mapped_column(JSON, default=list)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[int] = mapped_column(Integer)
    used_at: Mapped[int | None] = mapped_column(Integer)
class Connection(Base):
    __tablename__='connections'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    name: Mapped[str] = mapped_column(String(120), default='Google Sheets')
    credential: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[int] = mapped_column(default=now)
class OAuthState(Base):
    __tablename__='oauth_states'
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id',ondelete='CASCADE'))
    verifier: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[int] = mapped_column(Integer)
class Store(Base):
    __tablename__='stores'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    marketplace: Mapped[str] = mapped_column(String(30), default='UK')
    currency: Mapped[str] = mapped_column(String(3), default='GBP')
    timezone: Mapped[str] = mapped_column(String(80), default='Europe/London')
    status: Mapped[str] = mapped_column(String(20), default='active')
    source: Mapped[str] = mapped_column(String(20), default='local')
    connection_id: Mapped[str | None] = mapped_column(ForeignKey('connections.id'))
    spreadsheet_id: Mapped[str | None] = mapped_column(String(180))
    sheet_id: Mapped[int | None] = mapped_column(Integer)
    tab_name: Mapped[str | None] = mapped_column(String(150))
    header_row: Mapped[int] = mapped_column(Integer, default=1)
    mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    mapping_version: Mapped[int] = mapped_column(Integer, default=1)
    financial_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    financial_basis: Mapped[str] = mapped_column(String(30), default='operational_profit')
    include_filler: Mapped[bool] = mapped_column(Boolean, default=False)
    writes_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    writer_contract: Mapped[bool] = mapped_column(Boolean, default=False)
    gates: Mapped[dict] = mapped_column(JSON, default=dict)
    poll_seconds: Mapped[int] = mapped_column(Integer, default=120)
    next_sync: Mapped[int] = mapped_column(Integer, default=0, index=True)
    last_sync: Mapped[int | None] = mapped_column(Integer)
    sync_error: Mapped[str | None] = mapped_column(Text)
    max_rows: Mapped[int] = mapped_column(Integer, default=10000)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[int] = mapped_column(default=now)
class Order(Base):
    __tablename__='orders'
    __table_args__=(UniqueConstraint('store_id','ebay_id', name='uq_order_store_ebay'), Index('ix_order_store_date', 'store_id','sold_on'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    store_id: Mapped[str] = mapped_column(ForeignKey('stores.id'), index=True)
    ebay_id: Mapped[str] = mapped_column(String(100))
    sold_on: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(Text, default='')
    earnings: Mapped[Decimal | None] = mapped_column(Money)
    cost: Mapped[Decimal | None] = mapped_column(Money)
    extra: Mapped[Decimal] = mapped_column(Money, default=Decimal('0'))
    refund: Mapped[Decimal] = mapped_column(Money, default=Decimal('0'))
    credit: Mapped[Decimal] = mapped_column(Money, default=Decimal('0'))
    filler: Mapped[Decimal] = mapped_column(Money, default=Decimal('0'))
    supplier_ref: Mapped[str] = mapped_column(String(150), default='')
    tracking: Mapped[str] = mapped_column(String(200), default='')
    courier: Mapped[str] = mapped_column(String(100), default='')
    postcode: Mapped[str] = mapped_column(String(30), default='')
    status: Mapped[str] = mapped_column(String(50), default='New')
    notes: Mapped[str] = mapped_column(Text, default='')
    origin: Mapped[str] = mapped_column(String(20), default='local')
    source_row: Mapped[int | None] = mapped_column(Integer)
    source_values: Mapped[dict] = mapped_column(JSON, default=dict)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    observed: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[int] = mapped_column(default=now)
class FinancialEntry(Base):
    __tablename__='financial_entries'
    __table_args__=(UniqueConstraint('store_id','idempotency_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'))
    store_id: Mapped[str] = mapped_column(ForeignKey('stores.id'), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    recognized_on: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[int] = mapped_column(default=now)
class PeriodClose(Base):
    __tablename__='period_closes'
    store_id: Mapped[str] = mapped_column(ForeignKey('stores.id'), primary_key=True)
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[int] = mapped_column(default=now)
class Target(Base):
    __tablename__='targets'
    __table_args__=(UniqueConstraint('store_id','month'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'))
    store_id: Mapped[str] = mapped_column(ForeignKey('stores.id'), index=True)
    month: Mapped[str] = mapped_column(String(7))
    amount: Mapped[Decimal] = mapped_column(Money)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[int] = mapped_column(default=now)
class Milestone(Base):
    __tablename__='milestones'
    __table_args__=(UniqueConstraint('store_id','month','level'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    store_id: Mapped[str] = mapped_column(ForeignKey('stores.id'), index=True)
    month: Mapped[str] = mapped_column(String(7))
    level: Mapped[int] = mapped_column(Integer)
    target_version: Mapped[int] = mapped_column(Integer)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    at: Mapped[int] = mapped_column(default=now)
class WriteIntent(Base):
    __tablename__='write_intents'
    __table_args__=(UniqueConstraint('org_id','idempotency_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    store_id: Mapped[str] = mapped_column(ForeignKey('stores.id'))
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'))
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    approver_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    base: Mapped[dict] = mapped_column(JSON)
    proposed: Mapped[dict] = mapped_column(JSON)
    postcode: Mapped[str] = mapped_column(String(30))
    mapping_version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(30), default='proposed', index=True)
    reason: Mapped[str] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[int] = mapped_column(default=now)
    updated_at: Mapped[int] = mapped_column(default=now)
class Job(Base):
    __tablename__='jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    store_id: Mapped[str | None] = mapped_column(ForeignKey('stores.id'))
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(30), default='pending', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[int] = mapped_column(Integer, default=now, index=True)
    started_at: Mapped[int | None] = mapped_column(Integer)
    finished_at: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[int] = mapped_column(default=now)
class Lease(Base):
    __tablename__='leases'
    key: Mapped[str] = mapped_column(String(220), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[int] = mapped_column(Integer)
class Notification(Base):
    __tablename__='notifications'
    __table_args__=(UniqueConstraint('org_id','dedupe_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    store_id: Mapped[str | None] = mapped_column(ForeignKey('stores.id'))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default='info')
    financial: Mapped[bool] = mapped_column(Boolean, default=False)
    dedupe_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[int] = mapped_column(default=now)
class NotificationRead(Base):
    __tablename__='notification_reads'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    notification_id: Mapped[str] = mapped_column(ForeignKey('notifications.id'), primary_key=True)
class CelebrationSeen(Base):
    __tablename__='celebration_seen'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    notification_id: Mapped[str] = mapped_column(ForeignKey('notifications.id'), primary_key=True)
    at: Mapped[int] = mapped_column(default=now)
class Task(Base):
    __tablename__='tasks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    store_id: Mapped[str] = mapped_column(ForeignKey('stores.id'))
    title: Mapped[str] = mapped_column(String(200))
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    due_on: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default='open')
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[int] = mapped_column(default=now)
class Audit(Base):
    __tablename__='audit'
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    store_id: Mapped[str | None] = mapped_column(ForeignKey('stores.id'))
    actor_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(100))
    object_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[int] = mapped_column(default=now)
