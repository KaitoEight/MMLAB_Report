import base64
import copy
from datetime import datetime
from sqlalchemy import select
from school_statistics import summarize
from school_report import with_statistics
from monthly_report import compose, docx_bytes, VN
from test_monthly import paper, doc_text, scheduled, client
from test_paired_monthly import bodies
from test_api import login
import monthly_service as service
import store


def task_report(done=(), planned=(), **kw):
    return paper(type='Báo cáo tháng',monthlyTasksVersion=2,monthlyTasks={
        'done':[{'date':'','content':v} for v in done],'planned':list(planned)},**kw)


def test_actual_46_papers_partition_without_double_counting_authors():
    ranks=['Q1']*3+['A*']+['A']*2+['B']*4+['C']+['Q2']*10+['C-Unranked']*25
    rows=[paper(id=str(i),title=f'Unique scientific work {i}',ranking=rank,status='Chưa rõ') for i,rank in enumerate(ranks)]
    rows.append(paper(id='duplicate',title=rows[0]['title'],ranking='Q1',memberIds=[1],venue='MAPR2026'))
    rows += [paper(id='external',title='Outside lab paper',memberIds=[]),paper(id='deleted',title='Deleted paper',deletedAt='2026-09-01')]
    r=compose(rows,'2026-09');r['scopusTarget']=44
    result=summarize(r);counts=result['metrics']['paper']
    assert counts['scopus']==46 and sum(counts['ranks'].values())==46
    assert counts['ranks']=={'Q1':3,'A* và A':3,'Rank B':4,'Rank C':1,'Q2':10,'Scopus khác':25}
    assert '46 / 44' in result['a'] and len(result['a'].splitlines())==1
    assert 'Unique scientific work' not in result['a'] and 'Chế Quang Huy' not in result['a']
    assert rows[0]['status']=='Chưa rõ'  # Receipt approval must not rewrite publication status.


def test_exact_short_sample_pattern_for_done_and_planned():
    r=compose([paper(ranking='Q1'),task_report(
        ['Mới được công nhận thêm 04 NCS','01 NCS đã báo cáo xong chuyên đề 3','Nghiệm thu 2 đề tài D1'],
        ['Nộp 05 bài tạp chí Q1, 06 bài báo hội nghị','Chuẩn bị nộp 02 hồ sơ NCS','Nghiệm thu 2 đề tài D1'],id='tasks')],'2026-09')
    r['scopusTarget']=44;s=summarize(r)
    assert s['a'].splitlines()==[
        'KPI bài báo: hoàn thành 1 / 44 bài báo Scopus. Trong đó: Q1: 1 bài.',
        'KPI NCS: mới được công nhận thêm 04 NCS.',
        '01 NCS đã báo cáo xong chuyên đề 3.',
        'Nghiệm thu 2 đề tài D1.']
    assert s['b'].splitlines()==[
        'KPI bài báo: nộp 05 bài tạp chí Q1, 06 bài báo hội nghị.',
        'KPI NCS: chuẩn bị nộp 02 hồ sơ NCS.',
        'Nghiệm thu 2 đề tài D1.']
    original=copy.deepcopy(r);blocks=bodies(docx_bytes(r,'school'))
    assert blocks['Phần A.1']==blocks['Phần A.2'] and len(blocks['Phần A.1'])==4
    assert blocks['Phần B.1']==blocks['Phần B.2'] and len(blocks['Phần B.1'])==3
    assert 'A study of realistic video retrieval' in doc_text(docx_bytes(r,'discussion'))
    assert r==original


def test_dates_stage_numbers_and_project_codes_are_not_quantities():
    r=compose([task_report(['24/09/2026, 01 NCS đã báo cáo xong chuyên đề 3','25/09/2026, Nghiệm thu 02 đề tài D1'])],'2026-09')
    s=summarize(r)
    assert '01 NCS' in s['a'] and 'Nghiệm thu 2 đề tài D1' in s['a']
    assert all(v['count'] in (1,2) for v in s['metrics']['a'])


def test_preparing_and_negated_events_never_become_done_results():
    r=compose([task_report(['Chuẩn bị nộp 02 hồ sơ NCS','Chưa nghiệm thu 2 đề tài D1',
        'Nộp hồ sơ nghiệm thu 2 đề tài D1','Dự kiến báo cáo chuyên đề 3 của 01 NCS',
        'Không được công nhận 04 NCS','Đang thực hiện đề tài D1'])],'2026-09')
    s=summarize(r)
    assert not s['metrics']['a'] and not s['a']
    assert len(doc_text(docx_bytes(r,'discussion')))>0


def test_missing_quantity_not_invented_and_no_default_target():
    r=compose([task_report([],['Chuẩn bị nộp các hồ sơ NCS','Nộp nhiều bài báo Q1','Tiếp tục thực hiện nghiên cứu'])],'2026-09')
    s=summarize(r)
    assert not s['metrics']['b'] and not s['b'] and s['notes']
    assert s['metrics']['scopusTarget'] is None
    assert '/ 44' not in doc_text(docx_bytes(r,'school'))


