"""Hosted adapter tests. They do NOT claim live Vercel or PostgreSQL verification."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from xcomify.config import Settings
from xcomify.db import Database
from xcomify.vercel_runtime import cloud_settings, create_hosted_app, normalize_postgres_url

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def hosted_env(monkeypatch):
    for name in ('DATABASE_URL', 'XCOMIFY_ENCRYPTION_KEY', 'XCOMIFY_BOOTSTRAP_TOKEN',
                 'XCOMIFY_BASE_URL', 'XCOMIFY_ENV', 'XCOMIFY_WORKER', 'XCOMIFY_DEMO',
                 'XCOMIFY_DATA_DIR', 'VERCEL_ENV', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET'):
        monkeypatch.delenv(name, raising=False)
    values = {
        'DATABASE_URL': 'postgresql://unit:unit@db.example.test/unit',
        'XCOMIFY_ENCRYPTION_KEY': Fernet.generate_key().decode(),
        'XCOMIFY_BOOTSTRAP_TOKEN': 'unit-test-bootstrap-' + 'x' * 40,
        'XCOMIFY_BASE_URL': 'https://app.example.test',
        'VERCEL_ENV': 'production',
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values

@pytest.mark.parametrize('prefix', ['postgres', 'postgresql', 'postgresql+psycopg'])
def test_postgres_scheme_normalization(prefix):
    url = make_url(normalize_postgres_url(prefix + '://user:pass@db.example.test/test'))
    assert url.drivername == 'postgresql+psycopg'
    assert url.query['sslmode'] == 'require'
    assert url.query['connect_timeout'] == '10'

@pytest.mark.parametrize('url', [
    'sqlite:////tmp/data.db',
    'postgresql://user:pass@db.example.test/test?sslmode=disable',
    'postgresql://user:pass@db.example.test/test?sslmode=prefer',
    'postgresql:///test',
    'not a connection string',
])
def test_reject_unsafe_database_configuration(url):
    with pytest.raises(RuntimeError):
        normalize_postgres_url(url)

@pytest.mark.parametrize('name', ['DATABASE_URL', 'XCOMIFY_ENCRYPTION_KEY', 'XCOMIFY_BOOTSTRAP_TOKEN', 'XCOMIFY_BASE_URL'])
def test_missing_production_settings_fail_closed(hosted_env, monkeypatch, name):
    monkeypatch.delenv(name)
    with pytest.raises(RuntimeError, match='Required production settings missing'):
        cloud_settings()

def test_production_settings_disable_embedded_worker(hosted_env, monkeypatch):
    monkeypatch.setenv('XCOMIFY_WORKER', 'true')
    settings = cloud_settings()
    assert settings.production
    assert not settings.worker
    assert settings.data_dir == Path('/tmp/xcomify')
    assert settings.database_url.startswith('postgresql+psycopg://')
    assert settings.cookie_name == '__Host-xcomify'

@pytest.mark.parametrize('origin', ['http://app.example.test', 'https://app.example.test/path', 'https://user:pass@app.example.test', 'https://app.example.test?q=1'])
def test_invalid_origin_is_rejected(hosted_env, monkeypatch, origin):
    monkeypatch.setenv('XCOMIFY_BASE_URL', origin)
    with pytest.raises(RuntimeError, match='exact HTTPS origin'):
        cloud_settings()

def test_preview_does_not_use_production_secrets(hosted_env, monkeypatch):
    monkeypatch.setenv('VERCEL_ENV', 'preview')
    with pytest.raises(RuntimeError, match='production-only'):
        cloud_settings()

def test_cloud_demo_mode_rejected(hosted_env, monkeypatch):
    monkeypatch.setenv('XCOMIFY_DEMO', 'true')
    with pytest.raises(RuntimeError, match='synthetic demo'):
        cloud_settings()

def test_build_entrypoint_import_never_connects_database(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Import-time database access is prohibited')
    monkeypatch.setattr(Database, '__init__', forbidden)
    module = importlib.import_module('index')
    importlib.reload(module)
    assert module.app.state.hosted_backend._backend is None

def test_failure_response_is_private_and_redacts_secrets():
    def broken():
        raise RuntimeError('do-not-leak-this-secret')
    app = create_hosted_app(settings_factory=broken)
    with TestClient(app) as client:
        response = client.get('/')
        assert response.status_code == 503
        assert 'do-not-leak-this-secret' not in response.text
        assert 'no-store' in response.headers['cache-control']

def test_hosted_http_adapter_with_local_test_database(tmp_path):
    settings = Settings(tmp_path, f'sqlite:///{tmp_path / "adapter.db"}',
                        Fernet.generate_key().decode(), 'only-for-isolated-test',
                        base_url='http://testserver', worker=False)
    app = create_hosted_app(settings_factory=lambda: settings, database_factory=Database)
    assert app.state.hosted_backend._backend is None
    with TestClient(app) as client:
        client.headers.update({'Origin': 'http://testserver', 'X-Xcomify-Request': '1'})
        assert client.get('/').status_code == 200
        assert client.get('/static/app.js').status_code == 200
        assert client.get('/api/setup/status').json()['configured'] is False
        response = client.post('/api/setup', json={
            'email': 'adapter@example.test', 'password': 'Strong-adapter-testing-password-42!',
            'name': 'Adapter test', 'setup_code': settings.bootstrap_token,
        })
        assert response.status_code == 200, response.text
        assert client.get('/api/me').json()['user']['email'] == 'adapter@example.test'
        assert client.get('/api/setup/status').json()['configured'] is True
    assert app.state.hosted_backend._database is None

def test_cloud_database_uses_nullpool_without_opening_connection(monkeypatch):
    import xcomify.db as module
    recorded = {}
    def fake_create_engine(url, **kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(dispose=lambda: None)
    monkeypatch.setattr(module, 'create_engine', fake_create_engine)
    database = Database('postgresql+psycopg://unit:unit@db.example.test/unit', serverless=True)
    assert recorded['poolclass'] is NullPool
    assert recorded['connect_args']['prepare_threshold'] is None
    database.close()

def test_static_build_copies_only_public_allowlist(tmp_path):
    from scripts.build_vercel import ASSETS, build_assets
    source = tmp_path / 'xcomify' / 'static'
    source.mkdir(parents=True)
    for name in ASSETS:
        (source / name).write_text('fixture')
    (source / '.env').write_text('DO_NOT_COPY=secret')
    assert build_assets(tmp_path) == len(ASSETS)
    assert {p.name for p in (tmp_path / 'public' / 'static').iterdir()} == set(ASSETS)

def test_deployment_profiles_explicitly_separate_worker():
    base = json.loads((ROOT / 'vercel.json').read_text())
    daemon = json.loads((ROOT / 'infra' / 'vercel.with-daemon.json').read_text())
    assert base['framework'] == 'fastapi'
    assert 'crons' not in base and 'daemons' not in base
    assert daemon['daemons']['sheets-sync']['command'] == ['python', '-m', 'xcomify.cloud_worker']
    assert daemon['daemons']['sheets-sync']['instances']['iad1'] == 1

def test_migration_remains_idempotent_in_local_edition(tmp_path):
    database = Database(f'sqlite:///{tmp_path / "repeat.db"}')
    try:
        database.migrate()
        database.migrate()
    finally:
        database.close()
