# Deployment: Celery worker and Celery Beat

Storefront orders and email delivery depend on two background processes
besides Gunicorn. Neither is started by the GitHub deploy workflows today;
they must be installed and managed on each server.

## What runs where

| Process | Command | Needed for |
|---|---|---|
| Gunicorn | `ecommerce-backend.service` (restarted by the deploy workflow) | the API |
| Celery worker | `celery -A EcommerceBackend worker --loglevel=INFO` | sending emails, running scheduled tasks |
| Celery Beat | `celery -A EcommerceBackend beat --loglevel=INFO --schedule <writable path>/celerybeat-schedule` | scheduling the periodic tasks below |
| Redis | broker at `CELERY_BROKER_URL_SETTINGS` | both Celery processes |

Run **exactly one** Beat process per deployment (database). Two Beat
processes enqueue every task twice; the tasks are idempotent, but it wastes
work. Workers can be scaled freely.

## Scheduled tasks (`CELERY_BEAT_SCHEDULE` in `EcommerceBackend/settings.py`)

| Entry | Task | Every | What it does |
|---|---|---|---|
| `expire-pending-orders` | `checkout_api.tasks.expire_pending_orders_task` | 5 min | Cancels PENDING storefront orders whose stock reservation expired, releases their stock and emails the customer. Then releases any other expired reservations. |
| `recover-stale-email-logs` | `email_api.tasks.recover_stale_email_logs_task` | 10 min | Re-dispatches emails stuck in PENDING for 15+ minutes (order emails only; at most 3 times) and marks emails stuck in PROCESSING as FAILED. |

Both are safe to run concurrently and to rerun. The same work can be run by
hand:

```bash
python manage.py expire_pending_orders
```

If Beat is not running, expired storefront orders stay PENDING (they still
cannot be confirmed) and lost order emails are never retried.

## Environment and settings

From `EcommerceBackend/env.py` (copied from `.env.example`; never commit it):

- `CELERY_BROKER_URL_SETTINGS` — Redis URL used by the API, worker and Beat.
  All three must point at the same broker.
- `FRONTEND_BASE_URL_SETTINGS` — storefront URL used in order email links.
- SMTP settings (`SMTP_*_SETTINGS`, `EMAIL_FROM_SETTINGS`) — used by the
  worker, which is where emails are actually sent.

In `EcommerceBackend/settings.py` (not environment-driven):

- `CHECKOUT_RESERVATION_MINUTES = 30` — how long a storefront order holds
  its stock. Because expired orders are now cancelled automatically, this is
  also the window staff have to confirm a new order.

## Example systemd units

Adjust paths, user and unit names to the server. These are examples only;
the deploy workflows do not reference them.

```ini
# /etc/systemd/system/ecommerce-celery-worker.service
[Unit]
Description=Ecommerce Celery worker
After=network.target redis-server.service

[Service]
User=<deploy user>
WorkingDirectory=<project path>
ExecStart=<project path>/env/bin/celery -A EcommerceBackend worker --loglevel=INFO
Restart=always

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/ecommerce-celery-beat.service
[Unit]
Description=Ecommerce Celery Beat
After=network.target redis-server.service

[Service]
User=<deploy user>
WorkingDirectory=<project path>
ExecStart=<project path>/env/bin/celery -A EcommerceBackend beat --loglevel=INFO --schedule /var/lib/ecommerce/celerybeat-schedule
Restart=always

[Install]
WantedBy=multi-user.target
```

## Deploy implications

- The workflows only restart Gunicorn. After a deploy that changes task
  code (any `tasks.py`, `email_api/services/email.py`,
  `checkout_api/services.py`, settings), restart the worker and Beat too,
  or they keep running the old code.
- Migrations run before Gunicorn restarts; the worker should be restarted
  after `migrate`.
- Adding `sudo systemctl restart <worker> <beat>` to the workflows is a
  deliberate follow-up once the unit names exist on every server: the
  workflow scripts run with `set -e`, so a missing unit fails the deploy.
