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


# ── Order notifications ──────────────────────


class OrderNotificationTestBase(TestCase):
    def setUp(self):
        from account_api.models import AccountType, ChartOfAccount
        from customer_api.models import CustomerProfile
        from product_api.models import Product, ProductVariant
        from user_api.models import User

        self.staff_user = User.objects.create_user(
            username="notify-staff",
            email="notify-staff@example.com",
            password="test-pass-123",
            role="STAFF",
            first_name="Rina",
        )
        self.customer_user = User.objects.create_user(
            username="notify-customer",
            email="notify-customer@example.com",
            password="test-pass-123",
            role="CUSTOMER",
            first_name="Karim",
        )
        self.customer = CustomerProfile.objects.create(
            user=self.customer_user,
        )
        product = Product.objects.create(
            name="Notify Product",
            current_selling_price=Decimal("100.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            sku="NOTIFY-001",
        )
        self.cash_account = ChartOfAccount.objects.create(
            name="Cash",
            account_type=AccountType.ASSET,
        )

    def _recipient(self, email, **kwargs):
        from email_api.models import OrderNotificationRecipient

        return OrderNotificationRecipient.objects.create(
            email=email, **kwargs
        )

    def _create_sale(self, channel=None):
        from datetime import date

        from sale_api.services import create_sale

        payload = {
            "customer": self.customer,
            "account": self.cash_account,
            "sale_date": date(2026, 11, 1),
            "discount_amount": Decimal("0.00"),
            "tax_amount": Decimal("0.00"),
            "items": [{
                "product_variant": self.variant,
                "quantity": 3,
                "unit_price": Decimal("100.00"),
                "line_total": Decimal("300.00"),
            }],
        }
        if channel:
            payload["channel"] = channel
        with mock.patch(DELAY), \
                self.captureOnCommitCallbacks(execute=True):
            return create_sale(self.staff_user, payload)

    def _notification_logs(self, email_type):
        return EmailLog.objects.filter(email_type=email_type)


class OrderPlacedNotificationTest(OrderNotificationTestBase):
    def test_new_sale_notifies_each_active_recipient(self):
        from django.utils import timezone as tz

        self._recipient("ops@example.com")
        self._recipient("warehouse@example.com")
        self._recipient("paused@example.com", is_active=False)
        self._recipient("gone@example.com", deleted_at=tz.now())

        with self.settings(FRONTEND_BASE_URL="https://shop.example/"):
            sale = self._create_sale()

        logs = self._notification_logs(
            EmailType.ORDER_PLACED_NOTIFICATION
        )
        self.assertEqual(
            sorted(logs.values_list("recipient", flat=True)),
            ["ops@example.com", "warehouse@example.com"],
        )
        log = logs.first()
        self.assertIsNone(log.related_user)
        self.assertEqual(log.metadata["sale_id"], sale.id)
        self.assertIn(sale.invoice_number, log.subject)
        context = log.metadata["context"]
        self.assertEqual(context["item_count"], 3)
        self.assertEqual(context["customer_name"], "Karim")
        self.assertEqual(
            context["order_admin_url"],
            f"https://shop.example/admin/orders/{sale.id}/",
        )

    def test_no_recipients_queues_nothing(self):
        self._create_sale()

        self.assertFalse(
            self._notification_logs(
                EmailType.ORDER_PLACED_NOTIFICATION
            ).exists()
        )

    def test_requeue_does_not_duplicate(self):
        from email_api.services import queue_order_notifications

        self._recipient("ops@example.com")
        sale = self._create_sale()

        with mock.patch(DELAY), \
                self.captureOnCommitCallbacks(execute=True):
            queue_order_notifications(
                sale.id, EmailType.ORDER_PLACED_NOTIFICATION
            )

        self.assertEqual(
            self._notification_logs(
                EmailType.ORDER_PLACED_NOTIFICATION
            ).count(),
            1,
        )

    def test_queue_failure_does_not_break_the_sale(self):
        from sale_api.models import Sale

        self._recipient("ops@example.com")
        with mock.patch(
            "email_api.services.order_notification.EmailService.queue",
            side_effect=RuntimeError("boom"),
        ):
            sale = self._create_sale()

        self.assertTrue(Sale.objects.filter(pk=sale.pk).exists())


class OrderCancelledNotificationTest(OrderNotificationTestBase):
    def test_staff_cancellation_notifies_recipients(self):
        from sale_api.models import SaleStatus
        from sale_api.services import update_sale_status

        self._recipient("ops@example.com")
        sale = self._create_sale()

        with mock.patch(DELAY), \
                self.captureOnCommitCallbacks(execute=True):
            update_sale_status(
                self.staff_user, sale, SaleStatus.CANCELLED
            )

        log = self._notification_logs(
            EmailType.ORDER_CANCELLED_NOTIFICATION
        ).get()
        self.assertEqual(log.recipient, "ops@example.com")
        self.assertEqual(
            log.metadata["context"]["cancelled_by"], "staff (Rina)"
        )

    def test_customer_cancellation_notifies_recipients(self):
        from checkout_api.services import cancel_order
        from sale_api.models import Sale

        self._recipient("ops@example.com")
        sale = self._create_sale(channel=Sale.SaleChannel.WEBSITE)

        with mock.patch(DELAY), \
                self.captureOnCommitCallbacks(execute=True):
            cancel_order(user=self.customer_user, sale=sale)

        log = self._notification_logs(
            EmailType.ORDER_CANCELLED_NOTIFICATION
        ).get()
        self.assertEqual(
            log.metadata["context"]["cancelled_by"], "the customer"
        )


class OrderNotificationRecipientApiTest(TestCase):
    URL = "/api/v1/email/order-notification-recipients/"

    def setUp(self):
        from django.contrib.auth.models import Permission
        from rest_framework.test import APIClient

        from user_api.models import User

        self.client = APIClient()
        self.manager = User.objects.create_user(
            username="notify-manager",
            email="manager@example.com",
            password="test-pass-123",
            role="STAFF",
        )
        self.manager.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="email_api",
            codename__endswith="ordernotificationrecipient",
        ))
        self.outsider = User.objects.create_user(
            username="notify-outsider",
            email="outsider@example.com",
            password="test-pass-123",
            role="STAFF",
        )

    def test_user_without_permission_is_forbidden(self):
        self.client.force_authenticate(self.outsider)

        self.assertEqual(self.client.get(self.URL).status_code, 403)
        self.assertEqual(
            self.client.post(
                self.URL, {"email": "a@example.com"}
            ).status_code,
            403,
        )

    def test_create_normalizes_and_rejects_duplicates(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            self.URL, {"email": " Ops@Example.com ", "name": "Ops"}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["email"], "ops@example.com")

        duplicate = self.client.post(self.URL, {"email": "OPS@example.com"})
        self.assertEqual(duplicate.status_code, 400)

    def test_delete_is_soft_and_email_can_be_added_again(self):
        from email_api.models import OrderNotificationRecipient

        self.client.force_authenticate(self.manager)
        created = self.client.post(self.URL, {"email": "ops@example.com"})

        deleted = self.client.delete(f"{self.URL}{created.data['id']}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get(self.URL).data["count"], 0)
        self.assertIsNotNone(
            OrderNotificationRecipient.objects.get(
                pk=created.data["id"]
            ).deleted_at
        )

        again = self.client.post(self.URL, {"email": "ops@example.com"})
        self.assertEqual(again.status_code, 201)

    def test_toggle_active(self):
        self.client.force_authenticate(self.manager)
        created = self.client.post(self.URL, {"email": "ops@example.com"})

        response = self.client.patch(
            f"{self.URL}{created.data['id']}/", {"is_active": False}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])
