import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from tracker.models import Bill, Payment, Loan, Recurrence
from tracker.services import materialize_recurring


@override_settings(SECURE_SSL_REDIRECT=False)
class PaymentTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('family',password='test-password-1234')
        self.client.force_login(self.user)
        self.bill=Bill.objects.create(title='Internet',amount='1000.00',due_date=timezone.localdate(),responsible=self.user,created_by=self.user)

    def pay(self,amount,key=None):
        return self.client.post(f'/api/bills/{self.bill.pk}/payments/',json.dumps({'amount':amount,'paid_date':timezone.localdate().isoformat(),'request_key':key or str(uuid.uuid4())}),content_type='application/json')

    def test_partial_payment_changes_balance_and_full_payment_marks_paid(self):
        self.assertEqual(self.pay('400.00').status_code,201)
        self.assertEqual(self.bill.balance,Decimal('600.00'))
        self.assertEqual(self.client.get('/api/snapshot/').json()['bills'][0]['status'],'partial')
        self.pay('600.00')
        self.assertEqual(self.client.get('/api/snapshot/').json()['bills'][0]['status'],'paid')

    def test_overpayment_and_stale_balance_are_rejected(self):
        self.pay('800.00')
        self.assertEqual(self.pay('500.00').status_code,409)
        self.assertEqual(Payment.objects.count(),1)

    def test_retrying_same_payment_is_idempotent(self):
        key=str(uuid.uuid4())
        self.assertEqual(self.pay('1000.00',key).status_code,201)
        self.assertEqual(self.pay('1000.00',key).status_code,200)
        self.assertEqual(Payment.objects.count(),1)

    def test_reusing_payment_key_with_changed_amount_is_rejected(self):
        key=str(uuid.uuid4())
        self.pay('100.00',key)
        self.assertEqual(self.pay('200.00',key).status_code,409)

    def test_loan_installments_sum_to_exact_agreed_total(self):
        response=self.client.post('/api/loans/',json.dumps({'title':'Test loan','total':'1000.00','installments':3,'first_due':'2027-01-31'}),content_type='application/json')
        self.assertEqual(response.status_code,201)
        loan=Loan.objects.get()
        installments=list(loan.bills.order_by('due_date'))
        self.assertEqual([b.amount for b in installments],[Decimal('333.33'),Decimal('333.33'),Decimal('333.34')])
        self.assertEqual([b.due_date for b in installments],[date(2027,1,31),date(2027,2,28),date(2027,3,31)])

    def test_recurrence_restarts_do_not_duplicate_occurrences(self):
        recurrence=Recurrence.objects.create(title='Rent',amount='5000',category='Household',next_due=date(2027,1,31),anchor_day=31,responsible=self.user,created_by=self.user)
        materialize_recurring(date(2027,1,31)); materialize_recurring(date(2027,1,31))
        self.assertEqual(Bill.objects.filter(recurrence=recurrence).count(),2)
        recurrence.refresh_from_db()
        self.assertEqual(recurrence.next_due,date(2027,3,31))

    def test_future_payment_date_is_rejected(self):
        response=self.client.post(f'/api/bills/{self.bill.pk}/payments/',json.dumps({'amount':'1','paid_date':(timezone.localdate()+timedelta(days=1)).isoformat(),'request_key':str(uuid.uuid4())}),content_type='application/json')
        self.assertEqual(response.status_code,400)
