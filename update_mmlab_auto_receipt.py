# -*- coding: utf-8 -*-
"""MMLab: automatic receipts + school monthly report (update for the previous v9 code).

Place this file next to run_local.py, stop the app, then run:
    python update_mmlab_auto_receipt.py
    npm ci --prefix frontend
    npm run build --prefix frontend
    python run_local.py

Optional: python update_mmlab_auto_receipt.py --check

Changes:
- Worker-read forwarded reports are automatically approved on receipt.
- Paper email contains saved details and an OPTIONAL edit link. No confirmation.
- Public edits work repeatedly, with revision conflicts and deleted-link checks.
- Admin review remains optional. Reviewing does not cancel the receipt email.
- Existing worker receipts migrate once; no historical mail is queued/resubmitted.
- School DOCX includes A.1/A.2/B.1/B.2/recommendations; unit code 6; 2021-2030.
- Unassigned work falls under A.2/B.2 in school output, not duplicated into KHCL.
- No example KPI totals/targets are hardcoded. Dates still follow receipt month.

No packages required for this updater. No network access, no email sending,
no changes to .env, secrets or database. Sources are backed up under _backups.
Database metadata migrates when the app next starts. MAIL_MODE=smtp is still
required for real sending. PUBLIC_BASE_URL must be reachable for remote edits.
The readable source diff is embedded below; there is no encoded archive.
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

MANIFEST = {'backend/admin_reports.py': {'before': '3a4bfd042d51f09897966cb0bbb98390f70ac08f7d892be34f924915c5ccc025', 'after': 'c08551cb9ada63283679383095d34214ad1dd490effa5f1eab66cd674d272ef6'}, 'backend/intake.py': {'before': '8aae7ae4ec94c88c0362d6e613944012379c6b3a734162b503e744a7480405e3', 'after': 'd98ab471763e30d145ffe419bd2799df3e36ab80cd7bc153ea76121b1835b031'}, 'backend/main.py': {'before': '0ee59407d3b839eb172b1e0b1c05324913ff2bece0662e2a9da7e6b9fc05d211', 'after': '9da3a7a30fc8c24e3e7f00635010c54bfd77d3bec2358616385fae7e1406e7c1'}, 'backend/monthly_report.py': {'before': '3e51cb5c87d5bb3f0893398da17b95dfe36c70380be92d34d26c70febd4926c2', 'after': 'e816f7b64bd655de486730ab8d35ecb5af3d026b7352b0952478cf3923a4837e'}, 'backend/monthly_service.py': {'before': '37ab48cc9687513216ad92cbbbe2968844353348761d14a4c77e80dc8dcd5990', 'after': '11ae3b8091e21cb433318243267d0bfd0cf02443afb2f9623bdb372dbef2ffc6'}, 'backend/receipt_policy.py': {'before': None, 'after': '4fbc1a28b6d345b02af9688a21a45d8f29a284dc3b01b87772b67c40b1c88570'}, 'backend/store.py': {'before': '2268ae677d59753dbad9c15ccafc08d48c2815be16b703629d072b27a42d6d6c', 'after': 'a5b355853e4fc69a34847747b11e4e1e6cf6794ab896b3dfac87fee792c0aa37'}, 'backend/tests/test_admin_confirmation.py': {'before': '1341cf3a275c1f3fa518a5076e1f31de71f62513e1c5f06d7c564bde01d18a64', 'after': 'dc73ce391a922a74193d636b14526a104aa865a10f252c9f6bb75c8990aa5ec9'}, 'backend/tests/test_auto_receipt.py': {'before': None, 'after': '16039c1cbeef045996d12213e9b73f2f8ac3772ed64445403767cb937010c378'}, 'backend/tests/test_confirmation.py': {'before': '4b5da2ca819c4c0f356b65d0fe2a75ee8dd9acfab7d8b9cb8b53275c900f14ac', 'after': '816a573c5f8a88b1b65c4cc18f2e0f04c2133a74a7230c2807492ec7f2ecccae'}, 'backend/tests/test_monthly.py': {'before': '6947f6e60a0f727c7e3cefdcef4a6b5e999dad304e5a2607096c906689b309a6', 'after': '9abe3112ea6539692feebf19da7a6fd02a59a8a9fd0558cffad4650e74297383'}, 'backend/tests/test_task_assembly.py': {'before': '34a380889bbb98d04fa937ce1946dd02ab47fa8ffba50b7368d347528ce7d0d5', 'after': '00062024784ab0f916666073b713370f5c621904e8271dc48889d4b126a88619'}, 'frontend/src/Dashboard.tsx': {'before': 'a39977c38df73126e9481273a3324c3ccf4c1c5bb9ac192ab9b99b01432cd5ed', 'after': '6b3b9c146f594ac212de2775f7bfad4e55501b7235e333d4a3b5bf76841446d0'}, 'frontend/src/MonthlyReports.tsx': {'before': 'b041c8b3d9901e4ae12eb6336bc503515de65e9ae41aa711d2449856ad5990e8', 'after': '8dfd84b8b1ccaf55ac33fd9ff87a4e051448efe7caa0e4ddd07bcfd19c9ad013'}, 'frontend/src/PaperActions.tsx': {'before': '0bce2ff6f8684234be3ab8c30e5d97b3e0ef5e4e3aeed01b4841e32cc300ab7f', 'after': 'a260f83d3a07c754eb9418f102525e48752ab69bbabc6ffd239a1823f794cf70'}, 'frontend/src/PaperConfirm.tsx': {'before': '64a3480e57ab3750f6a2da7d81fa4867266818d0a61861bbead636f4d7314c05', 'after': '83d47c4b4e31de282fe528d9e9c125bfd33d764998b4e5c26edda37d5fa74a63'}, 'frontend/src/lib/research.ts': {'before': '81e8d5f8acb46785120b7b0e5272f4196fc21af9c4390d289e0d804400fbb40d', 'after': '7c9de40042c5ba62e4481a3c92d6d1d2d917834c22c7638f8aac8373bccc0d6e'}}

PATCH = r'''--- a/backend/admin_reports.py
+++ b/backend/admin_reports.py
@@ -66,8 +66,11 @@
             conn.execute(update(store.intakes).where(store.intakes.c.id==row['id']).values(
                 fields={k:report[k] for k in intake.FIELDS},original=report,status='confirmed',
                 revision=row['revision']+1,confirmed_at=stamp))
-            conn.execute(update(store.outbox).where(store.outbox.c.id==row['id'],store.outbox.c.status.in_(['pending','retry'])).values(
-                status='cancelled',last_error='Admin đã xác nhận, không cần gửi yêu cầu xác nhận đang chờ.'))
+            outgoing=conn.execute(select(store.outbox).where(store.outbox.c.id==row['id'])).mappings().first()
+            if outgoing and outgoing['status'] in ('pending','retry'):
+                payload=dict(outgoing['payload'])
+                payload.update(intake.mail_content({**row,'fields':{k:report[k] for k in intake.FIELDS},'original':report},payload['link']))
+                conn.execute(update(store.outbox).where(store.outbox.c.id==row['id']).values(payload=payload))
         conn.execute(update(store.reports).where(store.reports.c.id==ident).values(payload=report))
     return {'report':report,'alreadyConfirmed':False}
 
--- a/backend/intake.py
+++ b/backend/intake.py
@@ -55,18 +55,22 @@
 
 def mail_content(row, link):
     _, errors = validation(row['fields'])
-    lines = ['Chào bạn,', '', 'MMLab đã nhận được email Paper bạn chuyển tiếp.',
-             f"Mã tiếp nhận: {row['id'][:12]}", '',
-             'Thông tin hệ thống trích xuất (chưa được bạn xác nhận):', 'Type of Report: Paper']
-    lines += [f"{LABELS[key]}: {row['fields'][key] or '[CẦN BỔ SUNG]'}" for key in FIELDS]
+    lines = ['Chào bạn,', '', 'MMLab đã tự động ghi nhận Paper bạn chuyển tiếp.',
+             'Bạn không cần xác nhận lại. Dưới đây là thông tin đã được lưu:',
+             f"Mã tiếp nhận: {row['id'][:12]}", '', 'Type of Report: Paper']
+    lines += [f"{LABELS[key]}: {row['fields'][key] or '[CHƯA CÓ THÔNG TIN]'}" for key in FIELDS]
+    lines += ['Status: ' + (row['original'].get('status') or 'Chưa xác định')]
+    names = ', '.join(m['name'] for m in resolve_members(row['fields'].get('authors', '')))
+    lines += ['Thành viên lab: ' + (names or 'Chưa đối chiếu được thành viên lab')]
     if errors:
-        lines += ['', 'Các trường cần bổ sung hoặc kiểm tra:']
+        lines += ['', 'Báo cáo đã được ghi nhận; các thông tin sau còn thiếu hoặc cần sửa:']
         lines += [f"- {LABELS.get(e['field'],e['field'])}: {e['reason']}" for e in errors]
-    lines += ['', 'Vui lòng mở form đã điền sẵn, sửa/bổ sung thông tin và bấm Xác nhận & gửi:', link,
-              '', 'Link dùng riêng cho báo cáo này và hết hạn sau 7 ngày. Không chuyển link cho người khác.',
-              'Email này xác nhận đã nhận thư, chưa đồng nghĩa dữ liệu đã đầy đủ hoặc bài báo đã được xuất bản.',
-              'Nếu mọi trường đã đúng, vẫn vui lòng xác nhận trên form.', '', 'MMLab — UIT']
-    return {'subject': f"[MMLab] Đã nhận Paper — cần xác nhận #{row['id'][:12]}",
+    lines += ['', 'Nếu thông tin đã đúng, bạn không cần thao tác thêm.',
+              'Chỉnh sửa hoặc bổ sung thông tin (tùy chọn, không cần đăng nhập):', link,
+              'Link riêng cho báo cáo này, có hiệu lực 7 ngày.',
+              '', 'Tự động ghi nhận không đồng nghĩa bài báo đã được hội nghị/tạp chí chấp nhận. '
+              'Index/Ranking được lưu theo thông tin khai báo.', '', 'MMLab — UIT']
+    return {'subject': f"[MMLab] Đã ghi nhận Paper #{row['id'][:12]}",
             'body': '\n'.join(lines), 'link': link,
             'in_reply_to': row['original'].get('messageId', '')}
 
@@ -86,7 +90,7 @@
         stamp = report.get('receivedAt')
         since = os.getenv('AUTO_REPLY_SINCE') or conn.execute(select(store.workflow_settings.c.value).where(store.workflow_settings.c.key=='reply_since')).scalar_one()
         if not stamp or datetime.fromisoformat(stamp) < datetime.fromisoformat(since):
-            return 'Thư đến trước mốc tự động phản hồi. Có thể tạo email xác nhận cho riêng Paper này.'
+            return 'Thư đến trước mốc tự động phản hồi. Có thể tạo email kết quả cho riêng Paper này.'
     return ''
 
 
@@ -145,8 +149,6 @@
 def confirm(token, fields, revision):
     with store.mutation() as conn:
         row = token_row(conn, token)
-        if row['status'] == 'confirmed':
-            return {'confirmed':True, 'alreadyConfirmed':True,'confirmationSource':row['original'].get('confirmationSource','sender')}
         if revision != row['revision']:
             raise HTTPException(409, 'Dữ liệu đã thay đổi. Hãy tải lại form.')
         model, errors = validation(fields)
@@ -154,6 +156,10 @@
             return {'confirmed':False, 'errors':errors}
         normalized = model.model_dump(mode='json')
         report = dict(row['original'])
+        if report.get('confirmationStatus') == 'confirmed':
+            history = list(report.get('confirmationHistory', []))
+            history.append({k:report.get(k) for k in ('confirmationSource','confirmedBy','confirmedAt','reportVersion')})
+            report['confirmationHistory'] = history
         report['reportVersion'] = report.get('reportVersion', 0) + 1
         for key in FIELDS:
             report[key] = normalized[key]
@@ -165,15 +171,20 @@
         if not ids:issues.append('Không tìm thấy thành viên chính thức của lab trong tác giả.')
         if owner not in ids:owner=None;issues.append('Chưa xác định Person in Charge trong tác giả.')
         report.update(memberIds=ids, memberId=owner, isValid=True, missingFields=[],invalidFields=[],
-                      issues=issues, warnings=['Thông tin do người gửi xác nhận; Index/Ranking chưa được xác minh bên ngoài.'],
+                      issues=issues, warnings=['Thông tin do người gửi cập nhật; Index/Ranking chưa được xác minh bên ngoài.'],
                       confirmationStatus='confirmed', confirmedAt=store.now(), intakeId=row['id'])
         report.update(confirmationSource='sender',confirmedBy=row['recipient'])
-        updated = conn.execute(update(store.intakes).where(store.intakes.c.id==row['id'],store.intakes.c.status=='pending',
+        updated = conn.execute(update(store.intakes).where(store.intakes.c.id==row['id'],store.intakes.c.status!='cancelled',
                                  store.intakes.c.revision==revision).values(fields={k:normalized[k] for k in FIELDS},
                                  status='confirmed',revision=revision+1,confirmed_at=report['confirmedAt'],original=report))
         if updated.rowcount != 1:raise HTTPException(409, 'Form đã được xử lý. Hãy tải lại trang.')
         conn.execute(update(store.reports).where(store.reports.c.id==row['report_id']).values(payload=report))
-    return {'confirmed':True, 'alreadyConfirmed':False, 'confirmationSource':'sender', 'warnings':issues}
+        outgoing = conn.execute(select(store.outbox).where(store.outbox.c.id==row['id'])).mappings().first()
+        if outgoing and outgoing['status'] in ('pending','retry'):
+            payload = dict(outgoing['payload'])
+            payload.update(mail_content({**row, 'fields':{k:normalized[k] for k in FIELDS}, 'original':report}, payload['link']))
+            conn.execute(update(store.outbox).where(store.outbox.c.id==row['id']).values(payload=payload))
+    return {'confirmed':True, 'alreadyConfirmed':False, 'revision':revision+1, 'confirmationSource':'sender', 'warnings':issues}
 
 
 def admin_list():
@@ -192,7 +203,6 @@
         if not row:raise HTTPException(404,'Không tìm thấy hồ sơ.')
         row=dict(row)
         if row['status']=='cancelled':raise HTTPException(410,'Hồ sơ đã bị hủy.')
-        if row['status']=='confirmed':raise HTTPException(409,'Báo cáo đã xác nhận.')
         token=secrets.token_urlsafe(32)
         conn.execute(update(store.intakes).where(store.intakes.c.id==ident).values(
             token_hash=hashlib.sha256(token.encode()).hexdigest(),expires=time.time()+7*86400,revision=row['revision']+1))
@@ -226,8 +236,6 @@
             raise HTTPException(404, 'Không tìm thấy báo cáo.')
         if revision is not None and report.get('reportVersion',0)!=revision:
             raise HTTPException(409,'Báo cáo vừa thay đổi. Đóng chi tiết và mở lại trước khi gửi.')
-        if report.get('confirmationStatus')=='confirmed':
-            raise HTTPException(409,'Paper đã được xác nhận. Sửa và lưu nếu muốn yêu cầu xác nhận phiên bản mới.')
         if not report.get('mailWorkflowSource'):
             raise HTTPException(409, 'Cần quét Gmail lại để xác định người forward từ email gốc trước khi gửi.')
         reason = receipt_block_reason(conn, report, include_cutoff=False)
@@ -238,7 +246,7 @@
         expired=row['expires']<time.time()
         if mail['status'] not in ('pending','retry') or expired:
             if not resend:
-                raise HTTPException(409,'Đã có email xác nhận trước đó. Chọn Gửi lại email xác nhận để cấp link mới.')
+                raise HTTPException(409,'Đã có email kết quả trước đó. Chọn Gửi lại email kết quả để cấp link mới.')
             token=secrets.token_urlsafe(32)
             conn.execute(update(store.intakes).where(store.intakes.c.id==row['id']).values(
                 token_hash=hashlib.sha256(token.encode()).hexdigest(),expires=time.time()+7*86400,revision=row['revision']+1))
--- a/backend/main.py
+++ b/backend/main.py
@@ -175,12 +175,11 @@
 class PaperConfirmation(BaseModel):
     fields: PaperFields
     revision: int = Field(strict=True,ge=0)
-    confirmed: bool = Field(strict=True)
+    confirmed: bool = Field(default=True,strict=True)  # Legacy clients may still send it.
 
 
 @app.post('/api/paper-confirm')
 def submit_paper(data: PaperConfirmation, request: Request):
-    if not data.confirmed:raise HTTPException(400,'Vui lòng xác nhận đã kiểm tra thông tin.')
     result = intake.confirm(paper_token(request),data.fields.model_dump(),data.revision)
     return JSONResponse(result,status_code=200 if result['confirmed'] else 422)
 
--- a/backend/monthly_report.py
+++ b/backend/monthly_report.py
@@ -11,7 +11,8 @@
 
 VN=timezone(timedelta(hours=7))
 SECTIONS=('a1','a2','aOther','b1','b2','bOther','recommendations')
-DEFAULT_STRATEGY='KHCL Trường giai đoạn 2021-2025'
+DEFAULT_STRATEGY='Chiến lược Phát triển Trường, giai đoạn 2021-2030'
+PLAN_REFERENCE='Kế hoạch hành động năm 2026: https://link.uit.edu.vn/KH2026'
 
 
 def validate_period(period):
@@ -41,6 +42,15 @@
 
 def docx_bytes(report, variant):
     if variant not in ('discussion','school'):raise ValueError('Unknown report variant')
+    # Work on a copy: rendering must not mutate the admin's saved draft.
+    report={**report,'sections':dict(report['sections'])}
+    if report['strategyLabel']=='KHCL Trường giai đoạn 2021-2025':report['strategyLabel']=DEFAULT_STRATEGY
+    if variant=='school':
+        # Only explicitly tagged strategic tasks enter A.1/B.1.
+        # Other tasks are regular work; preserve their source text.
+        for phase in ('a','b'):
+            report['sections'][phase+'2']='\n'.join(filter(None,[report['sections'].get(phase+'2','').strip(),report['sections'].get(phase+'Other','').strip()]))
+            report['sections'][phase+'Other']=''
     doc=Document(); sec=doc.sections[0]
     sec.page_width=Cm(21);sec.page_height=Cm(29.7)
     sec.top_margin=Cm(2);sec.bottom_margin=Cm(2);sec.left_margin=Cm(2.5);sec.right_margin=Cm(2)
@@ -62,21 +72,22 @@
         return p
     paragraph('TRƯỜNG ĐẠI HỌC CÔNG NGHỆ THÔNG TIN',True,True)
     paragraph('ĐƠN VỊ: PHÒNG THÍ NGHIỆM TRUYỀN THÔNG ĐA PHƯƠNG TIỆN',True,True)
+    if variant=='school':paragraph('Mã đơn vị: 6',True)
     template=report.get('isTemplate',False)
     stamp=datetime.fromisoformat(report['generatedAt']).astimezone(VN)
     p=paragraph('Ngày … tháng … năm ……' if template else f'Ngày {stamp.day:02d} tháng {stamp.month:02d} năm {stamp.year}');p.alignment=WD_ALIGN_PARAGRAPH.RIGHT
     y,m=map(int,report['planPeriod'].split('-'))
-    paragraph(('BÁO CÁO CÔNG TÁC' if variant=='discussion' else 'KẾ HOẠCH CÔNG TÁC')+(' THÁNG …/……' if template else f' THÁNG {m:02d}/{y}'),True,True)
-    if variant=='discussion' and not template:
+    paragraph('BÁO CÁO CÔNG TÁC'+(' THÁNG …/……' if template else f' THÁNG {m:02d}/{y}'),True,True)
+    if not template:
         paragraph(f"Kết quả tháng {report['period'][5:]}/{report['period'][:4]} và kế hoạch tháng {m:02d}/{y}",center=True)
     def section(key,title):
-        if not template and not report['sections'].get(key,'').strip():return
+        if variant!='school' and not template and not report['sections'].get(key,'').strip():return
         if template and key=='b1' and variant=='discussion':doc.add_page_break()
         doc.add_heading(title,level=1)
-        if template and key in ('b1','b2'):
-            paragraph('Lưu ý đối chiếu với Kế hoạch Trường 2023 đã xây dựng tại https://link.uit.edu.vn/isucb')
+        if key in ('a1','b1','b2'):
+            paragraph(PLAN_REFERENCE)
         text=report['sections'].get(key,'').strip()
-        for line in text.splitlines() if text else ['…']:
+        for line in text.splitlines() if text else ['…' if template else 'Chưa có nội dung được ghi nhận.']:
             if line.rstrip(':') in TOPICS:
                 doc.add_heading(line.rstrip(':'),level=2)
             else:
@@ -85,7 +96,7 @@
                     p.paragraph_format.left_indent=Cm(.35)
                     p.paragraph_format.first_line_indent=Cm(-.35)
                     p.runs[0].text='• '+line
-    if variant=='discussion':
+    if variant in ('discussion','school'):
         section('a1',f"Phần A.1: Tình hình thực hiện nhiệm vụ phục vụ {report['strategyLabel']} trong tháng trước")
         section('a2','Phần A.2: Tình hình thực hiện nhiệm vụ thường xuyên và đột xuất trong tháng trước')
         if report['sections'].get('aOther'):section('aOther', 'Phần A: Kết quả công tác trong tháng trước' if not report['sections'].get('a1') and not report['sections'].get('a2') else 'Nội dung thực hiện bổ sung')
@@ -95,12 +106,12 @@
     if variant=='discussion' and report.get('reviewNotes'):
         doc.add_heading('Nội dung cần bổ sung để hoàn thiện báo cáo',level=1)
         for note in report['reviewNotes']:paragraph(note)
-    if template or report['sections'].get('recommendations','').strip():
+    if variant=='school' or template or report['sections'].get('recommendations','').strip():
         section('recommendations','Phần 3: Các kiến nghị')
     if doc.paragraphs:doc.paragraphs[-1].paragraph_format.keep_with_next=True
     p=paragraph('Trưởng đơn vị\n(Ký và ghi rõ họ tên)\n\n'+report['signatory'],True)
     p.alignment=WD_ALIGN_PARAGRAPH.RIGHT
-    doc.core_properties.title=('Báo cáo thảo luận ' if variant=='discussion' else 'Kế hoạch nộp trường ')+report['planPeriod']
+    doc.core_properties.title=('Báo cáo thảo luận ' if variant=='discussion' else 'Báo cáo nộp trường ')+report['planPeriod']
     doc.core_properties.author='MMLab - UIT'
     out=io.BytesIO();doc.save(out);return out.getvalue()
 
--- a/backend/monthly_service.py
+++ b/backend/monthly_service.py
@@ -10,7 +10,7 @@
 from fastapi import HTTPException
 import store
 import mailer
-from monthly_report import VN, SECTIONS, compose, docx_bytes, validate_period
+from monthly_report import VN, SECTIONS, compose, docx_bytes, validate_period, DEFAULT_STRATEGY
 from mmlab_pipeline.members import DIRECTORY
 
 drafts=Table('monthly_drafts',store.meta,Column('period',String,primary_key=True),Column('payload',JSON,nullable=False),Column('revision',Integer,nullable=False))
@@ -53,7 +53,10 @@
     if conn is None:
         with store.engine.connect() as c:return read_draft(period,c,fresh)
     saved=conn.execute(select(drafts).where(drafts.c.period==period)).mappings().first()
-    if saved and not fresh:return {**saved['payload'],'revision':saved['revision'],'customized':True}
+    if saved and not fresh:
+        report={**saved['payload'],'revision':saved['revision'],'customized':True}
+        if report['strategyLabel']=='KHCL Trường giai đoạn 2021-2025':report['strategyLabel']=DEFAULT_STRATEGY
+        return report
     records=conn.execute(select(store.reports.c.payload).where(store.reports.c.mailbox==store.mailbox())).scalars().all()
     return {**compose(records,period),'revision':saved['revision'] if saved else 0,'customized':False}
 
@@ -84,7 +87,7 @@
         attachments=[{'name':f'mmlab-{report["planPeriod"]}-{variant}.docx','content':base64.b64encode(docx_bytes(report,variant)).decode(),
                       'subtype':'vnd.openxmlformats-officedocument.wordprocessingml.document'} for variant in ('discussion','school')]
         payload={'subject':f'[MMLab] Báo cáo thảo luận và kế hoạch tháng {report["planPeriod"]}',
-                 'body':f'Kính gửi các thành viên MMLab,\n\nĐính kèm hai bản báo cáo:\n1. Bản thảo luận: công việc đã thực hiện tháng {period} và kế hoạch tháng {report["planPeriod"]}.\n2. Bản kế hoạch để hoàn thiện và nộp trường: chỉ gồm phần Sẽ.\n\nVui lòng trao đổi và bổ sung các nội dung chưa phân nhóm hoặc còn thiếu.\n\nTrân trọng,\nMMLab — UIT',
+                 'body':f'Kính gửi các thành viên MMLab,\n\nĐính kèm hai bản báo cáo:\n1. Bản thảo luận: công việc đã thực hiện tháng {period} và kế hoạch tháng {report["planPeriod"]}.\n2. Bản báo cáo nộp trường: A.1, A.2, B.1, B.2 và kiến nghị; đơn vị mã 6, chiến lược 2021–2030.\n\nVui lòng trao đổi và bổ sung các nội dung chưa phân nhóm hoặc còn thiếu.\n\nTrân trọng,\nMMLab — UIT',
                  'attachments':attachments}
         conn.execute(store.insert(batches).values(period=period,payload=payload,created_at=now.isoformat()))
         assert len(DIRECTORY)==12 and len({m['email'] for m in DIRECTORY})==12
--- a/backend/receipt_policy.py
+++ b/backend/receipt_policy.py
@@ -0,0 +1,37 @@
+"""Automatic receipt approval is independent of validation and publication status."""
+from sqlalchemy import select, update
+import store
+
+POLICY = 'automatic-receipt-v1'
+OWNED_FIELDS = ('approvalStatus', 'approvalSource', 'approvedAt')
+
+
+def approve_received(report):
+    if report.get('mailWorkflowSource') and report.get('forwarded') and not report.get('deletedAt'):
+        report.update(approvalStatus='approved', approvalSource='automatic',
+                      approvedAt=report.get('approvedAt') or store.now())
+    return report
+
+
+def migrate():
+    """Upgrade existing receipts without queuing or resending historical email."""
+    import intake
+    with store.mutation() as conn:
+        key = POLICY + ':' + store.mailbox()
+        if conn.execute(select(store.workflow_settings.c.key).where(store.workflow_settings.c.key == key)).first():
+            return
+        rows = conn.execute(select(store.reports).where(store.reports.c.mailbox == store.mailbox())).mappings().all()
+        for row in rows:
+            report = approve_received(dict(row['payload']))
+            if report.get('approvalStatus') != 'approved' or report.get('deletedAt'):
+                continue
+            conn.execute(update(store.reports).where(store.reports.c.id == row['id']).values(payload=report))
+            forms = conn.execute(select(store.intakes).where(store.intakes.c.report_id == row['id'], store.intakes.c.status != 'cancelled')).mappings().all()
+            for form in forms:
+                conn.execute(update(store.intakes).where(store.intakes.c.id == form['id']).values(original=report))
+                outgoing = conn.execute(select(store.outbox).where(store.outbox.c.id == form['id'])).mappings().first()
+                if outgoing and outgoing['status'] in ('pending', 'retry'):
+                    payload = dict(outgoing['payload'])
+                    payload.update(intake.mail_content({**form, 'original':report}, payload['link']))
+                    conn.execute(update(store.outbox).where(store.outbox.c.id == form['id']).values(payload=payload))
+        conn.execute(store.insert(store.workflow_settings).values(key=key, value=store.now()))
--- a/backend/store.py
+++ b/backend/store.py
@@ -64,6 +64,9 @@
         conn.execute(insert(workflow_settings).values(key='reply_since', value=now()).on_conflict_do_nothing(index_elements=['key']))
         conn.execute(insert(workflow_settings).values(key='monthly_started', value=now()).on_conflict_do_nothing(index_elements=['key']))
 
+    from receipt_policy import migrate
+    migrate()
+
 
 def state():
     with engine.connect() as conn:
@@ -100,11 +103,16 @@
                 continue
             # Imported data cannot forge server-owned edit/deletion markers.
             for key in ('deletedAt', 'adminEditedAt', 'adminEditedBy', 'reportVersion',
-                        'confirmationStatus','confirmationSource','confirmedBy','confirmedAt','confirmationHistory','intakeId'):
+                        'confirmationStatus','confirmationSource','confirmedBy','confirmedAt','confirmationHistory','intakeId',
+                        'approvalStatus','approvalSource','approvedAt'):
                 r.pop(key, None)
             from intake import register_paper, receipt_block_reason
             # Never trust this flag from an imported JSON file.
             r['mailWorkflowSource'] = bool(workflow)
+            from receipt_policy import approve_received
+            if workflow and existing and existing.get('approvalStatus')=='approved':
+                r['approvedAt']=existing['approvedAt']
+            approve_received(r)
             intake_row = register_paper(conn, r) if workflow else None
             if r['type'] == 'Paper':
                 r['receiptIssue'] = '' if intake_row else (receipt_block_reason(conn, r) if workflow else 'Nhập JSON không tự gửi email. Quét Gmail để xác định người forward.')
--- a/backend/tests/test_admin_confirmation.py
+++ b/backend/tests/test_admin_confirmation.py
@@ -27,7 +27,7 @@
     assert approve(workflow,r,revision=9).status_code==409
 
 
-def test_admin_approval_cancels_pending_mail_and_public_form_cannot_overwrite(workflow,monkeypatch):
+def test_admin_review_keeps_receipt_and_rejects_stale_public_edits(workflow,monkeypatch):
     original=valid_seed();r=store.read_reports()[0][0];_,token=get_link();login(workflow)
     result=approve(workflow,r);assert result.status_code==200,result.text
     confirmed=result.json()['report']
@@ -37,10 +37,10 @@
     view=workflow.get('/api/paper-confirm',headers=headers(token)).json()
     assert view['status']=='confirmed' and view['confirmationSource']=='admin'
     response=workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':{**VALID,'title':'Overwrite attempt'},'revision':0,'confirmed':True})
-    assert response.json()['alreadyConfirmed']
+    assert response.status_code==409
     assert store.read_reports()[0][0]['title']==VALID['title']
     monkeypatch.setenv('MAIL_MODE','smtp');calls=[]
-    mailer.dispatch(sender=lambda r:calls.append(r) or ('sent',None));assert calls==[]
+    mailer.dispatch(sender=lambda r:calls.append(r) or ('sent',None));assert len(calls)==1
     store.ingest(original,workflow=True)
     assert store.read_reports()[0][0]['confirmationSource']=='admin'
     assert approve(workflow,confirmed).json()['alreadyConfirmed']
--- a/backend/tests/test_auto_receipt.py
+++ b/backend/tests/test_auto_receipt.py
@@ -0,0 +1,95 @@
+"""Regression tests for the automatic receipt policy and the new school form."""
+import copy
+from sqlalchemy import select, update
+from test_confirmation import workflow, seed, get_link, headers, VALID, ORIGIN
+from test_api import login
+from test_admin_reports import edit_payload
+from test_monthly import doc_text, paper
+from monthly_report import compose, docx_bytes
+from models import Bundle
+import store
+import intake
+import receipt_policy
+
+
+def test_incomplete_forward_approved_without_changing_validation(workflow):
+    seed()
+    r=store.read_reports()[0][0]
+    assert r['approvalStatus']=='approved' and r['approvalSource']=='automatic'
+    assert not r['isValid'] and r['missingFields'] and r['memberIds']==[]
+    row,_=get_link()
+    assert 'không cần xác nhận lại' in row['body'] and 'tùy chọn' in row['body']
+    assert 'cần xác nhận' not in row['subject']
+    with store.engine.connect() as c:assert c.execute(select(store.outbox.c.status)).scalar_one()=='pending'
+
+
+def test_approval_survives_mail_configuration_error(workflow,monkeypatch):
+    monkeypatch.setenv('PUBLIC_BASE_URL','invalid')
+    seed()
+    r=store.read_reports()[0][0]
+    assert r['approvalStatus']=='approved' and r['receiptIssue'] and intake.admin_list()==[]
+
+
+def test_repeat_public_edit_no_checkbox_and_stale_revision_conflicts(workflow):
+    original=seed();_,token=get_link()
+    first=workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':0})
+    assert first.status_code==200 and first.json()['revision']==1
+    changed={**VALID,'title':'A second revision of the research paper'}
+    second=workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':changed,'revision':1})
+    assert second.status_code==200 and second.json()['revision']==2
+    assert workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':1}).status_code==409
+    store.ingest(original,workflow=True)
+    r=store.read_reports()[0][0]
+    assert r['title']==changed['title'] and r['approvalStatus']=='approved'
+    assert intake.admin_list()[0]['body'].count(changed['title'])==1
+    login(workflow)
+    response=workflow.request('DELETE','/api/reports/'+r['id'],headers={'Origin':ORIGIN},json={'revision':r['reportVersion']})
+    assert response.status_code==200
+    assert workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':2}).status_code==410
+
+
+def test_admin_edit_preserves_automatic_approval(workflow):
+    seed();r=store.read_reports()[0][0];login(workflow)
+    result=workflow.put('/api/reports/'+r['id'],headers={'Origin':ORIGIN},json=edit_payload(r,**VALID))
+    assert result.status_code==200 and result.json()['report']['approvalStatus']=='approved'
+
+
+def test_import_cannot_forge_receipt_approval(workflow):
+    b=seed(workflow=False).model_dump()
+    b['reports'][0].update(approvalStatus='approved',approvalSource='automatic',approvedAt=store.now())
+    store.ingest(Bundle.model_validate(b))
+    assert not store.read_reports()[0][0].get('approvalStatus')
+
+
+def test_migration_idempotent_no_historical_send_and_deleted_stay_deleted(workflow):
+    seed();r=store.read_reports()[0][0];_,token=get_link()
+    legacy={k:v for k,v in r.items() if k not in receipt_policy.OWNED_FIELDS}
+    legacy['status']='Chưa rõ'
+    with store.mutation() as c:
+        c.execute(store.workflow_settings.delete().where(store.workflow_settings.c.key==receipt_policy.POLICY+':'+store.mailbox()))
+        c.execute(update(store.reports).values(payload=legacy))
+        c.execute(update(store.intakes).values(original=legacy))
+        c.execute(update(store.outbox).values(payload={'subject':'Cần xác nhận','body':'old','link':'http://localhost:8080/#confirm='+token}))
+        c.execute(store.insert(store.reports).values(id='deleted',mailbox=store.mailbox(),payload={**legacy,'id':'deleted','deletedAt':store.now()}))
+    receipt_policy.migrate();receipt_policy.migrate()
+    r=store.read_reports()[0][0]
+    assert r['approvalStatus']=='approved' and r['status']=='Chưa rõ' and not r['isValid']
+    assert len(intake.admin_list())==1 and 'không cần xác nhận lại' in intake.admin_list()[0]['body']
+    with store.mutation() as c:c.execute(update(store.outbox).values(status='sent'))
+    receipt_policy.migrate()
+    assert intake.admin_list()[0]['mailStatus']=='sent'
+    assert len(store.read_reports()[0])==1
+
+
+def test_school_form_sections_unit_strategy_month_and_no_invented_targets():
+    r=compose([paper(taskGroup='unassigned',date='2026-07-15')],'2026-07')
+    r['sections'].update(bOther='Chuẩn bị hồ sơ nghiên cứu sinh',recommendations='Đề nghị hỗ trợ máy tính')
+    original=copy.deepcopy(r)
+    text=doc_text(docx_bytes(r,'school'))
+    for expected in ('THÁNG 08/2026','Mã đơn vị: 6','Phần A.1','Phần A.2','Phần B.1','Phần B.2','Phần 3','2021-2030','KH2026','Đề nghị hỗ trợ máy tính'):
+        assert expected in text
+    assert text.count('A study of realistic video retrieval')==1
+    a1=text.split('Phần A.1')[1].split('Phần A.2')[0]
+    assert 'A study of realistic video retrieval' not in a1
+    assert '46 / 44' not in text and '2021-2025' not in text
+    assert r==original  # School output must not modify saved discussion data.
--- a/backend/tests/test_confirmation.py
+++ b/backend/tests/test_confirmation.py
@@ -62,7 +62,7 @@
     row,token=get_link()
     assert row['recipient']=='student@gmail.com'
     assert 'committee@conf.example' not in row['body']
-    assert '[CẦN BỔ SUNG]' in row['body']
+    assert '[CHƯA CÓ THÔNG TIN]' in row['body']
     r=workflow.get('/api/paper-confirm',headers=headers(token))
     assert r.status_code==200
     assert r.json()['fields']['title']=='A research paper'
@@ -77,11 +77,10 @@
     invalid=workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':{**VALID,'ranking':'XYZ'},'revision':0,'confirmed':True})
     assert invalid.status_code==422
     assert any(e['field']=='ranking' for e in invalid.json()['errors'])
-    assert workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':0,'confirmed':False}).status_code==400
-    r=workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':0,'confirmed':True})
+    r=workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':0})
     assert r.status_code==200 and r.json()['confirmed']
     r=workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':0,'confirmed':True})
-    assert r.json()['alreadyConfirmed']
+    assert r.status_code==409
     store.ingest(original,workflow=True)
     records,_=store.read_reports()
     assert len(records)==1
--- a/backend/tests/test_monthly.py
+++ b/backend/tests/test_monthly.py
@@ -79,8 +79,8 @@
 def test_docx_variants_and_blank_dates():
     r=compose([],'2026-12');r['sections'].update(a1='ĐÃ-HOÀN-TẤT',b1='SẼ-THỰC-HIỆN')
     discussion=doc_text(docx_bytes(r,'discussion'));school=doc_text(docx_bytes(r,'school'))
-    assert 'ĐÃ-HOÀN-TẤT' in discussion and 'ĐÃ-HOÀN-TẤT' not in school
-    assert 'Phần A.' not in school and 'SẼ-THỰC-HIỆN' in school and 'THÁNG 01/2027' in school
+    assert 'ĐÃ-HOÀN-TẤT' in discussion and 'ĐÃ-HOÀN-TẤT' in school
+    assert 'Phần A.1' in school and 'Phần A.2' in school and 'SẼ-THỰC-HIỆN' in school and 'THÁNG 01/2027' in school
     template=doc_text(blank_template('school'))
     assert 'THÁNG …/……' in template and 'Ngày … tháng … năm ……' in template
 
--- a/backend/tests/test_task_assembly.py
+++ b/backend/tests/test_task_assembly.py
@@ -53,14 +53,14 @@
     assert 'Tiếp tục nghiên cứu' in result['data']['planned']
 
 
-def test_unknown_sender_excluded_from_school_and_empty_sections_hidden():
+def test_unknown_sender_excluded_from_school_and_required_sections_present():
     unknown=paper(id='unknown',type='Báo cáo tháng',memberIds=[],sender='unknown@example.com',monthlyTasks={'planned':['Seminar: công cụ "The']})
     known=paper(id='known',type='Báo cáo tháng',memberIds=[7],monthlyTasks={'planned':['Seminar: Robotics','Đi học PhD']})
     result=compose([unknown,known],'2026-09')
     assert len(result['reviewNotes'])==1
     texts={v:'\n'.join(p.text for p in Document(io.BytesIO(docx_bytes(result,v))).paragraphs) for v in ('discussion','school')}
     assert 'unknown@example.com' in texts['discussion'] and 'unknown@example.com' not in texts['school']
-    assert 'Phần A' not in texts['school'] and 'Robotics' in texts['school']
+    assert 'Phần A.1' in texts['school'] and 'Robotics' in texts['school']
     assert 'Chưa có nội dung báo cáo' not in texts['school']
     assert 'chưa phân nhóm' not in texts['school']
     assert 'Seminar và hội nghị' in texts['school']
--- a/frontend/src/Dashboard.tsx
+++ b/frontend/src/Dashboard.tsx
@@ -76,7 +76,7 @@
      <section className="stats-grid" aria-label="Số liệu tổng hợp">
       {[{label:'Công trình / hoạt động',number:works.length,desc:'Đã gộp các báo cáo cùng công trình',icon:BookOpen,color:'teal'}, {label:'Bản ghi báo cáo',number:filtered.length,desc:'Giữ từng người phụ trách và vai trò',icon:FileText,color:'blue'}, {label:'Thành viên tham gia',number:active.length,desc:'Đối chiếu trong 12 thành viên lab',icon:Users,color:'violet'}].map((stat,i)=><button key={stat.label} className={`stat-card ${stat.color} ${i===3&&quality?'selected':''}`} onClick={()=>{if(i===3)setQuality(v=>!v);else if(i===2)setView('members');else document.querySelector('.report-panel')?.scrollIntoView({behavior:'smooth'})}} aria-pressed={i===3?quality:undefined}><div className="stat-top"><span>{stat.label}</span><stat.icon size={19}/></div><strong className="stat-number">{String(stat.number).padStart(2,'0')}{i===2&&<small>/12</small>}</strong><p>{stat.desc}</p></button>)}
      </section>
-     <section className="panel report-panel"><div className="panel-heading report-heading"><div><h2>Báo cáo chi tiết <span className="count-badge">{filtered.length}</span></h2><p>Nhấn tiêu đề để xem thông tin đầy đủ.</p></div><div className="search-control"><Search size={16}/><Input aria-label="Tìm báo cáo" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Tìm tiêu đề, tác giả, venue…"/></div></div><div className="report-table"><Table><TableHeader><TableRow><TableHead className="date-cell">NGÀY NHẬN</TableHead><TableHead>CÔNG TRÌNH / HOẠT ĐỘNG</TableHead><TableHead>NGƯỜI PHỤ TRÁCH</TableHead><TableHead>VAI TRÒ</TableHead><TableHead>XẾP HẠNG</TableHead><TableHead>THÔNG TIN</TableHead><TableHead>THAO TÁC</TableHead></TableRow></TableHeader><TableBody>{[...filtered].sort((a,b)=>b.date.localeCompare(a.date)||a.id.localeCompare(b.id)).map(r=><TableRow key={r.id}><TableCell className="date-cell">{dateLabel(r.date)}</TableCell><TableCell className="title-cell"><button onClick={()=>setSelected(r)}>{r.title}</button><div><span>{r.type}</span><i/> {r.type==='Báo cáo tháng'?'Nhiệm vụ trong tháng':r.venue||'Chưa có venue'} {r.type!=='Báo cáo tháng'&&<span className="accepted">{r.status||'Chưa rõ trạng thái'}</span>}</div></TableCell><TableCell><span className="person-label">{members.find(m=>m.id===r.memberId)?.name||'Chưa xác định'}</span><span className="person-mail">{members.find(m=>m.id===r.memberId)?.email||'Cần đối soát'}</span></TableCell><TableCell><Badge variant="outline" className={r.role==='First author'?'first-author':'co-author'}>{r.type==='Báo cáo tháng'?'—':r.role||'Chưa rõ'}</Badge></TableCell><TableCell><span className="ranking-label">{r.type==='Báo cáo tháng'?'—':r.ranking||'—'}</span></TableCell><TableCell><button className={r.issues.length?'quality-label':'quality-label good'} onClick={()=>setSelected(r)}>{r.issues.length?<AlertCircle size={14}/>:<Check size={14}/>} {r.confirmationStatus==='pending'?'Chờ xác nhận':r.confirmationStatus==='confirmed'?(r.confirmationSource==='admin'?'Admin đã xác nhận':'Người gửi đã xác nhận'):r.isValid===false?'Không hợp lệ':r.issues.length?'Cần kiểm tra':'Đầy đủ'}</button></TableCell><TableCell>{r.source==='gmail'&&<div className="row-actions">{r.type==='Paper'&&<Button size="sm" variant="outline" onClick={()=>setSelected(r)}>Xác nhận</Button>}<Button size="sm" variant="ghost" onClick={()=>{setSelected(null);setEditing(r)}}>Sửa</Button><Button size="sm" variant="ghost" className="delete-button" disabled={deleting===r.id} onClick={()=>void deleteReport(r)}>{deleting===r.id?'Đang xóa…':'Xóa'}</Button></div>}</TableCell></TableRow>)}</TableBody></Table>{!filtered.length&&<div className="table-empty"><Mail size={30}/><h3>{source==='gmail'&&!connection.configured&&!connection.importInfo?'Gmail chưa được kết nối':'Không có báo cáo phù hợp'}</h3><p>{source==='gmail'&&!connection.configured&&!connection.importInfo?'Kết nối đúng hộp thư lab để bắt đầu lấy dữ liệu thực.':'Thử đổi thời gian, thành viên hoặc loại báo cáo.'}</p><Button variant="outline" onClick={()=>source==='gmail'&&!connection.configured&&!connection.importInfo?document.querySelector('.product-settings')?.setAttribute('open',''):reset()}>{source==='gmail'&&!connection.configured&&!connection.importInfo?'Nhập dữ liệu':'Xóa bộ lọc'}</Button></div>}</div><div className="panel-foot"><span>{filtered.length} bản ghi · {works.length} công trình riêng biệt</span><span>Nguồn: {source==='sample'?'bảng dữ liệu mẫu':'Gmail'}</span></div></section>
+     <section className="panel report-panel"><div className="panel-heading report-heading"><div><h2>Báo cáo chi tiết <span className="count-badge">{filtered.length}</span></h2><p>Nhấn tiêu đề để xem thông tin đầy đủ.</p></div><div className="search-control"><Search size={16}/><Input aria-label="Tìm báo cáo" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Tìm tiêu đề, tác giả, venue…"/></div></div><div className="report-table"><Table><TableHeader><TableRow><TableHead className="date-cell">NGÀY NHẬN</TableHead><TableHead>CÔNG TRÌNH / HOẠT ĐỘNG</TableHead><TableHead>NGƯỜI PHỤ TRÁCH</TableHead><TableHead>VAI TRÒ</TableHead><TableHead>XẾP HẠNG</TableHead><TableHead>THÔNG TIN</TableHead><TableHead>THAO TÁC</TableHead></TableRow></TableHeader><TableBody>{[...filtered].sort((a,b)=>b.date.localeCompare(a.date)||a.id.localeCompare(b.id)).map(r=><TableRow key={r.id}><TableCell className="date-cell">{dateLabel(r.date)}</TableCell><TableCell className="title-cell"><button onClick={()=>setSelected(r)}>{r.title}</button><div><span>{r.type}</span><i/> {r.type==='Báo cáo tháng'?'Nhiệm vụ trong tháng':r.venue||'Chưa có venue'} {r.type!=='Báo cáo tháng'&&<span className="accepted">{r.status||'Chưa rõ trạng thái'}</span>}</div></TableCell><TableCell><span className="person-label">{members.find(m=>m.id===r.memberId)?.name||'Chưa xác định'}</span><span className="person-mail">{members.find(m=>m.id===r.memberId)?.email||'Cần đối soát'}</span></TableCell><TableCell><Badge variant="outline" className={r.role==='First author'?'first-author':'co-author'}>{r.type==='Báo cáo tháng'?'—':r.role||'Chưa rõ'}</Badge></TableCell><TableCell><span className="ranking-label">{r.type==='Báo cáo tháng'?'—':r.ranking||'—'}</span></TableCell><TableCell><button className={r.issues.length?'quality-label':'quality-label good'} onClick={()=>setSelected(r)}>{r.issues.length?<AlertCircle size={14}/>:<Check size={14}/>} {r.approvalStatus==='approved'?(r.isValid===false?'Đã ghi nhận · Thiếu/sai thông tin':'Đã tự động ghi nhận'):r.confirmationStatus==='pending'?'Đã ghi nhận':r.confirmationStatus==='confirmed'?(r.confirmationSource==='admin'?'Admin đã xác nhận':'Người gửi đã xác nhận'):r.isValid===false?'Không hợp lệ':r.issues.length?'Cần kiểm tra':'Đầy đủ'}</button></TableCell><TableCell>{r.source==='gmail'&&<div className="row-actions">{r.type==='Paper'&&<Button size="sm" variant="outline" onClick={()=>setSelected(r)}>Email kết quả</Button>}<Button size="sm" variant="ghost" onClick={()=>{setSelected(null);setEditing(r)}}>Sửa</Button><Button size="sm" variant="ghost" className="delete-button" disabled={deleting===r.id} onClick={()=>void deleteReport(r)}>{deleting===r.id?'Đang xóa…':'Xóa'}</Button></div>}</TableCell></TableRow>)}</TableBody></Table>{!filtered.length&&<div className="table-empty"><Mail size={30}/><h3>{source==='gmail'&&!connection.configured&&!connection.importInfo?'Gmail chưa được kết nối':'Không có báo cáo phù hợp'}</h3><p>{source==='gmail'&&!connection.configured&&!connection.importInfo?'Kết nối đúng hộp thư lab để bắt đầu lấy dữ liệu thực.':'Thử đổi thời gian, thành viên hoặc loại báo cáo.'}</p><Button variant="outline" onClick={()=>source==='gmail'&&!connection.configured&&!connection.importInfo?document.querySelector('.product-settings')?.setAttribute('open',''):reset()}>{source==='gmail'&&!connection.configured&&!connection.importInfo?'Nhập dữ liệu':'Xóa bộ lọc'}</Button></div>}</div><div className="panel-foot"><span>{filtered.length} bản ghi · {works.length} công trình riêng biệt</span><span>Nguồn: {source==='sample'?'bảng dữ liệu mẫu':'Gmail'}</span></div></section>
      {view==='overview'?<>
       <section className="charts-grid"><div className="panel trend-panel"><div className="panel-heading"><div><h2>Báo cáo theo thời gian</h2><p>Công trình và bản ghi trong kỳ</p></div><div className="chart-legend"><span><i className="legend-teal"/>Công trình</span><span><i className="legend-blue"/>Bản ghi</span></div></div>{filtered.length?<div className="trend-chart" role="img" aria-label={`Biểu đồ ${works.length} công trình, ${filtered.length} bản ghi trong ${periodLabel}`}><ResponsiveContainer width="100%" height="100%"><BarChart data={chart} barGap={4} margin={{top:8,right:6,bottom:0,left:-27}}><CartesianGrid strokeDasharray="3 5" vertical={false} stroke="#e7edf1"/><XAxis dataKey="label" tickLine={false} axisLine={false} tick={{fill:'#788698',fontSize:12}} dy={8} interval={period==='month'?4:0}/><YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{fill:'#788698',fontSize:12}}/><Tooltip cursor={{fill:'#f1f6f8'}} contentStyle={{border:'1px solid #e2e9ed',borderRadius:10,fontSize:14}}/><Bar dataKey="works" name="Công trình" fill="#159c8d" maxBarSize={24} radius={[4,4,0,0]}/><Bar dataKey="reports" name="Bản ghi" fill="#a6b9d4" maxBarSize={24} radius={[4,4,0,0]}/></BarChart></ResponsiveContainer></div>:<div className="chart-empty"><Activity size={28}/><p>Chưa có dữ liệu trong kỳ này</p><span>Thử đổi khoảng thời gian hoặc nguồn dữ liệu.</span></div>}<div className="panel-foot"><span>{periodLabel}</span><span>Công trình được gộp trong kỳ</span></div></div>
        <div className="panel categories-panel"><div className="panel-heading"><div><h2>Loại báo cáo</h2><p>Theo công trình / hoạt động</p></div><span className="small-label">{works.length} TỔNG</span></div><div className="category-rows">{categories.map((c,i)=>{const n=works.filter(r=>r.type===c).length;return <button key={c} className={`category-row ${category===c?'chosen':''}`} onClick={()=>setCategory(category===c?'all':c)}><span className={`category-dot dot-${i}`}/><span>{c}</span><div className="category-track"><div style={{width:`${works.length?n/works.length*100:0}%`}}/></div><strong>{n}</strong></button>})}</div><div className="category-caption"><CircleHelp size={14}/> Nhấn vào một loại để lọc báo cáo</div></div></section>
--- a/frontend/src/MonthlyReports.tsx
+++ b/frontend/src/MonthlyReports.tsx
@@ -14,9 +14,9 @@
  return <section className="monthly-workspace"><div className="monthly-toolbar"><label>Tháng tổng hợp <input aria-label="Tháng tổng hợp" type="month" value={period} onChange={e=>{if(e.target.value&&(!dirty||window.confirm('Bỏ thay đổi chưa lưu và đổi tháng?')))setPeriod(e.target.value)}}/></label><Button variant="outline" onClick={()=>void refresh()}>Tổng hợp lại</Button><Button onClick={()=>void save()} disabled={!draft||busy||!dirty}>{busy?'Đang lưu…':'Lưu báo cáo'}</Button></div>
  <p className="monthly-schedule">Hai bản được gửi đến 12 thành viên lúc 09:00 thứ Hai cuối cùng mỗi tháng. Lịch tiếp theo: {next||'Đang tải…'}.</p>
  {error&&<p className="login-error" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
- {draft&&<>{draft.customized&&(!draft.assemblyVersion||draft.assemblyVersion<2)&&<p className="editor-hint">Đây là bản đã lưu bằng cách tổng hợp cũ. Bấm Tổng hợp lại để nối dòng và gộp mục trùng; kiểm tra nội dung trước khi lưu.</p>}<div className="monthly-downloads"><div><h2>Bản thảo luận · Đã và Sẽ</h2><p>Kết quả tháng {period}; kế hoạch tháng {draft.planPeriod}.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/discussion.docx`}>Tải Word</a></div><div><h2>Bản nộp trường · Sẽ</h2><p>Chỉ kế hoạch tháng {draft.planPeriod}, kèm kiến nghị và người ký.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/school.docx`}>Tải Word</a></div></div>{dirty&&<p className="editor-hint">Lưu thay đổi trước khi tải Word.</p>}
+ {draft&&<>{draft.customized&&(!draft.assemblyVersion||draft.assemblyVersion<2)&&<p className="editor-hint">Đây là bản đã lưu bằng cách tổng hợp cũ. Bấm Tổng hợp lại để nối dòng và gộp mục trùng; kiểm tra nội dung trước khi lưu.</p>}<div className="monthly-downloads"><div><h2>Bản thảo luận · Đã và Sẽ</h2><p>Kết quả tháng {period}; kế hoạch tháng {draft.planPeriod}.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/discussion.docx`}>Tải Word</a></div><div><h2>Bản nộp trường · A và B</h2><p>Báo cáo tháng {draft.planPeriod}: A.1, A.2, B.1, B.2 và kiến nghị. Mã đơn vị: 6.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/school.docx`}>Tải Word</a></div></div>{dirty&&<p className="editor-hint">Lưu thay đổi trước khi tải Word.</p>}
  <p>{draft.records} báo cáo nguồn. {draft.counts.unknownPaperStatus>0&&`${draft.counts.unknownPaperStatus} công trình chưa có trạng thái xác định, không tính là đã được chấp nhận.`}</p>
- {Boolean(draft.reviewNotes?.length)&&<details className="product-settings"><summary>Nội dung cần bổ sung ({draft.reviewNotes?.length})</summary><p>Các mục này chỉ kèm bản thảo luận, chưa đưa vào bản kế hoạch nộp trường. Sửa thông tin ở báo cáo nguồn rồi tổng hợp lại.</p>{draft.reviewNotes?.map((note,i)=><p key={i}>{note}</p>)}</details>}
+ {Boolean(draft.reviewNotes?.length)&&<details className="product-settings"><summary>Nội dung cần bổ sung ({draft.reviewNotes?.length})</summary><p>Các mục này chỉ kèm bản thảo luận, chưa đưa vào bản báo cáo nộp trường. Sửa thông tin ở báo cáo nguồn rồi tổng hợp lại.</p>{draft.reviewNotes?.map((note,i)=><p key={i}>{note}</p>)}</details>}
  <div className="monthly-meta"><label>Tên kế hoạch chiến lược<input value={draft.strategyLabel} onChange={e=>{setDraft({...draft,strategyLabel:e.target.value});setDirty(true)}}/></label><label>Trưởng đơn vị<input value={draft.signatory} onChange={e=>{setDraft({...draft,signatory:e.target.value});setDirty(true)}}/></label></div>
  {Object.entries(labels).map(([key,label])=><label className="monthly-section" key={key}><strong>{label}</strong><textarea rows={Math.min(12,Math.max(3,(draft.sections[key]||'').split('\n').length+1))} value={draft.sections[key]||''} onChange={e=>{setDraft({...draft,sections:{...draft.sections,[key]:e.target.value}});setDirty(true)}}/></label>)}
  </>}
--- a/frontend/src/PaperActions.tsx
+++ b/frontend/src/PaperActions.tsx
@@ -16,21 +16,22 @@
  const queued=!!email&&!email.expired&&['pending','retry'].includes(email.mailStatus);
  const resend=!!email&&(!queued||email.expired);
  async function send(){
-  if(resend&&!window.confirm('Gửi lại email xác nhận cho '+email?.recipient+'? Link cũ sẽ hết hiệu lực. Nếu lần gửi trước chưa rõ kết quả, kiểm tra thư đã gửi trước khi tiếp tục.'))return;
+  if(resend&&!window.confirm('Gửi lại email kết quả cho '+email?.recipient+'? Link cũ sẽ hết hiệu lực. Nếu lần gửi trước chưa rõ kết quả, kiểm tra thư đã gửi trước khi tiếp tục.'))return;
   changing.current=true;setBusy('mail');setError('');setNotice('');
   try{const d:Info=await fetch('/api/reports/'+current.id+'/request-confirmation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:current.reportVersion||0,resend})}).then(readApiResponse);setInfo(d);onChanged(d.report);setNotice(d.mailMode==='smtp'?'Đã tạo email và đưa vào hàng đợi gửi.':'Đã tạo email và link. Để gửi thật, đặt MAIL_MODE=smtp trong .env rồi khởi động lại app.')}catch(e){setError(e instanceof Error?e.message:'Không tạo được email.')}finally{changing.current=false;setBusy('')}
  }
  async function approve(){
-  if(!window.confirm('Xác nhận bạn đã kiểm tra toàn bộ thông tin Paper này? Hệ thống sẽ ghi nhận người xác nhận là admin và hủy email yêu cầu xác nhận còn đang chờ.'))return;
+  if(!window.confirm('Xác nhận bạn đã kiểm tra toàn bộ thông tin Paper này? Hệ thống sẽ ghi nhận người xác nhận là admin . Email kết quả vẫn được gửi tự động.'))return;
   changing.current=true;setBusy('admin');setError('');setNotice('');
-  try{const d=await fetch('/api/reports/'+current.id+'/admin-confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:current.reportVersion||0,confirmed:true})}).then(readApiResponse);onChanged(d.report);setInfo(old=>old?{...old,report:d.report,email:old.email?{...old.email,mailStatus:queued?'cancelled':old.email.mailStatus}:null}:old);setNotice('Admin đã xác nhận thông tin Paper.')}catch(e){setError(e instanceof Error?e.message:'Không xác nhận được.')}finally{changing.current=false;setBusy('')}
+  try{const d=await fetch('/api/reports/'+current.id+'/admin-confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:current.reportVersion||0,confirmed:true})}).then(readApiResponse);onChanged(d.report);setInfo(old=>old?{...old,report:d.report,email:old.email?{...old.email,mailStatus:old.email.mailStatus}:null}:old);setNotice('Admin đã xác nhận thông tin Paper.')}catch(e){setError(e instanceof Error?e.message:'Không xác nhận được.')}finally{changing.current=false;setBusy('')}
  }
- return <section className="paper-actions" aria-label="Xác nhận Paper"><h3>Xác nhận thông tin Paper</h3>
- <p>{confirmed?`Đã xác nhận bởi ${current.confirmationSource==='admin'?'admin '+(current.confirmedBy||''): 'người gửi'+(current.confirmedBy?' '+current.confirmedBy:'')}${current.confirmedAt?' · '+new Date(current.confirmedAt).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):''}`:'Chọn gửi form cho người báo cáo hoặc admin kiểm tra và xác nhận trực tiếp.'}</p>
- <div className="paper-action-buttons"><Button variant="outline" onClick={()=>void send()} disabled={!info||!!busy||confirmed||queued||email?.mailStatus==='sending'}>{busy==='mail'?'Đang tạo…':queued?'Email đang chờ gửi':resend?'Gửi lại email xác nhận':'Gửi email xác nhận'}</Button><Button onClick={()=>void approve()} disabled={!info||!!busy||confirmed}>{busy==='admin'?'Đang xác nhận…':confirmed?'Đã xác nhận':'Admin xác nhận'}</Button></div>
+ return <section className="paper-actions" aria-label="Thông tin Paper"><h3>Thông tin đã ghi nhận</h3>
+ {current.approvalStatus==='approved'&&<p>Đã tự động ghi nhận. Người gửi không cần xác nhận lại.</p>}
+ <p>{confirmed?`Đã xác nhận bởi ${current.confirmationSource==='admin'?'admin '+(current.confirmedBy||''): 'người gửi'+(current.confirmedBy?' '+current.confirmedBy:'')}${current.confirmedAt?' · '+new Date(current.confirmedAt).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):''}`:'Người gửi có thể sửa qua link trong email. Admin có thể kiểm tra thông tin tại đây.'}</p>
+ <div className="paper-action-buttons"><Button variant="outline" onClick={()=>void send()} disabled={!info||!!busy||queued||email?.mailStatus==='sending'}>{busy==='mail'?'Đang tạo…':queued?'Email đang chờ gửi':resend?'Gửi lại email kết quả':'Gửi email kết quả'}</Button><Button onClick={()=>void approve()} disabled={!info||!!busy||confirmed}>{busy==='admin'?'Đang xác nhận…':confirmed?'Đã xác nhận':'Admin xác nhận'}</Button></div>
  {queued&&info?.mailMode!=='smtp'&&<p>Chưa bật gửi email thật. Đặt MAIL_MODE=smtp trong .env rồi khởi động lại app.</p>}
- {confirmed&&<p>Muốn thay đổi thông tin, bấm Sửa báo cáo. Sau khi lưu cần xác nhận lại phiên bản mới.</p>}
+ {confirmed&&<p>Muốn thay đổi thông tin, bấm Sửa báo cáo. Thay đổi được lưu trực tiếp, không yêu cầu người gửi xác nhận lại.</p>}
  {error&&<p className="login-error" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
- {email&&<details><summary>Xem email và link xác nhận</summary><p><strong>Gửi đến:</strong> {email.recipient}</p><p><strong>Tiêu đề:</strong> {email.subject}</p><pre>{email.body}</pre>{email.expired?<p>Link đã hết hạn. Gửi lại email để cấp link mới.</p>:<a href={email.link} target="_blank" rel="noreferrer">Mở trang xác nhận</a>}</details>}
+ {email&&<details><summary>Xem email kết quả và link chỉnh sửa</summary><p><strong>Gửi đến:</strong> {email.recipient}</p><p><strong>Tiêu đề:</strong> {email.subject}</p><pre>{email.body}</pre>{email.expired?<p>Link đã hết hạn. Gửi lại email để cấp link mới.</p>:<a href={email.link} target="_blank" rel="noreferrer">Mở trang chỉnh sửa</a>}</details>}
  </section>
 }
--- a/frontend/src/PaperConfirm.tsx
+++ b/frontend/src/PaperConfirm.tsx
@@ -14,21 +14,20 @@
 ];
 export default function PaperConfirm({token}:{token:string}){
  const [record,setRecord]=useState<Record|null>(null),[fields,setFields]=useState<Fields>({title:'',authors:'',venue:'',role:'',index:'',ranking:''});
- const [errors,setErrors]=useState<ErrorField[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[confirmed,setConfirmed]=useState(false),[done,setDone]=useState(false),[warnings,setWarnings]=useState<string[]>([]);
- useEffect(()=>{let active=true;fetch('/api/paper-confirm',{headers:{Authorization:'Bearer '+token}}).then(async r=>{const data=await r.json();if(!r.ok)throw Error(data.error||'Không mở được form.');if(active){setRecord(data);setFields(data.fields);setErrors(data.errors);setDone(data.status==='confirmed')}}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[token]);
- async function submit(e:React.FormEvent){e.preventDefault();if(!record)return;setBusy(true);setError('');try{const r=await fetch('/api/paper-confirm',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({fields,revision:record.revision,confirmed})});const data=await r.json();if(!r.ok){if(data.errors){setErrors(data.errors);setError('Vui lòng bổ sung hoặc sửa các trường được đánh dấu.');return}throw Error(data.error||'Chưa gửi được form.')}setDone(true);setRecord(old=>old?{...old,confirmationSource:data.confirmationSource||'sender'}:old);setWarnings(data.warnings||[])}catch(e){setError(e instanceof Error?e.message:'Không kết nối được máy chủ.')}finally{setBusy(false)}}
- return <main className="confirmation-page"><div className="confirmation-card"><div className="confirm-brand"><div className="brand-mark"><FlaskConical/></div><span>MMLAB / UIT</span></div><p className="eyebrow">XÁC NHẬN BÁO CÁO PAPER</p>
-  <h1>{done?(record?.confirmationSource==='admin'?'Admin đã xác nhận báo cáo':'Đã ghi nhận xác nhận'):'Kiểm tra thông tin bài báo'}</h1>
-  {done?<div className="confirmation-success"><CheckCircle2 size={36}/><p>Thông tin đã được lưu và cập nhật trên dashboard của lab. Anh/chị có thể đóng trang này.</p>{warnings.map((w,i)=><p key={i}>{w}</p>)}</div>:<>
-   <p>Trang này không yêu cầu đăng nhập hoặc mã OTP. Hệ thống đã điền những thông tin đọc được từ email. Vui lòng kiểm tra tất cả trường; ô còn thiếu được đánh dấu để bổ sung.</p>
+ const [errors,setErrors]=useState<ErrorField[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[done,setDone]=useState(false),[warnings,setWarnings]=useState<string[]>([]);
+ useEffect(()=>{let active=true;fetch('/api/paper-confirm',{headers:{Authorization:'Bearer '+token}}).then(async r=>{const data=await r.json();if(!r.ok)throw Error(data.error||'Không mở được form.');if(active){setRecord(data);setFields(data.fields);setErrors(data.errors);setDone(false)}}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[token]);
+ async function submit(e:React.FormEvent){e.preventDefault();if(!record)return;setBusy(true);setError('');try{const r=await fetch('/api/paper-confirm',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({fields,revision:record.revision})});const data=await r.json();if(!r.ok){if(data.errors){setErrors(data.errors);setError('Vui lòng bổ sung hoặc sửa các trường được đánh dấu.');return}throw Error(data.error||'Chưa gửi được form.')}setDone(true);setRecord(old=>old?{...old,revision:data.revision,confirmationSource:data.confirmationSource||'sender'}:old);setWarnings(data.warnings||[])}catch(e){setError(e instanceof Error?e.message:'Không kết nối được máy chủ.')}finally{setBusy(false)}}
+ return <main className="confirmation-page"><div className="confirmation-card"><div className="confirm-brand"><div className="brand-mark"><FlaskConical/></div><span>MMLAB / UIT</span></div><p className="eyebrow">CHỈNH SỬA BÁO CÁO PAPER</p>
+  <h1>{done?'Đã lưu thay đổi':'Kiểm tra thông tin bài báo'}</h1>
+  {done?<div className="confirmation-success"><CheckCircle2 size={36}/><p>Thông tin đã được lưu và cập nhật trên dashboard của lab. Anh/chị có thể đóng trang này.</p><button onClick={()=>setDone(false)}>Tiếp tục chỉnh sửa</button>{warnings.map((w,i)=><p key={i}>{w}</p>)}</div>:<>
+   <p>Trang này không yêu cầu đăng nhập hoặc mã OTP. Hệ thống đã điền những thông tin đọc được từ email. Báo cáo đã được ghi nhận tự động, không cần xác nhận lại. Chỉ lưu khi bạn muốn sửa hoặc bổ sung thông tin.</p>
    {record&&<p className="confirmation-meta">Mã tiếp nhận #{record.id} · Type of Report: Paper</p>}
    {error&&<p role="alert" className="login-error"><AlertCircle size={16}/> {error}</p>}
    {!record&&!error&&<p>Đang tải thông tin…</p>}
    {record&&<form onSubmit={submit} noValidate><div className="confirmation-fields">{labels.map(({key,label,hint})=>{const issue=errors.filter(e=>e.field===key);const missing=!fields[key].trim();return <label className={(missing||issue.length)?'incomplete':''} key={key}><span>{label} <b>*</b>{missing&&<small>Cần bổ sung</small>}</span>
     {key==='role'?<select aria-invalid={!!issue.length} value={fields[key]} onChange={e=>setFields({...fields,[key]:e.target.value})}><option value="">Chọn vai trò</option><option value="First author">First author</option><option value="Co-author">Co-author</option>{fields.role&&!['First author','Co-author'].includes(fields.role)&&<option value={fields.role}>{fields.role} — cần kiểm tra</option>}</select>:<textarea rows={key==='title'||key==='authors'?2:1} aria-invalid={!!issue.length} value={fields[key]} placeholder={hint} onChange={e=>setFields({...fields,[key]:e.target.value})}/>}<em>{hint}</em>{issue.map((v,i)=><strong className="field-error" key={i}>{v.reason}</strong>)}</label>})}</div>
-    <label className="confirm-checkbox"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/><span>Tôi đã kiểm tra và xác nhận thông tin trên là đúng.</span></label>
-    <button className="confirm-submit" disabled={!confirmed||busy}>{busy?'Đang lưu…':'Xác nhận & gửi'}</button>
-    <p className="confirmation-meta">Xác nhận của người gửi không thay thế việc xác minh Index/Ranking từ nguồn học thuật. Link này chỉ cấp quyền cho báo cáo trên.</p>
+    <button className="confirm-submit" disabled={busy}>{busy?'Đang lưu…':'Lưu thay đổi'}</button>
+    <p className="confirmation-meta">Index/Ranking được lưu theo thông tin khai báo. Link này chỉ cấp quyền cho báo cáo trên.</p>
    </form>}
   </>}
  </div></main>;
--- a/frontend/src/lib/research.ts
+++ b/frontend/src/lib/research.ts
@@ -17,7 +17,7 @@
 export type Category = typeof categories[number];
 export type Report = {
   taskGroup?:'strategic'|'routine'|'unassigned'; reportVersion?:number; adminEditedAt?:string; adminEditedBy?:string;
-  confirmationSource?:'admin'|'sender'; confirmedBy?:string; confirmedAt?:string; receiptIssue?: string; confirmationStatus?:'pending'|'confirmed'; id:string; date:string; memberId:number|null; type:Category; title:string; status:string; role:string; authors:string; venue:string; ranking:string; index:string|null; memberIds:number[]; source:'sample'|'gmail'; forwarded:boolean|null; gmailId?:string; issues:string[]; sourceId?:string; messageId?:string; isValid?:boolean; missingFields?:string[]; warnings?:string[]; reportPeriod?:string|null; monthlyTasks?:{done:{date:string;content:string}[]|null;planned:string[]|null}|null };
+  approvalStatus?:'approved'; approvalSource?:'automatic'; approvedAt?:string; confirmationSource?:'admin'|'sender'; confirmedBy?:string; confirmedAt?:string; receiptIssue?: string; confirmationStatus?:'pending'|'confirmed'; id:string; date:string; memberId:number|null; type:Category; title:string; status:string; role:string; authors:string; venue:string; ranking:string; index:string|null; memberIds:number[]; source:'sample'|'gmail'; forwarded:boolean|null; gmailId?:string; issues:string[]; sourceId?:string; messageId?:string; isValid?:boolean; missingFields?:string[]; warnings?:string[]; reportPeriod?:string|null; monthlyTasks?:{done:{date:string;content:string}[]|null;planned:string[]|null}|null };
 export const normalize = (v:string) => v.normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[đĐ]/g,'d').toLowerCase().replace(/[-‐‑–—\s]+/g,' ').trim();
 export function resolveMembers(text:string):number[] {
  const t=normalize(text);
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
    cli = argparse.ArgumentParser(description="Update the previous MMLab self-hosted source safely.")
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
    backup = root / '_backups' / ('auto-receipt-' + stamp)
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
    print("Next: npm ci --prefix frontend")
    print("      npm run build --prefix frontend")
    print("      python run_local.py")
    print("Use the same Python environment as before. Real mail requires MAIL_MODE=smtp.")


if __name__ == '__main__':
    main()
