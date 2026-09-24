# -*- coding: utf-8 -*-
"""MMLab: reply emails, member-by-member discussion, concise school statistics.

Apply AFTER update_mmlab_school_statistics.py from the previous update.
Stop the app; place this file beside run_local.py, then run:
    python update_mmlab_reply_members.py
    npm run build --prefix frontend
    python run_local.py

--check previews compatibility without writing anything. Existing source files
are backed up under _backups/reply-members-*. An incompatible local edit causes
an all-files preflight stop; this updater does not overwrite it or modify .env.
No packages, credentials, database contents or live emails are changed by the
updater itself. All changed application code and regression tests are embedded
below as a readable unified diff, so no ZIP is required.

On app restart, pending/retry receipts get the original forwarded subject with
Re:, the outer Message-ID in In-Reply-To and the outer References ancestry.
Outgoing Message-IDs remain unique. Recipients remain the outer forwarder only,
with the existing anti-loop rules and optional edit link. No CC/Reply-To or
quoted conference recipients are added. Sent/failed/uncertain mail is not
requeued. Old imported records lacking a usable outer Message-ID cannot supply
reliable threading; the application never invents one from a quoted email.
SMTP headers are tested locally; live Gmail conversation grouping is not tested.

The discussion Word attachment has 12 member sections in roster order, each
with Da lam / Se lam (Vietnamese labels in actual output). All categories remain.
Explicit owner suffixes are mapped; a mentioned name inside task prose does not
assign ownership. Shared papers appear for each credited member. Unassigned
content stays in a final common section. Current admin edits take precedence.
Empty phases say no content was recorded, not that the member did no work.
The last-Monday schedule uses the same renderer. Already frozen/sent batches
are not rewritten or sent again.

School A.1=A.2 and B.1=B.2 remain short summaries. Completed Paper display is:
Q1 3 bai, A* va A: 3 bai, Rank B: 4 bai, Rank C: 1 bai, Scopus: 25 bai.
Those example numbers are NOT inserted into the report. Only actual nonzero
counts appear, including Q2/Q3/Q4 when present. A work is counted once across
members; Scopus is the residual displayed group, not a second total of all
ranked works. The internal Scopus khac metric key is retained for compatibility.
The completion/target preamble is removed; optional targets stay in stored
metrics. Year-to-date scope is identified separately in the document header.
Manual aggregate breakdowns stay declared data, never added atop work counts.
"""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile

MANIFEST = {'backend/discussion_report.py': {'before': None, 'after': 'b17981968a632bc0382f77ca620710319083cb51a08a32bd075acbd6908d57f0'}, 'backend/imap_fetch.py': {'before': '0aafc8dbea851a7f94dce61ab35a5d76b11236d8ecc65b900dcf3a1ab4ab189a', 'after': '41548226a336cc4d090169c0d01377709023958c8120c17fd2f247f63303d7fe'}, 'backend/intake.py': {'before': 'd98ab471763e30d145ffe419bd2799df3e36ab80cd7bc153ea76121b1835b031', 'after': '0a6b800a969763655425bd4a581be9448190428b54a4edf2562ed968ae86f9b1'}, 'backend/mail_threading.py': {'before': None, 'after': '715fb18a9a5365414a349e68b5115c26a46ca420d63348c2cad179143574451b'}, 'backend/mailer.py': {'before': '8283fdb52f883ab6c90f348e22a2d703f33f1889d00de72a0e8235ebf02cd047', 'after': '5892e1a80555b19df27e6e20abb40dec581385fa7eea0a4585c742cc4e5fd111'}, 'backend/monthly_report.py': {'before': 'bc828006b2caa0e14cd810f54d938b8aa292738ff61b9366063771d3d5a141e2', 'after': '6d608f0d2dfd729c2d36df1f8b38c5be58b24277c2273809e8dfcac116a62928'}, 'backend/school_statistics.py': {'before': '6b5eddc33a0f0925f4d37e99950f92f0d4eec9029131affd2dff2879829b3989', 'after': '8b09ee2cd481ed9e5670fc9d91bbe02137cead2671b2e5707177292529007167'}, 'backend/store.py': {'before': 'a5b355853e4fc69a34847747b11e4e1e6cf6794ab896b3dfac87fee792c0aa37', 'after': '2cb26c5f45bd801b3d8da0bc4cc8abb0f1c0e8c35d180d80914c9a4c2f8819f9'}, 'backend/tests/test_auto_receipt.py': {'before': '0a3ee124c523ea0e48ad6fdba04e35190378ae4755867e531a1e309e0d824f91', 'after': 'b6d7984125730530403f5ed8fe1a0abc0677d18973a595d7073b10b2aff21959'}, 'backend/tests/test_confirmation.py': {'before': '816a573c5f8a88b1b65c4cc18f2e0f04c2133a74a7230c2807492ec7f2ecccae', 'after': '3fcbfdaeab0252fd4e7fd78e2b6b806792528dd305c96f2963e4825edc9a449d'}, 'backend/tests/test_monthly.py': {'before': 'e7959bcff3553d7ad56dbcb2f6f36281c21cb13389395fc90a1c6b4abfa1f4bd', 'after': '07ad817b6dcc72ba660c9654b131a3d7a8ef5a7b1b9591a35fb40a90d3e6642a'}, 'backend/tests/test_paired_monthly.py': {'before': '0f56337a4d303326c579a39dd73f6c81438bcc6de0ea78a229c38ac01ac035cb', 'after': '4b0a8f3e57a550602a0b78da0365f565450c400585dbc5af04c0ae02a0d3d46e'}, 'backend/tests/test_reply_members.py': {'before': None, 'after': '26f82ddca3911fad9f7e2b52a729b5f3f004d94b9fac578396dd5e4373a4fae2'}, 'backend/tests/test_school_filter.py': {'before': 'cc0ee06ae70e9044d816a94a6dc28a1b6744c1a688a8d54e5c0eeafe3dcc66f4', 'after': '19299a2b3b57cb85fd87826793fd8c1343318372b74a8bfbdea2d259a62ee6f9'}, 'backend/tests/test_school_statistics.py': {'before': '91074a38a4d1eb5e2bdfe83c78056b6c78fa671ec73e0361a772edb8da84d419', 'after': 'e1d23c41e3e370ce58d63cbd60618ee79d179397455f06e69a48ebaf2b272150'}, 'frontend/src/MonthlyReports.tsx': {'before': 'f9ce403feaea97965d1dd9e3ed0c86b29e8b569281cfd08884a57300ca59816d', 'after': '24749839e42cc6b8b17582d398d3ae5ee3122a593e7a413576b1fa993a197330'}}

