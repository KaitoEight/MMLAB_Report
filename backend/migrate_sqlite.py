"""Copy persisted reports/snapshots from the native demo to the configured DB."""
import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
import store


def migrate(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('SQLite source file not found.')
    source = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        rows = source.execute('SELECT id,mailbox,payload FROM reports').fetchall()
        snapshots = source.execute('SELECT mailbox,payload FROM snapshots').fetchall()
        store.init_db()
        with store.engine.begin() as conn:
            for ident, mailbox, payload in rows:
                statement = store.insert(store.reports).values(id=ident, mailbox=mailbox, payload=json.loads(payload))
                conn.execute(statement.on_conflict_do_update(index_elements=['id'], set_={'payload':statement.excluded.payload}))
            for mailbox, payload in snapshots:
                incoming = json.loads(payload)
                existing = conn.execute(select(store.snapshots.c.payload).where(store.snapshots.c.mailbox==mailbox)).scalar_one_or_none()
                if existing and datetime.fromisoformat(existing['generatedAt']) > datetime.fromisoformat(incoming['generatedAt']):
                    continue
                statement = store.insert(store.snapshots).values(mailbox=mailbox,payload=incoming)
                conn.execute(statement.on_conflict_do_update(index_elements=['mailbox'], set_={'payload':statement.excluded.payload}))
        return len(rows)
    finally:
        source.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sqlite_path')
    args=parser.parse_args()
    print('Imported reports:',migrate(args.sqlite_path))
