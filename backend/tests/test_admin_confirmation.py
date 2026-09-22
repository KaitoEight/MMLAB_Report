from sqlalchemy import select,update
from test_api import login
from test_confirmation import workflow,seed,get_link,headers,VALID,ORIGIN
from test_admin_reports import edit_payload
from models import Bundle
import intake
import store
import mailer


def valid_seed(workflow_enabled=True):
    body='Type of Report: Paper\n'+'\n'.join(intake.LABELS[k]+': '+v for k,v in VALID.items())
    return seed(body=body,workflow=workflow_enabled)


def approve(c,r,**changes):
    return c.post('/api/reports/'+r['id']+'/admin-confirm',headers={'Origin':ORIGIN},json={'revision':r.get('reportVersion',0),'confirmed':True,**changes})


def test_confirmation_requires_admin_origin_and_explicit_agreement(workflow):
    valid_seed();r=store.read_reports()[0][0];_,token=get_link();path='/api/reports/'+r['id']
    assert approve(workflow,r).status_code==401
    assert workflow.get(path+'/confirmation',headers=headers(token)).status_code==401
    login(workflow)
    assert workflow.post(path+'/admin-confirm',json={'revision':0,'confirmed':True}).status_code==403
    assert approve(workflow,r,confirmed=False).status_code==422
    assert approve(workflow,r,revision=9).status_code==409


def test_admin_review_keeps_receipt_and_rejects_stale_public_edits(workflow,monkeypatch):
    original=valid_seed();r=store.read_reports()[0][0];_,token=get_link();login(workflow)
    result=approve(workflow,r);assert result.status_code==200,result.text
    confirmed=result.json()['report']
    assert confirmed['confirmationSource']=='admin' and confirmed['confirmedBy']=='admin'
    assert confirmed['confirmationStatus']=='confirmed' and confirmed['reportVersion']==1
    assert confirmed['memberIds']==[1,7]
    view=workflow.get('/api/paper-confirm',headers=headers(token)).json()
    assert view['status']=='confirmed' and view['confirmationSource']=='admin'
    response=workflow.post('/api/paper-confirm',headers=headers(token),json={'fields':{**VALID,'title':'Overwrite attempt'},'revision':0,'confirmed':True})
    assert response.status_code==409
    assert store.read_reports()[0][0]['title']==VALID['title']
    monkeypatch.setenv('MAIL_MODE','smtp');calls=[]
    mailer.dispatch(sender=lambda r:calls.append(r) or ('sent',None));assert len(calls)==1
    store.ingest(original,workflow=True)
    assert store.read_reports()[0][0]['confirmationSource']=='admin'
    assert approve(workflow,confirmed).json()['alreadyConfirmed']
    assert workflow.post('/api/reports/'+r['id']+'/request-confirmation',headers={'Origin':ORIGIN}).status_code==409


def test_admin_requires_valid_fields_and_lab_author(workflow):
    seed();r=store.read_reports()[0][0];login(workflow)
    response=approve(workflow,r);assert response.status_code==422 and 'All authors' in response.text
    changed=workflow.put('/api/reports/'+r['id'],headers={'Origin':ORIGIN},json=edit_payload(r,**{**VALID,'authors':'Someone Else'})).json()['report']
    assert approve(workflow,changed).status_code==422


def test_admin_can_confirm_import_without_sending_to_unverified_recipient(workflow):
    valid_seed(False);r=store.read_reports()[0][0];login(workflow)
    path='/api/reports/'+r['id']
    assert workflow.get(path+'/confirmation').json()['email'] is None
    assert workflow.post(path+'/request-confirmation',headers={'Origin':ORIGIN}).status_code==409
    assert approve(workflow,r).status_code==200
    with store.engine.connect() as c:assert c.execute(select(store.outbox)).first() is None


def test_edit_after_approval_requires_new_confirmation_and_keeps_history(workflow):
    valid_seed();r=store.read_reports()[0][0];login(workflow)
    approved=approve(workflow,r).json()['report']
    edited=workflow.put('/api/reports/'+r['id'],headers={'Origin':ORIGIN},json=edit_payload(approved,title='New title after approval')).json()['report']
    assert edited['confirmationStatus']=='pending' and not edited.get('confirmedBy')
    assert edited['confirmationHistory'][-1]['confirmationSource']=='admin'
    response=workflow.post('/api/reports/'+r['id']+'/request-confirmation',headers={'Origin':ORIGIN},json={'revision':edited['reportVersion'],'resend':True})
    assert response.status_code==200,response.text
    assert response.json()['email']['mailStatus']=='pending'
    assert 'New title after approval' in response.json()['email']['body']
    assert approve(workflow,edited).status_code==200


def test_email_preview_recipient_resend_and_repeat_click_idempotence(workflow):
    valid_seed();r=store.read_reports()[0][0];row,old_token=get_link();login(workflow);path='/api/reports/'+r['id']
    info=workflow.get(path+'/confirmation').json()
    assert info['email']['recipient']=='student@gmail.com' and info['email']['link']
    assert info['mailMode']=='preview'
    with store.mutation() as c:c.execute(update(store.outbox).values(status='sent'))
    assert workflow.post(path+'/request-confirmation',headers={'Origin':ORIGIN},json={'revision':0,'resend':False}).status_code==409
    first=workflow.post(path+'/request-confirmation',headers={'Origin':ORIGIN},json={'revision':0,'resend':True})
    assert first.status_code==200 and first.json()['email']['link']!=info['email']['link']
    assert workflow.get('/api/paper-confirm',headers=headers(old_token)).status_code==404
    second=workflow.post(path+'/request-confirmation',headers={'Origin':ORIGIN},json={'revision':0,'resend':True})
    assert second.json()['email']['link']==first.json()['email']['link']
    with store.engine.connect() as c:assert len(c.execute(select(store.outbox)).all())==1
    with store.mutation() as c:c.execute(update(store.outbox).values(status='sending'))
    assert workflow.post(path+'/request-confirmation',headers={'Origin':ORIGIN},json={'revision':0,'resend':True}).status_code==409


def test_json_import_cannot_forge_admin_confirmation(workflow):
    b=valid_seed(False).model_dump();b['reports'][0].update(confirmationSource='admin',confirmedBy='admin',confirmationStatus='confirmed',confirmedAt=store.now())
    store.ingest(Bundle.model_validate(b))
    r=store.read_reports()[0][0]
    assert not r.get('confirmationSource') and not r.get('confirmedBy') and not r.get('confirmationStatus')
