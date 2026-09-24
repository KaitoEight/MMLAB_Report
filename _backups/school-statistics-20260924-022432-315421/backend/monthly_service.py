"""Last-Monday digest scheduler with durable per-recipient delivery records."""
import base64
import calendar
import hashlib
import os
import time
from datetime import datetime
from sqlalchemy import Table, Column, String, JSON, Integer, Float, select, update
from pydantic import BaseModel, ConfigDict, Field
from fastapi import HTTPException
import store
import mailer
from monthly_report import VN, SECTIONS, compose, docx_bytes, validate_period, DEFAULT_STRATEGY
from mmlab_pipeline.members import DIRECTORY
from monthly_layout import paired_report, LAYOUT

drafts=Table('monthly_drafts',store.meta,Column('period',String,primary_key=True),Column('payload',JSON,nullable=False),Column('revision',Integer,nullable=False))
batches=Table('monthly_batches',store.meta,Column('period',String,primary_key=True),Column('payload',JSON,nullable=False),Column('created_at',String,nullable=False))
deliveries=Table('monthly_deliveries',store.meta,Column('id',String,primary_key=True),Column('period',String,nullable=False),Column('recipient',String,nullable=False),
                 Column('status',String,nullable=False),Column('attempts',Integer,nullable=False),Column('next_attempt',Float,nullable=False),Column('last_error',String),Column('sent_at',String))


