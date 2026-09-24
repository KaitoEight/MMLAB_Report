"""Paper receipt, private correction links and explicit user confirmation."""
import hashlib
import os
import re
import secrets
import time
from datetime import datetime
from email.utils import getaddresses
from urllib.parse import urlsplit
from pydantic import ValidationError
from sqlalchemy import select, update
from fastapi import HTTPException
from mmlab_pipeline.validator import WorkReport, LABELS
from mmlab_pipeline.members import resolve_members, sender_matches
from settings import mailbox
import store

FIELDS = ('title', 'authors', 'venue', 'role', 'index', 'ranking')


def reply_recipient(message):
    """Use only the outer From, never Reply-To or quoted recipients."""
    if len(message.get_all('From', [])) != 1:
        return '', 'From phải có đúng một người gửi.'
    people = getaddresses([str(message['From'])])
    if len(people) != 1 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", people[0][1]):
        return '', 'Không xác định được địa chỉ người forward.'
    address = people[0][1]
    auto = str(message.get('Auto-Submitted', 'no')).lower()
    precedence = str(message.get('Precedence', '')).lower()
    if address.lower() == mailbox() or auto != 'no' or precedence in ('bulk', 'list', 'junk') or message.get('List-Id'):
        return '', 'Không tự phản hồi thư hệ thống/danh sách hoặc chính hộp thư lab.'
    if re.search(r'(?:no[._-]?reply|mailer-daemon|postmaster)', address.split('@')[0], re.I):
        return '', 'Địa chỉ tự động không nhận phản hồi.'
    return address, ''


def public_base():
    value = os.getenv('PUBLIC_BASE_URL', os.getenv('APP_ORIGIN', 'http://localhost:8080')).rstrip('/')
    parsed = urlsplit(value)
    if parsed.scheme not in ('https', 'http') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('PUBLIC_BASE_URL phải là origin, ví dụ https://reports.example.com')
    if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1'):
        raise ValueError('PUBLIC_BASE_URL công khai phải dùng HTTPS.')
    return value


def validation(fields):
    try:
        model = WorkReport.model_validate({'report_type': 'Paper', **fields})
        return model, []
    except ValidationError as exc:
        return None, [{'field': e['loc'][0] if e['loc'] else 'report', 'reason': e['msg']} for e in exc.errors(include_url=False, include_context=False)]


def mail_content(row, link):
    _, errors = validation(row['fields'])
    lines = ['Chào bạn,', '', 'MMLab đã nhận được email Paper bạn chuyển tiếp.',
             f"Mã tiếp nhận: {row['id'][:12]}", '',
             'Thông tin hệ thống trích xuất (chưa được bạn xác nhận):', 'Type of Report: Paper']
    lines += [f"{LABELS[key]}: {row['fields'][key] or '[CẦN BỔ SUNG]'}" for key in FIELDS]
    if errors:
        lines += ['', 'Các trường cần bổ sung hoặc kiểm tra:']
        lines += [f"- {LABELS.get(e['field'],e['field'])}: {e['reason']}" for e in errors]
    lines += ['', 'Vui lòng mở form đã điền sẵn, sửa/bổ sung thông tin và bấm Xác nhận & gửi:', link,
              '', 'Link dùng riêng cho báo cáo này và hết hạn sau 7 ngày. Không chuyển link cho người khác.',
              'Email này xác nhận đã nhận thư, chưa đồng nghĩa dữ liệu đã đầy đủ hoặc bài báo đã được xuất bản.',
              'Nếu mọi trường đã đúng, vẫn vui lòng xác nhận trên form.', '', 'MMLab — UIT']
    return {'subject': f"[MMLab] Đã nhận Paper — cần xác nhận #{row['id'][:12]}",
            'body': '\n'.join(lines), 'link': link,
            'in_reply_to': row['original'].get('messageId', '')}