PATCH = r'''--- a/backend/discussion_report.py
+++ b/backend/discussion_report.py
@@ -0,0 +1,31 @@
+"""Group current editable task bodies by explicit member attribution."""
+import re
+from mmlab_pipeline.members import DIRECTORY, normalized_name
+from monthly_assembly import TOPICS
+from monthly_layout import paired_report
+
+NAMES = {normalized_name(alias): m['id'] for m in DIRECTORY
+         for alias in (m['name'], m['email'], *m['aliases'])}
+
+
+def by_member(report):
+    report = paired_report(report)
+    groups = {m['id']: {'id':m['id'], 'name':m['name'], 'done':[], 'planned':[]} for m in DIRECTORY}
+    common = {'id':None, 'name':'Nội dung chung / chưa gắn thành viên', 'done':[], 'planned':[]}
+    for key, phase in (('a1', 'done'), ('b1', 'planned')):
+        for raw in report['sections'].get(key, '').splitlines():
+            text = re.sub(r'^\s*[*•+]\s+', '', raw).strip()
+            if not text or text.rstrip(':') in TOPICS:
+                continue
+            suffix = re.search(r'\s+\(([^()]*)\)\s*$', text)
+            owners = []
+            if suffix:
+                parts = re.split(r'[,;]', suffix[1])
+                ids = [NAMES.get(normalized_name(part)) for part in parts]
+                # Full attribution only: a mention in task prose is not ownership.
+                if ids and all(ids):
+                    owners = list(dict.fromkeys(ids)); text = text[:suffix.start()].rstrip()
+            targets = [groups[mid] for mid in owners] if owners else [common]
+            for group in targets:
+                if text not in group[phase]:group[phase].append(text)
+    return [*groups.values(), *([common] if common['done'] or common['planned'] else [])]
--- a/backend/imap_fetch.py
+++ b/backend/imap_fetch.py
@@ -134,6 +134,7 @@
         'index': data.get('index') or None, 'memberIds': [p['id'] for p in people],
         'source': 'gmail', 'forwarded': has_forward, 'issues': list(dict.fromkeys(issues)),
         'sourceId': source_id, 'messageId': str(message.get('Message-ID', '')),
+        'replyReferences': ' '.join(str(v) for v in (message.get_all('References', []) or message.get_all('In-Reply-To', [])))[:32000],
         'sender': sender, 'subject': subject, 'isValid': result['is_valid'],
         'missingFields': result['missing_fields'], 'invalidFields': result['invalid_fields'],
         'warnings': result['warnings'], 'mappingEvidence': result['mapping_evidence'],
--- a/backend/intake.py
+++ b/backend/intake.py
@@ -54,6 +54,7 @@
 
 
 def mail_content(row, link):
+    from mail_threading import reply_headers
     _, errors = validation(row['fields'])
     lines = ['Chào bạn,', '', 'MMLab đã tự động ghi nhận Paper bạn chuyển tiếp.',
              'Bạn không cần xác nhận lại. Dưới đây là thông tin đã được lưu:',
@@ -70,9 +71,7 @@
               'Link riêng cho báo cáo này, có hiệu lực 7 ngày.',
               '', 'Tự động ghi nhận không đồng nghĩa bài báo đã được hội nghị/tạp chí chấp nhận. '
               'Index/Ranking được lưu theo thông tin khai báo.', '', 'MMLab — UIT']
-    return {'subject': f"[MMLab] Đã ghi nhận Paper #{row['id'][:12]}",
-            'body': '\n'.join(lines), 'link': link,
-            'in_reply_to': row['original'].get('messageId', '')}
+    return {**reply_headers(row['original']), 'body': '\n'.join(lines), 'link': link}
 
 
 def receipt_block_reason(conn, report, include_cutoff=True):
--- a/backend/mail_threading.py
+++ b/backend/mail_threading.py
@@ -0,0 +1,38 @@
+"""Reply metadata comes exclusively from the outer message headers."""
+import re
+
+# Conservative interoperable subset of RFC message IDs. Never accept controls.
+ID = re.compile(r'<[^<>\s@\x00-\x20\x7f-\uffff]+@[^<>\s@\x00-\x20\x7f-\uffff]+>')
+
+
+def message_ids(value):
+    return list(dict.fromkeys(v for v in ID.findall(str(value or '')[:32000]) if v.isascii() and len(v) <= 990))
+
+
+def reply_headers(original):
+    subject = re.sub(r'[\x00-\x20\x7f]+', ' ', str(original.get('subject') or '')).strip()
+    subject = subject if re.match(r'^re\s*:', subject, re.I) else 'Re: ' + subject
+    parent = str(original.get('messageId') or '').strip()
+    refs = message_ids(original.get('replyReferences', ''))
+    if not parent.isascii() or not ID.fullmatch(parent) or len(parent) > 990:
+        parent = ''; refs = []
+    else:
+        refs = [v for v in refs if v != parent]
+        # Bound abusive chains while retaining the root and most recent ancestors.
+        refs = (refs[:1] + refs[-18:] if len(refs) > 19 else refs) + [parent]
+    return {'subject': subject.rstrip(), 'in_reply_to': parent, 'references': ' '.join(refs)}
+
+
+def migrate_pending():
+    """Refresh queued receipts only; never resend sent/uncertain historical mail."""
+    from sqlalchemy import select, update
+    import store
+    with store.mutation() as conn:
+        rows = conn.execute(select(store.outbox.c.id, store.outbox.c.payload, store.intakes.c.original)
+            .join(store.intakes, store.intakes.c.id == store.outbox.c.id)
+            .join(store.reports, store.reports.c.id == store.intakes.c.report_id)
+            .where(store.reports.c.mailbox == store.mailbox(), store.intakes.c.status != 'cancelled',
+                   store.outbox.c.status.in_(['pending', 'retry']))).mappings().all()
+        for row in rows:
+            payload = {**row['payload'], **reply_headers(row['original'])}
+            conn.execute(update(store.outbox).where(store.outbox.c.id == row['id']).values(payload=payload))
--- a/backend/mailer.py
+++ b/backend/mailer.py
@@ -26,10 +26,11 @@
     message['Message-ID'] = f"<mmlab-{row['id']}-{payload.get('delivery_id','initial')}@{mailbox().split('@')[1]}>"
     message['Auto-Submitted'] = 'auto-replied'
     message['X-Auto-Response-Suppress'] = 'All'
-    ref = payload.get('in_reply_to', '')
-    if re.fullmatch(r'<[^<>\s]{1,990}>', ref):
-        message['In-Reply-To'] = ref
-        message['References'] = ref
+    from mail_threading import reply_headers
+    thread = reply_headers({'messageId':payload.get('in_reply_to'), 'replyReferences':payload.get('references')})
+    if thread['in_reply_to']:
+        message['In-Reply-To'] = thread['in_reply_to']
+        message['References'] = thread['references']
     message.set_content(payload['body'])
     for attachment in payload.get('attachments', []):
         message.add_attachment(base64.b64decode(attachment['content']),maintype='application',subtype=attachment['subtype'],filename=attachment['name'])
--- a/backend/monthly_report.py
+++ b/backend/monthly_report.py
@@ -76,6 +76,8 @@
     paragraph('BÁO CÁO CÔNG TÁC'+(' THÁNG …/……' if template else f' THÁNG {m:02d}/{y}'),True,True)
     if not template:
         paragraph(f"Kết quả tháng {report['period'][5:]}/{report['period'][:4]} và kế hoạch tháng {m:02d}/{y}",center=True)
+    if variant=='school' and report.get('paperScope')=='year':
+        paragraph(f"Số liệu bài báo: lũy kế năm {report['period'][:4]} đến {report['period'][5:]}/{report['period'][:4]}.")
     def section(key,title):
         if template and key=='b1' and variant=='discussion':doc.add_page_break()
         doc.add_heading(title,level=1)
@@ -102,8 +104,14 @@
         section('b1',f"Phần B.1: Kế hoạch công tác các nhiệm vụ phục vụ {report['strategyLabel']} trong tháng này")
         section('b2','Phần B.2: Kế hoạch công tác các nhiệm vụ thường xuyên và đột xuất trong tháng này')
     else:
-        section('a1','Phần A: Công việc đã thực hiện')
-        section('b1','Phần B: Kế hoạch công việc')
+        from discussion_report import by_member
+        for member in by_member(report):
+            title = f"{member['id']}. {member['name']}" if member['id'] else member['name']
+            doc.add_heading(title, level=1)
+            for phase, label in (('done','Đã làm'), ('planned','Sẽ làm')):
+                doc.add_heading(label, level=2)
+                for line in member[phase] or ['Chưa có nội dung được ghi nhận.']:
+                    paragraph('• ' + line)
     if doc.paragraphs:doc.paragraphs[-1].paragraph_format.keep_with_next=True
     p=paragraph('Trưởng đơn vị\n(Ký và ghi rõ họ tên)\n\n'+report['signatory'],True)
     p.alignment=WD_ALIGN_PARAGRAPH.RIGHT
--- a/backend/school_statistics.py
+++ b/backend/school_statistics.py
@@ -163,6 +163,17 @@
     return paper_lines + lines
 
 
+def declaration_breakdown(text):
+    # Keep declared ranks; do not infer missing ranks or derive a residual from
+    # a potentially overlapping or incomplete manually declared breakdown.
+    parts=re.split(r'trong\s+đó\s*:',text,flags=re.I,maxsplit=1)
+    if len(parts)==2:
+        return re.sub(r'Scopus\s+khác', 'Scopus', parts[1].strip().rstrip('.'),flags=re.I)+'.'
+    match=re.search(r'(\d+)\s*(?:/\s*\d+\s*)?bài(?: báo)? Scopus',text,re.I)
+    if match:return f'Scopus: {int(match[1])} bài.'
+    return text.rstrip('.')+'.'
+
+
 def summarize(report):
     notes=[];phase_rows={}
     for phase in ('a','b'):
@@ -182,17 +193,20 @@
         totals,declarations=aggregate_tasks(phase_rows[phase],phase,catalog,notes)
         lines=[]
         if phase=='a' and catalog['scopus']:
-            n=catalog['scopus'];ratio=f'{n} / {target}' if target is not None else str(n)
-            parts=[f'{rank}: {catalog["ranks"][rank]} bài' for rank in RANKS if catalog['ranks'].get(rank)]
-            scope_label=f' (lũy kế năm {report["period"][:4]} đến {report["period"][5:]}/{report["period"][:4]})' if scope=='year' else ''
-            lines.append(f'KPI bài báo{scope_label}: hoàn thành {ratio} bài báo Scopus. Trong đó: '+', '.join(parts)+'.')
+            parts=[]
+            for rank in RANKS:
+                n=catalog['ranks'].get(rank,0)
+                if n:
+                    label='Scopus' if rank=='Scopus khác' else rank
+                    parts.append(f'{label}{" " if label.startswith("Q") else ": "}{n} bài')
+            lines.append(', '.join(parts)+'.')
         if phase=='a' and catalog['isiOnly']:
             lines.append(f'KPI bài báo: {catalog["isiOnly"]} bài ISI ngoài nhóm Scopus.')
         if phase=='a' and declarations:
             if catalog['works']:
                 notes.append('Có cả tổng số bài báo khai báo và danh sách Paper; dùng danh sách công trình, không cộng chồng tổng số.')
             elif len(declarations)==1:
-                lines.append('KPI bài báo: '+declarations[0].rstrip('.')+'.')
+                lines.append(declaration_breakdown(declarations[0]))
                 notes.append('Tổng số bài báo lấy từ dòng tổng hợp khai báo; chưa đối chiếu với danh sách công trình.')
             else:notes.append('Có nhiều tổng số bài báo khai báo khác nhau; cần thống nhất một tổng số.')
         lines.extend(render_tasks(totals,phase))
--- a/backend/store.py
+++ b/backend/store.py
@@ -66,6 +66,8 @@
 
     from receipt_policy import migrate
     migrate()
+    from mail_threading import migrate_pending
+    migrate_pending()
 
 
 def state():
--- a/backend/tests/test_auto_receipt.py
+++ b/backend/tests/test_auto_receipt.py
@@ -89,9 +89,9 @@
     for expected in ('THÁNG 08/2026','Mã đơn vị: 6','Phần A.1','Phần A.2','Phần B.1','Phần B.2','2021-2030','KH2026'):
         assert expected in text
     assert 'A study of realistic video retrieval' not in text
-    assert text.count('hoàn thành 1 bài báo Scopus')==2
+    assert text.count('Scopus: 1 bài.')==2
     a1=text.split('Phần A.1')[1].split('Phần A.2')[0]
-    assert 'hoàn thành 1 bài báo Scopus' in a1
+    assert 'Scopus: 1 bài.' in a1
     assert 'Phần 3' not in text and 'Đề nghị hỗ trợ máy tính' not in text
     assert '46 / 44' not in text and '2021-2025' not in text
     assert r==original  # School output must not modify saved discussion data.
--- a/backend/tests/test_confirmation.py
+++ b/backend/tests/test_confirmation.py
@@ -152,6 +152,9 @@
     assert captured['to']==['student@gmail.com']
     assert captured['message']['Auto-Submitted']=='auto-replied'
     assert captured['message']['In-Reply-To']=='<outer-message@test.example>'
+    assert captured['message']['Subject']=='Re: Fwd: Paper decision'
+    assert captured['message']['References']=='<outer-message@test.example>'
+    assert captured['message']['Message-ID']!='<outer-message@test.example>'
 
 
 def test_historical_manual_confirmation_is_idempotent_and_survives_rescan(workflow, monkeypatch):
--- a/backend/tests/test_monthly.py
+++ b/backend/tests/test_monthly.py
@@ -80,7 +80,7 @@
 def test_docx_variants_and_blank_dates():
     r=compose([],'2026-12');r['sections'].update(a1='KPI bài báo: hoàn thành 02 bài báo Scopus',b1='KPI bài báo: nộp 03 bài tạp chí Q1')
     discussion=doc_text(docx_bytes(r,'discussion'));school=doc_text(docx_bytes(r,'school'))
-    assert 'hoàn thành 02 bài báo Scopus' in discussion and 'hoàn thành 02 bài báo Scopus' in school
+    assert 'hoàn thành 02 bài báo Scopus' in discussion and 'Scopus: 2 bài.' in school
     assert 'Phần A.1' in school and 'Phần A.2' in school and 'nộp 03 bài tạp chí Q1' in school and 'THÁNG 01/2027' in school
     template=doc_text(blank_template('school'))
     assert 'THÁNG …/……' in template and 'Ngày … tháng … năm ……' in template
--- a/backend/tests/test_paired_monthly.py
+++ b/backend/tests/test_paired_monthly.py
@@ -32,7 +32,7 @@
         text=doc_text(docx_bytes(r,variant))
         for label in ('Accepted','Được chấp nhận','chưa rõ trạng thái','Chưa xác nhận','Phần 3'):
             assert label not in text
-    assert len(bodies(docx_bytes(r,'discussion')))==2
+    assert len(bodies(docx_bytes(r,'discussion')))==12
     assert rows[0]['status']=='Accepted' and rows[1]['status']=='Chưa rõ'
 
 
@@ -65,7 +65,7 @@
     assert sections['b1']==sections['b2']==payload['sections']['b1']
     assert c.put('/api/monthly/2026-09',json=payload,headers={'Origin':'http://testserver'}).status_code==409
     text=doc_text(c.get('/api/monthly/2026-09/school.docx').content)
-    assert text.count('KPI bài báo: hoàn thành 02 bài báo Scopus')==2 and text.count('KPI NCS: chuẩn bị nộp 02 hồ sơ NCS')==2
+    assert text.count('Scopus: 2 bài.')==2 and text.count('KPI NCS: chuẩn bị nộp 02 hồ sơ NCS')==2
     from datetime import datetime
     from monthly_report import VN
     import base64, store
@@ -73,7 +73,7 @@
     with store.engine.connect() as conn:
         outgoing=conn.execute(select(service.batches.c.payload)).scalar_one()
     text=doc_text(base64.b64decode(outgoing['attachments'][1]['content']))
-    assert text.count('KPI bài báo: hoàn thành 02 bài báo Scopus')==2
+    assert text.count('Scopus: 2 bài.')==2
     # Clearing A must also clear its mirrored A.2, not restore an earlier copy.
     payload.update(revision=response.json()['revision'],sections={'a1':'','b1':'Kế hoạch mới'})
     cleared=c.put('/api/monthly/2026-09',json=payload,headers={'Origin':'http://testserver'}).json()
--- a/backend/tests/test_reply_members.py
+++ b/backend/tests/test_reply_members.py
@@ -0,0 +1,125 @@
+import base64
+import copy
+import io
+from datetime import datetime
+from email.message import EmailMessage
+from email.parser import BytesParser
+from email import policy
+from unittest.mock import patch
+import pytest
+from docx import Document
+from sqlalchemy import select, update
+from mail_threading import reply_headers, migrate_pending
+from imap_fetch import analyze
+from discussion_report import by_member
+from monthly_report import compose, docx_bytes, VN
+from school_statistics import summarize, declaration_breakdown
+from mmlab_pipeline.members import DIRECTORY
+from test_confirmation import workflow, seed
+from test_monthly import paper, doc_text, scheduled, client
+from test_api import login
+import monthly_service as service
+import store
+import mailer
+
+
+def test_threading_outer_headers_and_smtp_serialization(workflow, monkeypatch):
+    bundle=seed()
+    msg=EmailMessage();msg['From']='student@gmail.com';msg['Subject']='Fwd: Kết quả bài báo'
+    msg['Message-ID']='<outer@sample.org>'
+    msg['References']='<root@sample.org> <prior@sample.org>'
+    msg.set_content('Type of Report: Paper\nTitle of Work: Paper Example\n---------- Forwarded message ---------\nMessage-ID: <conference@sample.org>\nSubject: unrelated title')
+    event=analyze(msg.as_bytes(),'imap:mmlab@uit.edu.vn:INBOX:123:18','2026-09-24T01:00:00+00:00')
+    headers=reply_headers(event['report'])
+    assert headers=={'subject':'Re: Fwd: Kết quả bài báo','in_reply_to':'<outer@sample.org>',
+                     'references':'<root@sample.org> <prior@sample.org> <outer@sample.org>'}
+    monkeypatch.setenv('MMLAB_APP_PASSWORD','test-only')
+    captured={}
+    class SMTP:
+        def __init__(self,*a,**k):pass
+        def login(self,*a):pass
+        def send_message(self,message,**kw):captured.update(message=BytesParser(policy=policy.default).parsebytes(message.as_bytes()),**kw)
+        def quit(self):pass
+    payload={**headers,'body':'Đã ghi nhận. Link chỉnh sửa tùy chọn.'}
+    with patch.object(mailer.smtplib,'SMTP_SSL',SMTP):
+        assert mailer.deliver({'id':'test-reply','recipient':'student@gmail.com','payload':payload})==('sent',None)
+    actual=captured['message']
+    assert str(actual['Subject'])==headers['subject']
+    assert actual['References']==headers['references'] and actual['In-Reply-To']==headers['in_reply_to']
+    assert captured['to_addrs']==['student@gmail.com']
+    assert 'conference@' not in str(actual['References'])
+    assert actual['Message-ID']!=headers['in_reply_to']
+
+
+@pytest.mark.parametrize('subject,expected',[('Re: Fwd: Paper','Re: Fwd: Paper'),('FW: Paper','Re: FW: Paper'),('Tiêu đề\r\n gấp','Re: Tiêu đề gấp')])
+def test_reply_subject(subject,expected):
+    assert reply_headers({'subject':subject})['subject']==expected
+
+
+@pytest.mark.parametrize('bad',['','garbage','<bad>','<valid@x>\r\nBcc: hidden@x','<one@x> <two@x>'])
+def test_missing_or_bad_parent_does_not_thread_to_quoted_ancestor(bad):
+    result=reply_headers({'messageId':bad,'replyReferences':'<ancestor@x>'})
+    assert not result['in_reply_to'] and not result['references']
+
+
+@pytest.mark.parametrize('status',['pending','retry','sent','unknown','failed'])
+def test_pending_upgrade_never_resends_existing_mail(workflow,status):
+    seed()
+    with store.engine.begin() as conn:
+        row=conn.execute(select(store.outbox)).mappings().one()
+        old={**row['payload'],'subject':'[MMLab] Old receipt'}
+        conn.execute(update(store.outbox).values(status=status,payload=old))
+    migrate_pending();migrate_pending()
+    with store.engine.connect() as conn:actual=conn.execute(select(store.outbox)).mappings().one()
+    assert actual['status']==status and actual['attempts']==row['attempts']
+    assert actual['payload']['subject']==('Re: Fwd: Paper decision' if status in ('pending','retry') else '[MMLab] Old receipt')
+    assert actual['payload']['link']==old['link']
+
+
+def test_discussion_roster_ownership_manual_edits_and_common_lines():
+    report=compose([paper(memberIds=[1,7])],'2026-09')
+    report['sections']['a1']+='\nThảo luận với Nguyễn Vinh Tiệp (Chế Quang Huy)\nCông việc chung (cần làm ngay)\nTheo dõi Nguyễn Vinh Tiệp\nBảo trì (Nguyễn Vinh Tiệp, ngoài lab)'
+    report['sections']['b1']='Seminar về PPO (Chế Quang Huy)\nNghiên cứu mới (Nguyễn Vinh Tiệp)\nSeminar về PPO (Chế Quang Huy)'
+    before=copy.deepcopy(report);groups=by_member(report)
+    assert [v['id'] for v in groups]==list(range(1,13))+[None]
+    assert len(groups[0]['done'])==1 and len(groups[6]['done'])==2
+    assert groups[6]['planned']==['Seminar về PPO']
+    assert 'Công việc chung (cần làm ngay)' in groups[-1]['done']
+    assert 'Theo dõi Nguyễn Vinh Tiệp' in groups[-1]['done']
+    assert 'Bảo trì (Nguyễn Vinh Tiệp, ngoài lab)' in groups[-1]['done']
+    assert all(not groups[i]['done'] for i in (1,2,3,4,5,7,8,9,10,11))
+    blob=docx_bytes(report,'discussion');doc=Document(io.BytesIO(blob))
+    headings=[p.text for p in doc.paragraphs if p.style.name=='Heading 1']
+    assert headings[:12]==[f"{m['id']}. {m['name']}" for m in DIRECTORY]
+    text=doc_text(blob)
+    assert text.count('A study of realistic video retrieval')==2
+    assert text.index('1. Nguyễn Vinh Tiệp') < text.index('Đã làm') < text.index('Sẽ làm') < text.index('2. Đặng Văn Thìn')
+    assert summarize(report)['metrics']['paper']['scopus']==1
+    assert report==before
+    report['sections']['a1']=''
+    assert all(not g['done'] for g in by_member(report))
+
+
+def test_exact_requested_rank_labels_and_real_counts():
+    ranks=['Q1']*3+['A*']+['A']*2+['B']*4+['C']+['C-Unranked']*25
+    report=compose([paper(id=str(i),title=f'Paper number {i}',ranking=rank) for i,rank in enumerate(ranks)],'2026-09')
+    assert summarize(report)['a']=='Q1 3 bài, A* và A: 3 bài, Rank B: 4 bài, Rank C: 1 bài, Scopus: 25 bài.'
+    small=compose([paper(id=str(i),title=f'Unranked paper {i}') for i in range(3)],'2026-09')
+    assert summarize(small)['a']=='Scopus: 3 bài.'
+    text=doc_text(docx_bytes(report,'school'))
+    assert 'KPI bài báo: hoàn thành' not in text and 'Scopus khác' not in text and 'Trong đó:' not in text
+    assert declaration_breakdown('hoàn thành 46 / 44 bài báo Scopus. Trong đó: Q1 3 bài, Scopus khác: 25 bài')=='Q1 3 bài, Scopus: 25 bài.'
+
+
+def test_last_monday_frozen_discussion_uses_member_sections(scheduled):
+    login(scheduled)
+    draft=scheduled.get('/api/monthly/2026-09').json()
+    payload={k:draft[k] for k in ('revision','strategyLabel','signatory')}
+    payload['sections']={'a1':'Viết báo cáo (Chế Quang Huy)','b1':'Seminar robotics (Chế Quang Huy)'}
+    assert scheduled.put('/api/monthly/2026-09',json=payload,headers={'Origin':'http://testserver'}).status_code==200
+    assert service.enqueue_due(datetime(2026,9,28,9,tzinfo=VN))
+    assert not service.enqueue_due(datetime(2026,9,28,10,tzinfo=VN))
+    with store.engine.connect() as conn:batch=conn.execute(select(service.batches.c.payload)).scalar_one()
+    text=doc_text(base64.b64decode(batch['attachments'][0]['content']))
+    huy=text.split('7. Chế Quang Huy')[1].split('8. Trương Quốc Trường')[0]
+    assert 'Đã làm' in huy and 'Viết báo cáo' in huy and 'Sẽ làm' in huy and 'Seminar robotics' in huy
--- a/backend/tests/test_school_filter.py
+++ b/backend/tests/test_school_filter.py
@@ -68,7 +68,7 @@
 def test_structured_paper_title_is_not_recategorized_by_keyword():
     r=paper(title='Seminar Scheduling and Best Paper Award Prediction',status='Chưa rõ')
     report=compose([r],'2026-09')
-    assert 'hoàn thành 1 bài báo Scopus' in school_projection(report)['sections']['a1']
+    assert 'Scopus: 1 bài.' in school_projection(report)['sections']['a1']
     assert r['title'] not in school_projection(report)['sections']['a1']
     assert 'Accepted' not in doc_text(docx_bytes(report,'school'))
     assert report['counts']['acceptedConference']==0
--- a/backend/tests/test_school_statistics.py
+++ b/backend/tests/test_school_statistics.py
@@ -26,7 +26,7 @@
     result=summarize(r);counts=result['metrics']['paper']
     assert counts['scopus']==46 and sum(counts['ranks'].values())==46
     assert counts['ranks']=={'Q1':3,'A* và A':3,'Rank B':4,'Rank C':1,'Q2':10,'Scopus khác':25}
-    assert '46 / 44' in result['a'] and len(result['a'].splitlines())==1
+    assert result['a']=='Q1 3 bài, Q2 10 bài, A* và A: 3 bài, Rank B: 4 bài, Rank C: 1 bài, Scopus: 25 bài.'
     assert 'Unique scientific work' not in result['a'] and 'Chế Quang Huy' not in result['a']
     assert rows[0]['status']=='Chưa rõ'  # Receipt approval must not rewrite publication status.
 
@@ -37,7 +37,7 @@
         ['Nộp 05 bài tạp chí Q1, 06 bài báo hội nghị','Chuẩn bị nộp 02 hồ sơ NCS','Nghiệm thu 2 đề tài D1'],id='tasks')],'2026-09')
     r['scopusTarget']=44;s=summarize(r)
     assert s['a'].splitlines()==[
-        'KPI bài báo: hoàn thành 1 / 44 bài báo Scopus. Trong đó: Q1: 1 bài.',
+        'Q1 1 bài.',
         'KPI NCS: mới được công nhận thêm 04 NCS.',
         '01 NCS đã báo cáo xong chuyên đề 3.',
         'Nghiệm thu 2 đề tài D1.']
@@ -86,8 +86,8 @@
         paper(id='removed',title='Removed',date='2026-02-01',deletedAt='2026-09-01')]
     r=compose(rows,'2026-09');r.update(paperScope='year',scopusTarget=44)
     s=summarize(r)
-    assert s['metrics']['paper']['scopus']==2 and 'lũy kế năm 2026 đến 09/2026' in s['a']
-    assert '2 / 44' in s['a']
+    assert s['metrics']['paper']['scopus']==2 and 'lũy kế năm 2026 đến 09/2026' in doc_text(docx_bytes(r,'school'))
+    assert s['a']=='Scopus: 2 bài.' and s['metrics']['scopusTarget']==44
     r['sections']['a1']=''
     assert summarize(r)['metrics']['paper']['scopus']==1
     r['paperScope']='month';assert summarize(r)['metrics']['paper']['scopus']==0
@@ -126,7 +126,7 @@
     assert saved.status_code==200,saved.text
     summary=saved.json()['schoolSummary'];loaded=c.get('/api/monthly/2026-09').json()
     assert loaded['scopusTarget']==44 and loaded['paperScope']=='year' and loaded['schoolSummary']==summary
-    assert '1 / 44' in summary['a'] and len(summary['a'].splitlines())==4
+    assert summary['a'].startswith('Q1 1 bài.') and len(summary['a'].splitlines())==4
     document=doc_text(c.get('/api/monthly/2026-09/school.docx').content)
     assert 'Example research' not in document
     for line in summary['a'].splitlines():assert document.count(line)==2*(1+int(line in summary['b'].splitlines()))
--- a/frontend/src/MonthlyReports.tsx
+++ b/frontend/src/MonthlyReports.tsx
@@ -14,7 +14,7 @@
  return <section className="monthly-workspace"><div className="monthly-toolbar"><label>Tháng tổng hợp <input aria-label="Tháng tổng hợp" type="month" value={period} onChange={e=>{if(e.target.value&&(!dirty||window.confirm('Bỏ thay đổi chưa lưu và đổi tháng?')))setPeriod(e.target.value)}}/></label><Button variant="outline" onClick={()=>void refresh()}>Tổng hợp lại</Button><Button onClick={()=>void save()} disabled={!draft||busy||!dirty}>{busy?'Đang lưu…':'Lưu báo cáo'}</Button></div>
  <p className="monthly-schedule">Hai bản được gửi đến 12 thành viên lúc 09:00 thứ Hai cuối cùng mỗi tháng. Lịch tiếp theo: {next||'Đang tải…'}.</p>
  {error&&<p className="login-error" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
- {draft&&<>{draft.customized&&(!draft.assemblyVersion||draft.assemblyVersion<2)&&<p className="editor-hint">Đây là bản đã lưu bằng cách tổng hợp cũ. Bấm Tổng hợp lại để nối dòng và gộp mục trùng; kiểm tra nội dung trước khi lưu.</p>}<div className="monthly-downloads"><div><h2>Bản thảo luận · Đã và Sẽ</h2><p>Toàn bộ Đã tháng {period} và Sẽ tháng {draft.planPeriod}, gồm tất cả nhóm công việc.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/discussion.docx`}>Tải Word</a></div><div><h2>Bản nộp trường · A và B</h2><p>Thống kê số lượng bài báo, NCS và đề tài. Đã → A.1/A.2; Sẽ → B.1/B.2. Mã đơn vị: 6.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/school.docx`}>Tải Word</a></div></div>{dirty&&<p className="editor-hint">Lưu thay đổi trước khi tải Word.</p>}
+ {draft&&<>{draft.customized&&(!draft.assemblyVersion||draft.assemblyVersion<2)&&<p className="editor-hint">Đây là bản đã lưu bằng cách tổng hợp cũ. Bấm Tổng hợp lại để nối dòng và gộp mục trùng; kiểm tra nội dung trước khi lưu.</p>}<div className="monthly-downloads"><div><h2>Bản thảo luận · Đã và Sẽ</h2><p>Theo từng thành viên: Đã làm tháng {period}, Sẽ làm tháng {draft.planPeriod}. Gồm tất cả nhóm công việc.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/discussion.docx`}>Tải Word</a></div><div><h2>Bản nộp trường · A và B</h2><p>Thống kê số lượng bài báo, NCS và đề tài. Đã → A.1/A.2; Sẽ → B.1/B.2. Mã đơn vị: 6.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/school.docx`}>Tải Word</a></div></div>{dirty&&<p className="editor-hint">Lưu thay đổi trước khi tải Word.</p>}
  <p>Nhập đầy đủ Đã và Sẽ ở hai ô dưới. Bản thảo luận giữ toàn bộ nội dung. Bản nộp trường tự cộng số lượng bài báo, NCS, đề tài và chép A.1 sang A.2, B.1 sang B.2.</p>
  <section className="monthly-section" aria-label="Thống kê nộp trường"><h2>Thống kê nộp trường</h2>
  <div className="monthly-meta"><label>Phạm vi bài báo<select value={draft.paperScope||'month'} onChange={e=>{setDraft({...draft,paperScope:e.target.value as 'month'|'year'});setDirty(true)}}><option value="month">Trong tháng {period}</option><option value="year">Lũy kế năm {period.slice(0,4)} đến tháng {period.slice(5)}</option></select></label><label>Chỉ tiêu Scopus trong kỳ đã chọn (tùy chọn)<input type="number" min="1" max="100000" step="1" placeholder="Chưa đặt chỉ tiêu" value={draft.scopusTarget??''} onChange={e=>{setDraft({...draft,scopusTarget:e.target.value===''?null:Number(e.target.value)});setDirty(true)}}/></label></div>
'''

