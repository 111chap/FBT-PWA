from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from tracker.models import Bill, Payment, PushSubscription, ReminderDelivery, WorkerHeartbeat
from tracker.services import deliver_reminders
import uuid


@override_settings(SECURE_SSL_REDIRECT=False,VAPID_PUBLIC_KEY='test-public',VAPID_PRIVATE_KEY='test-private',VAPID_SUBJECT='mailto:test@example.com')
class ReminderTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('family',password='test-password-1234')
        self.now=datetime(2026,11,20,10,tzinfo=ZoneInfo('Asia/Manila'))
        self.bill=Bill.objects.create(title='Electricity',amount='100',due_date=self.now.date(),created_by=self.user,responsible=self.user)
        self.subscription=PushSubscription.objects.create(user=self.user,endpoint='https://fcm.googleapis.com/fcm/send/test',keys={})

    @patch('tracker.services.send_push')
    def test_worker_restart_does_not_resend_delivered_reminder_same_day(self,send):
        deliver_reminders(self.now); deliver_reminders(self.now)
        self.assertEqual(send.call_count,1)
        self.assertIsNotNone(ReminderDelivery.objects.get().delivered_at)

    @patch('tracker.services.send_push')
    def test_paid_bill_suppresses_notification(self,send):
        Payment.objects.create(receipt_required=False,bill=self.bill,amount='100',paid_date=self.now.date(),recorded_by=self.user,request_key=uuid.uuid4())
        deliver_reminders(self.now)
        send.assert_not_called()

    @patch('tracker.services.send_push',side_effect=TimeoutError)
    def test_temporary_failure_retries_with_daily_cap(self,send):
        for _ in range(5): deliver_reminders(self.now)
        self.assertEqual(send.call_count,3)
        self.assertIsNone(ReminderDelivery.objects.get().delivered_at)

    @patch('tracker.services.send_push')
    def test_quiet_hours_suppress_notification(self,send):
        deliver_reminders(self.now.replace(hour=22))
        send.assert_not_called()

    def test_health_reports_missing_stale_and_live_worker_honestly(self):
        self.client.force_login(self.user)
        worker=lambda: next(c for c in self.client.get('/api/status/').json()['checks'] if c['name']=='Reminder worker')
        self.assertEqual(worker()['state'],'error')
        WorkerHeartbeat.objects.create(name='reminders',updated_at=timezone.now()-timedelta(minutes=5))
        self.assertEqual(worker()['state'],'error')
        call_command('reminder_worker',once=True)
        self.assertEqual(worker()['state'],'healthy')

    @override_settings(VAPID_PRIVATE_KEY='')
    def test_missing_push_configuration_is_not_shown_as_healthy(self):
        self.client.force_login(self.user)
        checks=self.client.get('/api/status/').json()['checks']
        self.assertEqual(next(c for c in checks if c['name']=='Push delivery')['state'],'warning')
