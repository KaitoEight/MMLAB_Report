import io
from docx import Document
from mmlab_pipeline.tasks import repair_tasks
from mmlab_pipeline.parser import parse_and_validate_email
from monthly_report import compose, docx_bytes
from test_monthly import paper


def test_join_before_deduplicate_preserves_two_different_manuscripts():
    tasks=[{'date':'2026-08-20','content':'Hoàn thành bản thảo dự kiến nộp'},
           {'date':'','content':'tạp chí, với nội dung xây dựng dữ liệu'},
           {'date':'','content':'trong lĩnh vực pháp luật'},
           {'date':'2026-08-20','content':'Hoàn thành bản thảo dự kiến nộp'},
           {'date':'','content':'tạp chí, với nội dung trích xuất đặc trưng'},
           {'date':'','content':'bài toán truy vấn pháp luật'}]
    repaired=repair_tasks(tasks)
    assert len(repaired)==2 and repaired[0]['date']=='20/08/2026'
    assert 'xây dựng dữ liệu trong lĩnh vực' in repaired[0]['content']
    assert 'trích xuất đặc trưng bài toán' in repaired[1]['content']
    assert repair_tasks(repaired)==repaired


def test_dates_duplicate_lines_and_distinct_people():
    tasks=repair_tasks([{'date':'','content':'14/8/2026: nhận kết quả Revision một journal'},
                        {'date':'14/8/2026','content':'nhận kết quả Revision một journal'},
                        {'date':'15/8/2026','content':'nhận kết quả Revision một journal'},
                        {'date':'','content':'1-30/07/2026, Hướng dẫn sinh viên'}])
    assert len(tasks)==3 and tasks[0]['date']=='14/08/2026'
    assert tasks[2]['date']=='1-30/07/2026'
    common={'date':'2026-09-01','content':'Thực hiện đề tài nghiên cứu'}
    a=paper(id='a',type='Báo cáo tháng',memberIds=[7],monthlyTasks={'done':[common]})
    b=paper(id='b',type='Báo cáo tháng',memberIds=[3],monthlyTasks={'done':[common]})
    result=compose([a,b],'2026-09')
    assert result['sections']['aOther'].count('Thực hiện đề tài nghiên cứu')==2


def test_bullet_and_action_boundaries_not_joined():
    tasks=repair_tasks(['+ Tiếp tục nghiên cứu','- Hướng dẫn sinh viên','- trong nhóm phụ trách','*#%','-'])
    assert [x['content'] for x in tasks]==['Tiếp tục nghiên cứu','Hướng dẫn sinh viên','trong nhóm phụ trách']
    assert repair_tasks(tasks,join_wrapped=False)==tasks
    r=paper(type='Báo cáo tháng',monthlyTasksVersion=2,monthlyTasks={'done':tasks})
    result=compose([r],'2026-09')
    assert result['sections']['aOther'].count('(Chế Quang Huy)')==3


def test_monthly_parser_does_not_drop_seminar_or_continuation_labels():
    body='Đã:\n- 24/08/2026, Hướng dẫn đội thi đạt giải 3\ntrack Creative\nSẽ:\n+ Seminar: Trình bày công cụ "The\nResearch Assistant"\n+ Tiếp tục nghiên cứu'
    result=parse_and_validate_email('Báo cáo tháng',''+body,'huycq@uit.edu.vn')
    assert result['is_valid']
    assert len(result['data']['done'])==1
    assert 'track Creative' in result['data']['done'][0]['content']
    assert result['data']['planned'][0]=='Seminar: Trình bày công cụ "The Research Assistant"'
    assert 'Tiếp tục nghiên cứu' in result['data']['planned']


def test_unknown_sender_excluded_from_school_and_required_sections_present():
    unknown=paper(id='unknown',type='Báo cáo tháng',memberIds=[],sender='unknown@example.com',monthlyTasks={'planned':['Seminar: công cụ "The']})
    known=paper(id='known',type='Báo cáo tháng',memberIds=[7],monthlyTasks={'planned':['Seminar: Robotics','Đi học PhD']})
    result=compose([unknown,known],'2026-09')
    assert len(result['reviewNotes'])==1
    texts={v:'\n'.join(p.text for p in Document(io.BytesIO(docx_bytes(result,v))).paragraphs) for v in ('discussion','school')}
    assert 'unknown@example.com' in texts['discussion'] and 'unknown@example.com' not in texts['school']
    assert 'Phần A.1' in texts['school'] and 'Robotics' in texts['school']
    assert 'Chưa có nội dung báo cáo' not in texts['school']
    assert 'chưa phân nhóm' not in texts['school']
    assert 'Seminar và hội nghị' in texts['school']


def test_no_paper_status_inferred_from_monthly_manuscript_or_revision():
    r=paper(type='Báo cáo tháng',monthlyTasks={'done':[{'date':'','content':'Hoàn thành bản thảo dự kiến nộp tạp chí'},
                                                     {'date':'','content':'Nhận Revision journal'}]})
    result=compose([r],'2026-09')
    assert result['counts']['acceptedJournal']==0 and result['counts']['submittedJournal']==0
