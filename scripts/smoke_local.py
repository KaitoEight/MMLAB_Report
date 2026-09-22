"""Checks packaged native startup, static assets, authentication and real API import.
Uses only synthetic credentials/data in a temporary directory, never Gmail.
Run with the same Python environment as the backend.
"""
import hashlib
import http.cookiejar
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory() as directory:
        target=Path(directory)
        shutil.copy2(ROOT/'run_local.py',target/'run_local.py')
        shutil.copytree(ROOT/'backend',target/'backend',ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
        shutil.copytree(ROOT/'frontend/dist',target/'frontend/dist')
        (target/'secrets').mkdir()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        origin=f'http://localhost:{port}'
        (target/'.env').write_text(f'APP_PORT={port}\nAPP_ORIGIN={origin}\nADMIN_USER=admin\n')
        test_password='local-smoke-test-only'
        digest=hashlib.pbkdf2_hmac('sha256',test_password.encode(),b'local-test-salt',600000).hex()
        (target/'secrets/admin_password_hash.txt').write_text(f'pbkdf2_sha256$600000${b"local-test-salt".hex()}${digest}')
        (target/'secrets/session_key.txt').write_text('synthetic-local-session-key-more-than-32-characters')
        (target/'secrets/gmail_password.txt').write_text('')
        process=subprocess.Popen([sys.executable,str(target/'run_local.py')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=(os.name!='nt'))
        try:
            client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            for _ in range(40):
                if process.poll() is not None:raise RuntimeError('Native launcher exited early')
                try:
                    client.open(origin+'/api/health',timeout=1).close();break
                except OSError:time.sleep(.5)
            else:raise RuntimeError('Native server did not start')
            def post(path,data,method='POST'):
                req=urllib.request.Request(origin+path,data=json.dumps(data).encode(),headers={'Origin':origin,'Content-Type':'application/json'},method=method)
                with client.open(req,timeout=5) as response:return json.load(response)
            html=client.open(origin).read().decode()
            asset=re.search(r'src="([^"]+\.js)"',html)[1]
            assert len(client.open(origin+asset).read())>10000
            try:client.open(origin+'/api/reports');raise AssertionError('Private API accessible')
            except urllib.error.HTTPError as exc:assert exc.code==401
            post('/api/login',{'username':'admin','password':test_password})
            fixture=json.loads((ROOT/'backend/tests/fixture_export.json').read_text())
            post('/api/reports/import',fixture)
            data=json.load(client.open(origin+'/api/reports'))
            assert len(data['reports'])==len(fixture['reports'])
            for _ in range(20):
                data=json.load(client.open(origin+'/api/reports'))
                if data['worker']['online']:break
                time.sleep(.5)
            assert data['worker']['online']
            assert not data['configured']
            report=data['reports'][0]
            deleted=post('/api/reports/'+report['id'],{'revision':report.get('reportVersion',0)},method='DELETE')
            assert deleted=={'deleted':True}
            assert all(r['id']!=report['id'] for r in json.load(client.open(origin+'/api/reports'))['reports'])
            post('/api/reports/import',fixture)
            assert all(r['id']!=report['id'] for r in json.load(client.open(origin+'/api/reports'))['reports'])
            print('PASS native launcher, frontend assets, private login, import, worker heartbeat, HTTP DELETE and no resurrection after import.')
        finally:
            if os.name!='nt':os.killpg(process.pid,signal.SIGINT)
            else:process.send_signal(signal.CTRL_C_EVENT)
            try:output=process.communicate(timeout=15)[0]
            except subprocess.TimeoutExpired:process.kill();output=process.communicate()[0]
            if process.returncode not in (0,-2):print(output.decode(errors='replace')[-3000:])


if __name__=='__main__':main()
