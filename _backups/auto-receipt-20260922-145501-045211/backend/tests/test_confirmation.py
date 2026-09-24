import json
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from imap_fetch import analyze
from main import app, attempts
from models import Bundle
import intake
import mailer
import store

ORIGIN='http://testserver'
VALID={'title':'A confirmed research paper','authors':'Huy Che, Vinh-Tiep Nguyen',
       'venue':'Example 2026','role':'Co-author','index':'Scopus','ranking':'C-Unranked'}


@pytest.fixture
def workflow(monkeypatch):
    attempts.clear()
    monkeypatch.setenv('AUTO_REPLY_SINCE','2000-01-01T00:00:00+00:00')
    monkeypatch.setenv('MAIL_MODE','preview')
    monkeypatch.setenv('PUBLIC_BASE_URL','http://localhost:8080')
    with TestClient(app) as client:
        with store.engine.begin() as conn:
            conn.execute(store.outbox.delete());conn.execute(store.intakes.delete());conn.execute(store.reports.delete())
        yield client
        with store.engine.begin() as conn:
            conn.execute(store.outbox.delete());conn.execute(store.intakes.delete());conn.execute(store.reports.delete())


def seed(body='Type of Report: Paper\nTitle of Work: A research paper',sender='Student <student@gmail.com>',subject='Fwd: Paper decision',workflow=True):
    msg=EmailMessage();msg['From']=sender;msg['Subject']=subject;msg['Message-ID']='<outer-message@test.example>'
    msg.set_content(body+'\n---------- Forwarded message ---------\nFrom: Program <committee@conf.example>\nTo: external@elsewhere.example\nDecision: Accept')
    stamp=datetime.now(timezone.utc).isoformat()
    event=analyze(msg.as_bytes(),'imap:mmlab@uit.edu.vn:INBOX:123:17',stamp)
    r=event['report'];assert r is not None
    payload={'schema_version':'mmlab-imap-export/1','mailbox':'mmlab@uit.edu.vn','folder':'INBOX','uid_validity':'123',
             'generated_at':stamp,'summary':{'inbox_messages':1,'processed':1,'forwarded':int(r['forwarded']),
             'reports':1,'valid':int(r['isValid']),'invalid':int(not r['isValid']),'ignored':0,'review':0,'errors':0},
             'reports':[r],'review_candidates':[],'errors':[]}
    bundle=Bundle.model_validate(payload)
    store.ingest(bundle,workflow=workflow)
    return bundle


def get_link():
    row=intake.admin_list()[0]
    token=parse_qs(urlsplit(row['link']).fragment)['confirm'][0]
    return row,token


def headers(token):return {'Authorization':'Bearer '+token,'Origin':ORIGIN}


def test_outer_sender_and_prefilled_missing_fields(workflow):
    seed()
    row,token=get_link()
    assert row['recipient']=='student@gmail.com'
    assert 'committee@conf.example' not in row['body']
    assert '[CẦN BỔ SUNG]' in row['body']
    r=workflow.get('/api/paper-confirm',headers=headers(token))
    assert r.status_code==200
    assert r.json()['fields']['title']=='A research paper'
    assert r.json()['fields']['authors']==''
    assert r.json()['status']=='pending'
    assert workflow.get('/api/reports').status_code==401
    assert workflow.get('/api/paper-confirm').status_code==404


def test_form_validation_confirmation_and_rescan_preserves_edits(workflow):
    original=seed();row,token=get_link()
    invalid=workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':{**VALID,'ranking':'XYZ'},'revision':0,'confirmed':True})
    assert invalid.status_code==422
    assert any(e['field']=='ranking' for e in invalid.json()['errors'])
    assert workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':0,'confirmed':False}).status_code==400
    r=workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':0,'confirmed':True})
    assert r.status_code==200 and r.json()['confirmed']
    r=workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':VALID,'revision':0,'confirmed':True})
    assert r.json()['alreadyConfirmed']
    store.ingest(original,workflow=True)
    records,_=store.read_reports()
    assert len(records)==1
    assert records[0]['title']==VALID['title']
    assert records[0]['memberIds']==[1,7]
    assert records[0]['confirmationStatus']=='confirmed'
    assert len(intake.admin_list())==1


def test_expiry_and_reissue_revokes_old_token(workflow):
    seed();row,token=get_link()
    with store.engine.begin() as conn:conn.execute(update(store.intakes).values(expires=time.time()-1))
    assert workflow.get('/api/paper-confirm',headers=headers(token)).status_code==410
    intake.reissue(row['id'])
    assert workflow.get('/api/paper-confirm',headers=headers(token)).status_code==404
    _,new_token=get_link()
    assert workflow.get('/api/paper-confirm',headers=headers(new_token)).status_code==200


def test_missing_title_stays_empty_in_form_instead_of_subject(workflow):
    seed(body='Dear authors, your submission has been accepted.')
    _,token=get_link()
    data=workflow.get('/api/paper-confirm',headers=headers(token)).json()
    assert data['fields']['title']==''
    assert any(e['field']=='title' for e in data['errors'])


