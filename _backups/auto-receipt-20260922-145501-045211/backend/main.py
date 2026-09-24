import hashlib
import hmac
import json
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.middleware.sessions import SessionMiddleware
from models import Bundle
from settings import configured, interval, mailbox, secret
import store
import intake
import mailer
import admin_reports
import monthly_service
from monthly_report import docx_bytes


@asynccontextmanager
async def lifespan(app):
    if len(secret('SESSION_KEY')) < 32 or not secret('ADMIN_PASSWORD_HASH'):
        raise RuntimeError('Chạy setup_local.py để tạo cấu hình đăng nhập.')
    store.init_db()
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=secret('SESSION_KEY'), session_cookie='mmlab_session',
                   max_age=8 * 3600, same_site='strict', https_only=os.getenv('COOKIE_SECURE', 'false') == 'true')
attempts = defaultdict(deque)


@app.middleware('http')
async def guard(request: Request, call_next):
    if request.url.path.startswith('/api/') and request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
        origins = {os.getenv('APP_ORIGIN', 'http://localhost:8080').rstrip('/')}
        if request.url.path == '/api/paper-confirm':
            origins.add(intake.public_base())
        if request.headers.get('origin') not in origins:
            return JSONResponse({'error': 'Nguồn yêu cầu không hợp lệ.'}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse({'error': exc.detail}, status_code=exc.status_code)


def authorized(request):
    if request.session.get('user') != os.getenv('ADMIN_USER', 'admin'):
        raise HTTPException(401, 'Cần đăng nhập.')


@app.get('/api/health')
def health():
    with store.engine.connect() as conn:
        conn.exec_driver_sql('SELECT 1')
    return {'ok': True}


class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=1024)


@app.post('/api/login')
def login(data: Login, request: Request):
    key = request.client.host if request.client else 'local'
    queue = attempts[key]
    while queue and time.monotonic() - queue[0] > 300:
        queue.popleft()
    if len(queue) >= 10:
        raise HTTPException(429, 'Thử đăng nhập quá nhiều lần. Đợi 5 phút.')
    queue.append(time.monotonic())
    try:
        algorithm, rounds, salt, expected = secret('ADMIN_PASSWORD_HASH').split('$')
        if algorithm != 'pbkdf2_sha256':
            raise ValueError('Unknown hash')
        actual = hashlib.pbkdf2_hmac('sha256', data.password.encode(), bytes.fromhex(salt), int(rounds)).hex()
    except (ValueError, OSError):
        raise HTTPException(503, 'Cấu hình đăng nhập chưa hợp lệ.')
    if not hmac.compare_digest(actual, expected) or not hmac.compare_digest(data.username, os.getenv('ADMIN_USER', 'admin')):
        raise HTTPException(401, 'Sai tên đăng nhập hoặc mật khẩu.')
    queue.clear()
    request.session.clear()
    request.session['user'] = data.username
    return {'username': data.username}


@app.get('/api/session')
def session(request: Request):
    authorized(request)
    return {'username': request.session['user']}


@app.post('/api/logout')
def logout(request: Request):
    request.session.clear()
    return {'ok': True}


@app.get('/api/reports')
def reports(request: Request):
    authorized(request)
    records, snapshot = store.read_reports()
    s = store.state()
    return {'configured': configured(), 'lastSync': s['finished_at'], 'mailbox': mailbox(), 'reports': records,
            'ignored': snapshot['summary']['ignored'] if snapshot else 0,
            'total': snapshot['summary']['processed'] if snapshot else 0,
            'importInfo': snapshot, 'worker': s, 'pollSeconds': interval(),
            'mailMode': mailer.mode(), 'mailDiagnostics':intake.diagnostics(s), 'intakes':intake.admin_list()}


def paper_token(request):
    value = request.headers.get('authorization','')
    if not value.startswith('Bearer '):
        raise HTTPException(404, 'Link không hợp lệ.')
    return value[7:]


@app.get('/api/paper-confirm')
def get_paper_form(request: Request):
    return intake.view(paper_token(request))


@app.post('/api/intakes/{ident}/reissue')
def reissue_paper_link(ident: str, request: Request):
    authorized(request)
    return intake.reissue(ident)


