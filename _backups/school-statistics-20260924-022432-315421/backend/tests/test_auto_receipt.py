"""Regression tests for the automatic receipt policy and the new school form."""
import copy
from sqlalchemy import select, update
from test_confirmation import workflow, seed, get_link, headers, VALID, ORIGIN
from test_api import login
from test_admin_reports import edit_payload
from test_monthly import doc_text, paper
from monthly_report import compose, docx_bytes
from models import Bundle
import store
import intake
import receipt_policy


def test_incomplete_forward_approved_without_changing_validation(workflow):
    seed()
    r=store.read_reports()[0][0]
    assert r['approvalStatus']=='approved' and r['approvalSource']=='automatic'
    assert not r['isValid'] and r['missingFields'] and r['memberIds']==[]
    row,_=get_link()
    assert 'không cần xác nhận lại' in row['body'] and 'tùy chọn' in row['body']
    assert 'cần xác nhận' not in row['subject']
    with store.engine.connect() as c:assert c.execute(select(store.outbox.c.status)).scalar_one()=='pending'


def test_approval_survives_mail_configuration_error(workflow,monkeypatch):
    monkeypatch.setenv('PUBLIC_BASE_URL','invalid')
    seed()
    r=store.read_reports()[0][0]
    assert r['approvalStatus']=='approved' and r['receiptIssue'] and intake.admin_list()==[]


def test_repeat_public_edit_no_checkbox_and_stale_revision_conflicts(workflow):
    original=seed();_,token=get_link()
    first=workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':0})
    assert first.status_code==200 and first.json()['revision']==1
    changed={**VALID,'title':'A second revision of the research paper'}
    second=workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':changed,'revision':1})
    assert second.status_code==200 and second.json()['revision']==2
    assert workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':1}).status_code==409
    store.ingest(original,workflow=True)
    r=store.read_reports()[0][0]
    assert r['title']==changed['title'] and r['approvalStatus']=='approved'
    assert intake.admin_list()[0]['body'].count(changed['title'])==1
    login(workflow)
    response=workflow.request('DELETE','/api/reports/'+r['id'],headers={'Origin':ORIGIN},json={'revision':r['reportVersion']})
    assert response.status_code==200
    assert workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':2}).status_code==410


def test_admin_edit_preserves_automatic_approval(workflow):
    seed();r=store.read_reports()[0][0];login(workflow)
    result=workflow.put('/api/reports/'+r['id'],headers={'Origin':ORIGIN},json=edit_payload(r,**VALID))
    assert result.status_code==200 and result.json()['report']['approvalStatus']=='approved'


def test_import_cannot_forge_receipt_approval(workflow):
    b=seed(workflow=False).model_dump()
    b['reports'][0].update(approvalStatus='approved',approvalSource='automatic',approvedAt=store.now())
    store.ingest(Bundle.model_validate(b))
    assert not store.read_reports()[0][0].get('approvalStatus')


def test_migration_idempotent_no_historical_send_and_deleted_stay_deleted(workflow):
    seed();r=store.read_reports()[0][0];_,token=get_link()
    legacy={k:v for k,v in r.items() if k not in receipt_policy.OWNED_FIELDS}
    legacy['status']='Chưa rõ'
    with store.mutation() as c:
        c.execute(store.workflow_settings.delete().where(store.workflow_settings.c.key==receipt_policy.POLICY+':'+store.mailbox()))
        c.execute(update(store.reports).values(payload=legacy))
        c.execute(update(store.intakes).values(original=legacy))
        c.execute(update(store.outbox).values(payload={'subject':'Cần xác nhận','body':'old','link':'http://localhost:8080/#confirm='+token}))
        c.execute(store.insert(store.reports).values(id='deleted',mailbox=store.mailbox(),payload={**legacy,'id':'deleted','deletedAt':store.now()}))
    receipt_policy.migrate();receipt_policy.migrate()
    r=store.read_reports()[0][0]
    assert r['approvalStatus']=='approved' and r['status']=='Chưa rõ' and not r['isValid']
    assert len(intake.admin_list())==1 and 'không cần xác nhận lại' in intake.admin_list()[0]['body']
    with store.mutation() as c:c.execute(update(store.outbox).values(status='sent'))
    receipt_policy.migrate()
    assert intake.admin_list()[0]['mailStatus']=='sent'
    assert len(store.read_reports()[0])==1


def test_school_form_sections_unit_strategy_month_and_no_invented_targets():
    r=compose([paper(taskGroup='unassigned',date='2026-07-15')],'2026-07')
    r['sections'].update(b1='Chuẩn bị hồ sơ nghiên cứu sinh',recommendations='Đề nghị hỗ trợ máy tính')
    original=copy.deepcopy(r)
    text=doc_text(docx_bytes(r,'school'))
    for expected in ('THÁNG 08/2026','Mã đơn vị: 6','Phần A.1','Phần A.2','Phần B.1','Phần B.2','2021-2030','KH2026'):
        assert expected in text
    assert text.count('A study of realistic video retrieval')==2
    a1=text.split('Phần A.1')[1].split('Phần A.2')[0]
    assert 'A study of realistic video retrieval' in a1
    assert 'Phần 3' not in text and 'Đề nghị hỗ trợ máy tính' not in text
    assert '46 / 44' not in text and '2021-2025' not in text
    assert r==original  # School output must not modify saved discussion data.
