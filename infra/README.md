# Hosted deployment gate

The working/tested distribution is the local SQLite edition. The Docker/PostgreSQL profile is provided for deployment engineering; it was **not launched or benchmarked** in the build environment. Do not expose the local HTTP edition to a LAN or internet.

For a hosted system, use a persistent Linux service, PostgreSQL, private database network, HTTPS reverse proxy and secret management. Set `XCOMIFY_ENV=production`, an exact HTTPS `XCOMIFY_BASE_URL`, `DATABASE_URL=postgresql+psycopg://...`, encryption key and bootstrap token. Generate keys locally with the cryptography library; never paste real values into chats or source control. The included compose example reads environment values and publishes only app port 8080 to loopback. A reverse proxy must preserve Host and Origin. This app does not trust arbitrary forwarded-IP headers. Configure trusted proxy/IP rate limiting at the edge before production.

One web process with its embedded elected worker is the initial supported topology. For a separate worker, set `XCOMIFY_WORKER=false` on web and run `python -m xcomify.worker` with the same environment. The durable database lease elects one worker. Do not deploy multiple unsupervised instances expecting unlimited concurrency. Long scans can expire the lease and fail safely; validate actual spreadsheet sizes and limits.

The original blueprint called for Next.js/NestJS/PostgreSQL/Redis. This deliverable intentionally uses FastAPI/SQLAlchemy/browser JS with a transactional database queue, which runs without a JavaScript build service. PostgreSQL compatibility is designed but not tested here. It is not a hidden Redis substitute: unfinished operations live durably in `jobs` and `write_intents`.

Before release: create a staging database; execute all tests against PostgreSQL; inspect migrations/transactions; verify Google OAuth callback and one isolated real Sheet; test real extension versions; test MFA/recovery; configure certificate rotation, backups/PITR, monitoring and least-privilege database credentials; perform a restore drill and security review. Pin container images by a verified digest in your infrastructure repository. Optional psycopg requirements need a deployment lock after testing on your target image.

`Database.migrate()` installs schema version 1 and refuses newer versions. It is not an automatic upgrade/migration framework for future schema changes. No automatic SQLite-to-PostgreSQL migration is claimed. Do not point a new URL at an existing account and expect data to move.

Cloud hosting, domain, emails and Google Cloud configuration have not been purchased, created or changed. No recurring hosting cost estimate or uptime SLA is asserted.