def receipt_block_reason(conn, report, include_cutoff=True):
    if report.get('type') != 'Paper':
        return 'Không phải Paper.'
    if not report.get('forwarded'):
        return 'Chưa nhận diện được thư forward.'
    if not report.get('replyRecipient'):
        return report.get('replySuppressedReason') or 'Chưa xác định người nhận phản hồi.'
    try:
        public_base()
    except ValueError as exc:
        return str(exc)
    if include_cutoff:
        stamp = report.get('receivedAt')
        since = os.getenv('AUTO_REPLY_SINCE') or conn.execute(select(store.workflow_settings.c.value).where(store.workflow_settings.c.key=='reply_since')).scalar_one()
        if not stamp or datetime.fromisoformat(stamp) < datetime.fromisoformat(since):
            return 'Thư đến trước mốc tự động phản hồi. Có thể tạo email xác nhận cho riêng Paper này.'
    return ''


def register_paper(conn, report, allow_historical=False):
    if receipt_block_reason(conn, report, include_cutoff=False):
        return None
    recipient = report['replyRecipient']
    message_id = report.get('messageId') or report['sourceId']
    ident = hashlib.sha256((mailbox()+'\n'+recipient.lower()+'\n'+message_id).encode()).hexdigest()
    existing = conn.execute(select(store.intakes).where(store.intakes.c.id==ident)).mappings().first()
    if existing:
        if existing['status'] != 'cancelled':
            return dict(existing)
        if not allow_historical:
            return None
        conn.execute(store.outbox.delete().where(store.outbox.c.id==ident))
        conn.execute(store.intakes.delete().where(store.intakes.c.id==ident))
    if not allow_historical and receipt_block_reason(conn, report):
        return None
    token = secrets.token_urlsafe(32)
    row = {'id':ident, 'report_id':report['id'], 'recipient':recipient,
           'fields':{k:('' if LABELS[k] in report.get('missingFields',[]) else report.get(k) or '') for k in FIELDS}, 'original':report,
           'token_hash':hashlib.sha256(token.encode()).hexdigest(), 'expires':time.time()+7*86400,
           'status':'pending', 'revision':0, 'created_at':store.now(), 'confirmed_at':None}
    link = public_base() + '/#confirm=' + token
    conn.execute(store.insert(store.intakes).values(**row).on_conflict_do_nothing(index_elements=['id']))
    payload = mail_content(row, link)
    conn.execute(store.insert(store.outbox).values(id=ident,recipient=recipient,payload=payload,
                 status='pending',attempts=0,next_attempt=0).on_conflict_do_nothing(index_elements=['id']))
    return row


def token_row(conn, token):
    if not re.fullmatch(r'[A-Za-z0-9_-]{40,100}', token):
        raise HTTPException(404, 'Link không hợp lệ.')
    row = conn.execute(select(store.intakes).where(store.intakes.c.token_hash==hashlib.sha256(token.encode()).hexdigest())).mappings().first()
    if not row:
        raise HTTPException(404, 'Link không hợp lệ.')
    if row['status'] == 'cancelled':
        raise HTTPException(410, 'Báo cáo đã bị xóa hoặc được admin thay đổi loại. Link này đã ngừng hoạt động.')
    if row['expires'] < time.time():
        raise HTTPException(410, 'Link đã hết hạn. Liên hệ quản trị MMLab để cấp lại.')
    return dict(row)


def view(token):
    with store.engine.connect() as conn:
        row = token_row(conn, token)
    _, errors = validation(row['fields'])
    return {'id':row['id'][:12], 'fields':row['fields'], 'errors':errors,
            'status':row['status'], 'revision':row['revision'], 'expiresAt':row['expires'],
            'confirmationSource':row['original'].get('confirmationSource','sender'),
            'warnings':row['original'].get('warnings', [])}


