"""Interactive setup for Windows and Ubuntu; never embeds passwords in commands."""
import getpass
import hashlib
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def write_secret(name, value):
    path = ROOT / 'secrets' / (name + '.txt')
    path.write_text(value, encoding='utf-8')
    # Parent 0700 protects local files; container users need to read the mounted file.
    if os.name != 'nt':
        path.chmod(0o644)


def main():
    directory = ROOT / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    if not (ROOT / '.env').exists():
        (ROOT / '.env').write_bytes((ROOT / '.env.example').read_bytes())
    print('MMLab local setup | username: admin (can change ADMIN_USER in .env)')
    if not (directory / 'admin_password_hash.txt').exists() or input('Reset dashboard password? [y/N]: ').strip().lower() == 'y':
        while True:
            password = getpass.getpass('Dashboard password (at least 12 characters): ')
            if len(password) >= 12 and password == getpass.getpass('Confirm password: '):
                break
            print('Passwords must match and contain at least 12 characters.')
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600000).hex()
        write_secret('admin_password_hash', f'pbkdf2_sha256$600000${salt.hex()}${digest}')
        write_secret('session_key', secrets.token_urlsafe(48))
        password = ''
    for name in ['postgres_password', 'session_key']:
        if not (directory / (name + '.txt')).exists():
            write_secret(name, secrets.token_urlsafe(48))
    password = getpass.getpass('Gmail App Password (Enter = demo only / keep existing): ').replace(' ', '')
    if password or not (directory / 'gmail_password.txt').exists():
        write_secret('gmail_password', password)
    print('Configuration saved locally. Run: docker compose up -d --build')
    print('Open http://localhost:8080 | Login with your dashboard password.')


if __name__ == '__main__':
    main()
