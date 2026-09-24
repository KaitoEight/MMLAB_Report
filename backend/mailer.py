"""Durable SMTP outbox. Uncertain delivery is held for review, never blindly resent."""
import os
import base64
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formatdate
from sqlalchemy import select, update
from settings import mailbox, secret
import store


def mode():
    return os.getenv("MAIL_MODE", "preview").strip().strip("\"'").lower()


def deliver(row):
    payload = row['payload']
    message = EmailMessage()
    message['From'] = mailbox()
    message['To'] = row['recipient']
    message['Subject'] = payload['subject']
    message['Date'] = formatdate(localtime=False)
    message['Message-ID'] = f"<mmlab-{row['id']}-{payload.get('delivery_id','initial')}@{mailbox().split('@')[1]}>"
    message['Auto-Submitted'] = 'auto-replied'
    message['X-Auto-Response-Suppress'] = 'All'
    from mail_threading import reply_headers
    thread = reply_headers({'messageId':payload.get('in_reply_to'), 'replyReferences':payload.get('references')})
    if thread['in_reply_to']:
        message['In-Reply-To'] = thread['in_reply_to']
        message['References'] = thread['references']
    message.set_content(payload['body'])
    for attachment in payload.get('attachments', []):
        message.add_attachment(base64.b64decode(attachment['content']),maintype='application',subtype=attachment['subtype'],filename=attachment['name'])
    smtp = None
    data_started = False
    try:
        smtp = smtplib.SMTP_SSL('smtp.gmail.com',465,context=ssl.create_default_context(),timeout=30)
        smtp.login(mailbox(), secret('MMLAB_APP_PASSWORD').replace(' ', ''))
        data_started = True
        smtp.send_message(message,from_addr=mailbox(),to_addrs=[row['recipient']])
        return 'sent', None
    except (smtplib.SMTPRecipientsRefused,smtplib.SMTPSenderRefused) as exc:
        return 'failed', type(exc).__name__
    except smtplib.SMTPResponseException as exc:
        return ('retry' if exc.smtp_code < 500 else 'failed'), f'SMTP {exc.smtp_code}'
    except (OSError,smtplib.SMTPException) as exc:
        return ('unknown' if data_started else 'retry'), type(exc).__name__
    finally:
        if smtp:
            try:smtp.quit()
            except (OSError,smtplib.SMTPException):pass


def dispatch(sender=deliver):
    # Preview produces the complete email and live form but sends no real email.
    if mode() != 'smtp':return
    with store.engine.connect() as conn:
        rows = conn.execute(select(store.outbox).where(store.outbox.c.status.in_(['pending','retry']),
                    store.outbox.c.next_attempt<=time.time()).limit(10)).mappings().all()
    for candidate in rows:
        row=dict(candidate)
        with store.mutation() as conn:
            fresh = conn.execute(select(store.outbox).where(store.outbox.c.id==row['id'])).mappings().first()
            if not fresh or fresh['status'] not in ('pending','retry'):
                continue
            row = dict(fresh)
            expires=conn.execute(select(store.intakes.c.expires).where(store.intakes.c.id==row['id'])).scalar_one()
            if expires < time.time():
                conn.execute(update(store.outbox).where(store.outbox.c.id==row['id']).values(status='failed',last_error='Link hết hạn; cấp link mới trước khi gửi.'))
                continue
            claim=conn.execute(update(store.outbox).where(store.outbox.c.id==row['id'],store.outbox.c.status==row['status'])
                               .values(status='sending',attempts=row['attempts']+1))
        if claim.rowcount!=1:continue
        state,error=sender(row)
        if state=='retry' and row['attempts']>=4:state='failed'
        with store.engine.begin() as conn:
            conn.execute(update(store.outbox).where(store.outbox.c.id==row['id'],store.outbox.c.status=='sending').values(status=state,last_error=error,
                sent_at=store.now() if state=='sent' else None,next_attempt=time.time()+min(3600,60*2**row['attempts'])))


def recover_interrupted():
    with store.engine.begin() as conn:
        conn.execute(update(store.outbox).where(store.outbox.c.status=='sending').values(status='unknown',
                last_error='Worker đã dừng trong lúc gửi; cần kiểm tra Sent trước khi gửi lại.'))