def confirm(token, fields, revision):
    with store.mutation() as conn:
        row = token_row(conn, token)
        if row['status'] == 'confirmed':
            return {'confirmed':True, 'alreadyConfirmed':True,'confirmationSource':row['original'].get('confirmationSource','sender')}
        if revision != row['revision']:
            raise HTTPException(409, 'Dữ liệu đã thay đổi. Hãy tải lại form.')
        model, errors = validation(fields)
        if errors:
            return {'confirmed':False, 'errors':errors}
        normalized = model.model_dump(mode='json')
        report = dict(row['original'])
        report['reportVersion'] = report.get('reportVersion', 0) + 1
        for key in FIELDS:
            report[key] = normalized[key]
        members = resolve_members(normalized['authors'])
        ids = [m['id'] for m in members]
        owners = sender_matches(row['recipient'])
        owner = report.get('memberId') if report.get('memberId') in ids else (owners[0]['member']['id'] if len(owners)==1 else None)
        issues = []
        if not ids:issues.append('Không tìm thấy thành viên chính thức của lab trong tác giả.')
        if owner not in ids:owner=None;issues.append('Chưa xác định Person in Charge trong tác giả.')
        report.update(memberIds=ids, memberId=owner, isValid=True, missingFields=[],invalidFields=[],
                      issues=issues, warnings=['Thông tin do người gửi xác nhận; Index/Ranking chưa được xác minh bên ngoài.'],
                      confirmationStatus='confirmed', confirmedAt=store.now(), intakeId=row['id'])
        report.update(confirmationSource='sender',confirmedBy=row['recipient'])
        updated = conn.execute(update(store.intakes).where(store.intakes.c.id==row['id'],store.intakes.c.status=='pending',
                                 store.intakes.c.revision==revision).values(fields={k:normalized[k] for k in FIELDS},
                                 status='confirmed',revision=revision+1,confirmed_at=report['confirmedAt'],original=report))
        if updated.rowcount != 1:raise HTTPException(409, 'Form đã được xử lý. Hãy tải lại trang.')
        conn.execute(update(store.reports).where(store.reports.c.id==row['report_id']).values(payload=report))
    return {'confirmed':True, 'alreadyConfirmed':False, 'confirmationSource':'sender', 'warnings':issues}


def admin_list():
    with store.engine.connect() as conn:
        rows = conn.execute(select(store.intakes, store.outbox.c.status.label('mail_status'),
                    store.outbox.c.payload.label('mail_payload'), store.outbox.c.last_error)
                    .join(store.outbox,store.intakes.c.id==store.outbox.c.id).where(store.intakes.c.status!='cancelled').order_by(store.intakes.c.created_at.desc()).limit(200)).mappings().all()
    return [{'id':r['id'],'recipient':r['recipient'],'status':r['status'],'mailStatus':r['mail_status'],
             'title':r['fields'].get('title',''), 'createdAt':r['created_at'],'lastError':r['last_error'],
             'subject':r['mail_payload']['subject'],'body':r['mail_payload']['body'],'link':r['mail_payload']['link']} for r in rows]


def reissue(ident):
    with store.mutation() as conn:
        row=conn.execute(select(store.intakes).where(store.intakes.c.id==ident)).mappings().first()
        if not row:raise HTTPException(404,'Không tìm thấy hồ sơ.')
        row=dict(row)
        if row['status']=='cancelled':raise HTTPException(410,'Hồ sơ đã bị hủy.')
        if row['status']=='confirmed':raise HTTPException(409,'Báo cáo đã xác nhận.')
        token=secrets.token_urlsafe(32)
        conn.execute(update(store.intakes).where(store.intakes.c.id==ident).values(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),expires=time.time()+7*86400,revision=row['revision']+1))
        payload=mail_content(row,public_base()+'/#confirm='+token)
        payload['delivery_id']=secrets.token_hex(8)
        conn.execute(update(store.outbox).where(store.outbox.c.id==ident).values(payload=payload,status='pending',attempts=0,next_attempt=0,last_error=None,sent_at=None))
    return {'ok':True}


def confirmation_info(report_id, conn=None):
    if conn is None:
        with store.engine.connect() as c:return confirmation_info(report_id,c)
    report=conn.execute(select(store.reports.c.payload).where(store.reports.c.id==report_id,store.reports.c.mailbox==mailbox())).scalar_one_or_none()
    if not report or report.get('deletedAt'):raise HTTPException(404,'Không tìm thấy báo cáo.')
    if report['type']!='Paper':raise HTTPException(409,'Chỉ áp dụng cho Paper.')
    row=conn.execute(select(store.intakes,store.outbox.c.payload.label('mail_payload'),store.outbox.c.status.label('mail_status'))
        .join(store.outbox,store.outbox.c.id==store.intakes.c.id)
        .where(store.intakes.c.report_id==report_id,store.intakes.c.status!='cancelled')).mappings().first()
    import mailer
    return {'report':report,'mailMode':mailer.mode(),'email':None if not row else {
        'recipient':row['recipient'],'subject':row['mail_payload']['subject'],'body':row['mail_payload']['body'],
        'link':row['mail_payload']['link'],'mailStatus':row['mail_status'],'expired':row['expires']<time.time()}}


