"""Argon2id passwords, opaque server sessions, action/store authorization, TOTP."""
import base64, hashlib, hmac, json, re, secrets, struct, time
from urllib.parse import quote
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select
from .models import Assignment, Audit, Store, User, Session, now

HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))
ROLES = {
    'owner': {'*'},
    'admin': {'stores:view','orders:view','orders:edit','finance:view','costs:view','targets:edit','reports:export','tasks:edit','sync:run','writes:approve','audit:view'},
    'manager': {'stores:view','orders:view','orders:edit','finance:view','costs:view','targets:edit','reports:export','tasks:edit','sync:run'},
    'operations': {'stores:view','orders:view','orders:edit','tasks:edit','sync:run'},
    'finance': {'stores:view','orders:view','finance:view','costs:view','finance:adjust','reports:export','audit:view'},
    'viewer': {'stores:view','orders:view','finance:view'},
}
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def password_valid(password):
    if not 14 <= len(password) <= 256: raise HTTPException(422, 'Use a password or passphrase between 14 and 256 characters.')
    if password.lower() in {'passwordpassword','12345678901234','xcomifyxcomify','abcdefghijklmn'} or len(set(password)) < 6:
        raise HTTPException(422, 'Choose a less predictable passphrase.')
def verify_password(encoded, password):
    try: return HASHER.verify(encoded, password)
    except (VerificationError, InvalidHashError): return False

def seal(settings, value): return Fernet(settings.encryption_key.encode()).encrypt(value.encode()).decode()
def unseal(settings, value): return Fernet(settings.encryption_key.encode()).decrypt(value.encode()).decode()

def totp_at(secret, counter):
    key = base64.b32decode(secret.upper() + '=' * ((8-len(secret)%8)%8))
    mac = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = mac[-1] & 15
    return str((struct.unpack('>I', mac[offset:offset+4])[0] & 0x7fffffff) % 1000000).zfill(6)
def verify_totp(secret, code, last_counter=-1, timestamp=None):
    if not re.fullmatch(r'\d{6}', str(code)): return None
    c = int((timestamp if timestamp is not None else time.time()) // 30)
    for candidate in [c, c-1, c+1]:
        if candidate > last_counter and hmac.compare_digest(totp_at(secret, candidate), code): return candidate
    return None

def can(user, action): return '*' in ROLES.get(user.role,set()) or action in ROLES.get(user.role,set())
def require(user, action):
    if not can(user, action): raise HTTPException(403, 'Your role does not permit this action.')
def scoped_ids(db, user):
    q = select(Store.id).where(Store.org_id==user.org_id)
    if user.role != 'owner': q=q.join(Assignment, Assignment.store_id==Store.id).where(Assignment.user_id==user.id)
    return list(db.scalars(q).all())
def store_access(db, user, store_id, action='stores:view'):
    require(user,action)
    store=db.get(Store,store_id)
    if not store or store.org_id != user.org_id: raise HTTPException(404,'Store not found.')
    if user.role != 'owner' and not db.get(Assignment, (user.id,store_id)): raise HTTPException(404,'Store not found.')
    return store

def owner_only(user):
    if user.role!='owner': raise HTTPException(403,'Only the owner can perform this action.')
def stepup(session, mfa=False):
    if session.stepup_until < now(): raise HTTPException(428,'Reauthenticate in Security settings first (valid for 10 minutes).')
    if mfa and not session.mfa_verified: raise HTTPException(428,'Enable MFA and reauthenticate before enabling or approving Google writes.')

def audit(db,user,action,store_id=None,object_id=None,details=None,org_id=None):
    # Callers pass an allowlisted redacted payload. No credentials, full cells, or postcodes.
    db.add(Audit(org_id=org_id or user.org_id,store_id=store_id,actor_id=user.id if user else None,
                 action=action,object_id=object_id,details=details or {}))

def safe_csv(value):
    val = '' if value is None else str(value)
    if val.lstrip().startswith(('=','+','-','@','\t','\r','\n')): return "'"+val
    return val
