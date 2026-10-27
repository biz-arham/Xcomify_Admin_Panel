"""Separate persistent worker for a managed daemon; never started by HTTP requests."""
import logging
import signal
import threading
from sqlalchemy import update
from .db import Database
from .models import Lease, now
from .vercel_runtime import cloud_settings
from .worker import Worker

log = logging.getLogger('xcomify.cloud_worker')

def main():
    logging.basicConfig(level=logging.INFO)
    settings = cloud_settings()
    database = Database(settings.database_url)
    database.migrate()
    stop = threading.Event()
    def request_stop(signum, frame):
        stop.set()
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    worker = Worker(database, settings)
    log.info('Cloud sync worker started. No Google access occurs without an active authorized connection.')
    try:
        while not stop.is_set():
            try:
                worker.tick()
            except Exception:
                log.error('Worker tick failed; inspect durable job and sync status before retrying.')
            stop.wait(2)
    finally:
        try:
            with database.Session.begin() as db:
                db.execute(update(Lease).where(Lease.key == 'worker', Lease.owner == worker.owner).values(expires_at=now()-1))
        finally:
            database.close()
    log.info('Cloud worker stopped. Interrupted external writes still require reconciliation.')

if __name__ == '__main__':
    main()
