import uuid
from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from tracker.models import AuditEvent, Bill, Payment, Loan


@override_settings(SECURE_SSL_REDIRECT=False)
class HistorySnapshotTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User=get_user_model()
        cls.admin=User.objects.create_superuser('history-admin',password='Fictional-history-admin-123!')
        cls.payer=User.objects.create_user('history-payer')
        cls.member=User.objects.create_user('history-reader')
        cls.loan=Loan.objects.create(title='Family car',total='100',installments=1,created_by=cls.admin)
        cls.bill=Bill.objects.create(title='Car installment',amount='100',due_date=date(2028,1,31),loan=cls.loan,responsible=cls.payer,created_by=cls.admin)
        for amount,day,recorder in [('40',20,cls.admin),('60',25,cls.member)]:
            Payment.objects.create(bill=cls.bill,amount=amount,paid_date=date(2027,1,day),recorded_by=recorder,request_key=uuid.uuid4())

    def test_every_member_gets_shared_history_without_financial_or_audit_writes(self):
        for user in [self.admin,self.payer,self.member]:
            self.client.force_login(user)
            before=AuditEvent.objects.count()
            snapshot=self.client.get('/api/snapshot/').json()
            bill=snapshot['bills'][0]
            self.assertEqual(bill['responsible_id'],self.payer.pk)
            self.assertEqual(bill['balance'],'0.00')
            self.assertEqual(bill['amount'],'100.00')
            self.assertEqual(bill['loan_id'],self.loan.pk)
            self.assertEqual({p['recorded_by_id'] for p in bill['payments']},{self.admin.pk,self.member.pk})
            self.assertEqual(AuditEvent.objects.count(),before)
            self.assertNotIn('events',snapshot)
        self.assertEqual(Payment.objects.count(),2)

    def test_renamed_and_deactivated_accounts_keep_stable_attribution(self):
        User=get_user_model()
        User.objects.filter(pk=self.payer.pk).update(username='renamed-payer',is_active=False)
        User.objects.filter(pk=self.member.pk).update(username='renamed-recorder',is_active=False)
        self.client.force_login(self.admin)
        snapshot=self.client.get('/api/snapshot/').json()
        bill=snapshot['bills'][0]
        self.assertEqual(bill['responsible'],'renamed-payer')
        self.assertEqual(bill['responsible_id'],self.payer.pk)
        self.assertIn({'id':self.admin.pk,'username':'history-admin'},snapshot['members'])
        self.assertNotIn(self.payer.pk,[m['id'] for m in snapshot['members']])
        recorder=next(p for p in bill['payments'] if p['recorded_by_id']==self.member.pk)
        self.assertEqual(recorder['recorded_by'],'renamed-recorder')