def create_for_report(report_id, revision=None, resend=False):
    """Explicit admin action; the recipient always comes from worker-read headers."""
    with store.mutation() as conn:
        report = conn.execute(select(store.reports.c.payload).where(
            store.reports.c.id==report_id, store.reports.c.mailbox==mailbox())).scalar_one_or_none()
        if not report or report.get('deletedAt'):
            raise HTTPException(404, 'Không tìm thấy báo cáo.')
        if revision is not None and report.get('reportVersion',0)!=revision:
            raise HTTPException(409,'Báo cáo vừa thay đổi. Đóng chi tiết và mở lại trước khi gửi.')
        if report.get('confirmationStatus')=='confirmed':
            raise HTTPException(409,'Paper đã được xác nhận. Sửa và lưu nếu muốn yêu cầu xác nhận phiên bản mới.')
        if not report.get('mailWorkflowSource'):
            raise HTTPException(409, 'Cần quét Gmail lại để xác định người forward từ email gốc trước khi gửi.')
        reason = receipt_block_reason(conn, report, include_cutoff=False)
        if reason:raise HTTPException(409, reason)
        row = register_paper(conn, report, allow_historical=True)
        mail=conn.execute(select(store.outbox).where(store.outbox.c.id==row['id'])).mappings().one()
        if mail['status']=='sending':raise HTTPException(409,'Email đang được gửi. Đợi hoàn tất trước khi thao tác lại.')
        expired=row['expires']<time.time()
        if mail['status'] not in ('pending','retry') or expired:
            if not resend:
                raise HTTPException(409,'Đã có email xác nhận trước đó. Chọn Gửi lại email xác nhận để cấp link mới.')
            token=secrets.token_urlsafe(32)
            conn.execute(update(store.intakes).where(store.intakes.c.id==row['id']).values(
                token_hash=hashlib.sha256(token.encode()).hexdigest(),expires=time.time()+7*86400,revision=row['revision']+1))
            payload=mail_content(row,public_base()+'/#confirm='+token)
            payload['delivery_id']=secrets.token_hex(8)
            conn.execute(update(store.outbox).where(store.outbox.c.id==row['id']).values(
                payload=payload,status='pending',attempts=0,next_attempt=0,last_error=None,sent_at=None))
        report = dict(report, confirmationStatus=row['status'], intakeId=row['id'], receiptIssue='')
        conn.execute(update(store.reports).where(store.reports.c.id==report_id).values(payload=report))
        result=confirmation_info(report_id,conn)
    return {'ok': True, 'status': row['status'], **result}


def diagnostics(worker_state):
    import mailer
    mode = mailer.mode()
    notes = []
    if mode != 'smtp':
        notes.append('Chưa bật gửi email: sửa MAIL_MODE=smtp trong .env rồi khởi động lại ứng dụng.')
    if not worker_state.get('online'):
        notes.append('Worker chưa hoạt động. Chạy run_local.py và giữ cửa sổ đang mở.')
    elif worker_state.get('running'):
        notes.append('Đang quét Gmail; email phản hồi được xử lý sau khi lượt quét hoàn tất.')
    if worker_state.get('error'):
        notes.append(worker_state['error'])
    try:
        base = public_base()
        if urlsplit(base).hostname in ('localhost', '127.0.0.1'):
            notes.append('Link đang dùng localhost: người nhận chỉ mở được trên máy chạy ứng dụng. Cấu hình URL HTTPS public để dùng từ máy khác.')
    except ValueError as exc:
        notes.append(str(exc))
    with store.engine.connect() as conn:
        since = conn.execute(select(store.workflow_settings.c.value).where(store.workflow_settings.c.key=='reply_since')).scalar_one_or_none()
    return {'notes': notes, 'replySince': os.getenv('AUTO_REPLY_SINCE') or since}
