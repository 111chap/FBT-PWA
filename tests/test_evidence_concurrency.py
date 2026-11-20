import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest import skipUnless
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import connection,close_old_connections,connections
from django.test import Client,TransactionTestCase,override_settings
from django.utils import timezone
from tracker.models import Bill,Payment,ReceiptRevision,PushSubscription,ReminderDelivery
from tracker.services import deliver_reminders
from tests.media_helpers import receipt


@skipUnless(connection.vendor=='postgresql','Concurrency requires PostgreSQL.')
@override_settings(SECURE_SSL_REDIRECT=False)
class EvidenceConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('evidence-concurrency-fixture',password='Fictional-passphrase-42!')
        self.bill=Bill.objects.create(title='Fictional parallel bill',amount='100',due_date=timezone.localdate(),created_by=self.user,responsible=self.user)

    def test_parallel_retries_commit_one_payment_and_one_evidence_revision(self):
        asset=receipt(self.bill,self.user);barrier=Barrier(2);key=str(uuid.uuid4())
        payload={'receipt_id':str(asset.pk),'amount':'40','paid_date':timezone.localdate().isoformat(),'request_key':key}
        def pay(_):
            close_old_connections()
            try:
                client=Client();client.force_login(get_user_model().objects.get(pk=self.user.pk));barrier.wait(timeout=15)
                return client.post(f'/api/bills/{self.bill.pk}/payments/',json.dumps(payload),content_type='application/json').status_code
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(pay,[1,2]))
        self.assertEqual(sorted(results),[200,201]);self.assertEqual(Payment.objects.count(),1);self.assertEqual(ReceiptRevision.objects.count(),1)

    @override_settings(VAPID_PUBLIC_KEY='fixture',VAPID_PRIVATE_KEY='fixture',VAPID_SUBJECT='mailto:fixture@example.test')
    @patch('tracker.services.send_push')
    def test_parallel_scheduler_invocations_suppress_duplicate_milestones(self,send):
        now=datetime(2026,12,25,10,tzinfo=ZoneInfo('Asia/Manila'))
        self.bill.due_date=now.date();self.bill.save()
        PushSubscription.objects.create(user=self.user,endpoint='https://fcm.googleapis.com/fcm/send/fixture',keys={})
        barrier=Barrier(2)
        def dispatch(_):
            close_old_connections()
            try:barrier.wait(timeout=15);deliver_reminders(now)
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(dispatch,[1,2]))
        self.assertEqual(send.call_count,1);self.assertEqual(ReminderDelivery.objects.get().attempts,1)
