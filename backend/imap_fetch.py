"""Read-only MMLab Gmail IMAP → field validation → dashboard JSON.
No password is written to disk. No message is marked read, moved, or deleted.
"""
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import imaplib
import json
import os
import re
import sqlite3
import ssl
import sys
import time
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from intake import reply_recipient

from mmlab_pipeline.members import fold, sender_matches
from mmlab_pipeline.validator import report_type as canonical_type
from mmlab_pipeline.parser import (MAX_EML_BYTES, extract, normalize_body,
                                   parse_and_validate_email, split_segments)

VERSION = 'mmlab-imap-export/1'
VN = timezone(timedelta(hours=7))
MAX_BYTES = MAX_EML_BYTES
MONTHLY_POLICY = 'monthly-task-wrapping-v4'


def forwarded(subject: str, body: str) -> bool:
    return bool(re.search(r'(?i)\b(?:fwd|fw)\s*:', subject) or len(split_segments(body)) > 1)


def decode_message(raw: bytes):
    message = BytesParser(policy=policy.default).parsebytes(raw)
    part = message.get_body(preferencelist=('plain', 'html'))
    body = part.get_content() if part else ''
    if not body.strip():
        part = message.get_body(preferencelist=('html',))
        body = part.get_content() if part else ''
    return message, normalize_body(body)


