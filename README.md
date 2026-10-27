> **Vercel package:** read `VERCEL_START_HERE.txt` and `README_VERCEL.md` first. This archive has NOT been deployed. The default hosted profile is web-only; automatic sync requires the optional separate worker.

# Xcomify Central Command

**A runnable, local-first multi-store operations application.** This distribution includes application source, browser UI, database schema, security controls, Google OAuth/Sheets integration code, deterministic tests and deployment/runbooks. It is not only a visual prototype. It is also **not a claim that the entire enterprise blueprint has been completed, independently audited or deployed**.

Start with **[START_HERE.txt](START_HERE.txt)** for Roman Urdu setup instructions. See **[feature status](docs/FEATURE_STATUS.md)** for exact limits.

## Run

Install Python 3.13 (the tested interpreter). Python 3.11+ is accepted by the helper. The first installation needs access to Python package servers.

**Windows:** extract the complete ZIP, then open `START_WINDOWS.bat`. For an isolated synthetic demonstration, open `START_DEMO_WINDOWS.bat` instead. The first-run helper creates `.venv`, installs `requirements.lock`, starts the backend and opens `http://localhost:8787`.

**macOS/Linux:** `./start.sh` or `python3 scripts/launch.py`; append `--demo` for demonstration data. Platform launchers were reviewed, but execution was verified on Linux only.

**Manual:**

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.lock
python run.py
# Or: python run.py --demo
```

Create your own owner account using the setup code printed by the server. There is no shipped/default admin login. The email field identifies an invited account; this edition does not send verification or recovery email. Invitations are private single-use links shared by the owner. A secure HTTPS hosted deployment is required before team access outside this computer.

Do not run demo and real mode on the same port simultaneously. Demo ignores a real `DATABASE_URL` and uses its separate database. The server process must stay running for background sync. Closing the browser does not stop the server; shutting down the PC does.

## Working features

- Multi-store records with per-store currency, timezone, profit definition approval and targets.
- Authenticated UI, owner bootstrap, Argon2id, opaque server-side sessions, CSRF/Origin protections, TOTP/recovery codes, recent-identity checks and scoped roles.
- Orders, CSV import preview/validation, search, pagination, local edits and traceable adjustments.
- Exact-decimal operational profit, missing-input exclusion, currency-separated totals, closing snapshots and target calculations.
- Animated target rings, progress bars, daily pacing, one-time server-recorded milestone celebrations and reduced-motion support.
- Invitations, store assignment, revocation, tasks, notifications, CSV export and print layout.
- Private Google OAuth adapter, metadata/header mapping, read-only previews, durable background scans and single-cell proposal/approval/write/verify flow.
- Formula/protection checks, source identity/postcode validation, row relocation, conflict queue, ambiguous-outcome handling and emergency write-stop.
- Encrypted SQLite backup, restore into an empty destination, writes-off recovery and audit history.

**Connection is not configuration.** Google functionality requires your own client configuration and file authorization. No real Sheets or eBay accounts were accessed. Mapped writes remain off until you review the actual financial/mapping meanings and required release gates. A target progress number is not a statutory accounting statement.

## Repository

```text
run.py                    Local server launcher
xcomify/main.py            API, authentication and scoped business endpoints
xcomify/static/            Responsive browser UI, no external CDN/build step
xcomify/models.py          Version-1 relational schema
xcomify/security.py        Passwords, MFA, roles and audit helpers
xcomify/finance.py         Exact-decimal profit and target logic
xcomify/google.py          Real OAuth/Sheets HTTP adapter
xcomify/sync.py            Source import and controlled write state machine
xcomify/worker.py          Durable queue + elected worker
xcomify/backup.py          Encrypted local backups and safe restoration
scripts/                  Install, backup, restore and offline owner recovery
schema/                   Generated reference DDL, not a separate migration engine
tests/                    Unit/API/adapter/recovery verification
infra/                    Untested hosted deployment template
```

## Architecture decision

The earlier specification proposed Next.js/NestJS/PostgreSQL/Redis. This implementation instead uses **FastAPI, SQLAlchemy, a private SQLite local database, browser JavaScript/CSS and a durable database-backed job queue**. It runs without npm, Redis or a front-end build service. PostgreSQL is supported by the ORM design and a deployment profile is included, but that profile has not been run here. This is a documented implementation change, not a claim that the originally named stack was delivered.

The initial schema is installed automatically. A newer schema version refuses startup to prevent accidental downgrade. Future schema changes require explicit tested migrations. Existing `.data` is never bundled into releases.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
```

Read **[docs/TEST_RESULTS.md](docs/TEST_RESULTS.md)** for the actual measured results, environment and what remains unverified. Deterministic fake-adapter tests are not equivalent to live Google/extension acceptance tests.

## Configuration and recovery

Copy `.env.example` to `.env` only when configuring integration/hosting. Keep filled secrets private. Follow [Google setup](docs/GOOGLE_SETUP.md), [security](docs/SECURITY.md), [operations](docs/OPERATIONS.md) and [hosted deployment](infra/README.md).

Backups contain encrypted business data and the key material needed to restore protected credentials. Store the backup recovery key separately. Losing both recovery credentials and key material is not recoverable by a hidden support backdoor.

No marketplace purchases, cancellations, refunds, tracking submissions, emails, public sharing, cloud subscriptions or production writes were performed while building this package.
