"""Optional Python-only Windows demo (SQLite); Docker uses PostgreSQL instead."""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    if not (ROOT / 'secrets/admin_password_hash.txt').exists():
        sys.exit('Run python setup_local.py first.')
    if not (ROOT / 'frontend/dist/index.html').exists():
        sys.exit('Frontend build missing. Run npm ci and npm run build inside frontend, or use the packaged ZIP.')
    env = os.environ.copy()
    for line in (ROOT / '.env').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key,value = line.split('=',1)
            env[key.strip()] = value.strip()
    for key,name in [('ADMIN_PASSWORD_HASH','admin_password_hash'),('SESSION_KEY','session_key'),('MMLAB_APP_PASSWORD','gmail_password')]:
        env[key + '_FILE'] = str(ROOT / 'secrets' / (name + '.txt'))
    data = ROOT / 'data'
    data.mkdir(exist_ok=True)
    env['DATABASE_URL'] = 'sqlite:///' + (data/'reports.sqlite3').as_posix()
    env['IMAP_OUTPUT'] = str(data/'imap')
    env['STATIC_DIR'] = str(ROOT/'frontend/dist')
    env['PYTHONUNBUFFERED'] = '1'
    port = env.get('APP_PORT','8080')
    mail_mode = env.get('MAIL_MODE', 'preview').strip().strip("\"'").lower()
    print('Email replies: ' + ('SMTP enabled' if mail_mode == 'smtp' else 'OFF / preview. Set MAIL_MODE=smtp in .env and restart to send.'), flush=True)
    print('Confirmation URL: ' + env.get('PUBLIC_BASE_URL', env.get('APP_ORIGIN', 'http://localhost:8080')), flush=True)
    processes=[]
    try:
        processes.append(subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port',port,'--no-proxy-headers','--no-access-log'],cwd=ROOT/'backend',env=env))
        for _ in range(60):
            if processes[0].poll() is not None:
                sys.exit('Backend failed to start. See error above.')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1) as r:
                    if r.status==200:break
            except OSError:time.sleep(1)
        else:sys.exit('Backend did not become ready.')
        processes.append(subprocess.Popen([sys.executable,'-u','worker.py'],cwd=ROOT/'backend',env=env))
        print(f'Open http://localhost:{port} | Keep this window open. Ctrl+C to stop.',flush=True)
        while all(p.poll() is None for p in processes):time.sleep(1)
    except KeyboardInterrupt:
        print('Stopping MMLab...')
    finally:
        for p in processes:
            if p.poll() is None:p.terminate()
        for p in processes:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait()


if __name__=='__main__':main()