def analyze(raw: bytes, source_id: str, received_at: str) -> dict:
    stamp = datetime.fromisoformat(received_at)
    if stamp.tzinfo is None:
        raise ValueError("received_at must include timezone")
    received_at = stamp.astimezone(VN).isoformat()
    message, body = decode_message(raw)
    subject, sender = str(message.get('Subject', '')), str(message.get('From', ''))
    has_forward = forwarded(subject, body)
    if str(message.get('Auto-Submitted','')).casefold() == 'auto-replied':
        return {'source_id':source_id,'state':'ignored','forwarded':has_forward,
                'received_at':received_at,'subject':'','validation':None,'report':None}
    segments = split_segments(body)
    candidates = [s for s in segments if set(extract(s)[0]) & {'report_type', 'done', 'planned'}]
    selected = candidates[0] if candidates else segments[0]
    metadata, metadata_issues = {}, []
    for line in selected['lines']:
        match = re.match(r'^\s*[*_]{0,2}(Person in Charge|Status|Date)[*_]{0,2}\s*:\s*[*_]{0,2}(.*?)\s*$', line, re.I)
        if match:
            key = match[1].casefold()
            value = match[2].strip().rstrip('*_').strip()
            if key in metadata:
                metadata_issues.append(f'Trường {match[1]} xuất hiện nhiều lần.')
            else:
                metadata[key] = value
    # Optional table metadata must not become an unknown schema field or title continuation.
    clean = '\n'.join(line for line in body.splitlines() if not re.match(
        r'^\s*[*_]{0,2}(Person in Charge|Status|Date)[*_]{0,2}\s*:', line, re.I))
    result = parse_and_validate_email(subject, clean, sender, received_at=received_at)
    # A forwarded acceptance without the lab template is a draft Paper, never a
    # guessed complete record. Only extract an explicitly quoted submission title.
    has_type = any('report_type' in extract(s)[0] for s in segments)
    if result['category'] is None and not has_type and has_forward and re.search(
            r'\b(?:paper|submission)\b', fold(subject + '\n' + body[:20000])):
        title_match = re.search(r'titled\s+["“](.+?)["”]', subject, re.I)
        title = title_match[1] if title_match else ''
        result = parse_and_validate_email(subject, 'Type of Report: Paper\nTitle of Work: ' + title, sender)
        result['warnings'].append('Paper nhận diện từ email forward không có template; người gửi cần bổ sung và xác nhận.')
    if result['category'] == 'Monthly Report':
        # Status/Role/Rank/Index/Venue are not monthly report requirements.
        metadata_issues = []
    defects = [type(d).__name__ for p in message.walk() for d in p.defects]
    if defects:
        result['warnings'].append('MIME cần kiểm tra: ' + ', '.join(defects))
        result['needs_review'] = True
    result['warnings'].extend(metadata_issues)
    if metadata_issues:
        result['needs_review'] = True
    category = result['category']
    looks_like_report = bool(candidates or 'bao cao thang' in fold(subject) or (has_forward and re.search(r'\b(?:paper|submission|accepted|conference|seminar|award|nghien cuu|giai thuong|de tai)\b', fold(subject + '\n' + body[:20000]))))
    if category is None:
        return {'source_id': source_id, 'state': 'review' if looks_like_report else 'ignored',
                'forwarded': has_forward, 'received_at': received_at,
                'subject': subject if looks_like_report else '',
                'validation': result if looks_like_report else None, 'report': None}
    data = result['data']
    people = result['credited_members']
    person_source = metadata.get('person in charge') or result['provenance'].get('report_sender') or sender
    owners = sender_matches(person_source)
    person_id = owners[0]['member']['id'] if len(owners) == 1 else None
    if category in ('Paper', 'Project') and person_id not in [p['id'] for p in people]:
        person_id = None
    issues = [f'Thiếu {label}.' for label in result['missing_fields']]
    issues += [f"{err['field']}: {err['reason']}" for err in result['invalid_fields']]
    if not person_id and category != 'Monthly Report':
        issues.append('Chưa xác định Person in Charge; không gán vai trò cho mọi tác giả.')
    if not people:
        issues.append('Không tìm thấy thành viên chính thức của lab.')
    issues += metadata_issues
    if result['needs_review']:
        issues.append('Cần kiểm tra nguồn hoặc đối soát: ' + '; '.join(result['warnings']))
    raw_type = data.get('report_type', '')
    report_type = {'Paper': 'Paper', 'Project': 'Đề tài', 'Monthly Report': 'Báo cáo tháng'}.get(category, canonical_type(raw_type))
    status = metadata.get('status', '')
    if not status and re.search(r'(?im)^\s*\*{0,2}decision\*{0,2}\s*:\s*\*{0,2}accept\b', body):
        status = 'Accepted'
    if category == 'Monthly Report':
        status = ''
    elif not status:
        status = 'Chưa rõ'
    report = {
        'id': hashlib.sha256(source_id.encode()).hexdigest(),
        'date': received_at[:10], 'memberId': person_id, 'type': report_type,
        'title': data.get('title', '') or subject or '(Thiếu tiêu đề)',
        'status': status, 'role': data.get('role', ''), 'authors': data.get('authors', ''),
        'venue': data.get('venue', ''), 'ranking': data.get('ranking', ''),
        'index': data.get('index') or None, 'memberIds': [p['id'] for p in people],
        'source': 'gmail', 'forwarded': has_forward, 'issues': list(dict.fromkeys(issues)),
        'sourceId': source_id, 'messageId': str(message.get('Message-ID', '')),
<<<<<<< HEAD
        'replyReferences': ' '.join(str(v) for v in (message.get_all('References', []) or message.get_all('In-Reply-To', [])))[:32000],
=======
>>>>>>> 7d8b3d32e37d57bbb3f356c1bd45e50e3337c878
        'sender': sender, 'subject': subject, 'isValid': result['is_valid'],
        'missingFields': result['missing_fields'], 'invalidFields': result['invalid_fields'],
        'warnings': result['warnings'], 'mappingEvidence': result['mapping_evidence'],
        'monthlyTasks': {'done': data.get('done'), 'planned': data.get('planned')}
                        if category == 'Monthly Report' else None,
        'reportPeriod': result['provenance'].get('report_month'),
        'dateBasis': 'IMAP INTERNALDATE / Asia/Ho_Chi_Minh',
        'receivedAt': received_at,
    }
    report['replyRecipient'], report['replySuppressedReason'] = reply_recipient(message)
    if category=='Monthly Report':report['monthlyTasksVersion']=2
    return {'source_id': source_id, 'state': 'reported', 'forwarded': has_forward,
            'monthly_policy': MONTHLY_POLICY if category == 'Monthly Report' else None,
            'received_at': received_at, 'report': report}


