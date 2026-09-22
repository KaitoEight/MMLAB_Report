import os
from pathlib import Path
from sqlalchemy import URL


def secret(name: str) -> str:
    path = os.getenv(name + '_FILE')
    return Path(path).read_text(encoding='utf-8').strip() if path else os.getenv(name, '')


def database_url():
    if os.getenv('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    return URL.create('postgresql+psycopg', username='mmlab', password=secret('POSTGRES_PASSWORD'),
                      host=os.getenv('DB_HOST', 'db'), database='mmlab')


def mailbox():
    return os.getenv('GMAIL_MAILBOX', 'mmlab@uit.edu.vn').strip().lower()


def interval():
    return max(60, int(os.getenv('POLL_SECONDS', '60')))


def configured():
    return bool(secret('MMLAB_APP_PASSWORD').replace(' ', ''))
