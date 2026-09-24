"""Binary-safe PostgreSQL backup, works in Windows PowerShell and on Ubuntu."""
from datetime import datetime
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
out = root/'backups'
out.mkdir(exist_ok=True)
target = out/('mmlab-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.dump')
try:
    with target.open('wb') as stream:
        subprocess.run(['docker','compose','exec','-T','db','pg_dump','-U','mmlab','-d','mmlab','-Fc'],cwd=root,stdout=stream,check=True)
except Exception:
    target.unlink(missing_ok=True)
    raise
print('Saved:',target)
