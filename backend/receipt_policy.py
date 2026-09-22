"""Automatic receipt approval is independent of validation and publication status."""
from sqlalchemy import select, update
import store

POLICY = 'automatic-receipt-v1'
OWNED_FIELDS = ('approvalStatus', 'approvalSource', 'approvedAt')


def approve_received(report):
    if report.get('mailWorkflowSource') and report.get('forwarded') and not report.get('deletedAt'):
        report.update(approvalStatus='approved', approvalSource='automatic',
                      approvedAt=report.get('approvedAt') or store.now())
    return report


def migrate():
    """Upgrade existing receipts without queuing or resending historical email."""
    import intake
    with store.mutation() as conn:
        key = POLICY + ':' + store.mailbox()
        if conn.execute(select(store.workflow_settings.c.key).where(store.workflow_settings.c.key == key)).first():
            return
        rows = conn.execute(select(store.reports).where(store.reports.c.mailbox == store.mailbox())).mappings().all()
        for row in rows:
            report = approve_received(dict(row['payload']))
            if report.get('approvalStatus') != 'approved' or report.get('deletedAt'):
                continue
            conn.execute(update(store.reports).where(store.reports.c.id == row['id']).values(payload=report))
            forms = conn.execute(select(store.intakes).where(store.intakes.c.report_id == row['id'], store.intakes.c.status != 'cancelled')).mappings().all()
            for form in forms:
                conn.execute(update(store.intakes).where(store.intakes.c.id == form['id']).values(original=report))
                outgoing = conn.execute(select(store.outbox).where(store.outbox.c.id == form['id'])).mappings().first()
                if outgoing and outgoing['status'] in ('pending', 'retry'):
                    payload = dict(outgoing['payload'])
                    payload.update(intake.mail_content({**form, 'original':report}, payload['link']))
                    conn.execute(update(store.outbox).where(store.outbox.c.id == form['id']).values(payload=payload))
        conn.execute(store.insert(store.workflow_settings).values(key=key, value=store.now()))
