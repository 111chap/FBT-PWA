import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.db import connection, connections, close_old_connections, transaction, IntegrityError
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone
from tests.media_helpers import receipt
from tracker.models import Bill, Payment, Loan, MutationReceipt


@skipUnless(connection.vendor == 'postgresql', 'Row locking must be verified against PostgreSQL.')
@override_settings(SECURE_SSL_REDIRECT=False)
class ConcurrentPaymentTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('concurrency', password='testing-concurrent-payments-123')
        self.bill = Bill.objects.create(title='Shared bill',amount='1000.00',due_date=timezone.localdate(),responsible=self.user,created_by=self.user)

    def test_two_members_cannot_overpay_the_same_balance(self):
        assets=[str(receipt(self.bill,self.user).pk) for _ in range(2)]
        barrier = Barrier(2)
        def pay(_):
            close_old_connections()
            try:
                client = Client()
                client.force_login(get_user_model().objects.get(pk=self.user.pk))
                barrier.wait(timeout=15)
                return client.post(f'/api/bills/{self.bill.pk}/payments/', json.dumps({'receipt_id':assets[_],'amount':'800.00','paid_date':timezone.localdate().isoformat(),'request_key':str(uuid.uuid4())}), content_type='application/json').status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(pay, range(2)))
        self.assertEqual(sorted(results),[201,409])
        self.assertEqual(Payment.objects.count(),1)

    def test_database_trigger_prevents_concurrent_non_api_overpayment(self):
        barrier = Barrier(2)
        def pay(_):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                try:
                    with transaction.atomic():
                        Payment.objects.create(receipt_required=False,bill_id=self.bill.pk,amount='800.00',paid_date=timezone.localdate(),recorded_by_id=self.user.pk,request_key=uuid.uuid4())
                    return 'committed'
                except IntegrityError:
                    return 'rejected'
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(pay, range(2)))
        self.assertEqual(sorted(results),['committed','rejected'])
        self.assertEqual(Payment.objects.count(),1)

    def test_simultaneous_loan_retries_commit_one_schedule(self):
        barrier=Barrier(2)
        key=str(uuid.uuid4())
        payload={'title':'Retry test','total':'90','installments':3,'first_due':'2028-01-31','request_key':key}
        def create(_):
            close_old_connections()
            try:
                client=Client(); client.force_login(get_user_model().objects.get(pk=self.user.pk))
                barrier.wait(timeout=15)
                return client.post('/api/loans/',json.dumps(payload),content_type='application/json').status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(create,range(2)))
        self.assertEqual(sorted(results),[200,201])
        self.assertEqual(Loan.objects.count(),1)
        self.assertEqual(Bill.objects.filter(loan__isnull=False).count(),3)
        self.assertEqual(MutationReceipt.objects.count(),1)
