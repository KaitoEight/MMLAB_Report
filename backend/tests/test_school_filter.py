import copy
from monthly_report import compose, docx_bytes
from monthly_assembly import TOPICS
from school_report import filtered_body, school_projection
from test_monthly import paper, doc_text
from test_paired_monthly import bodies


def test_discussion_keeps_all_tasks_school_only_three_categories():
    r=paper(type='Báo cáo tháng',monthlyTasksVersion=2,monthlyTasks={
        'done':[{'date':'','content':t} for t in [
            'Nộp 02 bài báo tạp chí Q1','NCS hoàn thành chuyên đề 3',
            'Nghiệm thu 2 đề tài D1','Seminar về robotics',
            'Đạt giải Best Paper Award','Hướng dẫn sinh viên thực hiện khóa luận',
            'Hoàn thành cuốn luận văn thạc sĩ','Bảo trì máy chủ']],
        'planned':['Nộp 05 bài tạp chí Q1, 06 bài báo hội nghị',
                   'Chuẩn bị nộp 02 hồ sơ NCS','Nghiệm thu 2 đề tài D1',
                   'Seminar về PPO và GRPO','Tham gia cuộc thi NLP','Giảng dạy ở khoa KHMT']})
    report=compose([r],'2026-09');original=copy.deepcopy(report)
    discussion=doc_text(docx_bytes(report,'discussion'));school=doc_text(docx_bytes(report,'school'))
    for value in ('robotics','Best Paper Award','khóa luận','luận văn thạc sĩ','Bảo trì máy chủ','PPO và GRPO','cuộc thi NLP','Giảng dạy'):
        assert value in discussion and value not in school,value
    for value in ('Nộp 02 bài báo','chuyên đề 3','Nghiệm thu 2 đề tài','Nộp 05 bài','02 hồ sơ NCS'):
        assert value in discussion,value
    for value in ('đã nộp 02 bài tạp chí Q1','01 NCS đã báo cáo xong chuyên đề 3','Nghiệm thu 2 đề tài','nộp 05 bài tạp chí Q1, 06 bài báo hội nghị','02 hồ sơ NCS'):
        assert value in school,value
    blocks=bodies(docx_bytes(report,'school'))
    assert blocks['Phần A.1']==blocks['Phần A.2']
    assert blocks['Phần B.1']==blocks['Phần B.2']
    assert 'Nộp 05 bài' not in '\n'.join(blocks['Phần A.1'])
    assert 'Nộp 02 bài' not in '\n'.join(blocks['Phần B.1'])
    assert report==original


def test_manual_example_values_remain_declarations_not_hardcoded_defaults():
    text='* KPI bài báo: hoàn thành 46 / 44 bài báo Scopus. Trong đó: Q1 3 bài, A* và A: 3 bài\n* KPI NCS: mới được công nhận thêm 04 NCS\n* 01 NCS đã báo cáo xong chuyên đề 3.\n* Nghiệm thu 2 đề tài D1\n* Hướng dẫn sinh viên và giảng dạy'
    filtered=filtered_body(text)
    assert '46 / 44' in filtered and '04 NCS' in filtered and '01 NCS' in filtered
    assert 'Hướng dẫn' not in filtered and 'KPI bài báo: KPI bài báo:' not in filtered
    empty=doc_text(docx_bytes(compose([],'2026-09'),'school'))
    assert '46 / 44' not in empty and '04 NCS' not in empty


def test_editable_text_filter_does_not_depend_on_stale_assembly_counts():
    report=compose([paper()],'2026-09')
    report['sections']['a1']='KPI NCS: 03 NCS được công nhận\nGiảng dạy tại khoa KHMT'
    result=school_projection(report)
    assert '03 NCS' in result['sections']['a1']
    assert 'A study of realistic' not in result['sections']['a1']
    assert 'Giảng dạy' not in result['sections']['a1']
    report['sections']['a1']=''
    assert school_projection(report)['sections']['a2']==''


def test_monthly_unmatched_quote_is_kept_in_discussion_and_unmapped_not_credited():
    known=paper(id='known',type='Báo cáo tháng',monthlyTasksVersion=2,monthlyTasks={
        'done':None,'planned':['Seminar về công cụ "The Research Assistant']})
    unknown=paper(id='unknown',type='Báo cáo tháng',memberIds=[],sender='outside@example.com',monthlyTasksVersion=2,monthlyTasks={
        'done':[{'date':'','content':'Nộp 10 bài báo Scopus'}],'planned':['Nộp 05 hồ sơ NCS']})
    report=compose([known,unknown],'2026-09')
    discussion=doc_text(docx_bytes(report,'discussion'));school=doc_text(docx_bytes(report,'school'))
    assert 'The Research Assistant' in discussion
    assert 'outside@example.com' in discussion and '10 bài báo' in discussion
    assert 'outside@example.com' not in school and '10 bài báo' not in school and '05 hồ sơ' not in school
    assert unknown['memberIds']==[]


def test_structured_paper_title_is_not_recategorized_by_keyword():
    r=paper(title='Seminar Scheduling and Best Paper Award Prediction',status='Chưa rõ')
    report=compose([r],'2026-09')
    assert 'Scopus: 1 bài.' in school_projection(report)['sections']['a1']
    assert r['title'] not in school_projection(report)['sections']['a1']
    assert 'Accepted' not in doc_text(docx_bytes(report,'school'))
    assert report['counts']['acceptedConference']==0


def test_doctoral_seminar_allowed_but_general_seminar_excluded():
    text=TOPICS[3]+':\nBáo cáo seminar trong chương trình NCS\nSeminar về Robotics\n'+TOPICS[2]+':\nHoàn thành luận văn thạc sĩ\nChuẩn bị hồ sơ PhD'
    result=filtered_body(text)
    assert 'chương trình NCS' in result and 'hồ sơ PhD' in result
    assert 'Robotics' not in result and 'luận văn thạc sĩ' not in result
