"""Single IMAP reader process. Reads only, then commits validated reports atomically."""
import json
import os
import signal
import threading
import time
from pathlib import Path
from sqlalchemy import text
from imap_fetch import fetch_once
from models import Bundle
from settings import configured, interval, mailbox, secret
import store
import mailer
import monthly_service

stopping = threading.Event()


def run_once(fetcher=fetch_once):
    output = Path(os.getenv('IMAP_OUTPUT', '/data/imap'))
    store.set_state(running=True, requested=False, started_at=store.now(), error=None, progress=0, total=0)
    try:
        fetcher(mailbox(), secret('MMLAB_APP_PASSWORD').replace(' ', ''), os.getenv('IMAP_FOLDER', 'INBOX'), output,
                progress=lambda done, total: store.set_state(progress=done, total=total, heartbeat=time.time()))
        bundle = Bundle.model_validate_json((output / 'mmlab_export.json').read_bytes())
        store.ingest(bundle, workflow=True)
        store.set_state(finished_at=store.now(), error=None)
    except Exception as exc:
        # Exception type only: server errors may embed untrusted mailbox data.
        store.set_state(error=f'{type(exc).__name__}: lượt đồng bộ chưa hoàn tất; sẽ thử lại. Kiểm tra mạng và App Password.')
        print(f'IMAP cycle failed ({type(exc).__name__}); retry scheduled.', flush=True)
    finally:
        store.set_state(running=False, heartbeat=time.time())


def main():
    store.init_db()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    # Keep one connection alive to own the PostgreSQL session advisory lock.
    with store.engine.connect() as lock:
        if store.engine.dialect.name == 'postgresql':
            if not lock.execute(text('SELECT pg_try_advisory_lock(73160261)')).scalar():
                raise RuntimeError('Another IMAP worker already owns this database.')
            lock.commit()
        store.set_state(running=False, heartbeat=time.time())
        mailer.recover_interrupted()
        monthly_service.recover_interrupted()
        due = 0.0
        while not stopping.is_set():
            store.set_state(heartbeat=time.time())
            if configured() and (time.monotonic() >= due or store.state()['requested']):
                run_once()
                due = time.monotonic() + interval()
            try:
                mailer.dispatch()
                monthly_service.enqueue_due()
                monthly_service.dispatch()
            except Exception as exc:
                print(f'Mail queue pending ({type(exc).__name__}).', flush=True)
            stopping.wait(3)
        store.set_state(running=False, heartbeat=0)


if __name__ == '__main__':
    main()
