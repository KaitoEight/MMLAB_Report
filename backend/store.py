import hashlib
import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, Float, Integer, JSON, MetaData, String, Table, create_engine, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from settings import database_url, mailbox
from models import Bundle

engine = create_engine(database_url(), pool_pre_ping=True)
meta = MetaData()
reports = Table('reports', meta, Column('id', String, primary_key=True), Column('mailbox', String, nullable=False, index=True), Column('payload', JSON, nullable=False))
snapshots = Table('snapshots', meta, Column('mailbox', String, primary_key=True), Column('payload', JSON, nullable=False))
worker = Table('worker_state', meta, Column('id', Integer, primary_key=True), Column('requested', Boolean, default=False),
               Column('running', Boolean, default=False), Column('heartbeat', Float, default=0),
               Column('started_at', String), Column('finished_at', String), Column('error', String),
               Column('progress', Integer, default=0), Column('total', Integer, default=0))
workflow_settings = Table('workflow_settings', meta, Column('key', String, primary_key=True), Column('value', String, nullable=False))
intakes = Table('paper_intakes', meta, Column('id', String, primary_key=True),
                Column('report_id', String, nullable=False, index=True), Column('recipient', String, nullable=False),
                Column('fields', JSON, nullable=False), Column('original', JSON, nullable=False),
                Column('token_hash', String, nullable=False, unique=True), Column('expires', Float, nullable=False),
                Column('status', String, nullable=False), Column('revision', Integer, nullable=False),
                Column('created_at', String, nullable=False), Column('confirmed_at', String))
outbox = Table('mail_outbox', meta, Column('id', String, primary_key=True), Column('recipient', String, nullable=False),
               Column('payload', JSON, nullable=False), Column('status', String, nullable=False),
               Column('attempts', Integer, nullable=False, default=0), Column('next_attempt', Float, nullable=False, default=0),
               Column('last_error', String), Column('sent_at', String))


def now():
    return datetime.now(timezone.utc).isoformat()


def insert(table):
    return pg_insert(table) if engine.dialect.name == 'postgresql' else sqlite_insert(table)


@contextmanager
def mutation():
    """Serialize report changes, imports and public confirmations across processes."""
    with engine.connect() as conn:
        try:
            if engine.dialect.name == 'sqlite':
                conn.exec_driver_sql('BEGIN IMMEDIATE')
            else:
                conn.begin()
                conn.exec_driver_sql('SELECT pg_advisory_xact_lock(73160262)')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def init_db():
    import monthly_service  # Register monthly-report tables before migration.
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(worker).values(id=1, requested=False, running=False, heartbeat=0, progress=0, total=0).on_conflict_do_nothing(index_elements=['id']))
        # Activation baseline: do not reply retroactively to the existing mailbox.
        conn.execute(insert(workflow_settings).values(key='reply_since', value=now()).on_conflict_do_nothing(index_elements=['key']))
        conn.execute(insert(workflow_settings).values(key='monthly_started', value=now()).on_conflict_do_nothing(index_elements=['key']))

    from receipt_policy import migrate
    migrate()
    from mail_threading import migrate_pending
    migrate_pending()


def state():
    with engine.connect() as conn:
        result = dict(conn.execute(select(worker).where(worker.c.id == 1)).mappings().one())
    result['online'] = time.time() - (result['heartbeat'] or 0) < 100
    return result


def set_state(**values):
    with engine.begin() as conn:
        conn.execute(update(worker).where(worker.c.id == 1).values(**values))


def ingest(bundle: Bundle, workflow=False):
    if bundle.mailbox.lower() != mailbox():
        raise ValueError('File không thuộc hộp thư cấu hình.')
    from report_cleanup import clean_bundle
    payload = clean_bundle(bundle.model_dump())
    snapshot = {'importedAt': now(), 'generatedAt': bundle.generated_at, 'summary': payload['summary'],
                'review': {'review': bundle.review_candidates, 'errors': bundle.errors}}
    # One database transaction: records and snapshot either all persist, or none do.
    with mutation() as conn:
        for r in payload['reports']:
            r['id'] = 'imap-' + hashlib.sha256(r['sourceId'].encode()).hexdigest()
            existing = conn.execute(select(reports.c.payload).where(reports.c.id == r['id'])).scalar_one_or_none()
            if r.get('messageId') and r.get('sender'):
                same_messages = conn.execute(select(reports.c.payload).where(
                    reports.c.mailbox==mailbox(), reports.c.payload['messageId'].as_string()==r['messageId'],
                    reports.c.payload['sender'].as_string()==r['sender'])).scalars().all()
                if any(x.get('deletedAt') or x.get('adminEditedAt') or x.get('confirmationStatus')=='confirmed' for x in same_messages):
                    continue

            if existing and (existing.get('deletedAt') or existing.get('adminEditedAt') or existing.get('confirmationStatus') == 'confirmed'):
                continue
            # Imported data cannot forge server-owned edit/deletion markers.
            for key in ('deletedAt', 'adminEditedAt', 'adminEditedBy', 'reportVersion',
                        'confirmationStatus','confirmationSource','confirmedBy','confirmedAt','confirmationHistory','intakeId',
                        'approvalStatus','approvalSource','approvedAt'):
                r.pop(key, None)
            from intake import register_paper, receipt_block_reason
            # Never trust this flag from an imported JSON file.
            r['mailWorkflowSource'] = bool(workflow)
            from receipt_policy import approve_received
            if workflow and existing and existing.get('approvalStatus')=='approved':
                r['approvedAt']=existing['approvedAt']
            approve_received(r)
            intake_row = register_paper(conn, r) if workflow else None
            if r['type'] == 'Paper':
                r['receiptIssue'] = '' if intake_row else (receipt_block_reason(conn, r) if workflow else 'Nhập JSON không tự gửi email. Quét Gmail để xác định người forward.')
            if intake_row and intake_row['report_id'] != r['id']:
                continue  # Same sender and outer Message-ID: already received.
            existing = conn.execute(select(reports.c.payload).where(reports.c.id == r['id'])).scalar_one_or_none()
            # A mailbox rescan must never overwrite the user's confirmed correction.
            if existing and existing.get('confirmationStatus') == 'confirmed':
                continue
            if intake_row:
                r['confirmationStatus'] = intake_row['status']
                r['intakeId'] = intake_row['id']
            stmt = insert(reports).values(id=r['id'], mailbox=mailbox(), payload=r)
            conn.execute(stmt.on_conflict_do_update(index_elements=['id'], set_={'payload': stmt.excluded.payload}))
        stmt = insert(snapshots).values(mailbox=mailbox(), payload=snapshot)
        conn.execute(stmt.on_conflict_do_update(index_elements=['mailbox'], set_={'payload': stmt.excluded.payload}))
    return len(payload['reports'])


def read_reports():
    with engine.connect() as conn:
        records = conn.execute(select(reports.c.payload).where(reports.c.mailbox == mailbox())).scalars().all()
        snapshot = conn.execute(select(snapshots.c.payload).where(snapshots.c.mailbox == mailbox())).scalar_one_or_none()
    return [r for r in records if not r.get('deletedAt')], snapshot
