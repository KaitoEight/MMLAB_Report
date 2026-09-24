import base64
import copy
import io
from datetime import datetime
from email.message import EmailMessage
from email.parser import BytesParser
from email import policy
from unittest.mock import patch
import pytest
from docx import Document
from sqlalchemy import select, update
from mail_threading import reply_headers, migrate_pending
from imap_fetch import analyze
from discussion_report import by_member
from monthly_report import compose, docx_bytes, VN
from school_statistics import summarize, declaration_breakdown
from mmlab_pipeline.members import DIRECTORY
from test_confirmation import workflow, seed
from test_monthly import paper, doc_text, scheduled, client
from test_api import login
import monthly_service as service
import store
import mailer


def test_threading_outer_headers_and_smtp_serialization(workflow, monkeypatch):
    bundle=seed()
    msg=EmailMessage();msg['From']='student@gmail.com';msg['Subject']='Fwd: Kết quả bài báo'
    msg['Message-ID']='<outer@sample.org>'
    msg['References']='<root@sample.org> <prior@sample.org>'
    msg.set_content('Type of Report: Paper\nTitle of Work: Paper Example\n---------- Forwarded message ---------\nMessage-ID: <conference@sample.org>\nSubject: unrelated title')
    event=analyze(msg.as_bytes(),'imap:mmlab@uit.edu.vn:INBOX:123:18','2026-09-24T01:00:00+00:00')
    headers=reply_headers(event['report'])
    assert headers=={'subject':'Re: Fwd: Kết quả bài báo','in_reply_to':'<outer@sample.org>',
                     'references':'<root@sample.org> <prior@sample.org> <outer@sample.org>'}
    monkeypatch.setenv('MMLAB_APP_PASSWORD','test-only')
    captured={}
    class SMTP:
        def __init__(self,*a,**k):pass
        def login(self,*a):pass
        def send_message(self,message,**kw):captured.update(message=BytesParser(policy=policy.default).parsebytes(message.as_bytes()),**kw)
        def quit(self):pass
    payload={**headers,'body':'Đã ghi nhận. Link chỉnh sửa tùy chọn.'}
    with patch.object(mailer.smtplib,'SMTP_SSL',SMTP):
        assert mailer.deliver({'id':'test-reply','recipient':'student@gmail.com','payload':payload})==('sent',None)
    actual=captured['message']
    assert str(actual['Subject'])==headers['subject']
    assert actual['References']==headers['references'] and actual['In-Reply-To']==headers['in_reply_to']
    assert captured['to_addrs']==['student@gmail.com']
    assert 'conference@' not in str(actual['References'])
    assert actual['Message-ID']!=headers['in_reply_to']


@pytest.mark.parametrize('subject,expected',[('Re: Fwd: Paper','Re: Fwd: Paper'),('FW: Paper','Re: FW: Paper'),('Tiêu đề\r\n gấp','Re: Tiêu đề gấp')])
def test_reply_subject(subject,expected):
    assert reply_headers({'subject':subject})['subject']==expected


@pytest.mark.parametrize('bad',['','garbage','<bad>','<valid@x>\r\nBcc: hidden@x','<one@x> <two@x>'])
def test_missing_or_bad_parent_does_not_thread_to_quoted_ancestor(bad):
    result=reply_headers({'messageId':bad,'replyReferences':'<ancestor@x>'})
    assert not result['in_reply_to'] and not result['references']


@pytest.mark.parametrize('status',['pending','retry','sent','unknown','failed'])
def test_pending_upgrade_never_resends_existing_mail(workflow,status):
    seed()
    with store.engine.begin() as conn:
        row=conn.execute(select(store.outbox)).mappings().one()
        old={**row['payload'],'subject':'[MMLab] Old receipt'}
        conn.execute(update(store.outbox).values(status=status,payload=old))
    migrate_pending();migrate_pending()
    with store.engine.connect() as conn:actual=conn.execute(select(store.outbox)).mappings().one()
    assert actual['status']==status and actual['attempts']==row['attempts']
    assert actual['payload']['subject']==('Re: Fwd: Paper decision' if status in ('pending','retry') else '[MMLab] Old receipt')
    assert actual['payload']['link']==old['link']