class ConfirmationMailRequest(BaseModel):
    revision: int = Field(strict=True,ge=0)
    resend: bool = Field(default=False,strict=True)


@app.get('/api/reports/{report_id}/confirmation')
def confirmation_details(report_id: str, request: Request):
    authorized(request)
    return intake.confirmation_info(report_id)


@app.post('/api/reports/{report_id}/admin-confirm')
def admin_confirm(report_id: str, data: admin_reports.ConfirmReport, request: Request):
    authorized(request)
    return admin_reports.confirm(report_id,data,request.session['user'])


@app.post('/api/reports/{report_id}/request-confirmation')
def request_confirmation(report_id: str, request: Request, data: ConfirmationMailRequest | None=None):
    authorized(request)
    return intake.create_for_report(report_id,revision=data.revision if data else None,resend=data.resend if data else False)


class PaperFields(BaseModel):
    title: str = Field(max_length=10000)
    authors: str = Field(max_length=30000)
    venue: str = Field(max_length=3000)
    role: str = Field(max_length=300)
    index: str = Field(max_length=1000)
    ranking: str = Field(max_length=300)


class PaperConfirmation(BaseModel):
    fields: PaperFields
    revision: int = Field(strict=True,ge=0)
    confirmed: bool = Field(strict=True)


@app.post('/api/paper-confirm')
def submit_paper(data: PaperConfirmation, request: Request):
    if not data.confirmed:raise HTTPException(400,'Vui lòng xác nhận đã kiểm tra thông tin.')
    result = intake.confirm(paper_token(request),data.fields.model_dump(),data.revision)
    return JSONResponse(result,status_code=200 if result['confirmed'] else 422)


@app.put('/api/reports/{report_id}')
def edit_report(report_id: str, data: admin_reports.EditReport, request: Request):
    authorized(request)
    return admin_reports.edit(report_id, data, request.session['user'])


@app.delete('/api/reports/{report_id}')
def delete_report(report_id: str, data: admin_reports.DeleteReport, request: Request):
    authorized(request)
    return admin_reports.delete(report_id, data.revision, request.session['user'])


@app.get('/api/monthly/schedule')
def monthly_schedule(request: Request):
    authorized(request)
    return monthly_service.schedule_info()


@app.get('/api/monthly/{period}')
def monthly_draft(period: str, request: Request, fresh: bool=False):
    authorized(request)
    try:return monthly_service.read_draft(period,fresh=fresh)
    except ValueError:raise HTTPException(422,'Kỳ phải có dạng YYYY-MM.')


@app.put('/api/monthly/{period}')
def save_monthly(period: str, data: monthly_service.DraftEdit, request: Request):
    authorized(request)
    try:return monthly_service.save_draft(period,data)
    except ValueError:raise HTTPException(422,'Kỳ phải có dạng YYYY-MM.')


@app.get('/api/monthly/{period}/{variant}.docx')
def download_monthly(period: str, variant: str, request: Request):
    authorized(request)
    try:
        report=monthly_service.read_draft(period)
        content=docx_bytes(report,variant)
    except ValueError:raise HTTPException(422,'Kỳ hoặc loại báo cáo không hợp lệ.')
    return Response(content,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    headers={'Content-Disposition':f'attachment; filename="mmlab-{period}-{variant}.docx"'})


@app.post('/api/gmail/sync', status_code=202)
def sync(request: Request):
    authorized(request)
    if not configured():
        raise HTTPException(409, 'Chưa cấu hình App Password. Chạy lại setup_local.py và khởi động lại worker.')
    store.set_state(requested=True)
    return {'queued': True}


@app.post('/api/reports/import')
async def import_reports(request: Request):
    authorized(request)
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > 15 * 1024 * 1024:
            raise HTTPException(413, 'File vượt 15 MB.')
    try:
        bundle = Bundle.model_validate_json(bytes(chunks))
        count = store.ingest(bundle)
    except ValidationError:
        raise HTTPException(400, 'File JSON sai cấu trúc, UID hoặc số liệu tổng.')
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {'imported': count, 'duplicate': False}


static = Path(os.getenv('STATIC_DIR', '/app/static'))
if static.is_dir():
    app.mount('/', StaticFiles(directory=static, html=True), name='dashboard')
