# Xcomify: Vercel deployment preparation

**Status: prepared and tested locally; NOT uploaded, deployed, or live.**
Prepared on 27 October 2026 from the supplied Xcomify Central Command v1.0 archive.

The Vercel connection in the current ChatGPT workspace is disabled by its administrator. No Vercel project, deployment, database, paid service, DNS record, or Google permission has been created or changed. An authorized administrator must resolve access before an agent can deploy into that account. This package does not bypass that restriction.

## Changes in this package

- Native FastAPI `index.py` entrypoint, with no database connections or mutations at import/build inspection.
- Production-only adapter requiring an exact HTTPS origin, private owner setup token, stable encryption key, and PostgreSQL. SQLite, synthetic demo mode, unencrypted database settings, and Preview environments are rejected.
- Embedded worker disabled in HTTP functions. A separate persistent worker entrypoint and optional Vercel Daemons configuration retain the existing durable queue.
- PostgreSQL URL normalization, TLS defaults, HTTP-function connection-pool settings, and a transaction-scoped advisory lock around schema initialization.
- A build script that copies only public UI assets; deployment ignore rules exclude credentials and local databases.
- Original financial rules, permissions, Google adapters, and extension workflow preserved. No real Sheets or extensions were accessed.

## Hosting layout

Browser -> Vercel FastAPI application -> managed PostgreSQL.
Separate worker -> the same PostgreSQL queue -> authorized Google Sheets API.

Web and worker must share the database and stable encryption key. Use a provider-supported pooled database connection where appropriate and keep compute near the database. `/tmp` is scratch only, never durable application storage.

**The base `vercel.json` deploys web only. It does not process background sync or queued Sheet writes.** The optional `infra/vercel.with-daemon.json` adds a persistent worker, subject to beta acceptance, account support, and testing. A rendered dashboard is not proof that background work runs. No hidden daily-cron substitute is included.

## Required access and services

An authorized Vercel team/account connection, managed PostgreSQL database, canonical HTTPS domain, and private production settings are required. This is commercial business software: Vercel's fair-use rules restrict Hobby to non-commercial personal use, so select an eligible commercial plan. No paid resource has been purchased.

A new PostgreSQL connection creates a separate workspace. It does not automatically migrate existing local SQLite data. Preserve any existing data and review a migration separately.

## Private production environment variables

Never commit a populated `.env`, send credentials in chat, or publish screenshots containing secrets.

| Variable | Required value or purpose |
|---|---|
| `DATABASE_URL` | Authorized PostgreSQL connection URL, with URL-encoded credentials where needed and TLS. |
| `XCOMIFY_BASE_URL` | Exact HTTPS origin, e.g. `https://YOUR-APP-DOMAIN`; no route or query. |
| `XCOMIFY_ENCRYPTION_KEY` | Stable Fernet key generated privately on the owner's computer; retain a recovery copy. |
| `XCOMIFY_BOOTSTRAP_TOKEN` | Random first-owner setup token, at least 32 characters. |
| `XCOMIFY_ENV` | `production`. |
| `XCOMIFY_WORKER` | `false` for web; the separate worker starts explicitly. |
| `XCOMIFY_DEMO` | `false`. |
| `GOOGLE_CLIENT_ID` | Optional initially; required for private Sheets authorization. |
| `GOOGLE_CLIENT_SECRET` | Optional initially; required for private Sheets authorization. |

The hosted adapter normalizes settings and disables the embedded web worker. Do not rotate the encryption key without a reviewed re-encryption process: saved Google credentials rely on that key.

Run `python scripts/generate_hosting_secrets.py` ONLY on the owner's computer. Put its PRIVATE output directly in secret settings and secure recovery storage, never in chat or Git. No production secrets were generated for this package.

## Deployment procedure for an authorized administrator