def received_date(meta: bytes) -> str:
    match = re.search(rb'INTERNALDATE "([^"]+)"', meta)
    if not match:
        raise ValueError('Server không trả INTERNALDATE; không đoán ngày nhận thư.')
    # Explicit English month table avoids OS locale dependence on Windows.
    m = re.fullmatch(r'\s*(\d{1,2})-([A-Za-z]{3})-(\d{4}) (\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})', match[1].decode('ascii'))
    if not m:
        raise ValueError('INTERNALDATE không hợp lệ.')
    month = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].index(m[2].lower()) + 1
    offset = (int(m[8])*60+int(m[9])) * (1 if m[7] == '+' else -1)
    stamp = datetime(int(m[3]), month, int(m[1]), int(m[4]), int(m[5]), int(m[6]),
                     tzinfo=timezone(timedelta(minutes=offset)))
    return stamp.astimezone(VN).isoformat()


def open_cache(path: Path):
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS messages (source_id TEXT PRIMARY KEY, result TEXT NOT NULL)')
    return db


def export_snapshot(account: str, folder: str, validity: str, source_ids: list[str],
                    db: sqlite3.Connection, errors: list[dict], output: Path):
    events = []
    failed_ids = {e['source_id'] for e in errors}
    for source_id in source_ids:
        if source_id in failed_ids:
            continue
        row = db.execute('SELECT result FROM messages WHERE source_id=?', (source_id,)).fetchone()
        if row:
            events.append(json.loads(row[0]))
    reports = [e['report'] for e in events if e['state'] == 'reported']
    stats = {'inbox_messages': len(source_ids), 'processed': len(events),
             'forwarded': sum(e['forwarded'] for e in events), 'reports': len(reports),
             'valid': sum(r['isValid'] for r in reports),
             'invalid': sum(not r['isValid'] for r in reports),
             'ignored': sum(e['state'] == 'ignored' for e in events),
             'review': sum(e['state'] == 'review' for e in events), 'errors': len(errors)}
    payload = {'schema_version': VERSION, 'mailbox': account, 'folder': folder,
               'uid_validity': validity, 'generated_at': datetime.now(VN).isoformat(),
               'summary': stats, 'reports': reports,
               'review_candidates': [e for e in events if e['state'] == 'review'],
               'errors': errors}
    target = output / 'mmlab_export.json'
    temp = target.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(target)
    (output / 'summary.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    with (output / 'mmlab_reports.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Date','Person ID','Type','Title','Role','All authors','Venue','Ranking','Index','Valid','Forwarded','Issues'])
        for r in reports:
            values = [r['date'],r['memberId'],r['type'],r['title'],r['role'],r['authors'],r['venue'],r['ranking'],r['index'],r['isValid'],r['forwarded'],'; '.join(r['issues'])]
            writer.writerow(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v for v in values])
    return stats


