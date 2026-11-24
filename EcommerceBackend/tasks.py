# Dump command:
#   pg_dump -h <host> -p <port> -U <user> <db_name> \
#       -f db_backup/<db_name>_<timestamp>.sql
# Restore command:
#   psql -h <host> -p <port> -U <user> <db_name> \
#       -f db_backup/<db_name>_<timestamp>.sql
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import connection

from celery import shared_task

BACKUP_DIR = Path(settings.BASE_DIR) / "db_backup"
BACKUP_KEEP_DAYS = 7


@shared_task
def dump_database_task():
    """Periodic task scheduled by Celery Beat (CELERY_BEAT_SCHEDULE)."""
    db = connection.settings_dict
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"{db['NAME']}_{stamp}.sql"

    cmd = ["pg_dump"]
    if db.get("HOST"):
        cmd += ["-h", str(db["HOST"])]
    if db.get("PORT"):
        cmd += ["-p", str(db["PORT"])]
    cmd += ["-U", str(db["USER"]), str(db["NAME"])]

    env = os.environ.copy()
    if db.get("PASSWORD"):
        env["PGPASSWORD"] = str(db["PASSWORD"])

    try:
        with open(path, "w") as dump_file:
            subprocess.run(cmd, stdout=dump_file, env=env, check=True)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {"file": path.name}


@shared_task
def cleanup_old_db_backups_task():
    """Periodic task scheduled by Celery Beat (CELERY_BEAT_SCHEDULE)."""
    cutoff = time.time() - BACKUP_KEEP_DAYS * 24 * 60 * 60
    deleted = 0
    for path in BACKUP_DIR.glob("*.sql"):
        if path.stat().st_mtime < cutoff:
            path.unlink()
            deleted += 1
    return {"deleted": deleted}
