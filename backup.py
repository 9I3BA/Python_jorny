"""
Standalone backup script — run independently of Flask.

Usage:
    python backup.py

Schedule via Windows Task Scheduler or cron to run every few hours.
Creates a timestamped copy of platform.db in the backups/ folder.
Keeps only the last MAX_BACKUPS files.
"""
import glob
import os
import sqlite3
from datetime import datetime

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR  = os.path.join(BASE_DIR, 'backups')
DB_PATH     = os.path.join(BASE_DIR, 'instance', 'platform.db')
MAX_BACKUPS = 20


def create_backup(label='scheduled'):
    if not os.path.isfile(DB_PATH):
        print(f'[backup] ERROR: database not found at {DB_PATH}')
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = f'backup_{label}_{ts}.db'
    dest = os.path.join(BACKUP_DIR, name)

    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dest)
    src.backup(dst)
    dst.close()
    src.close()

    # prune oldest backups
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, 'backup_*.db')))
    while len(files) > MAX_BACKUPS:
        removed = files.pop(0)
        os.remove(removed)
        print(f'[backup] removed old backup: {os.path.basename(removed)}')

    size_kb = os.path.getsize(dest) / 1024
    print(f'[backup] created: {name}  ({size_kb:.1f} KB)')
    return name


if __name__ == '__main__':
    create_backup()