def test_discussion_roster_ownership_manual_edits_and_common_lines():
    report=compose([paper(memberIds=[1,7])],'2026-09')
    report['sections']['a1']+='\nThảo luận với Nguyễn Vinh Tiệp (Chế Quang Huy)\nCông việc chung (cần làm ngay)\nTheo dõi Nguyễn Vinh Tiệp\nBảo trì (Nguyễn Vinh Tiệp, ngoài lab)'
    report['sections']['b1']='Seminar về PPO (Chế Quang Huy)\nNghiên cứu mới (Nguyễn Vinh Tiệp)\nSeminar về PPO (Chế Quang Huy)'
    before=copy.deepcopy(report);groups=by_member(report)
    assert [v['id'] for v in groups]==list(range(1,13))+[None]
    assert len(groups[0]['done'])==1 and len(groups[6]['done'])==2
    assert groups[6]['planned']==['Seminar về PPO']
    assert 'Công việc chung (cần làm ngay)' in groups[-1]['done']
    assert 'Theo dõi Nguyễn Vinh Tiệp' in groups[-1]['done']
    assert 'Bảo trì (Nguyễn Vinh Tiệp, ngoài lab)' in groups[-1]['done']
    assert all(not groups[i]['done'] for i in (1,2,3,4,5,7,8,9,10,11))
    blob=docx_bytes(report,'discussion');doc=Document(io.BytesIO(blob))
    headings=[p.text for p in doc.paragraphs if p.style.name=='Heading 1']
    assert headings[:12]==[f"{m['id']}. {m['name']}" for m in DIRECTORY]
    text=doc_text(blob)
    assert text.count('A study of realistic video retrieval')==2
    assert text.index('1. Nguyễn Vinh Tiệp') < text.index('Đã làm') < text.index('Sẽ làm') < text.index('2. Đặng Văn Thìn')
    assert summarize(report)['metrics']['paper']['scopus']==1
    assert report==before
    report['sections']['a1']=''
    assert all(not g['done'] for g in by_member(report))


def test_exact_requested_rank_labels_and_real_counts():
    ranks=['Q1']*3+['A*']+['A']*2+['B']*4+['C']+['C-Unranked']*25
    report=compose([paper(id=str(i),title=f'Paper number {i}',ranking=rank) for i,rank in enumerate(ranks)],'2026-09')
    assert summarize(report)['a']=='Q1 3 bài, A* và A: 3 bài, Rank B: 4 bài, Rank C: 1 bài, Scopus: 25 bài.'
    small=compose([paper(id=str(i),title=f'Unranked paper {i}') for i in range(3)],'2026-09')
    assert summarize(small)['a']=='Scopus: 3 bài.'
    text=doc_text(docx_bytes(report,'school'))
    assert 'KPI bài báo: hoàn thành' not in text and 'Scopus khác' not in text and 'Trong đó:' not in text
    assert declaration_breakdown('hoàn thành 46 / 44 bài báo Scopus. Trong đó: Q1 3 bài, Scopus khác: 25 bài')=='Q1 3 bài, Scopus: 25 bài.'


def test_last_monday_frozen_discussion_uses_member_sections(scheduled):
    login(scheduled)
    draft=scheduled.get('/api/monthly/2026-09').json()
    payload={k:draft[k] for k in ('revision','strategyLabel','signatory')}
    payload['sections']={'a1':'Viết báo cáo (Chế Quang Huy)','b1':'Seminar robotics (Chế Quang Huy)'}
    assert scheduled.put('/api/monthly/2026-09',json=payload,headers={'Origin':'http://testserver'}).status_code==200
    assert service.enqueue_due(datetime(2026,9,28,9,tzinfo=VN))
    assert not service.enqueue_due(datetime(2026,9,28,10,tzinfo=VN))
    with store.engine.connect() as conn:batch=conn.execute(select(service.batches.c.payload)).scalar_one()
    text=doc_text(base64.b64decode(batch['attachments'][0]['content']))
    huy=text.split('7. Chế Quang Huy')[1].split('8. Trương Quốc Trường')[0]
    assert 'Đã làm' in huy and 'Viết báo cáo' in huy and 'Sẽ làm' in huy and 'Seminar robotics' in huy