1. Resolve the workspace Vercel restriction. Select the authorized team/project and approve the hosting plan, database, and beta-worker choice. Do not use alternative credentials to bypass organizational restrictions.
2. Validate on a separate staging project and database first. This profile refuses Preview. Use a separate staging project deployed as that project's production environment, with staging-only data and credentials. Never share production secrets with Preview.
3. Provision/select PostgreSQL, configure TLS, set private production environment variables, and enable the provider's approved backup/restore policy. Set the canonical origin to the actual project domain.
4. Import this project root from an authorized private Git repository using Vercel's documented deployment workflow after access is approved. Use Python 3.13, FastAPI, and the supplied `vercel.json`. Do not override it with an unrelated static output directory or upload local data folders.
5. The build copies only approved UI assets. The first application request initializes schema version 1 with a PostgreSQL advisory lock. For stricter database privileges, have an administrator initialize schema using the approved migration process and reduce runtime privileges afterward. Current code still checks schema on cold starts; it is not a full future-version migration framework.
6. Visit the exact canonical HTTPS origin. Complete owner setup with the private token and create your own password. Enable MFA before authorizing Sheet writes. There is no default admin password.
7. Start and verify the separate worker. System Status must show a current worker lease, and queued jobs must complete. Until then background synchronization is not operational.
8. Configure Google OAuth redirect as `XCOMIFY_BASE_URL/api/google/callback`, authorize a Google identity, keep Sheets Restricted, verify mappings on a test copy, reconcile imports, and only then approve limited write-back under the original release gates.
9. Test live sessions, MFA, permissions, token refresh, worker recovery, interrupted writes, backup restoration, and actual extensions before operating live stores.

## Optional Vercel Daemons profile: public beta

Vercel announced Daemons public beta on 15 October 2026. It supports continuously running container workers. This package provides a template, not a verified live deployment.

After an authorized operator approves beta use and confirms account capability, replace root `vercel.json` with `infra/vercel.with-daemon.json` and deploy that configuration. It adds:

- Worker build: `Dockerfile.worker`.
- Start command: `python -m xcomify.cloud_worker`.
- One instance in `iad1` as a template. Select an appropriate supported region near the database and review data-residency requirements before deployment.
- The same private production variables as web.

The worker handles termination signals, attempts to finish its current tick, and releases its lease on normal exit. An abrupt termination may interrupt a remote request; existing unknown-outcome reconciliation still applies. No guarantee of lossless concurrent editing is introduced.

The base profile deliberately does not enable beta infrastructure or a recurring worker bill automatically. When Daemons is unavailable or not approved, a separately authorized persistent worker host is needed for full sync. Never hide that missing capability or report queued changes as confirmed.

## Security and operational boundaries

- Local SQLite backup functions are not PostgreSQL backups. Use provider backup/PITR and verify restoration.
- Existing local records do not automatically move to PostgreSQL.
- HTTP functions never run an endless worker loop; there is no temporary SQLite fallback.
- This package uses a separate worker rather than a cron retrofit, so there is no cron endpoint or `CRON_SECRET`.
- Preview deployments are intentionally refused; use isolated staging projects.
- Vercel's actual builder, daemon/container, live PostgreSQL, live Google OAuth/Sheets, and production security review remain unverified here.
- The driver is pinned to `psycopg[binary]==3.3.6`, but this environment had no PostgreSQL server or installed psycopg driver. Tests inspect pool configuration and URL handling without proving a live database connection.
- Tests are not a penetration test or security certification. Configure edge rate limits, deployment protection, monitoring, private database access, and spending alerts with the owner.

## Verification

Run `python -m pytest -q` with the project dependencies. Actual results are included in `verification/vercel-test-results.txt`. See `docs/VERCEL_TEST_STATUS.md` for scope and outstanding release gates.

Original tests use isolated SQLite fixtures. New adapter tests use configuration checks and an injected local test database. The real production loader still refuses SQLite. No mocked result is presented as a connected Google or Vercel account.

## Official references checked

- https://vercel.com/docs/frameworks/backend/fastapi
- https://vercel.com/docs/functions/runtimes/python
- https://vercel.com/kb/guide/is-sqlite-supported-in-vercel
- https://vercel.com/changelog/vercel-daemons-is-now-in-public-beta
- https://vercel.com/daemons
- https://vercel.com/docs/limits/fair-use-guidelines
- https://pypi.org/project/psycopg-binary/

The October 2026 Python announcement is newer than older docs still describing Python as beta. Daemons is a separate public-beta feature. Validate current configuration and plan support in the actual account before release.