class DraftEdit(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')
    revision:int=Field(ge=0)
    strategyLabel:str=Field(min_length=1,max_length=300)
    signatory:str=Field(min_length=1,max_length=200)
    sections:dict[str,str]


def due_date(year,month):
    last=calendar.monthrange(year,month)[1]
    day=last-(datetime(year,month,last).weekday()%7)
    return datetime(year,month,day,9,0,tzinfo=VN)


def latest_due(now):
    now=now.astimezone(VN)
    due=due_date(now.year,now.month)
    if now<due:
        due=due_date(now.year-1 if now.month==1 else now.year,12 if now.month==1 else now.month-1)
    return due


def next_due(now=None):
    now=(now or datetime.now(VN)).astimezone(VN)
    due=due_date(now.year,now.month)
    if now>=due:due=due_date(now.year+int(now.month==12),1 if now.month==12 else now.month+1)
    return due.isoformat()


def read_draft(period, conn=None, fresh=False):
    validate_period(period)
    if conn is None:
        with store.engine.connect() as c:return read_draft(period,c,fresh)
    saved=conn.execute(select(drafts).where(drafts.c.period==period)).mappings().first()
    if saved and not fresh:
        report={**saved['payload'],'revision':saved['revision'],'customized':True}
        if report['strategyLabel']=='KHCL Trường giai đoạn 2021-2025':report['strategyLabel']=DEFAULT_STRATEGY
        return paired_report(report)
    records=conn.execute(select(store.reports.c.payload).where(store.reports.c.mailbox==store.mailbox())).scalars().all()
    return {**compose(records,period),'revision':saved['revision'] if saved else 0,'customized':False}


def save_draft(period,data):
    validate_period(period)
    if set(data.sections) not in ({'a1','b1'},set(SECTIONS)) or any(len(v)>100000 for v in data.sections.values()):
        raise HTTPException(422,'Nội dung các phần chưa đúng hoặc quá dài.')
    with store.mutation() as conn:
        report=read_draft(period,conn)
        if data.revision!=report['revision']:raise HTTPException(409,'Báo cáo tháng vừa thay đổi. Hãy tải lại.')
        sections={**report['sections'],'a1':data.sections['a1'],'b1':data.sections['b1']}
        report.update(strategyLabel=data.strategyLabel,signatory=data.signatory,sections=sections,layoutVersion=LAYOUT,revision=data.revision+1,customized=True)
        report=paired_report(report)
        stmt=store.insert(drafts).values(period=period,payload=report,revision=report['revision'])
        conn.execute(stmt.on_conflict_do_update(index_elements=['period'],set_={'payload':stmt.excluded.payload,'revision':stmt.excluded.revision}))
    return report


def enqueue_due(now=None):
    now=(now or datetime.now(VN)).astimezone(VN)
    if os.getenv('MONTHLY_REPORTS_ENABLED','true').lower()!='true':return False
    due=latest_due(now);period=due.strftime('%Y-%m')
    with store.mutation() as conn:
        activation=conn.execute(select(store.workflow_settings.c.value).where(store.workflow_settings.c.key=='monthly_started')).scalar_one()
        if due<datetime.fromisoformat(activation):return False
        if conn.execute(select(batches.c.period).where(batches.c.period==period)).first():return False
        report=read_draft(period,conn)
        report['generatedAt']=now.isoformat()
        attachments=[{'name':f'mmlab-{report["planPeriod"]}-{variant}.docx','content':base64.b64encode(docx_bytes(report,variant)).decode(),
                      'subtype':'vnd.openxmlformats-officedocument.wordprocessingml.document'} for variant in ('discussion','school')]
        payload={'subject':f'[MMLab] Báo cáo thảo luận và kế hoạch tháng {report["planPeriod"]}',
                 'body':f'Kính gửi các thành viên MMLab,\n\nĐính kèm hai bản báo cáo:\n1. Bản thảo luận: công việc đã thực hiện tháng {period} và kế hoạch tháng {report["planPeriod"]}.\n2. Bản báo cáo nộp trường: chỉ bài báo, NCS và đề tài; Đã ở A.1 = A.2, Sẽ ở B.1 = B.2; đơn vị mã 6, chiến lược 2021–2030.\n\nVui lòng trao đổi về kết quả và kế hoạch công việc.\n\nTrân trọng,\nMMLab — UIT',
                 'attachments':attachments}
        conn.execute(store.insert(batches).values(period=period,payload=payload,created_at=now.isoformat()))
        assert len(DIRECTORY)==12 and len({m['email'] for m in DIRECTORY})==12
        for member in DIRECTORY:
            ident=hashlib.sha256(f'monthly:{period}:{member["email"]}'.encode()).hexdigest()
            conn.execute(store.insert(deliveries).values(id=ident,period=period,recipient=member['email'],status='pending',attempts=0,next_attempt=0))
    return True


def dispatch(sender=mailer.deliver):
    if mailer.mode()!='smtp':return
    with store.engine.connect() as conn:
        ids=conn.execute(select(deliveries.c.id).where(deliveries.c.status.in_(['pending','retry']),deliveries.c.next_attempt<=time.time()).limit(12)).scalars().all()
    for ident in ids:
        with store.mutation() as conn:
            row=conn.execute(select(deliveries).where(deliveries.c.id==ident)).mappings().one()
            if row['status'] not in ('pending','retry'):continue
            payload=conn.execute(select(batches.c.payload).where(batches.c.period==row['period'])).scalar_one()
            row=dict(row)
            conn.execute(update(deliveries).where(deliveries.c.id==ident).values(status='sending',attempts=row['attempts']+1))
        state,error=sender({**row,'payload':payload})
        if state=='retry' and row['attempts']>=4:state='failed'
        with store.mutation() as conn:
            conn.execute(update(deliveries).where(deliveries.c.id==ident,deliveries.c.status=='sending').values(
                status=state,last_error=error,sent_at=store.now() if state=='sent' else None,next_attempt=time.time()+min(3600,60*2**row['attempts'])))


def recover_interrupted():
    with store.mutation() as conn:
        conn.execute(update(deliveries).where(deliveries.c.status=='sending').values(status='unknown',last_error='Cần kiểm tra thư đã gửi trước khi gửi lại.'))


def schedule_info():
    with store.engine.connect() as conn:
        rows=conn.execute(select(deliveries.c.period,deliveries.c.status)).all()
    return {'enabled':os.getenv('MONTHLY_REPORTS_ENABLED','true').lower()=='true','nextRun':next_due(),
            'recipients':[{'name':m['name'],'email':m['email']} for m in DIRECTORY],
            'sent':sum(s=='sent' for _,s in rows),'needsAttention':sum(s in ('unknown','failed') for _,s in rows)}
