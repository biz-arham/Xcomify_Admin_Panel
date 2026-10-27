"""Production-only Vercel adapter; no local database or embedded worker fallback."""
from __future__ import annotations
import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from sqlalchemy.engine import make_url
from fastapi import FastAPI
from starlette.responses import JSONResponse
from .config import Settings
from .db import Database

log = logging.getLogger('xcomify.hosting')


def normalize_postgres_url(value: str) -> str:
    """Use the shipped psycopg3 driver and require encrypted remote connections."""
    try:
        url = make_url(value)
    except Exception as exc:
        raise RuntimeError('DATABASE_URL must be a valid PostgreSQL URL.') from None
    if url.drivername not in {'postgres', 'postgresql', 'postgresql+psycopg'}:
        raise RuntimeError('Hosted deployment requires PostgreSQL; SQLite is not allowed.')
    if not url.host or not url.database:
        raise RuntimeError('DATABASE_URL requires a host and database name.')
    sslmode = url.query.get('sslmode', 'require')
    if sslmode not in {'require', 'verify-ca', 'verify-full'}:
        raise RuntimeError('Hosted PostgreSQL connections must require TLS.')
    query = dict(url.query)
    query.setdefault('sslmode', 'require')
    query.setdefault('connect_timeout', '10')
    return url.set(drivername='postgresql+psycopg', query=query).render_as_string(hide_password=False)


def cloud_settings() -> Settings:
    """Fail closed if cloud secrets, canonical origin or isolation are missing."""
    if os.getenv('VERCEL_ENV') not in {None, '', 'production'}:
        raise RuntimeError('This profile is production-only. Do not attach production secrets to preview deployments.')
    if os.getenv('XCOMIFY_DEMO', '').lower() == 'true':
        raise RuntimeError('The hosted profile cannot run synthetic demo mode.')
    names = ('DATABASE_URL', 'XCOMIFY_ENCRYPTION_KEY', 'XCOMIFY_BOOTSTRAP_TOKEN', 'XCOMIFY_BASE_URL')
    missing = [name for name in names if not os.getenv(name, '').strip()]
    if missing:
        raise RuntimeError('Required production settings missing: ' + ', '.join(missing))
    base = os.environ['XCOMIFY_BASE_URL'].rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise RuntimeError('XCOMIFY_BASE_URL must be the exact HTTPS origin, without a path or credentials.')
    if len(os.environ['XCOMIFY_BOOTSTRAP_TOKEN']) < 32:
        raise RuntimeError('XCOMIFY_BOOTSTRAP_TOKEN must have at least 32 random characters.')
    os.environ['DATABASE_URL'] = normalize_postgres_url(os.environ['DATABASE_URL'])
    os.environ['XCOMIFY_BASE_URL'] = base
    os.environ['XCOMIFY_ENV'] = 'production'
    os.environ['XCOMIFY_WORKER'] = 'false'
    os.environ['XCOMIFY_DEMO'] = 'false'
    # Scratch only: credentials and application data must never depend on /tmp.
    os.environ['XCOMIFY_DATA_DIR'] = '/tmp/xcomify'
    return Settings.from_env()


class HostedBackend:
    """Lazy initialization avoids database writes during Vercel build inspection."""
    def __init__(self, settings_factory=cloud_settings, database_factory=None, application_factory=None):
        self.settings_factory = settings_factory
        self.database_factory = database_factory or (lambda url: Database(url, serverless=True))
        self.application_factory = application_factory
        self._lock = threading.Lock()
        self._backend = None
        self._database = None

    def initialize(self):
        with self._lock:
            if self._backend is None:
                settings = self.settings_factory()
                if settings.worker:
                    raise RuntimeError('Embedded workers must be disabled in HTTP functions.')
                database = self.database_factory(settings.database_url)
                try:
                    factory = self.application_factory
                    if factory is None:
                        from .main import create_app
                        factory = create_app
                    backend = factory(settings, database)
                except Exception:
                    database.close()
                    raise
                self._database = database
                self._backend = backend
            return self._backend

    async def __call__(self, scope, receive, send):
        try:
            backend = await asyncio.to_thread(self.initialize)
        except Exception as exc:
            # Log only the exception type: connection errors may contain secrets.
            log.error('Cloud initialization failed (%s). Check deployment configuration and database access.', type(exc).__name__)
            response = JSONResponse(
                {'detail': 'Deployment configuration or database initialization is incomplete. Ask the owner to check the private deployment guide.',
                 'code': 'DEPLOYMENT_NOT_CONFIGURED'},
                status_code=503,
                headers={'Cache-Control': 'no-store, private', 'X-Content-Type-Options': 'nosniff'})
            await response(scope, receive, send)
            return
        await backend(scope, receive, send)

    def close(self):
        with self._lock:
            if self._database is not None:
                self._database.close()
            self._database = None
            self._backend = None


def create_hosted_app(settings_factory=cloud_settings, database_factory=None, application_factory=None) -> FastAPI:
    backend = HostedBackend(settings_factory, database_factory, application_factory)
    @asynccontextmanager
    async def lifespan(app):
        yield
        await asyncio.to_thread(backend.close)
    app = FastAPI(title='Xcomify Central Command', docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.state.hosted_backend = backend
    app.mount('/', backend)
    return app
