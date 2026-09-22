from email.message import EmailMessage
from mmlab_pipeline.parser import parse_and_validate_email
from imap_fetch import analyze, MONTHLY_POLICY
from models import Report

SUBJECT = 'Fwd: Báo cáo tháng 9/2026'
SENDER = 'thindv@uit.edu.vn'
BODY = 'Đã:\n01/09, Huấn luyện mô hình\nSẽ:\nNộp bài'


def test_monthly_no_paper_metadata_required():
    result = parse_and_validate_email(SUBJECT, BODY, SENDER)
    assert result['is_valid']
    assert not result['missing_fields']
    assert not result['invalid_fields']


def test_monthly_ignores_supplied_paper_metadata():
    body = BODY + '\nRanking: XYZ\nRanking: OTHER\nIndex: nope\nRole: nope\nVenue:\nStatus: pending\nAccepted: no'
    result = parse_and_validate_email(SUBJECT, body, SENDER)
    assert result['is_valid'], result
    assert not result['needs_review']


def test_monthly_accepts_free_tasks_bad_dates_and_empty_plans():
    result = parse_and_validate_email(SUBJECT, 'Đã:\n32/09, Sai ngày\nSẽ:', SENDER)
    assert result['is_valid'],result
    assert result['data']['done'][0]['date']=='32/09'
    assert result['data']['planned']==[]
    result = parse_and_validate_email(SUBJECT, 'Đã:\n01/09, Xong việc', SENDER)
    assert result['is_valid']
    assert result['data']['planned'] is None


def test_absent_done_is_null_and_free_text_is_preserved():
    result=parse_and_validate_email(SUBJECT,'Sẽ:\nTìm hiểu mô hình',SENDER)
    assert result['is_valid']
    assert result['data']['done'] is None
    assert result['data']['planned']==['Tìm hiểu mô hình']
    result=parse_and_validate_email(SUBJECT,'Đã:\nViết bài, chạy thử mô hình',SENDER)
    assert result['data']['done']==[{'date':'','content':'Viết bài, chạy thử mô hình'}]
    result=parse_and_validate_email(SUBJECT,'Báo cáo đính kèm.',SENDER)
    assert result['is_valid']
    assert result['data']['done'] is None and result['data']['planned'] is None


def test_repeated_blocks_merge_without_validation_error():
    result=parse_and_validate_email(SUBJECT,'Đã:\nViệc 1\nĐã:\nViệc 2\nSẽ:\nViệc 3',SENDER)
    assert result['is_valid']
    assert [t['content'] for t in result['data']['done']]==['Việc 1','Việc 2']


def test_monthly_sender_mapping_still_required():
    result = parse_and_validate_email(SUBJECT, BODY, 'outsider@gmail.com')
    assert not result['is_valid']
    assert any(e['field'] == 'Sender' for e in result['invalid_fields'])


def test_monthly_export_has_no_accepted_status():
    message = EmailMessage()
    message['Subject'] = SUBJECT
    message['From'] = SENDER
    message.set_content(BODY + '\nStatus: Accepted\nStatus: Pending\nRanking: XYZ')
    event = analyze(message.as_bytes(), 'imap:mmlab@uit.edu.vn:INBOX:123:17', '2026-09-30T00:00:00+07:00')
    report = event['report']
    assert report['isValid']
    assert report['issues'] == []
    assert all(not report.get(k) for k in ('status','role','ranking','index','venue'))
    assert event['monthly_policy'] == MONTHLY_POLICY


def test_absent_blocks_stay_null_through_export_and_api_schema():
    message = EmailMessage()
    message['Subject'] = SUBJECT
    message['From'] = SENDER
    message.set_content('Báo cáo đính kèm.')
    event = analyze(message.as_bytes(), 'imap:mmlab@uit.edu.vn:INBOX:123:18', '2026-09-30T00:00:00+07:00')
    report = Report.model_validate(event['report'])
    assert report.isValid
    assert report.model_dump(mode='json')['monthlyTasks'] == {'done': None, 'planned': None}


def test_subject_never_validated_and_period_uses_receipt_in_vietnam():
    for subject in ('Báo cáo tháng', 'Báo cáo tháng 99/0000', 'Kết quả công việc', ''):
        message = EmailMessage()
        message['Subject'] = subject
        message['From'] = SENDER
        message.set_content('Đã:\nViết bài')
        event = analyze(message.as_bytes(), 'imap:mmlab@uit.edu.vn:INBOX:123:19', '2026-09-30T20:30:00+00:00')
        report = Report.model_validate(event['report'])
        assert report.isValid, report.issues
        assert report.date == '2026-10-01'
        assert report.reportPeriod == '2026-10'
        assert report.monthlyTasks.planned is None


def test_explicit_monthly_type_without_subject_or_blocks():
    result = parse_and_validate_email('', 'Type of Report: Monthly Report', SENDER)
    assert result['is_valid'], result
    assert result['category'] == 'Monthly Report'
    assert result['data']['done'] is None
    assert 'report_month' not in result['provenance']  # No guessing a date in text-only calls.
