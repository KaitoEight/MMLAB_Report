import copy
from sqlalchemy import select
from test_api import login
from test_confirmation import workflow, seed, get_link, headers, VALID, ORIGIN
from models import Bundle
import store
import mailer
import intake


def edit_payload(report, **changes):
    return {'revision':report.get('reportVersion',0), 'type':report['type'],
            **{k:report.get(k) or '' for k in ('title','status','authors','venue','role','ranking','index')},
            'memberId':report.get('memberId'), 'memberIds':report.get('memberIds',[]),
            'monthlyTasks':report.get('monthlyTasks'), **changes}


def test_only_admin_can_edit_delete_and_origin_is_required(workflow):
    seed()
    report=store.read_reports()[0][0]
    path='/api/reports/'+report['id']
    _, token=get_link()
    assert workflow.put(path,headers=headers(token),json=edit_payload(report)).status_code==401
    assert workflow.request('DELETE',path,headers=headers(token),json={'revision':0}).status_code==401
    login(workflow)
    assert workflow.put(path,json=edit_payload(report)).status_code==403
    assert workflow.request('DELETE',path,headers={'Origin':'https://elsewhere.example'},json={'revision':0}).status_code==403
    assert workflow.put(path,headers={'Origin':ORIGIN},json=edit_payload(report,memberId=13)).status_code==422
    assert workflow.put(path,headers={'Origin':ORIGIN},json=edit_payload(report,date='2020-01-01')).status_code==422


def test_admin_edit_updates_public_form_and_prevents_stale_overwrite(workflow):
    original=seed()
    report=store.read_reports()[0][0]
    _,token=get_link()
    login(workflow)
    payload=edit_payload(report, **VALID, memberId=7)
    r=workflow.put('/api/reports/'+report['id'],headers={'Origin':ORIGIN},json=payload)
    assert r.status_code==200, r.text
    changed=r.json()['report']
    assert changed['memberIds']==[1,7] and changed['memberId']==7
    assert changed['date']==report['date'] and changed['adminEditedBy']=='admin'
    assert changed['isValid']
    store.ingest(original, workflow=True)
    assert store.read_reports()[0][0]['title']==VALID['title']
    assert workflow.put('/api/reports/'+report['id'],headers={'Origin':ORIGIN},json=payload).status_code==409
    # The public link still works after logout, with no login or OTP.
    workflow.post('/api/logout',headers={'Origin':ORIGIN})
    public=workflow.get('/api/paper-confirm',headers=headers(token))
    assert public.status_code==200 and public.json()['fields']['title']==VALID['title']
    assert workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':0,'confirmed':True}).status_code==409
    assert workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':public.json()['revision'],'confirmed':True}).status_code==200
    assert store.read_reports()[0][0]['reportVersion']==2


def test_delete_revokes_link_cancels_queue_and_stays_deleted_on_rescan(workflow,monkeypatch):
    original=seed()
    report=store.read_reports()[0][0]
    row, token=get_link()
    login(workflow)
    response=workflow.request('DELETE','/api/reports/'+report['id'],headers={'Origin':ORIGIN},json={'revision':0})
    assert response.status_code==200
    assert store.read_reports()[0]==[] and intake.admin_list()==[]
    assert workflow.get('/api/paper-confirm',headers=headers(token)).status_code==410
    assert workflow.post('/api/intakes/'+row['id']+'/reissue',headers={'Origin':ORIGIN}).status_code==410
    monkeypatch.setenv('MAIL_MODE','smtp')
    calls=[]
    mailer.dispatch(sender=lambda row:calls.append(row) or ('sent',None))
    assert calls==[]
    store.ingest(original,workflow=True)
    store.ingest(original,workflow=False)
    assert store.read_reports()[0]==[]
    # UID reset must not resurrect the same outer message.
    changed=original.model_dump()
    changed['uid_validity']='124'
    changed['reports'][0]['sourceId']='imap:mmlab@uit.edu.vn:INBOX:124:19'
    store.ingest(Bundle.model_validate(changed),workflow=True)
    assert store.read_reports()[0]==[]


def test_monthly_admin_edit_keeps_null_and_received_date(workflow):
    seed(body='Đã:\nViết báo cáo',sender='thindv@uit.edu.vn',subject='Báo cáo tháng')
    report=store.read_reports()[0][0]
    login(workflow)
    data=edit_payload(report,title='Báo cáo công việc',monthlyTasks={'done':None,'planned':['Chuẩn bị dữ liệu']})
    response=workflow.put('/api/reports/'+report['id'],headers={'Origin':ORIGIN},json=data)
    assert response.status_code==200
    r=response.json()['report']
    assert r['date']==report['date'] and r['reportPeriod']==report['date'][:7]
    assert r['monthlyTasks']=={'done':None,'planned':['Chuẩn bị dữ liệu']}
    assert r['isValid'] and not r['ranking']


def test_admin_can_save_incomplete_paper_without_suppressing_validation(workflow):
    seed()
    r=store.read_reports()[0][0]
    login(workflow)
    response=workflow.put('/api/reports/'+r['id'],headers={'Origin':ORIGIN},json=edit_payload(r,ranking='XYZ'))
    assert response.status_code==200
    data=response.json()['report']
    assert not data['isValid']
    assert any(e['field']=='Ranking' for e in data['invalidFields'])


def test_changed_type_cancels_public_paper_form(workflow):
    seed()
    report=store.read_reports()[0][0]
    _,token=get_link()
    login(workflow)
    response=workflow.put('/api/reports/'+report['id'],headers={'Origin':ORIGIN},json=edit_payload(report,type='Seminar',memberId=7,memberIds=[7]))
    assert response.status_code==200
    assert workflow.get('/api/paper-confirm',headers=headers(token)).status_code==410
    assert intake.admin_list()==[]


def test_confirmed_paper_can_be_edited_by_admin(workflow):
    original=seed()
    _,token=get_link()
    assert workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':0,'confirmed':True}).status_code==200
    report=store.read_reports()[0][0]
    login(workflow)
    response=workflow.put('/api/reports/'+report['id'],headers={'Origin':ORIGIN},json=edit_payload(report,title='Corrected by admin'))
    assert response.status_code==200
    store.ingest(original,workflow=True)
    assert store.read_reports()[0][0]['title']=='Corrected by admin'
