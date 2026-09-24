# -*- coding: utf-8 -*-
"""MMLab: complete discussion report, filtered school report.

Apply AFTER update_mmlab_form_ab.py (the previous two-field form update).
Place this file beside run_local.py, stop the app, and run:
    python update_mmlab_school_filter.py
    npm run build --prefix frontend
    python run_local.py
Then refresh the browser. For an older saved draft, use Tong hop lai / Luu
if you want to regenerate its content from source emails instead of retaining edits.

Discussion: every done/planned task, including seminars, awards, teaching and
other activities. An unresolved sender is identified by source, not credited as
a lab member. Unmatched quotation marks no longer discard monthly task text.

School: only publication, doctoral study (NCS), and research-project content.
Done -> A.1 and A.2; Planned -> B.1 and B.2. Both pairs repeat identical bodies.
The full discussion draft is preserved; filtering is a separate export projection.
Recognized topic headings and keywords classify editable text; when adding a
brief item manually, explicit labels such as KPI bai bao / KPI NCS / De tai NCKH
(with Vietnamese accents in the actual form) identify its intended category.
Doctoral seminars remain NCS milestones; general lab seminars stay in discussion.

The university instructions/section headings follow the supplied 2021-2030 form.
This does not verify the institutional plan or invent completion percentages,
annual targets, outcomes or example numbers (46/44, 04 NCS, etc.). User-entered
numbers remain declarations. Source publication status is never auto-converted
to Accepted. Report/receipt approval remains automatic as in the previous update.

This script performs no network calls and sends no emails. It backs up source
files under _backups, guards checksums, and does not touch .env, credentials or
stored reports. Use --check to check compatibility without changing any files.
The source diff below is readable, not an encoded archive.
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

MANIFEST = {'backend/monthly_assembly.py': {'before': '406cb9145a5686a36b0873f32313ac2af3654a9cf44501c4da00a10c2adf7b5e', 'after': '8d4333884ae14d25b9bb68ee7ac2e2c11f882160556018c36372f6baaac74c15'}, 'backend/monthly_report.py': {'before': 'a506b9c6232148a553f958c42d07cd40719de70ccb1169b9618f0e2e32ed7275', 'after': '6d224b5a9fa1f456c388ca2cf8565c5cef707375f5a5f7d82d6378280ab8d3dd'}, 'backend/monthly_service.py': {'before': '484f86c64eef8091bbaa22d6478050839c2954a297839a7a9bd0d3ebe847c5ce', 'after': '5718bce377ac2baded35513a566ca9285c3076dd08ee91fe6def9a6540e49bcb'}, 'backend/school_report.py': {'before': None, 'after': '117efa6bd41820fcf7e236e96f05fc162f9fd10ff578cd1590e7ec5ac94e3d07'}, 'backend/tests/test_monthly.py': {'before': '54323ce9c62666d6a3b7e2b0c3255914d2c038b337ce436c67b0ce33dde7edea', 'after': '3bb17a6f4d8629f854f16317fd69b3db8ca00788890ba8c857bc2b9ecddbe6f5'}, 'backend/tests/test_paired_monthly.py': {'before': '1e18d2a68d2e9ab48f2e22a12dbe9ef8e22733581b9a2acd1b2c04d04f99c1ed', 'after': 'db9ebb43a9ed4acf95c7f15759cda7948800240ed19610f4dc514640410b9b71'}, 'backend/tests/test_school_filter.py': {'before': None, 'after': 'f330e2e4cdd15a9d180e81e12a32e53cb0776d5b4677e336537a9c599b915242'}, 'backend/tests/test_task_assembly.py': {'before': '76dd01ef0745f709e159fd069dbd2d9f12a1d51419174c6cd6dda28b8f813224', 'after': '9adcb443c308b573d293e8bb90ffa9a83b2b0408d088e7db423859a87c271674'}, 'frontend/src/MonthlyReports.tsx': {'before': '4a087bf6cf6253903ebd72aef8455843afbeb279b5c71e9872ea885b2688b461', 'after': '922a2d3b42c9394778c7baac0dc13f964fd031500ac6f741f60e6bf9250925bd'}}

PATCH = r'''--- a/backend/monthly_assembly.py
+++ b/backend/monthly_assembly.py
@@ -9,6 +9,8 @@
 
 
 def topic(text, kind=None):
+    if kind in ('Paper','NCS','Đề tài'):
+        return {'Paper':TOPICS[0],'NCS':TOPICS[2],'Đề tài':TOPICS[1]}[kind]
     value=fold(text)
     if kind=='Giải thưởng' or re.search(r'\b(?:giai [123]|giai thuong|best paper award)\b',value):return TOPICS[4]
     if not kind and re.search(r'huong dan sinh vien|giang day|khoa luan',value):return TOPICS[5]
@@ -37,14 +39,13 @@
             for phase,field in [('a','done'),('b','planned')]:
                 for task in repair_tasks(tasks.get(field),join_wrapped=r.get('monthlyTasksVersion')!=2):
                     text=format_task(task)
-                    if not names or incomplete(text):
-                        reason='Chưa đối chiếu được người gửi với danh sách lab' if not names else 'Nội dung có dấu hiệu bị cắt, cần đọc lại email gốc'
-                        review.append(f"{reason}. Nguồn: {r.get('sender') or names or r['id']}. Nội dung: {text}")
-                        continue
-                    ident=(phase,tuple(sorted(member_ids)),task['date'],task['content'].casefold().rstrip(' .;'))
+                    if not names:
+                        review.append(f"Chưa đối chiếu được người gửi với danh sách lab. Nguồn: {r.get('sender') or r['id']}. Nội dung: {text}")
+                    ident=(phase,tuple(sorted(member_ids)) if names else (r.get('sender') or r['id'],),task['date'],task['content'].casefold().rstrip(' .;'))
                     if ident in seen_tasks:continue
                     seen_tasks.add(ident)
-                    entries[phase+group].append((topic(task['content']),f'{text} ({names})'))
+                    attribution=names or ('Nguồn: '+(r.get('sender') or r['id']))
+                    entries[phase+group].append((topic(task['content']),f'{text} ({attribution})'))
             continue
         key=work_key(r)
         if key in seen:continue
--- a/backend/monthly_report.py
+++ b/backend/monthly_report.py
@@ -9,6 +9,7 @@
 from mmlab_pipeline.members import fold
 from monthly_assembly import assemble, TOPICS
 from monthly_layout import paired_report, LAYOUT
+from school_report import school_projection
 
 VN=timezone(timedelta(hours=7))
 SECTIONS=('a1','a2','aOther','b1','b2','bOther','recommendations')
@@ -43,7 +44,7 @@
 
 def docx_bytes(report, variant):
     if variant not in ('discussion','school'):raise ValueError('Unknown report variant')
-    report=paired_report(report)
+    report=school_projection(report) if variant=='school' else paired_report(report)
     if report['strategyLabel']=='KHCL Trường giai đoạn 2021-2025':report['strategyLabel']=DEFAULT_STRATEGY
     doc=Document(); sec=doc.sections[0]
     sec.page_width=Cm(21);sec.page_height=Cm(29.7)
@@ -77,8 +78,13 @@
     def section(key,title):
         if template and key=='b1' and variant=='discussion':doc.add_page_break()
         doc.add_heading(title,level=1)
-        if key in ('a1','b1','b2'):
-            paragraph(PLAN_REFERENCE)
+        if variant=='school':
+            if key in ('a1','a2'):
+                paragraph('Với mỗi nhiệm vụ, cho biết kết quả thực hiện, đánh giá chất lượng, % hoàn thành, lý do chưa hoàn thành. Xin tham khảo kế hoạch đã xây dựng trong tháng trước.')
+            if key=='a1':
+                paragraph('Đề nghị phần này CHỈ báo cáo những nội dung KHCL nào có trong Kế hoạch tại https://link.uit.edu.vn/KH2026, báo cáo ngắn gọn 1–2 dòng.')
+            if key in ('b1','b2'):
+                paragraph('Lưu ý đối chiếu với Kế hoạch Trường 2026 đã xây dựng tại https://link.uit.edu.vn/KH2026')
         text=report['sections'].get(key,'').strip()
         for line in text.splitlines() if text else ['…' if template else 'Chưa có nội dung được ghi nhận.']:
             if line.rstrip(':') in TOPICS:
@@ -90,8 +96,8 @@
                     p.paragraph_format.first_line_indent=Cm(-.35)
                     p.runs[0].text='• '+line
     if variant=='school':
-        section('a1',f"Phần A.1: Tình hình thực hiện nhiệm vụ phục vụ {report['strategyLabel']} trong tháng trước")
-        section('a2','Phần A.2: Tình hình thực hiện nhiệm vụ thường xuyên và đột xuất trong tháng trước')
+        section('a1',f"Phần A.1: Báo cáo tình hình thực hiện nhiệm vụ phục vụ {report['strategyLabel']} trong tháng trước")
+        section('a2','Phần A.2: Báo cáo tình hình thực hiện nhiệm vụ thường xuyên và đột xuất khác trong tháng trước')
         section('b1',f"Phần B.1: Kế hoạch công tác các nhiệm vụ phục vụ {report['strategyLabel']} trong tháng này")
         section('b2','Phần B.2: Kế hoạch công tác các nhiệm vụ thường xuyên và đột xuất trong tháng này')
     else:
@@ -108,7 +114,7 @@
 def blank_template(variant):
     report=compose([], '2026-09')
     report['isTemplate']=True
-    done=['Tên công trình hoặc nội dung công việc; kết quả; người thực hiện.']
-    plans=['Nội dung công việc dự kiến; thời gian; người thực hiện.']
+    done=['KPI bài báo: …','KPI NCS: …','Đề tài NCKH: …']
+    plans=['KPI bài báo: …','KPI NCS: …','Đề tài NCKH: …']
     report['sections'].update(a1='\n'.join(done),a2='\n'.join(done),b1='\n'.join(plans),b2='\n'.join(plans),recommendations='…')
     return docx_bytes(report,variant)
--- a/backend/monthly_service.py
+++ b/backend/monthly_service.py
@@ -90,7 +90,7 @@
         attachments=[{'name':f'mmlab-{report["planPeriod"]}-{variant}.docx','content':base64.b64encode(docx_bytes(report,variant)).decode(),
                       'subtype':'vnd.openxmlformats-officedocument.wordprocessingml.document'} for variant in ('discussion','school')]
         payload={'subject':f'[MMLab] Báo cáo thảo luận và kế hoạch tháng {report["planPeriod"]}',
-                 'body':f'Kính gửi các thành viên MMLab,\n\nĐính kèm hai bản báo cáo:\n1. Bản thảo luận: công việc đã thực hiện tháng {period} và kế hoạch tháng {report["planPeriod"]}.\n2. Bản báo cáo nộp trường: A.1 = A.2, B.1 = B.2; đơn vị mã 6, chiến lược 2021–2030.\n\nVui lòng trao đổi về kết quả và kế hoạch công việc.\n\nTrân trọng,\nMMLab — UIT',
+                 'body':f'Kính gửi các thành viên MMLab,\n\nĐính kèm hai bản báo cáo:\n1. Bản thảo luận: công việc đã thực hiện tháng {period} và kế hoạch tháng {report["planPeriod"]}.\n2. Bản báo cáo nộp trường: chỉ bài báo, NCS và đề tài; Đã ở A.1 = A.2, Sẽ ở B.1 = B.2; đơn vị mã 6, chiến lược 2021–2030.\n\nVui lòng trao đổi về kết quả và kế hoạch công việc.\n\nTrân trọng,\nMMLab — UIT',
                  'attachments':attachments}
         conn.execute(store.insert(batches).values(period=period,payload=payload,created_at=now.isoformat()))
         assert len(DIRECTORY)==12 and len({m['email'] for m in DIRECTORY})==12
--- a/backend/school_report.py
+++ b/backend/school_report.py
@@ -0,0 +1,84 @@
+"""School report projection: publication, doctoral study and research projects only.
+
+The discussion draft remains the complete source. This projection never changes
+publication status, invents targets or interprets receipt approval as acceptance.
+"""
+import re
+from mmlab_pipeline.members import fold
+from monthly_layout import paired_report
+from monthly_assembly import TOPICS
+
+LABELS = {'paper': 'KPI bài báo', 'ncs': 'KPI NCS', 'project': 'Đề tài NCKH'}
+HEADINGS = {fold(TOPICS[0]): 'paper', fold(TOPICS[1]): 'project',
+            fold(TOPICS[2]): 'education',
+            **{fold(t): 'other' for t in TOPICS[3:]},
+            'kpi bai bao': 'paper', 'bai bao': 'paper', 'paper': 'paper',
+            'kpi ncs': 'ncs', 'ncs': 'ncs', 'de tai nckh': 'project', 'de tai': 'project'}
+NCS = re.compile(r'\b(?:ncs|phd|nghien cuu sinh|tieu luan tong quan|tltq|chuyen de [123]|cd [123])\b')
+PROJECT = re.compile(r'\bde tai\b|\bnafosted\b')
+PAPER = re.compile(r'\b(?:paper|bai bao|journal|tap chi|scopus|isi|camera.ready|rebuttal|resubmit)\b|\b(?:nop|submit)\s+(?:\d+\s+)?bai\b')
+OTHER = re.compile(r'\b(?:giang day|huong dan sinh vien|khoa luan|luan van thac si|best paper award|giai thuong|dat giai|tham du hoi nghi)\b')
+
+
+def category(text, heading=None):
+    value = fold(text)
+    # Such tasks stay in discussion; no lab member was resolved from their source.
+    if re.search(r'\(nguon: [^\n]+\)\s*$', value):
+        return None
+    # Explicit report kinds outrank keywords inside a title.
+    if re.match(r'^(?:seminar|giai thuong)\s*:', value):
+        return None
+    for prefix, kind in [('paper', 'paper'), ('ncs', 'ncs'), ('de tai', 'project'),
+                         ('kpi bai bao', 'paper'), ('kpi ncs', 'ncs'), ('de tai nckh', 'project')]:
+        if re.match(r'^' + prefix + r'\s*:', value):
+            return kind
+    if heading in ('paper','project','ncs'):
+        return heading
+    if OTHER.search(value):
+        return None
+    # Doctoral seminars are a doctoral milestone, not a general lab seminar.
+    if NCS.search(value):
+        return 'ncs'
+    if PROJECT.search(value):
+        return 'project'
+    if re.search(r'\bseminar\b', value):
+        return None
+    if PAPER.search(value):
+        return 'paper'
+    return None
+
+
+def filtered_body(body):
+    """Use headings as context, then emit only permitted content as short bullets."""
+    grouped = {key: [] for key in LABELS}
+    seen = set()
+    heading = None
+    for raw in body.splitlines():
+        text = re.sub(r'^\s*[-*•+]\s*', '', raw).strip()
+        if not text:
+            continue
+        normalized = fold(text.rstrip(':').strip())
+        if normalized in HEADINGS:
+            heading = HEADINGS[normalized]
+            continue
+        if text.endswith(':'):
+            heading = None
+            continue
+        kind = category(text, heading)
+        if not kind:
+            continue
+        # Existing KPI declarations are kept verbatim, including supplied numbers.
+        text = re.sub(r'^(?:KPI bài báo|KPI NCS|Đề tài NCKH|Paper|NCS|Đề tài)\s*:\s*', '', text, flags=re.I)
+        identity = (kind, text.casefold())
+        if identity not in seen:
+            seen.add(identity)
+            grouped[kind].append(text)
+    return '\n'.join(f'{LABELS[kind]}: {text}' for kind in LABELS for text in grouped[kind])
+
+
+def school_projection(report):
+    result = paired_report(report)
+    for phase in ('a', 'b'):
+        text = filtered_body(result['sections'][phase + '1'])
+        result['sections'][phase + '1'] = result['sections'][phase + '2'] = text
+    return result
--- a/backend/tests/test_monthly.py
+++ b/backend/tests/test_monthly.py
@@ -78,7 +78,7 @@
 
 
 def test_docx_variants_and_blank_dates():
-    r=compose([],'2026-12');r['sections'].update(a1='ĐÃ-HOÀN-TẤT',b1='SẼ-THỰC-HIỆN')
+    r=compose([],'2026-12');r['sections'].update(a1='KPI bài báo: ĐÃ-HOÀN-TẤT',b1='KPI bài báo: SẼ-THỰC-HIỆN')
     discussion=doc_text(docx_bytes(r,'discussion'));school=doc_text(docx_bytes(r,'school'))
     assert 'ĐÃ-HOÀN-TẤT' in discussion and 'ĐÃ-HOÀN-TẤT' in school
     assert 'Phần A.1' in school and 'Phần A.2' in school and 'SẼ-THỰC-HIỆN' in school and 'THÁNG 01/2027' in school
@@ -141,7 +141,7 @@
     assert c.get('/api/monthly/2026-09/school.docx').status_code==401
     login(c);assert c.get('/api/monthly/2026-99').status_code==422
     r=c.get('/api/monthly/2026-09').json()
-    body={k:r[k] for k in ('revision','strategyLabel','signatory','sections')};body['sections']['b1']='Sẽ báo cáo seminar đã thống nhất'
+    body={k:r[k] for k in ('revision','strategyLabel','signatory','sections')};body['sections']['b1']='NCS sẽ báo cáo chuyên đề 3'
     assert c.put('/api/monthly/2026-09',json=body).status_code==403
     assert c.put('/api/monthly/2026-09',json=body,headers={'Origin':'http://testserver'}).status_code==200
     assert c.put('/api/monthly/2026-09',json=body,headers={'Origin':'http://testserver'}).status_code==409
--- a/backend/tests/test_paired_monthly.py
+++ b/backend/tests/test_paired_monthly.py
@@ -57,7 +57,7 @@
 def test_two_field_api_save_download_and_scheduled_attachments(scheduled):
     c=scheduled;login(c);r=c.get('/api/monthly/2026-09').json()
     payload={k:r[k] for k in ('revision','strategyLabel','signatory')}
-    payload['sections']={'a1':'Công việc tháng trước','b1':'Kế hoạch tháng này'}
+    payload['sections']={'a1':'KPI bài báo: Công việc tháng trước','b1':'KPI NCS: Kế hoạch tháng này'}
     response=c.put('/api/monthly/2026-09',json=payload,headers={'Origin':'http://testserver'})
     assert response.status_code==200,response.text
     sections=response.json()['sections']
@@ -65,7 +65,7 @@
     assert sections['b1']==sections['b2']==payload['sections']['b1']
     assert c.put('/api/monthly/2026-09',json=payload,headers={'Origin':'http://testserver'}).status_code==409
     text=doc_text(c.get('/api/monthly/2026-09/school.docx').content)
-    assert text.count('Công việc tháng trước')==2 and text.count('Kế hoạch tháng này')==2
+    assert text.count('KPI bài báo: Công việc tháng trước')==2 and text.count('KPI NCS: Kế hoạch tháng này')==2
     from datetime import datetime
     from monthly_report import VN
     import base64, store
@@ -73,7 +73,7 @@
     with store.engine.connect() as conn:
         outgoing=conn.execute(select(service.batches.c.payload)).scalar_one()
     text=doc_text(base64.b64decode(outgoing['attachments'][1]['content']))
-    assert text.count('Công việc tháng trước')==2
+    assert text.count('KPI bài báo: Công việc tháng trước')==2
     # Clearing A must also clear its mirrored A.2, not restore an earlier copy.
     payload.update(revision=response.json()['revision'],sections={'a1':'','b1':'Kế hoạch mới'})
     cleared=c.put('/api/monthly/2026-09',json=payload,headers={'Origin':'http://testserver'}).json()
--- a/backend/tests/test_school_filter.py
+++ b/backend/tests/test_school_filter.py
@@ -0,0 +1,78 @@
+import copy
+from monthly_report import compose, docx_bytes
+from monthly_assembly import TOPICS
+from school_report import filtered_body, school_projection
+from test_monthly import paper, doc_text
+from test_paired_monthly import bodies
+
+
+def test_discussion_keeps_all_tasks_school_only_three_categories():
+    r=paper(type='Báo cáo tháng',monthlyTasksVersion=2,monthlyTasks={
+        'done':[{'date':'','content':t} for t in [
+            'Nộp 02 bài báo tạp chí Q1','NCS hoàn thành chuyên đề 3',
+            'Nghiệm thu 2 đề tài D1','Seminar về robotics',
+            'Đạt giải Best Paper Award','Hướng dẫn sinh viên thực hiện khóa luận',
+            'Hoàn thành cuốn luận văn thạc sĩ','Bảo trì máy chủ']],
+        'planned':['Nộp 05 bài tạp chí Q1, 06 bài báo hội nghị',
+                   'Chuẩn bị nộp 02 hồ sơ NCS','Nghiệm thu 2 đề tài D1',
+                   'Seminar về PPO và GRPO','Tham gia cuộc thi NLP','Giảng dạy ở khoa KHMT']})
+    report=compose([r],'2026-09');original=copy.deepcopy(report)
+    discussion=doc_text(docx_bytes(report,'discussion'));school=doc_text(docx_bytes(report,'school'))
+    for value in ('robotics','Best Paper Award','khóa luận','luận văn thạc sĩ','Bảo trì máy chủ','PPO và GRPO','cuộc thi NLP','Giảng dạy'):
+        assert value in discussion and value not in school,value
+    for value in ('Nộp 02 bài báo','chuyên đề 3','Nghiệm thu 2 đề tài','Nộp 05 bài','02 hồ sơ NCS'):
+        assert value in discussion and value in school,value
+    blocks=bodies(docx_bytes(report,'school'))
+    assert blocks['Phần A.1']==blocks['Phần A.2']
+    assert blocks['Phần B.1']==blocks['Phần B.2']
+    assert 'Nộp 05 bài' not in '\n'.join(blocks['Phần A.1'])
+    assert 'Nộp 02 bài' not in '\n'.join(blocks['Phần B.1'])
+    assert report==original
+
+
+def test_manual_example_values_remain_declarations_not_hardcoded_defaults():
+    text='* KPI bài báo: hoàn thành 46 / 44 bài báo Scopus. Trong đó: Q1 3 bài, A* và A: 3 bài\n* KPI NCS: mới được công nhận thêm 04 NCS\n* 01 NCS đã báo cáo xong chuyên đề 3.\n* Nghiệm thu 2 đề tài D1\n* Hướng dẫn sinh viên và giảng dạy'
+    filtered=filtered_body(text)
+    assert '46 / 44' in filtered and '04 NCS' in filtered and '01 NCS' in filtered
+    assert 'Hướng dẫn' not in filtered and 'KPI bài báo: KPI bài báo:' not in filtered
+    empty=doc_text(docx_bytes(compose([],'2026-09'),'school'))
+    assert '46 / 44' not in empty and '04 NCS' not in empty
+
+
+def test_editable_text_filter_does_not_depend_on_stale_assembly_counts():
+    report=compose([paper()],'2026-09')
+    report['sections']['a1']='KPI NCS: 03 NCS được công nhận\nGiảng dạy tại khoa KHMT'
+    result=school_projection(report)
+    assert '03 NCS' in result['sections']['a1']
+    assert 'A study of realistic' not in result['sections']['a1']
+    assert 'Giảng dạy' not in result['sections']['a1']
+    report['sections']['a1']=''
+    assert school_projection(report)['sections']['a2']==''
+
+
+def test_monthly_unmatched_quote_is_kept_in_discussion_and_unmapped_not_credited():
+    known=paper(id='known',type='Báo cáo tháng',monthlyTasksVersion=2,monthlyTasks={
+        'done':None,'planned':['Seminar về công cụ "The Research Assistant']})
+    unknown=paper(id='unknown',type='Báo cáo tháng',memberIds=[],sender='outside@example.com',monthlyTasksVersion=2,monthlyTasks={
+        'done':[{'date':'','content':'Nộp 10 bài báo Scopus'}],'planned':['Nộp 05 hồ sơ NCS']})
+    report=compose([known,unknown],'2026-09')
+    discussion=doc_text(docx_bytes(report,'discussion'));school=doc_text(docx_bytes(report,'school'))
+    assert 'The Research Assistant' in discussion
+    assert 'outside@example.com' in discussion and '10 bài báo' in discussion
+    assert 'outside@example.com' not in school and '10 bài báo' not in school and '05 hồ sơ' not in school
+    assert unknown['memberIds']==[]
+
+
+def test_structured_paper_title_is_not_recategorized_by_keyword():
+    r=paper(title='Seminar Scheduling and Best Paper Award Prediction',status='Chưa rõ')
+    report=compose([r],'2026-09')
+    assert r['title'] in school_projection(report)['sections']['a1']
+    assert 'Accepted' not in doc_text(docx_bytes(report,'school'))
+    assert report['counts']['acceptedConference']==0
+
+
+def test_doctoral_seminar_allowed_but_general_seminar_excluded():
+    text=TOPICS[3]+':\nBáo cáo seminar trong chương trình NCS\nSeminar về Robotics\n'+TOPICS[2]+':\nHoàn thành luận văn thạc sĩ\nChuẩn bị hồ sơ PhD'
+    result=filtered_body(text)
+    assert 'chương trình NCS' in result and 'hồ sơ PhD' in result
+    assert 'Robotics' not in result and 'luận văn thạc sĩ' not in result
--- a/backend/tests/test_task_assembly.py
+++ b/backend/tests/test_task_assembly.py
@@ -59,11 +59,12 @@
     result=compose([unknown,known],'2026-09')
     assert len(result['reviewNotes'])==1
     texts={v:'\n'.join(p.text for p in Document(io.BytesIO(docx_bytes(result,v))).paragraphs) for v in ('discussion','school')}
-    assert 'unknown@example.com' not in texts['discussion'] and 'unknown@example.com' not in texts['school']
-    assert 'Phần A.1' in texts['school'] and 'Robotics' in texts['school']
+    assert 'unknown@example.com' in texts['discussion'] and 'unknown@example.com' not in texts['school']
+    assert 'Phần A.1' in texts['school'] and 'Robotics' not in texts['school']
+    assert 'Robotics' in texts['discussion'] and 'Đi học PhD' in texts['school']
     assert 'Chưa có nội dung báo cáo' not in texts['school']
     assert 'chưa phân nhóm' not in texts['school']
-    assert 'Seminar và hội nghị' in texts['school']
+    assert 'Seminar và hội nghị' not in texts['school']
 
 
 def test_no_paper_status_inferred_from_monthly_manuscript_or_revision():
--- a/frontend/src/MonthlyReports.tsx
+++ b/frontend/src/MonthlyReports.tsx
@@ -2,7 +2,7 @@
 import {readApiResponse} from '@/lib/api';
 import {Button} from '@/components/ui/button';
 type Draft={period:string;planPeriod:string;revision:number;strategyLabel:string;signatory:string;sections:Record<string,string>;records:number;counts:Record<string,number>;reviewNotes?:string[];assemblyVersion?:number;customized?:boolean};
-const labels:Record<string,string>={a1:'Phần A · Công việc đã thực hiện (A.1 = A.2)',b1:'Phần B · Kế hoạch công việc (B.1 = B.2)'};
+const labels:Record<string,string>={a1:'Phần A · Toàn bộ công việc đã thực hiện',b1:'Phần B · Toàn bộ kế hoạch công việc'};
 export default function MonthlyReports(){
  const [period,setPeriod]=useState(new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit'}).format(new Date()));
  const [draft,setDraft]=useState<Draft|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[dirty,setDirty]=useState(false);
@@ -14,8 +14,8 @@
  return <section className="monthly-workspace"><div className="monthly-toolbar"><label>Tháng tổng hợp <input aria-label="Tháng tổng hợp" type="month" value={period} onChange={e=>{if(e.target.value&&(!dirty||window.confirm('Bỏ thay đổi chưa lưu và đổi tháng?')))setPeriod(e.target.value)}}/></label><Button variant="outline" onClick={()=>void refresh()}>Tổng hợp lại</Button><Button onClick={()=>void save()} disabled={!draft||busy||!dirty}>{busy?'Đang lưu…':'Lưu báo cáo'}</Button></div>
  <p className="monthly-schedule">Hai bản được gửi đến 12 thành viên lúc 09:00 thứ Hai cuối cùng mỗi tháng. Lịch tiếp theo: {next||'Đang tải…'}.</p>
  {error&&<p className="login-error" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
- {draft&&<>{draft.customized&&(!draft.assemblyVersion||draft.assemblyVersion<2)&&<p className="editor-hint">Đây là bản đã lưu bằng cách tổng hợp cũ. Bấm Tổng hợp lại để nối dòng và gộp mục trùng; kiểm tra nội dung trước khi lưu.</p>}<div className="monthly-downloads"><div><h2>Bản thảo luận · Đã và Sẽ</h2><p>Kết quả tháng {period}; kế hoạch tháng {draft.planPeriod}.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/discussion.docx`}>Tải Word</a></div><div><h2>Bản nộp trường · A và B</h2><p>Báo cáo tháng {draft.planPeriod}: A.1 = A.2, B.1 = B.2. Mã đơn vị: 6.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/school.docx`}>Tải Word</a></div></div>{dirty&&<p className="editor-hint">Lưu thay đổi trước khi tải Word.</p>}
- <p>Nhập nội dung một lần cho mỗi phần. Khi xuất, A.1 được chép sang A.2 và B.1 được chép sang B.2.</p>
+ {draft&&<>{draft.customized&&(!draft.assemblyVersion||draft.assemblyVersion<2)&&<p className="editor-hint">Đây là bản đã lưu bằng cách tổng hợp cũ. Bấm Tổng hợp lại để nối dòng và gộp mục trùng; kiểm tra nội dung trước khi lưu.</p>}<div className="monthly-downloads"><div><h2>Bản thảo luận · Đã và Sẽ</h2><p>Toàn bộ Đã tháng {period} và Sẽ tháng {draft.planPeriod}, gồm tất cả nhóm công việc.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/discussion.docx`}>Tải Word</a></div><div><h2>Bản nộp trường · A và B</h2><p>Chỉ bài báo, NCS và đề tài. Đã → A.1/A.2; Sẽ → B.1/B.2. Mã đơn vị: 6.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/school.docx`}>Tải Word</a></div></div>{dirty&&<p className="editor-hint">Lưu thay đổi trước khi tải Word.</p>}
+ <p>Nhập đầy đủ Đã và Sẽ ở hai ô dưới. Bản thảo luận giữ toàn bộ nội dung. Bản nộp trường tự lọc bài báo, NCS, đề tài và chép A.1 sang A.2, B.1 sang B.2.</p>
  {Object.entries(labels).map(([key,label])=><label className="monthly-section" key={key}><strong>{label}</strong><textarea rows={Math.min(12,Math.max(3,(draft.sections[key]||'').split('\n').length+1))} value={draft.sections[key]||''} onChange={e=>{setDraft({...draft,sections:{...draft.sections,[key]:e.target.value,[key==='a1'?'a2':'b2']:e.target.value}});setDirty(true)}}/></label>)}
  </>}
  </section>
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
    cli = argparse.ArgumentParser(description="Update the MMLab school filtering after the two-field monthly form update.")
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
    backup = root / '_backups' / ('school-filter-' + stamp)
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
    print("Restart the app using the same Python environment as before, then refresh the page.")


if __name__ == '__main__':
    main()