def test_year_scope_uses_receipt_year_and_excludes_future_deleted_and_outsiders():
    rows=[paper(id='past',title='Prior month paper',date='2026-01-01'),
        paper(id='duplicate',title='Prior month paper',date='2026-09-02'),
        paper(id='now',title='Current paper',date='2026-09-02'),
        paper(id='old',title='Old year',date='2025-12-01'),
        paper(id='future',title='Future',date='2026-10-01'),
        paper(id='outside',title='Outside',date='2026-08-01',memberIds=[]),
        paper(id='removed',title='Removed',date='2026-02-01',deletedAt='2026-09-01')]
    r=compose(rows,'2026-09');r.update(paperScope='year',scopusTarget=44)
    s=summarize(r)
    assert s['metrics']['paper']['scopus']==2 and 'lũy kế năm 2026 đến 09/2026' in s['a']
    assert '2 / 44' in s['a']
    r['sections']['a1']=''
    assert summarize(r)['metrics']['paper']['scopus']==1
    r['paperScope']='month';assert summarize(r)['metrics']['paper']['scopus']==0


def test_rank_conflicts_missing_index_and_isi_do_not_inflate_scopus():
    r=compose([],'2026-09')
    r['sections']['a1']='Công bố khoa học:\nSame work — MAPR 2026; Q1; Scopus (Chế Quang Huy)\nSame work — MAPR2026; B; Scopus (Nguyễn Vinh Tiệp)\nOther work — Journal; Q1; ISI (Chế Quang Huy)\nUnknown work — MAPR; Q1; chưa có index (Chế Quang Huy)'
    s=summarize(r)
    assert s['metrics']['paper']['scopus']==1 and s['metrics']['paper']['isiOnly']==1
    assert s['metrics']['paper']['ranks']=={'Scopus khác':1} and s['notes']


def test_duplicate_batch_declarations_and_repeat_report_not_added_twice():
    r=compose([task_report(['Nghiệm thu 02 đề tài D1','Nghiệm thu 02 đề tài D1','Mới được công nhận 04 NCS']),
        task_report(['Nghiệm thu 02 đề tài D1','Mới được công nhận 04 NCS'],id='second',memberIds=[1])],'2026-09')
    s=summarize(r)
    assert 'Nghiệm thu 2 đề tài D1' in s['a'] and 'thêm 04 NCS' in s['a']
    assert 'thêm 08 NCS' not in s['a']


def test_manual_total_not_added_on_top_of_catalog():
    r=compose([paper()],'2026-09');r['sections']['a1']+='\nKPI bài báo: hoàn thành 46 / 44 bài báo Scopus'
    s=summarize(r)
    assert s['metrics']['paper']['scopus']==1 and '46 / 44' not in s['a'] and s['notes']


def test_api_preview_target_scope_saved_and_frozen_email_matches(scheduled):
    c=scheduled;login(c);r=c.get('/api/monthly/2026-09').json()
    assert 'schoolSummary' in r and r['scopusTarget'] is None and r['paperScope']=='month'
    body={k:r[k] for k in ('revision','strategyLabel','signatory')}
    body.update(scopusTarget=44,paperScope='year',sections={
        'a1':'Công bố khoa học:\nExample research — MAPR; Q1; Scopus (Chế Quang Huy)\nKPI NCS: mới được công nhận thêm 04 NCS\n01 NCS đã báo cáo xong chuyên đề 3\nNghiệm thu 2 đề tài D1',
        'b1':'KPI bài báo: nộp 05 bài tạp chí Q1, 06 bài báo hội nghị\nKPI NCS: chuẩn bị nộp 02 hồ sơ NCS\nNghiệm thu 2 đề tài D1'})
    saved=c.put('/api/monthly/2026-09',json=body,headers={'Origin':'http://testserver'})
    assert saved.status_code==200,saved.text
    summary=saved.json()['schoolSummary'];loaded=c.get('/api/monthly/2026-09').json()
    assert loaded['scopusTarget']==44 and loaded['paperScope']=='year' and loaded['schoolSummary']==summary
    assert '1 / 44' in summary['a'] and len(summary['a'].splitlines())==4
    document=doc_text(c.get('/api/monthly/2026-09/school.docx').content)
    assert 'Example research' not in document
    for line in summary['a'].splitlines():assert document.count(line)==2*(1+int(line in summary['b'].splitlines()))
    assert service.enqueue_due(datetime(2026,9,28,9,tzinfo=VN))
    with store.engine.connect() as conn:payload=conn.execute(select(service.batches.c.payload)).scalar_one()
    school=doc_text(base64.b64decode(payload['attachments'][1]['content']))
    discussion=doc_text(base64.b64decode(payload['attachments'][0]['content']))
    assert 'Example research' in discussion and 'Example research' not in school
    for line in summary['a'].splitlines():assert school.count(line)==2*(1+int(line in summary['b'].splitlines()))
    next_report=c.get('/api/monthly/2026-10').json()
    assert next_report['paperScope']=='year' and next_report['scopusTarget']==44
    next_year=c.get('/api/monthly/2027-01').json()
    assert next_year['scopusTarget'] is None and next_year['paperScope']=='month'
    body['revision']=loaded['revision'];body['scopusTarget']=0
    assert c.put('/api/monthly/2026-09',json=body,headers={'Origin':'http://testserver'}).status_code==422
