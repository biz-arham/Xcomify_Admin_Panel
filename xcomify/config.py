"""Explicit environment configuration. Local secrets are never shipped."""
from dataclasses import dataclass
from pathlib import Path
import os
import secrets
from urllib.parse import urlparse
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent

def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

@dataclass
class Settings:
    data_dir: Path
    database_url: str
    encryption_key: str
    bootstrap_token: str
    base_url: str = 'http://localhost:8787'
    environment: str = 'local'
    demo: bool = False
    worker: bool = True
    google_client_id: str = ''
    google_client_secret: str = ''
    session_hours: int = 12
    idle_minutes: int = 60
    poll_seconds: int = 120
    @property
    def production(self): return self.environment == 'production'
    @property
    def cookie_name(self): return '__Host-xcomify' if self.production else 'xcomify_session'
    @property
    def redirect_uri(self): return self.base_url.rstrip('/') + '/api/google/callback'

    @classmethod
    def from_env(cls):
        load_env()
        demo = os.getenv('XCOMIFY_DEMO', 'false').lower() == 'true'
        env = os.getenv('XCOMIFY_ENV', 'local')
        if demo and env=='production': raise RuntimeError('Demo mode cannot run as production.')
        # Demo never inherits a real database URL or real workspace directory.
        data = Path(os.getenv('XCOMIFY_DEMO_DATA_DIR', str(ROOT / '.data-demo')) if demo else os.getenv('XCOMIFY_DATA_DIR',str(ROOT / '.data'))).resolve()
        data.mkdir(parents=True, exist_ok=True, mode=0o700)
        env = os.getenv('XCOMIFY_ENV', 'local')
        def secret_file(name, value, generator):
            if value: return value
            if env == 'production': raise RuntimeError(f'{name} must be provided by the secret manager in production.')
            path = data / name.lower()
            if not path.exists():
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, 'w') as f: f.write(generator())
            return path.read_text().strip()
        key = secret_file('XCOMIFY_ENCRYPTION_KEY', None if demo else os.getenv('XCOMIFY_ENCRYPTION_KEY'), lambda: Fernet.generate_key().decode())
        boot = secret_file('XCOMIFY_BOOTSTRAP_TOKEN', None if demo else os.getenv('XCOMIFY_BOOTSTRAP_TOKEN'), lambda: secrets.token_urlsafe(32))
        base = os.getenv('XCOMIFY_BASE_URL', 'http://localhost:8787').rstrip('/')
        db = f'sqlite:///{data / "xcomify-demo.db"}' if demo else os.getenv('DATABASE_URL', f'sqlite:///{data / "xcomify.db"}')
        if env == 'production':
            if urlparse(base).scheme != 'https': raise RuntimeError('Production requires an HTTPS base URL.')
            if not db.startswith('postgresql'): raise RuntimeError('Use PostgreSQL in production; SQLite is the local single-server edition.')
            if demo: raise RuntimeError('Demo mode cannot run as production.')
        Fernet(key.encode())
        return cls(data, db, key, boot, base, env, demo, os.getenv('XCOMIFY_WORKER', 'true').lower() == 'true',
                   os.getenv('GOOGLE_CLIENT_ID', ''), os.getenv('GOOGLE_CLIENT_SECRET', ''))
