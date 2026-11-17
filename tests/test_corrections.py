import json
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from django.test import TestCase, override_settings
from tracker.models import Bill, Payment, Loan, AuditEvent, AuditContext


@override_settings(SECURE_SSL_REDIRECT=False)
class CorrectionTests(TestCase):
    def setUp(self):
        self.admin=get_user_model().objects.create_superuser('correction-admin',password='Fictional-passphrase-123!')
        self.member=get_user_model().objects.create_user('correction-member',password='Fictional-passphrase-456!')
        self.client.force_login(self.admin)
        self.bill=Bill.objects.create(title='Fictional water',amount='100',due_date=date(2026,1,1),responsible=self.member,created_by=self.admin)
        self.payment=Payment.objects.create(bill=self.bill,amount='100',paid_date=date(2026,1,1),recorded_by=self.member,request_key=uuid.uuid4())

    def snapshot(self):return self.client.get('/api/snapshot/').json()
    def bill_data(self,bill=None):return next(b for b in self.snapshot()['bills'] if b['id']==(bill or self.bill).pk)
    def payload(self,kind='bill',obj=None,action='edit',**changes):
        bill=self.bill_data()
        record=bill if kind=='bill' else next(p for p in bill['payments'] if p['id']==self.payment.pk) if kind=='payment' else next(l for l in self.snapshot()['loans'] if l['id']==obj.pk)
        return {'request_key':str(uuid.uuid4()),'confirmed':True,'reason':'Correct a fictional entry','action':action,'expected_version':record['version'],'expected_bill_version':bill['version'],
                **({'title':bill['title'],'amount':bill['amount'],'due_date':bill['due_date'],'category':bill['category'],'notes':bill['notes'],'responsible':bill['responsible_id']} if kind=='bill' else {}),**changes}
    def post(self,kind,data,obj=None):
        target=obj or (self.payment if kind=='payment' else self.bill)
        return self.client.post(f'/api/manage/{kind}/{target.pk}/',json.dumps(data),content_type='application/json')

    def test_paid_bill_edit_and_retry_are_logged_once_with_reason(self):
        data=self.payload(title='Corrected title',amount='120')
        self.assertEqual(self.post('bill',data).status_code,200)
        count=AuditEvent.objects.count();self.assertEqual(self.post('bill',data).status_code,200);self.assertEqual(AuditEvent.objects.count(),count)
        self.assertEqual(self.bill_data()['balance'],'20.00')
        event=AuditEvent.objects.filter(entity_type='bill',entity_id=str(self.bill.pk),reason=data['reason']).latest('id')
        self.assertEqual(event.actor_id,self.admin.pk);self.assertEqual(event.before['title'],'Fictional water');self.assertEqual(event.after['title'],'Corrected title')
        self.assertEqual(AuditContext.objects.get(pk=1).reason,'')

    def test_paid_bill_deletion_keeps_payment_and_audit(self):
        data=self.payload(action='delete');self.assertEqual(self.post('bill',data).status_code,200)
        self.bill.refresh_from_db();self.assertTrue(self.bill.removed);self.assertTrue(Payment.objects.filter(pk=self.payment.pk).exists());self.assertEqual(self.snapshot()['bills'],[])
        self.assertTrue(AuditEvent.objects.filter(entity_type='bill',reason=data['reason'],after__removed=True).exists())

    def test_payment_edit_delete_and_stale_review(self):
        old=self.payload('payment',amount='90',paid_date='2026-01-02')
        self.assertEqual(self.post('payment',old).status_code,200)
        self.payment.refresh_from_db();self.assertEqual(self.payment.recorded_by_id,self.member.pk)
        old['request_key']=str(uuid.uuid4());self.assertEqual(self.post('payment',old).status_code,409)
        data=self.payload('payment',action='delete');self.assertEqual(self.post('payment',data).status_code,200)
        self.payment.refresh_from_db();self.assertTrue(self.payment.removed);self.assertEqual(self.bill_data()['balance'],'100.00');self.assertEqual(self.bill_data()['payments'],[])
        self.assertEqual(self.post('payment',data).status_code,200)
        response=self.client.post(f'/api/bills/{self.bill.pk}/payments/',json.dumps({'amount':'100','paid_date':'2026-01-01','request_key':str(uuid.uuid4())}),content_type='application/json')
        self.assertEqual(response.status_code,201)
        with self.assertRaises(IntegrityError),transaction.atomic():Payment.objects.create(bill=self.bill,amount='1',paid_date=date(2026,1,1),recorded_by=self.admin,request_key=uuid.uuid4())

    def test_invalid_reductions_and_future_payment_leave_no_logs(self):
        before=AuditEvent.objects.count()
        self.assertEqual(self.post('bill',self.payload(amount='99')).status_code,400)
        self.assertEqual(self.post('payment',self.payload('payment',amount='101',paid_date='2026-01-01')).status_code,400)
        self.assertEqual(self.post('payment',self.payload('payment',amount='100',paid_date='2100-01-01')).status_code,400)
        self.assertEqual(AuditEvent.objects.count(),before)

    def test_member_cannot_correct_and_missing_review_reason_key_rejected(self):
        data=self.payload(action='delete');self.client.force_login(self.member)
        self.assertEqual(self.post('bill',data).status_code,403)
        self.assertEqual(self.post('payment',data).status_code,403)
        self.assertEqual(self.post('loan',data,obj=self.bill).status_code,403)
        self.client.force_login(self.admin)
        for key,value in [('confirmed',False),('reason',''),('request_key','')]:
            invalid={**data,key:value};self.assertEqual(self.post('bill',invalid).status_code,400)

    def make_loan(self):
        loan=Loan.objects.create(title='Fictional bicycle',total='200',installments=2,created_by=self.admin)
        self.bill.loan=loan;self.bill.save(update_fields=['loan'])
        second=Bill.objects.create(title='Installment 2',amount='100',due_date=date(2026,2,1),responsible=self.member,created_by=self.admin,loan=loan)
        return loan,second

    def test_loan_edit_preserves_paid_installment_and_deletion_is_atomic(self):
        loan,second=self.make_loan();data=self.payload('loan',obj=loan,title='Corrected bicycle',total='240')
        self.assertEqual(self.post('loan',data,loan).status_code,200)
        self.bill.refresh_from_db();second.refresh_from_db();self.assertEqual(self.bill.amount,Decimal('100'));self.assertEqual(second.amount,Decimal('140'))
        events=AuditEvent.objects.filter(reason=data['reason']);self.assertEqual(events.values('transaction_id').distinct().count(),1)
        deletion=self.payload('loan',obj=loan,action='delete')
        self.assertEqual(self.post('loan',deletion,loan).status_code,200)
        self.assertEqual(self.snapshot()['loans'],[]);self.assertEqual(self.snapshot()['bills'],[])
        self.assertEqual(Payment.objects.count(),1)
        self.assertEqual(AuditEvent.objects.filter(reason=deletion['reason'],after__removed=True).count(),3)

    def test_bill_corrections_reconcile_loan_and_stale_sibling_conflicts(self):
        loan,second=self.make_loan();lv=self.snapshot()['loans'][0]['version']
        data=self.payload(expected_loan_version=lv,amount='120')
        self.assertEqual(self.post('bill',data).status_code,200);loan.refresh_from_db();self.assertEqual(loan.total,Decimal('220'))
        deletion=self.payload(action='delete',expected_loan_version=lv)
        self.assertEqual(self.post('bill',deletion).status_code,409)
        deletion['expected_loan_version']=self.snapshot()['loans'][0]['version'];self.assertEqual(self.post('bill',deletion).status_code,200)
        loan.refresh_from_db();self.assertEqual(loan.total,Decimal('100'));self.assertEqual(loan.installments,1)

    def test_failure_after_bill_changes_rolls_back_rows_and_logs(self):
        loan,second=self.make_loan();data=self.payload('loan',obj=loan,title='Will rollback',total='240')
        before=AuditEvent.objects.count();original=Loan.save
        def fail(instance,*args,**kwargs):
            if instance.pk==loan.pk:raise IntegrityError('fictional injected failure')
            return original(instance,*args,**kwargs)
        with patch.object(Loan,'save',fail):self.assertEqual(self.post('loan',data,loan).status_code,409)
        second.refresh_from_db();self.assertEqual(second.amount,Decimal('100'));self.assertEqual(AuditEvent.objects.count(),before)

    def test_fully_paid_loan_can_be_edited_and_deleted(self):
        loan,second=self.make_loan()
        Payment.objects.create(bill=second,amount='100',paid_date=date(2026,1,1),recorded_by=self.member,request_key=uuid.uuid4())
        edit=self.payload('loan',obj=loan,title='Paid loan correction',total='220')
        self.assertEqual(self.post('loan',edit,loan).status_code,200)
        second.refresh_from_db();self.assertEqual(second.balance,Decimal('20'))
        invalid=self.payload('loan',obj=loan,title='Too small',total='199');self.assertEqual(self.post('loan',invalid,loan).status_code,400)
        restore=self.payload('loan',obj=loan,title='Paid loan correction',total='200');self.assertEqual(self.post('loan',restore,loan).status_code,200)
        second.refresh_from_db();self.assertEqual(second.balance,0)
        data=self.payload('loan',obj=loan,action='delete');self.assertEqual(self.post('loan',data,loan).status_code,200)

    def test_payment_amount_and_date_both_change_versions(self):
        old=self.payload(title='Stale bill review')
        edit=self.payload('payment',amount='100',paid_date='2026-01-02');self.assertEqual(self.post('payment',edit).status_code,200)
        self.assertEqual(self.post('bill',old).status_code,409)

    def test_csrf_and_reason_are_required_for_admin_corrections(self):
        from django.test import Client
        client=Client(enforce_csrf_checks=True);client.force_login(self.admin)
        self.assertEqual(client.post(f'/api/manage/bill/{self.bill.pk}/',json.dumps(self.payload(action='delete')),content_type='application/json').status_code,403)

    def test_no_op_edits_are_rejected_without_claiming_an_audit_change(self):
        before=AuditEvent.objects.count()
        self.assertEqual(self.post('bill',self.payload()).status_code,400)
        self.assertEqual(self.post('payment',self.payload('payment',amount='100',paid_date='2026-01-01')).status_code,400)
        self.assertEqual(AuditEvent.objects.count(),before)
