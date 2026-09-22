import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent
temp = tempfile.TemporaryDirectory()
os.environ.update(DATABASE_URL='sqlite:///' + str(Path(temp.name) / 'test.sqlite3'),
                  SESSION_KEY='test-session-key-that-is-at-least-32-characters',
                  ADMIN_PASSWORD_HASH='pbkdf2_sha256$600000$' + '12' * 16 + '$' + hashlib.pbkdf2_hmac('sha256', b'test-password-123', bytes.fromhex('12' * 16), 600000).hex(),
                  APP_ORIGIN='http://testserver', MMLAB_APP_PASSWORD='')

import pytest
from fastapi.testclient import TestClient
from main import app, attempts
from models import Bundle
import store
import worker


@pytest.fixture
def client():
    attempts.clear()
    with TestClient(app) as c:
        with store.engine.begin() as db:
            db.execute(store.reports.delete())
            db.execute(store.snapshots.delete())
        yield c


def login(client):
    r = client.post('/api/login', headers={'Origin': 'http://testserver'}, json={'username': 'admin', 'password': 'test-password-123'})
    assert r.status_code == 200
    assert 'httponly' in r.headers['set-cookie'].lower()
    assert 'samesite=strict' in r.headers['set-cookie'].lower()


def bundle():
    return json.loads((ROOT / 'fixture_export.json').read_text())


def test_login_csrf_logout_and_private_data(client):
    assert client.get('/api/reports').status_code == 401
    assert client.get('/api/reports', headers={'oai-authenticated-user-id':'fake','oai-authenticated-user-email':'fake@test'}).status_code == 401
    assert client.post('/api/login', json={'username':'admin','password':'test-password-123'}).status_code == 403
    login(client)
    assert client.get('/api/reports').status_code == 200
    assert client.post('/api/logout', headers={'Origin':'https://foreign.test'}).status_code == 403
    assert client.post('/api/logout', headers={'Origin':'http://testserver'}).status_code == 200
    assert client.get('/api/reports').status_code == 401


def test_real_python_export_import_and_idempotence(client):
    login(client)
    b = bundle()
    for _ in range(2):
        r = client.post('/api/reports/import', headers={'Origin':'http://testserver'}, json=b)
        assert r.status_code == 200, r.text
    data = client.get('/api/reports').json()
    assert len(data['reports']) == len(b['reports'])
    assert data['reports'][0]['memberIds'] == b['reports'][0]['memberIds']
    assert data['importInfo']['summary'] == b['summary']


@pytest.mark.parametrize('defect', ['member','date','count','uid','mailbox','duplicate','bool'])
def test_reject_corrupt_import_before_writes(client, defect):
    login(client)
    b = bundle()
    if defect == 'member': b['reports'][0]['memberIds'] = [13]
    if defect == 'date': b['reports'][0]['date'] = '2026-02-30'
    if defect == 'count': b['summary']['valid'] += 1
    if defect == 'uid': b['reports'][0]['sourceId'] = 'imap:other@example.com:INBOX:123:17'
    if defect == 'mailbox': b['mailbox'] = 'other@example.com'
    if defect == 'duplicate': b['reports'].append(copy.deepcopy(b['reports'][0]))
    if defect == 'bool': b['reports'][0]['memberIds'] = [True]
    assert client.post('/api/reports/import', headers={'Origin':'http://testserver'}, json=b).status_code == 400
    assert client.get('/api/reports').json()['reports'] == []


def test_worker_ingests_without_browser_upload_and_failure_keeps_data(client, monkeypatch):
    monkeypatch.setenv('IMAP_OUTPUT', temp.name)
    def fake_fetch(account, password, folder, output, progress):
        progress(1,1)
        (output/'mmlab_export.json').write_text(json.dumps(bundle()))
    worker.run_once(fetcher=fake_fetch)
    login(client)
    first = client.get('/api/reports').json()
    assert len(first['reports']) == len(bundle()['reports'])
    assert first['lastSync']
    def fail(*args, **kwargs):raise OSError('secret must not reach UI')
    worker.run_once(fetcher=fail)
    second = client.get('/api/reports').json()
    assert second['reports'] == first['reports']
    assert second['lastSync'] == first['lastSync']
    assert 'secret must not reach UI' not in second['worker']['error']
    assert not second['worker']['running']


def test_sync_requires_config_and_enqueues(client, monkeypatch):
    login(client)
    assert client.post('/api/gmail/sync', headers={'Origin':'http://testserver'}).status_code == 409
    monkeypatch.setenv('MMLAB_APP_PASSWORD','fake-test-only')
    assert client.post('/api/gmail/sync', headers={'Origin':'http://testserver'}).status_code == 202
    assert store.state()['requested'] is True


def test_login_rate_limit(client):
    for _ in range(10):
        assert client.post('/api/login',headers={'Origin':'http://testserver'},json={'username':'admin','password':'bad'}).status_code == 401
    assert client.post('/api/login',headers={'Origin':'http://testserver'},json={'username':'admin','password':'bad'}).status_code == 429