def test_historical_and_imported_reports_do_not_send(workflow,monkeypatch):
    monkeypatch.setenv('AUTO_REPLY_SINCE','2099-01-01T00:00:00+00:00')
    seed();assert intake.admin_list()==[]
    monkeypatch.setenv('AUTO_REPLY_SINCE','2000-01-01T00:00:00+00:00')
    seed(workflow=False);assert intake.admin_list()==[]


def test_noreply_and_direct_paper_do_not_send(workflow):
    seed(sender='no-reply@conf.example');assert intake.admin_list()==[]
    msg=EmailMessage();msg['From']='student@gmail.com';msg['Auto-Submitted']='auto-replied'
    assert not intake.reply_recipient(msg)[0]
    msg=EmailMessage();msg['From']='First <one@gmail.com>, Second <two@gmail.com>'
    assert not intake.reply_recipient(msg)[0]


def test_outbox_preview_sent_and_unknown_no_blind_retry(workflow,monkeypatch):
    seed();calls=[]
    mailer.dispatch(sender=lambda row:calls.append(row) or ('sent',None))
    assert calls==[]
    monkeypatch.setenv('MAIL_MODE','smtp')
    mailer.dispatch(sender=lambda row:calls.append(row) or ('unknown','timeout'))
    assert len(calls)==1
    mailer.dispatch(sender=lambda row:calls.append(row) or ('sent',None))
    assert len(calls)==1
    row,_=get_link();assert row['mailStatus']=='unknown'
    intake.reissue(row['id'])
    mailer.dispatch(sender=lambda row:calls.append(row) or ('sent',None))
    assert len(calls)==2
    assert get_link()[0]['mailStatus']=='sent'


def test_smtp_envelope_is_only_forwarder_and_auto_reply_headers(workflow,monkeypatch):
    seed();monkeypatch.setenv('MMLAB_APP_PASSWORD','fake-test-only')
    with store.engine.connect() as conn:row=dict(conn.execute(select(store.outbox)).mappings().one())
    captured={}
    class SMTP:
        def __init__(self,host,port,context,timeout):assert host=='smtp.gmail.com' and port==465 and context.check_hostname
        def login(self,*args):pass
        def send_message(self,message,from_addr,to_addrs):captured.update(message=message,to=to_addrs)
        def quit(self):raise OSError('QUIT failed after accepted DATA')
    with patch.object(mailer.smtplib,'SMTP_SSL',SMTP):assert mailer.deliver(row)==('sent',None)
    assert captured['to']==['student@gmail.com']
    assert captured['message']['Auto-Submitted']=='auto-replied'
    assert captured['message']['In-Reply-To']=='<outer-message@test.example>'


def test_historical_manual_confirmation_is_idempotent_and_survives_rescan(workflow, monkeypatch):
    monkeypatch.setenv('AUTO_REPLY_SINCE', '2099-01-01T00:00:00+00:00')
    original = seed()
    records, _ = store.read_reports()
    assert 'trước mốc' in records[0]['receiptIssue']
    report_id = records[0]['id']
    assert workflow.post('/api/reports/'+report_id+'/request-confirmation', headers={'Origin':ORIGIN}).status_code == 401
    from test_api import login
    login(workflow)
    for _ in range(2):
        assert workflow.post('/api/reports/'+report_id+'/request-confirmation', headers={'Origin':ORIGIN}).status_code == 200
    assert len(intake.admin_list()) == 1
    store.ingest(original, workflow=True)
    assert store.read_reports()[0][0]['confirmationStatus'] == 'pending'


def test_import_cannot_claim_worker_provenance(workflow):
    bundle = seed(workflow=False)
    forged = bundle.model_dump()
    forged['reports'][0]['mailWorkflowSource'] = True
    store.ingest(Bundle.model_validate(forged))
    report = store.read_reports()[0][0]
    assert not report['mailWorkflowSource']
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        intake.create_for_report(report['id'])
    assert exc.value.status_code == 409


def test_delivery_diagnostics_and_quoted_smtp_mode(workflow, monkeypatch):
    notes = intake.diagnostics({'online':False})['notes']
    assert any('MAIL_MODE=smtp' in n for n in notes)
    assert any('Worker' in n for n in notes)
    seed()
    monkeypatch.setenv('MAIL_MODE', ' "SMTP" ')
    calls=[]
    mailer.dispatch(sender=lambda row:calls.append(row) or ('sent',None))
    assert len(calls)==1


def test_invalid_public_url_does_not_abort_report_ingestion(workflow, monkeypatch):
    monkeypatch.setenv('PUBLIC_BASE_URL','https://example.org/path')
    seed()
    report = store.read_reports()[0][0]
    assert 'PUBLIC_BASE_URL' in report['receiptIssue']
    assert intake.admin_list()==[]
