"""Reply metadata comes exclusively from the outer message headers."""
import re

# Conservative interoperable subset of RFC message IDs. Never accept controls.
ID = re.compile(r'<[^<>\s@\x00-\x20\x7f-\uffff]+@[^<>\s@\x00-\x20\x7f-\uffff]+>')


def message_ids(value):
    return list(dict.fromkeys(v for v in ID.findall(str(value or '')[:32000]) if v.isascii() and len(v) <= 990))


def reply_headers(original):
    subject = re.sub(r'[\x00-\x20\x7f]+', ' ', str(original.get('subject') or '')).strip()
    subject = subject if re.match(r'^re\s*:', subject, re.I) else 'Re: ' + subject
    parent = str(original.get('messageId') or '').strip()
    refs = message_ids(original.get('replyReferences', ''))
    if not parent.isascii() or not ID.fullmatch(parent) or len(parent) > 990:
        parent = ''; refs = []
    else:
        refs = [v for v in refs if v != parent]
        # Bound abusive chains while retaining the root and most recent ancestors.
        refs = (refs[:1] + refs[-18:] if len(refs) > 19 else refs) + [parent]
    return {'subject': subject.rstrip(), 'in_reply_to': parent, 'references': ' '.join(refs)}


def migrate_pending():
    """Refresh queued receipts only; never resend sent/uncertain historical mail."""
    from sqlalchemy import select, update
    import store
    with store.mutation() as conn:
        rows = conn.execute(select(store.outbox.c.id, store.outbox.c.payload, store.intakes.c.original)
            .join(store.intakes, store.intakes.c.id == store.outbox.c.id)
            .join(store.reports, store.reports.c.id == store.intakes.c.report_id)
            .where(store.reports.c.mailbox == store.mailbox(), store.intakes.c.status != 'cancelled',
                   store.outbox.c.status.in_(['pending', 'retry']))).mappings().all()
        for row in rows:
            payload = {**row['payload'], **reply_headers(row['original'])}
            conn.execute(update(store.outbox).where(store.outbox.c.id == row['id']).values(payload=payload))
