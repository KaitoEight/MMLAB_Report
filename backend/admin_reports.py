"""Admin report editing and soft deletion; source email metadata stays immutable."""
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, update
from models import Member, MonthlyTasks
from mmlab_pipeline.members import resolve_members, member_matches
from mmlab_pipeline.validator import WorkReport, LABELS
from settings import mailbox
import store
import intake


class EditReport(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', str_strip_whitespace=True)
    revision: int = Field(ge=0)
    taskGroup: Literal['strategic','routine','unassigned'] = 'unassigned'
    type: Literal['Paper', 'Đề tài', 'NCS', 'Seminar', 'Giải thưởng', 'Báo cáo tháng']
    title: str = Field(min_length=1, max_length=10000)
    status: str = Field(default='', max_length=300)
    authors: str = Field(default='', max_length=30000)
    venue: str = Field(default='', max_length=3000)
    role: str = Field(default='', max_length=300)
    ranking: str = Field(default='', max_length=300)
    index: str = Field(default='', max_length=1000)
    memberId: Member | None = None
    memberIds: list[Member] = Field(default_factory=list, max_length=12)
    monthlyTasks: MonthlyTasks | None = None


class DeleteReport(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    revision: int = Field(ge=0)


class ConfirmReport(DeleteReport):
    confirmed: Literal[True]


def confirm(ident, data, admin):
    with store.mutation() as conn:
        report=current(conn,ident,data.revision)
        if report['type']!='Paper':raise HTTPException(409,'Chỉ xác nhận thông tin Paper tại đây.')
        if report.get('confirmationStatus')=='confirmed':
            return {'report':report,'alreadyConfirmed':True}
        fields={k:('' if LABELS[k] in report.get('missingFields',[]) else report.get(k) or '') for k in intake.FIELDS}
        model,errors=intake.validation(fields)
        if errors:
            raise HTTPException(422,'Cần sửa trước khi xác nhận: '+'; '.join(LABELS.get(e['field'],e['field'])+': '+e['reason'] for e in errors))
        ids=[m['id'] for m in resolve_members(model.authors)]
        if not ids:raise HTTPException(422,'Cần có ít nhất một thành viên lab trong danh sách tác giả trước khi admin xác nhận.')
        # Do not silently accept an ambiguous duplicate field from the source email.
        if report.get('invalidFields'):
            raise HTTPException(422,'Báo cáo còn lỗi trích xuất. Mở Sửa, kiểm tra và lưu thông tin trước khi xác nhận.')
        report.update({k:getattr(model,k) for k in intake.FIELDS})
        if report.get('memberId') not in ids:report['memberId']=None
        stamp=store.now()
        report.update(memberIds=ids,isValid=True,missingFields=[],invalidFields=[],
                      issues=[] if report.get('memberId') else ['Chưa xác định người phụ trách trong tác giả.'],
                      mappingEvidence=member_matches(model.authors,'Admin confirmed All authors'),
                      confirmationStatus='confirmed',confirmationSource='admin',confirmedBy=admin,confirmedAt=stamp,
                      reportVersion=data.revision+1,
                      warnings=['Thông tin được admin xác nhận; Index/Ranking chưa được xác minh bên ngoài.'])
        rows=conn.execute(select(store.intakes).where(store.intakes.c.report_id==ident,store.intakes.c.status!='cancelled')).mappings().all()
        for row in rows:
            conn.execute(update(store.intakes).where(store.intakes.c.id==row['id']).values(
                fields={k:report[k] for k in intake.FIELDS},original=report,status='confirmed',
                revision=row['revision']+1,confirmed_at=stamp))
            outgoing=conn.execute(select(store.outbox).where(store.outbox.c.id==row['id'])).mappings().first()
            if outgoing and outgoing['status'] in ('pending','retry'):
                payload=dict(outgoing['payload'])
                payload.update(intake.mail_content({**row,'fields':{k:report[k] for k in intake.FIELDS},'original':report},payload['link']))
                conn.execute(update(store.outbox).where(store.outbox.c.id==row['id']).values(payload=payload))
        conn.execute(update(store.reports).where(store.reports.c.id==ident).values(payload=report))
    return {'report':report,'alreadyConfirmed':False}


def current(conn, ident, revision):
    row = conn.execute(select(store.reports.c.payload).where(
        store.reports.c.id == ident, store.reports.c.mailbox == mailbox())).scalar_one_or_none()
    if not row or row.get('deletedAt'):
        raise HTTPException(404, 'Báo cáo không còn tồn tại.')
    if row.get('reportVersion', 0) != revision:
        raise HTTPException(409, 'Báo cáo vừa được thay đổi. Đóng form và mở lại dữ liệu mới trước khi lưu/xóa.')
    return dict(row)


def cancel_intakes(conn, ident):
    ids = select(store.intakes.c.id).where(store.intakes.c.report_id == ident)
    conn.execute(update(store.outbox).where(store.outbox.c.id.in_(ids),
        store.outbox.c.status != 'sent').values(status='cancelled', last_error='Admin đã xóa hoặc đổi loại báo cáo.'))
    conn.execute(update(store.intakes).where(store.intakes.c.report_id == ident).values(status='cancelled', expires=0))


def edit(ident, data, admin):
    with store.mutation() as conn:
        report = current(conn, ident, data.revision)
        was_confirmed=report.get('confirmationStatus')=='confirmed'
        if was_confirmed:
            history=list(report.get('confirmationHistory',[]))
            history.append({k:report.get(k) for k in ('confirmationSource','confirmedBy','confirmedAt','reportVersion')})
            report['confirmationHistory']=history
            report['confirmationStatus']='pending'
            for key in ('confirmationSource','confirmedBy','confirmedAt'):report.pop(key,None)
        report.update(data.model_dump(exclude={'revision'}))
        report.update(issues=[], warnings=[], missingFields=[], invalidFields=[],
                      isValid=True, reportVersion=data.revision+1,
                      adminEditedAt=store.now(), adminEditedBy=admin)
        if data.type in ('Paper', 'Đề tài'):
            values = {k: getattr(data, k) for k in intake.FIELDS}
            try:
                work = WorkReport.model_validate({'report_type': data.type, **values})
                report.update({k: getattr(work, k) for k in intake.FIELDS})
            except ValidationError as exc:
                report['isValid'] = False
                for error in exc.errors(include_url=False, include_context=False):
                    key = error['loc'][0]
                    label = LABELS.get(key, key)
                    if not values.get(key):
                        report['missingFields'].append(label)
                    else:
                        report['invalidFields'].append({'field':label,'value':values.get(key),'reason':error['msg']})
                    report['issues'].append(f"{label}: {error['msg']}")
            report['memberIds'] = [m['id'] for m in resolve_members(data.authors)]
            report['mappingEvidence'] = member_matches(data.authors, 'Admin All authors')
            report['monthlyTasks'] = None
            report['reportPeriod'] = None
            if report['memberId'] not in report['memberIds']:
                report['memberId'] = None
                report['issues'].append('Chưa xác định người phụ trách trong danh sách tác giả.')
            report['warnings'] = ['Index/Ranking là thông tin khai báo, chưa xác minh bên ngoài.']
        else:
            report['memberIds'] = sorted(set(data.memberIds + ([data.memberId] if data.memberId else [])))
            report['mappingEvidence'] = []
            report['warnings'] = ['Thành viên do admin lựa chọn.']
            for key in ('status', 'authors', 'venue', 'role', 'ranking', 'index'):
                report[key] = ''
            if data.type == 'Báo cáo tháng':
                report['monthlyTasksVersion']=2
                report['monthlyTasks'] = data.monthlyTasks.model_dump() if data.monthlyTasks else {'done':None,'planned':None}
                report['reportPeriod'] = report['date'][:7]
            else:
                report['monthlyTasks'] = None
                report['reportPeriod'] = None
        if not report['memberIds']:
            report['issues'].append('Chưa xác định thành viên lab.')
            if data.type == 'Báo cáo tháng':
                report['isValid'] = False
        report['index'] = report['index'] or None
        row = conn.execute(select(store.intakes).where(
            store.intakes.c.report_id == ident, store.intakes.c.status != 'cancelled')).mappings().first()
        if row and data.type == 'Paper':
            row = dict(row)
            fields = {k: report.get(k) or '' for k in intake.FIELDS}
            # A pending public form stays accessible, but stale submissions fail.
            conn.execute(update(store.intakes).where(store.intakes.c.id == row['id']).values(
                fields=fields, original=report, revision=row['revision']+1,
                status='pending' if was_confirmed else row['status'],confirmed_at=None if was_confirmed else row['confirmed_at']))
            outgoing = conn.execute(select(store.outbox).where(store.outbox.c.id == row['id'])).mappings().first()
            if outgoing and outgoing['status'] in ('pending', 'retry'):
                row.update(fields=fields, original=report)
                payload = intake.mail_content(row, outgoing['payload']['link'])
                if 'delivery_id' in outgoing['payload']:
                    payload['delivery_id'] = outgoing['payload']['delivery_id']
                conn.execute(update(store.outbox).where(store.outbox.c.id == row['id'],
                    store.outbox.c.status.in_(['pending','retry'])).values(payload=payload))
        elif data.type != 'Paper':
            cancel_intakes(conn, ident)
            for key in ('confirmationStatus','confirmedAt','intakeId','receiptIssue'):
                report.pop(key, None)
        conn.execute(update(store.reports).where(store.reports.c.id == ident).values(payload=report))
    return {'report': report}


def delete(ident, revision, admin):
    with store.mutation() as conn:
        report = current(conn, ident, revision)
        report.update(deletedAt=store.now(), deletedBy=admin, reportVersion=revision+1)
        cancel_intakes(conn, ident)
        conn.execute(update(store.reports).where(store.reports.c.id == ident).values(payload=report))
    return {'deleted': True}