def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_diff(source, lines):
    original = source.splitlines(keepends=True)
    result, cursor, i = [], 0, 0
    while i < len(lines):
        header = re.fullmatch(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@.*\n?", lines[i])
        if not header:
            raise ValueError("Invalid embedded diff header")
        start = max(0, int(header.group(1)) - 1)
        if start < cursor:
            raise ValueError("Overlapping diff")
        result.extend(original[cursor:start])
        cursor, i = start, i + 1
        while i < len(lines) and not lines[i].startswith("@@ "):
            line = lines[i]
            if line[0] in " -":
                if cursor >= len(original) or original[cursor] != line[1:]:
                    raise ValueError("Diff context does not match source")
                cursor += 1
            if line[0] in " +":
                result.append(line[1:])
            if line[0] not in " +-":
                raise ValueError("Invalid diff line")
            i += 1
    result.extend(original[cursor:])
    return "".join(result)


def read_text(path):
    return path.read_text(encoding="utf-8-sig") if path.exists() else ""


def main():
    cli = argparse.ArgumentParser(description="Update the MMLab reply emails, member discussion and short rank statistics.")
    cli.add_argument("--check", action="store_true", help="Check only; do not write files")
    cli.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = cli.parse_args()
    root = args.root.resolve()
    if not (root / "run_local.py").is_file():
        sys.exit("Place this file beside run_local.py, or use --root PATH.")
    sections, key = {}, None
    lines = PATCH.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        if lines[i].startswith("--- a/"):
            key = lines[i][6:].rstrip("\n")
            if i+1 >= len(lines) or lines[i+1] != "+++ b/" + key + "\n":
                sys.exit("Invalid patch file headers")
            sections[key] = []
            i += 2
        else:
            if key is None:sys.exit("Invalid embedded patch")
            sections[key].append(lines[i])
            i += 1
    if set(sections) != set(MANIFEST):sys.exit("Incomplete embedded patch")
    pending, incompatible = {}, []
    for rel, hashes in MANIFEST.items():
        path = (root / rel).resolve()
        if not path.is_relative_to(root):sys.exit("Source path escapes project")
        old = read_text(path)
        if path.exists() and digest(old) == hashes['after']:
            continue  # Already updated: no rewrite and no extra backup.
        matches = (not path.exists()) if hashes['before'] is None else (path.exists() and digest(old) == hashes['before'])
        if not matches:
            incompatible.append(rel)
            continue
        new = apply_diff(old, sections[rel])
        if digest(new) != hashes['after']:sys.exit("Patch checksum failed: " + rel)
        if rel.endswith('.py'):compile(new, rel, 'exec')
        pending[rel] = new
    if incompatible:
        sys.exit("STOP: source differs from the previous version. Nothing was written.\n" + "\n".join(incompatible))
    if not pending:
        print("Already updated. Rebuild frontend if needed, then restart the app.")
        return
    if args.check:
        print("Compatible: " + str(len(pending)) + " source files will be updated. Nothing written.")
        return
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = root / '_backups' / ('reply-members-' + stamp)
    original = {}
    # Prepare all backups before replacing any source file.
    for rel in pending:
        path = root / rel
        original[rel] = path.read_bytes() if path.exists() else None
        if path.exists():
            saved = backup / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
    backup.mkdir(parents=True, exist_ok=True)
    (backup / 'changes.json').write_text(json.dumps({'new_files':[r for r,b in original.items() if b is None], 'changed_files':list(pending)}, indent=2), encoding='utf-8')
    changed = []
    try:
        for rel, content in pending.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
                    temp = Path(f.name)
                    f.write(content.encode('utf-8'))
                os.replace(temp, path)
                changed.append(rel)
            finally:
                if temp is not None and temp.exists():temp.unlink()
    except BaseException:
        for rel in reversed(changed):
            path = root / rel
            if original[rel] is None:path.unlink(missing_ok=True)
            else:path.write_bytes(original[rel])
        raise
    print("Updated " + str(len(pending)) + " source files.")
    print("Backup: " + str(backup))
    print("Next: npm run build --prefix frontend")
    print("      python run_local.py")
    print("Restart the app using the same Python environment as before, then refresh the page.")


if __name__ == '__main__':
    main()



