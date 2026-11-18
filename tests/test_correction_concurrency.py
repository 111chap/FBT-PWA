import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import date
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.db import connection, connections, close_old_connections
from django.test import Client, TransactionTestCase, override_settings
from tracker.models import Bill, Payment, AuditEvent


@skipUnless(connection.vendor=='postgresql','Financial row locks require PostgreSQL.')
@override_settings(SECURE_SSL_REDIRECT=False)
class CorrectionConcurrencyTests(TransactionTestCase):
    def test_two_admins_cannot_apply_stale_corrections(self):
        User=get_user_model();admins=[User.objects.create_superuser(f'correction-{i}',password='Fictional-passphrase-123!') for i in range(2)]
        bill=Bill.objects.create(title='Concurrent correction',amount='100',due_date=date(2026,1,1),responsible=admins[0],created_by=admins[0])
        Payment.objects.create(bill=bill,amount='100',paid_date=date(2026,1,1),recorded_by=admins[0],request_key=uuid.uuid4())
        client=Client();client.force_login(admins[0]);record=client.get('/api/snapshot/').json()['bills'][0]
        barrier=Barrier(2)
        def correct(index):
            close_old_connections()
            try:
                c=Client();c.force_login(User.objects.get(pk=admins[index].pk))
                payload={k:record[k] for k in ('title','amount','due_date','category','notes')}
                payload.update(responsible=record['responsible_id'],amount=str(120+index),expected_version=record['version'],reason='Concurrent admin correction',confirmed=True,action='edit',request_key=str(uuid.uuid4()))
                barrier.wait(timeout=15)
                return c.post(f'/api/manage/bill/{bill.pk}/',json.dumps(payload),content_type='application/json').status_code
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(correct,range(2)))
        self.assertEqual(sorted(results),[200,409]);bill.refresh_from_db();self.assertIn(bill.amount,(120,121))
        self.assertEqual(AuditEvent.objects.filter(reason='Concurrent admin correction').count(),1)

    def test_payment_correction_racing_new_payment_never_overpays(self):
        User=get_user_model();admin=User.objects.create_superuser('admin-correct',password='Fictional-passphrase-123!');member=User.objects.create_user('member-pay',password='Fictional-passphrase-456!')
        bill=Bill.objects.create(title='Race payment',amount='200',due_date=date(2026,1,1),responsible=member,created_by=admin)
        old=Payment.objects.create(bill=bill,amount='100',paid_date=date(2026,1,1),recorded_by=member,request_key=uuid.uuid4())
        c=Client();c.force_login(admin);record=c.get('/api/snapshot/').json()['bills'][0];barrier=Barrier(2)
        def mutate(index):
            close_old_connections()
            try:
                client=Client();client.force_login(User.objects.get(pk=admin.pk if index==0 else member.pk))
                payload={'amount':'150' if index==0 else '100','paid_date':'2026-01-01','request_key':str(uuid.uuid4())}
                if index==0:payload.update(expected_version=record['payments'][0]['version'],expected_bill_version=record['version'],reason='Concurrent payment correction',confirmed=True,action='edit')
                url=f'/api/manage/payment/{old.pk}/' if index==0 else f'/api/bills/{bill.pk}/payments/'
                barrier.wait(timeout=15)
                return client.post(url,json.dumps(payload),content_type='application/json').status_code
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(mutate,range(2)))
        self.assertEqual(result.count(409),1);self.assertIn(result[0],(200,409));self.assertIn(result[1],(201,409))
        bill.refresh_from_db();self.assertGreaterEqual(bill.balance,0)