def fetch_once(account: str, password: str, folder: str, output: Path, recheck=False, progress=None):
    output.mkdir(parents=True, exist_ok=True)
    db = open_cache(output / 'imap_cache.sqlite3')
    errors = []
    source_ids = []
    try:
        with imaplib.IMAP4_SSL('imap.gmail.com', 993, ssl_context=ssl.create_default_context(), timeout=30) as mail:
            mail.login(account, password)
            status, _ = mail.select(folder, readonly=True)
            if status != 'OK':
                raise RuntimeError('Không mở được thư mục ở chế độ chỉ đọc.')
            response = mail.response('UIDVALIDITY')[1]
            if not response or not response[0]:
                raise RuntimeError('Không có UIDVALIDITY; không tiếp tục để tránh nhận diện sai thư.')
            validity = response[0].decode('ascii')
            status, data = mail.uid('search', None, 'ALL')
            if status != 'OK':
                raise RuntimeError('Không lấy được danh sách UID.')
            uids = data[0].split() if data and data[0] else []
            if progress:
                progress(0, len(uids))
            source_ids = [f'imap:{account}:{folder}:{validity}:{uid.decode()}' for uid in uids]
            print(f'INBOX/Folder: {len(uids)} thư. Đang đọc và kiểm tra...', flush=True)
            for n, (uid, source_id) in enumerate(zip(uids, source_ids), 1):
                cached = db.execute('SELECT result FROM messages WHERE source_id=?', (source_id,)).fetchone()
                cached_event = json.loads(cached[0]) if cached else None
                old_monthly = (cached_event and (cached_event.get('report') or {}).get('type') == 'Báo cáo tháng'
                               and cached_event.get('monthly_policy') != MONTHLY_POLICY)
                if not recheck and cached and not old_monthly:
                    if progress and (n % 25 == 0 or n == len(uids)):
                        progress(n, len(uids))
                    continue
                try:
                    status, chunks = mail.uid('fetch', uid, '(RFC822.SIZE INTERNALDATE)')
                    if status != 'OK':
                        raise RuntimeError('Không lấy được metadata.')
                    meta = b' '.join(c for c in chunks if isinstance(c, bytes))
                    size = re.search(rb'RFC822.SIZE (\d+)', meta)
                    if not size or int(size[1]) > MAX_BYTES:
                        raise ValueError('Thư vượt 10 MB hoặc thiếu kích thước; cần kiểm tra riêng.')
                    stamp = received_date(meta)
                    status, chunks = mail.uid('fetch', uid, '(BODY.PEEK[])')
                    if status != 'OK':
                        raise RuntimeError('Không tải được nội dung.')
                    raw = next((c[1] for c in chunks if isinstance(c, tuple) and isinstance(c[1],bytes)), None)
                    if raw is None:
                        raise RuntimeError('Không có MIME body.')
                    if len(raw) > MAX_BYTES:
                        raise ValueError('Nội dung vượt giới hạn.')
                    event = analyze(raw, source_id, stamp)
                    db.execute('INSERT INTO messages(source_id,result) VALUES(?,?) ON CONFLICT(source_id) DO UPDATE SET result=excluded.result', (source_id, json.dumps(event, ensure_ascii=False)))
                    db.commit()
                except (OSError, ValueError, RuntimeError, UnicodeError, LookupError, imaplib.IMAP4.error) as exc:
                    errors.append({'source_id': source_id, 'error': type(exc).__name__, 'reason': str(exc)[:250]})
                if n % 25 == 0 or n == len(uids):
                    if progress:
                        progress(n, len(uids))
                    print(f'Đã kiểm tra {n}/{len(uids)}; lỗi cần thử lại: {len(errors)}', flush=True)
            stats = export_snapshot(account, folder, validity, source_ids, db, errors, output)
            print(json.dumps(stats, ensure_ascii=False, indent=2))
            print('Đã xuất:', output / 'mmlab_export.json')
            return stats
    finally:
        db.close()


def main():
    p = argparse.ArgumentParser(description='Read-only Gmail IMAP scan → MMLab validation and export')
    p.add_argument('--account', default='mmlab@uit.edu.vn')
    p.add_argument('--folder', default='INBOX')
    p.add_argument('--output', type=Path, default=Path('output'))
    p.add_argument('--recheck', action='store_true', help='Validate cached emails again')
    p.add_argument('--poll-seconds', type=int, default=0, help='Optional local polling, not Gmail push; minimum 60 s')
    args = p.parse_args()
    if args.poll_seconds and args.poll_seconds < 60:
        p.error('--poll-seconds phải >=60 hoặc 0')
    password = os.environ.get('MMLAB_APP_PASSWORD') or getpass.getpass('App Password (nhập ẩn): ')
    password = password.replace(' ', '')
    if not password:
        p.error('Chưa nhập App Password.')
    try:
        while True:
            fetch_once(args.account, password, args.folder, args.output, args.recheck)
            if not args.poll_seconds:
                break
            print(f'Đợi {args.poll_seconds} giây; giữ cửa sổ này mở. Ctrl+C để dừng.', flush=True)
            time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        print('\nĐã dừng. Những thư đã xử lý được giữ trong cache.')
    except imaplib.IMAP4.error:
        print('IMAP từ chối đăng nhập hoặc thao tác. Kiểm tra App Password/quyền hộp thư.', file=sys.stderr)
        return 1
    except (OSError, RuntimeError) as exc:
        print(f'Không hoàn thành lượt đọc: {type(exc).__name__}. Kiểm tra mạng rồi chạy lại.', file=sys.stderr)
        return 1
    finally:
        password = ''
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
