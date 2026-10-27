from sqlalchemy import create_engine, event, select, inspect, func, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from .models import Base, Version, System

SCHEMA_LOCK_KEY = 1480806223

class Database:
    def __init__(self, url, serverless=False):
        if url.startswith('sqlite'):
            kw = {'connect_args': {'check_same_thread': False, 'timeout': 30}}
        else:
            kw = {'pool_pre_ping': True}
            if serverless:
                # Use a managed provider pool rather than one idle pool per function.
                kw['poolclass'] = NullPool
                if url.startswith('postgresql+psycopg'):
                    kw['connect_args'] = {'prepare_threshold': None}
        self.engine = create_engine(url, **kw)
        if url.startswith('sqlite'):
            @event.listens_for(self.engine, 'connect')
            def setup_sqlite(conn, _):
                conn.execute('PRAGMA foreign_keys=ON')
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA busy_timeout=30000')
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    def migrate(self):
        with self.engine.begin() as conn:
            if self.engine.dialect.name == 'postgresql':
                conn.execute(text("SET LOCAL lock_timeout = '10s'"))
                conn.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': SCHEMA_LOCK_KEY})
            with self.Session(bind=conn) as db:
                if inspect(conn).has_table('schema_versions'):
                    latest = db.scalar(select(func.max(Version.version)))
                    if latest and latest > 1:
                        raise RuntimeError('Database schema is newer than this application. Refusing unsafe downgrade.')
                Base.metadata.create_all(conn)
                if not db.get(Version, 1):
                    db.add(Version(version=1))
                if not db.get(System, 'bootstrap'):
                    db.add(System(key='bootstrap', value={'complete': False}))
                db.flush()

    def close(self):
        self.engine.dispose()
