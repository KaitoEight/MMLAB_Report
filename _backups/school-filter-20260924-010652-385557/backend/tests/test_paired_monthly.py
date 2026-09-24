import copy
import io
from docx import Document
from sqlalchemy import select
from monthly_layout import paired_report, LAYOUT
from monthly_report import compose, docx_bytes
import monthly_service as service
from test_monthly import paper, scheduled, client, doc_text
from test_api import login


def bodies(blob):
    result = {}; key = None
    for p in Document(io.BytesIO(blob)).paragraphs:
        if p.style.name == 'Heading 1':
            key = p.text.split(':')[0];result[key] = []
        elif key and p.text.startswith('• '):
            result[key].append(p.text)
    return result


def test_mirrored_output_without_doubling_source_counts_or_status_labels():
    rows=[paper(status='Accepted'),paper(id='two',title='Another scientific article',status='Chưa rõ')]
    r=compose(rows,'2026-09')
    assert r['works']==2 and r['counts']['acceptedConference']==1
    assert r['sections']['a1']==r['sections']['a2']
    assert r['sections']['a1'].count('A study of realistic video retrieval')==1
    school=bodies(docx_bytes(r,'school'))
    assert school['Phần A.1']==school['Phần A.2']
    assert school['Phần B.1']==school['Phần B.2']
    for variant in ('school','discussion'):
        text=doc_text(docx_bytes(r,variant))
        for label in ('Accepted','Được chấp nhận','chưa rõ trạng thái','Chưa xác nhận','Phần 3'):
            assert label not in text
    assert len(bodies(docx_bytes(r,'discussion')))==2
    assert rows[0]['status']=='Accepted' and rows[1]['status']=='Chưa rõ'


def test_legacy_draft_merge_preserves_unique_tasks_and_no_duplicate_headings():
    r=compose([],'2026-09');r.pop('layoutVersion')
    r['sections'].update(a1='Công bố khoa học:\nĐược chấp nhận 1 bài báo hội nghị.\nĐược chấp nhận: Paper Alpha (Thìn)',
        a2='Công bố khoa học:\nĐược chấp nhận: Paper Alpha (Thìn)\nAccepted: Paper Beta (Huy)',
        aOther='Công bố khoa học:\nBài báo chưa rõ trạng thái: Paper Gamma (Tiệp)',
        b1='Dự định một',b2='Dự định hai',bOther='Dự định ba',recommendations='Kiến nghị cũ')
    original=copy.deepcopy(r)
    converted=paired_report(r)
    a=converted['sections']['a1']
    assert converted['sections']['a2']==a and a.count('Công bố khoa học:')==1
    assert all(a.count(s)==1 for s in ('Paper Alpha','Paper Beta','Paper Gamma'))
    assert converted['sections']['b1']==converted['sections']['b2']=='Dự định một\nDự định hai\nDự định ba'
    assert converted['sections']['recommendations']=='Kiến nghị cũ'
    assert paired_report(converted)==converted and r==original
    converted['sections']['a1']=''
    assert paired_report(converted)['sections']['a2']==''


def test_two_field_api_save_download_and_scheduled_attachments(scheduled):
    c=scheduled;login(c);r=c.get('/api/monthly/2026-09').json()
    payload={k:r[k] for k in ('revision','strategyLabel','signatory')}
    payload['sections']={'a1':'Công việc tháng trước','b1':'Kế hoạch tháng này'}
    response=c.put('/api/monthly/2026-09',json=payload,headers={'Origin':'http://testserver'})
    assert response.status_code==200,response.text
    sections=response.json()['sections']
    assert sections['a1']==sections['a2']==payload['sections']['a1']
    assert sections['b1']==sections['b2']==payload['sections']['b1']
    assert c.put('/api/monthly/2026-09',json=payload,headers={'Origin':'http://testserver'}).status_code==409
    text=doc_text(c.get('/api/monthly/2026-09/school.docx').content)
    assert text.count('Công việc tháng trước')==2 and text.count('Kế hoạch tháng này')==2
    from datetime import datetime
    from monthly_report import VN
    import base64, store
    assert service.enqueue_due(datetime(2026,9,28,9,tzinfo=VN))
    with store.engine.connect() as conn:
        outgoing=conn.execute(select(service.batches.c.payload)).scalar_one()
    text=doc_text(base64.b64decode(outgoing['attachments'][1]['content']))
    assert text.count('Công việc tháng trước')==2
    # Clearing A must also clear its mirrored A.2, not restore an earlier copy.
    payload.update(revision=response.json()['revision'],sections={'a1':'','b1':'Kế hoạch mới'})
    cleared=c.put('/api/monthly/2026-09',json=payload,headers={'Origin':'http://testserver'}).json()
    assert cleared['sections']['a1']==cleared['sections']['a2']==''
