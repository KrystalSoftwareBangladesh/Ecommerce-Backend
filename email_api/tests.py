from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.template import TemplateSyntaxError
from django.test import TestCase
from django.utils import timezone

from email_api.constants import EmailStatus, EmailType
from email_api.models.email_log import EmailLog
from email_api.services.email import (
    EmailService,
    recover_stale_email_logs,
)
from email_api.tasks import send_email_task


DELAY = "email_api.tasks.send_email_task.delay"
SEND = "email_api.tasks.EmailService.send"


class EmailTestBase(TestCase):
    def _log(self, status=EmailStatus.PENDING, metadata=None, age=None):
        email_log = EmailLog.objects.create(
            email_type=EmailType.ORDER_CONFIRMATION,
            status=status,
            recipient="customer@example.com",
            sender="shop@example.com",
            subject="Order",
            metadata=metadata or {},
        )
        if age is not None:
            # update() bypasses auto_now so the log looks stale.
            EmailLog.objects.filter(pk=email_log.pk).update(
                updated_at=timezone.now() - age
            )
        return email_log


class QueueTest(EmailTestBase):
    def test_persisted_context_is_json_safe(self):
        with mock.patch(DELAY) as delay, \
                self.captureOnCommitCallbacks(execute=True):
            email_log = EmailService.queue(
                email_type=EmailType.ORDER_CONFIRMATION,
                recipient="customer@example.com",
                context={"total_amount": Decimal("1060.00")},
                persist_context=True,
            )
        email_log.refresh_from_db()
        self.assertEqual(
            email_log.metadata["context"], {"total_amount": "1060.00"}
        )
        delay.assert_called_once_with(
            email_log.id, {"total_amount": "1060.00"}
        )

    def test_context_is_not_stored_by_default(self):
        with mock.patch(DELAY), \
                self.captureOnCommitCallbacks(execute=True):
            email_log = EmailService.queue(
                email_type=EmailType.PASSWORD_RESET,
                recipient="customer@example.com",
                context={"reset_url": "https://example.com/secret"},
            )
        email_log.refresh_from_db()
        self.assertNotIn("context", email_log.metadata)

    def test_dispatch_failure_leaves_log_pending_with_reason(self):
        with mock.patch(DELAY, side_effect=ConnectionError("down")):
            with self.assertRaises(ConnectionError):
                with self.captureOnCommitCallbacks(execute=True):
                    email_log = EmailService.queue(
                        email_type=EmailType.ORDER_CONFIRMATION,
                        recipient="customer@example.com",
                        context={},
                        persist_context=True,
                    )
        email_log = EmailLog.objects.get()
        self.assertEqual(email_log.status, EmailStatus.PENDING)
        self.assertIn("Dispatch failed", email_log.error_message)


class SendTaskTest(EmailTestBase):
    def test_sends_once_even_if_task_runs_twice(self):
        email_log = self._log()
        with mock.patch(SEND) as send:
            send_email_task.apply(args=(email_log.id, {}))
            send_email_task.apply(args=(email_log.id, {}))
        send.assert_called_once()

    def test_does_not_resend_sent_or_failed_logs(self):
        for status in (EmailStatus.SENT, EmailStatus.FAILED):
            email_log = self._log(status=status)
            with mock.patch(SEND) as send:
                send_email_task.apply(args=(email_log.id, {}))
            send.assert_not_called()
            email_log.refresh_from_db()
            self.assertEqual(email_log.status, status)

    def test_render_error_marks_log_failed(self):
        email_log = self._log()
        with mock.patch(SEND, side_effect=TemplateSyntaxError("bad")):
            result = send_email_task.apply(args=(email_log.id, {}))
        self.assertTrue(result.failed())
        email_log.refresh_from_db()
        self.assertEqual(email_log.status, EmailStatus.FAILED)
        self.assertIn("TemplateSyntaxError", email_log.error_message)


class RecoverStaleEmailLogsTest(EmailTestBase):
    stale = timedelta(hours=1)

    def test_stale_processing_is_failed_not_resent(self):
        email_log = self._log(
            status=EmailStatus.PROCESSING, age=self.stale
        )
        with mock.patch(DELAY) as delay:
            result = recover_stale_email_logs()
        delay.assert_not_called()
        self.assertEqual(result, {"redispatched": 0, "failed": 1})
        email_log.refresh_from_db()
        self.assertEqual(email_log.status, EmailStatus.FAILED)

    def test_stale_pending_with_context_is_redispatched_once(self):
        email_log = self._log(
            metadata={"context": {"invoice_number": "INV-1"}},
            age=self.stale,
        )
        with mock.patch(DELAY) as delay:
            first = recover_stale_email_logs()
            # The log was just touched, so it is no longer stale.
            second = recover_stale_email_logs()
        delay.assert_called_once_with(
            email_log.id, {"invoice_number": "INV-1"}
        )
        self.assertEqual(first, {"redispatched": 1, "failed": 0})
        self.assertEqual(second, {"redispatched": 0, "failed": 0})
        email_log.refresh_from_db()
        self.assertEqual(email_log.status, EmailStatus.PENDING)
        self.assertEqual(email_log.metadata["recovery_attempts"], 1)

    def test_stale_pending_without_context_is_failed(self):
        email_log = self._log(age=self.stale)
        with mock.patch(DELAY) as delay:
            recover_stale_email_logs()
        delay.assert_not_called()
        email_log.refresh_from_db()
        self.assertEqual(email_log.status, EmailStatus.FAILED)
        self.assertIn("no stored context", email_log.error_message)

    def test_gives_up_after_max_attempts(self):
        email_log = self._log(
            metadata={"context": {}, "recovery_attempts": 3},
            age=self.stale,
        )
        with mock.patch(DELAY) as delay:
            recover_stale_email_logs(max_attempts=3)
        delay.assert_not_called()
        email_log.refresh_from_db()
        self.assertEqual(email_log.status, EmailStatus.FAILED)

    def test_dispatch_failure_during_recovery_keeps_log_pending(self):
        email_log = self._log(metadata={"context": {}}, age=self.stale)
        with mock.patch(DELAY, side_effect=ConnectionError("down")):
            result = recover_stale_email_logs()
        self.assertEqual(result, {"redispatched": 1, "failed": 0})
        email_log.refresh_from_db()
        self.assertEqual(email_log.status, EmailStatus.PENDING)
        self.assertIn("Dispatch failed", email_log.error_message)

    def test_recent_logs_are_untouched(self):
        pending = self._log(metadata={"context": {}})
        processing = self._log(status=EmailStatus.PROCESSING)
        with mock.patch(DELAY) as delay:
            result = recover_stale_email_logs()
        delay.assert_not_called()
        self.assertEqual(result, {"redispatched": 0, "failed": 0})
        for email_log, status in (
            (pending, EmailStatus.PENDING),
            (processing, EmailStatus.PROCESSING),
        ):
            email_log.refresh_from_db()
            self.assertEqual(email_log.status, status)


class BeatScheduleTest(TestCase):
    def test_scheduled_tasks_are_registered(self):
        from EcommerceBackend.celery import app

        app.loader.import_default_modules()
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            with self.subTest(entry=name):
                self.assertIn(entry["task"], app.tasks)
