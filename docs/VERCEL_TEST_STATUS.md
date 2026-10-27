# Vercel package verification

Prepared 27 October 2026. This is local verification, not evidence of a live deployment.

## Executed

- Original application/sync tests after the database-initialization change: **63 passed**.
- Added hosted adapter tests: **26 passed**.
- Combined suite: **89 passed, 1 warning**, in 25.26 seconds.
- Python compilation of new/changed entrypoints: passed.
- Public asset build: four allowlisted UI assets copied.

New coverage includes database URL normalization/TLS, missing secret rejection, exact HTTPS-origin checks, preview and demo rejection, embedded-worker disablement, no database access at entrypoint import, secret-redacted initialization failures, an actual HTTP setup/login flow through the hosted adapter with an isolated injected SQLite fixture, pool configuration inspection, static asset allowlisting, deployment-profile structure, and repeated local schema initialization.

## Not executed / not established

No Vercel upload, actual Vercel build, live project URL, daemon container build/deployment, live PostgreSQL connection, Google OAuth authorization, real Sheets read/write, real extension regression, production backup/restore, load test, security penetration test, or paid infrastructure provisioning. The optional driver was pinned but not installed/tested against PostgreSQL in this environment.

The hosted loader rejects SQLite; test injection does not relax the production guard. PostgreSQL advisory-lock and TLS/pool code still require a real PostgreSQL integration test. The default deployment is web-only: automatic Sheet sync requires the separately configured persistent worker.

Raw combined output: `verification/vercel-test-results.txt`.
