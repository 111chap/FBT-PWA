import json
import uuid
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db import connection, IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.utils import timezone
from tracker.audit import audit_transaction
from tracker.models import AuditEvent, Bill, Payment, Recurrence, SiteSettings, Loan, MutationReceipt
from tracker.services import materialize_recurring, next_month
from tracker.versions import bill_version, version
from tests.test_audit import unavailable_audit_storage

User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class FamilyWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('family-admin', password='test-passphrase-only-123')
        cls.member = User.objects.create_user('payer', password='test-passphrase-only-456')
        cls.other = User.objects.create_user('another-payer')
        cls.schedule = Recurrence.objects.create(title='Internet', amount='100', next_due=date(2028, 1, 31), anchor_day=31, responsible=cls.member, created_by=cls.admin)
        cls.bill = Bill.objects.create(title='Internet', amount='100', due_date=date(2027, 12, 31), responsible=cls.member, created_by=cls.admin, recurrence=cls.schedule)

    def setUp(self):
        self.client.force_login(self.admin)

    def post(self, url, data):
        return self.client.post(url, json.dumps(data), content_type='application/json')

    def snapshot(self):
        return self.client.get('/api/snapshot/').json()

    def lifecycle(self, action, token=None):
        r = self.snapshot()['recurrences'][0]
        return self.post(f'/api/recurrences/{self.schedule.pk}/action/', {'action': action, 'expected_version': token or r['version']})

    def assign(self, payer=None, scope='current', **extra):
        r = self.snapshot()['recurrences'][0]
        return self.post(f'/api/bills/{self.bill.pk}/payer/', {'responsible': payer or self.other.pk, 'scope': scope, 'expected_version': bill_version(self.bill), 'recurrence_version': r['version'], **extra})

    def test_snapshot_and_cancel_have_no_financial_deletions(self):
        count = AuditEvent.objects.count()
        self.snapshot(); self.client.get('/api/reachable/')
        self.assertEqual(AuditEvent.objects.count(), count)
        self.assertEqual(self.lifecycle('cancel').status_code, 200)
        materialize_recurring(date(2028, 2, 29))
        self.assertEqual(Bill.objects.count(), 1)
        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.active)
        self.assertEqual(self.snapshot()['bills'][0]['id'], self.bill.pk)
        event = AuditEvent.objects.filter(entity_type='recurrence', action='update').get()
        self.assertEqual(event.actor_id, self.admin.pk)
        self.assertTrue(event.before['active'])
        self.assertFalse(event.after['active'])

    def test_members_cannot_cancel_remove_or_reassign(self):
        self.client.force_login(self.member)
        self.assertEqual(self.lifecycle('cancel').status_code, 403)
        self.assertEqual(self.lifecycle('remove').status_code, 403)
        self.assertEqual(self.assign().status_code, 403)
        self.assertEqual(self.post(f'/api/bills/{self.bill.pk}/remove/', {'expected_version': bill_version(self.bill)}).status_code, 403)
        self.assertFalse(Bill.objects.get(pk=self.bill.pk).removed)

    def test_monthly_anchor_handles_leap_and_year_transition(self):
        self.assertEqual(next_month(date(2027,12,31),31),date(2028,1,31))
        self.assertEqual(next_month(date(2028,1,31),31),date(2028,2,29))
        self.assertEqual(next_month(date(2028,2,29),31),date(2028,3,31))
        materialize_recurring(date(2028,1,31)); materialize_recurring(date(2028,1,31))
        self.assertEqual(Bill.objects.filter(recurrence=self.schedule).count(),3)

    def test_schedule_removal_retains_rows_and_atomic_audit(self):
        self.assertEqual(self.lifecycle('remove').status_code,200)
        self.assertEqual(self.snapshot()['bills'],[])
        self.assertEqual(Bill.objects.count(),1)
        event = AuditEvent.objects.filter(entity_type='recurrence', action='update').get()
        self.assertTrue(event.after['removed'])
        self.assertEqual(AuditEvent.objects.filter(transaction_id=event.transaction_id,entity_type='bill').count(),1)
        materialize_recurring(date(2028,2,29))
        self.assertEqual(Bill.objects.count(),1)

    def test_removal_of_paid_schedule_rejected_without_partial_changes(self):
        Payment.objects.create(bill=self.bill,amount='1',paid_date=timezone.localdate(),recorded_by=self.member,request_key=uuid.uuid4())
        count=AuditEvent.objects.count()
        self.assertEqual(self.lifecycle('remove').status_code,400)
        self.assertEqual(AuditEvent.objects.count(),count)
        self.assertFalse(Bill.objects.get(pk=self.bill.pk).removed)
        self.assertTrue(Recurrence.objects.get(pk=self.schedule.pk).active)

    def test_occurrence_removal_is_not_regenerated_by_worker(self):
        self.schedule.next_due=self.bill.due_date; self.schedule.save()
        self.assertEqual(self.post(f'/api/bills/{self.bill.pk}/remove/', {'expected_version':bill_version(self.bill)}).status_code,200)
        materialize_recurring(self.bill.due_date)
        self.assertEqual(Bill.objects.filter(recurrence=self.schedule,due_date=self.bill.due_date).count(),1)
        self.assertTrue(Bill.objects.get(pk=self.bill.pk).removed)

    def test_stale_payment_requires_new_review_even_if_balance_sufficient(self):
        token=bill_version(self.bill)
        Payment.objects.create(bill=self.bill,amount='1',paid_date=timezone.localdate(),recorded_by=self.member,request_key=uuid.uuid4())
        response=self.post(f'/api/bills/{self.bill.pk}/payments/',{'amount':'1','paid_date':timezone.localdate().isoformat(),'request_key':str(uuid.uuid4()),'expected_version':token})
        self.assertEqual(response.status_code,409)
        self.assertEqual(Payment.objects.count(),1)

    def test_creation_request_retries_do_not_duplicate_bills_or_schedules(self):
        payload={'title':'Power','amount':'125','due_date':'2028-01-31','repeat_monthly':True,'request_key':str(uuid.uuid4())}
        self.assertEqual(self.post('/api/bills/',payload).status_code,201)
        self.assertEqual(self.post('/api/bills/',payload).status_code,200)
        self.assertEqual(Bill.objects.count(),2)
        self.assertEqual(Recurrence.objects.count(),2)
        payload['amount']='130'
        self.assertEqual(self.post('/api/bills/',payload).status_code,409)
        self.assertEqual(MutationReceipt.objects.count(),1)

    def test_creation_request_retries_do_not_duplicate_loans(self):
        payload={'title':'Car','total':'100','installments':3,'first_due':'2028-01-31','request_key':str(uuid.uuid4())}
        self.assertEqual(self.post('/api/loans/',payload).status_code,201)
        self.assertEqual(self.post('/api/loans/',payload).status_code,200)
        self.assertEqual(Loan.objects.count(),1)
        self.assertEqual(Bill.objects.count(),4)

    def test_settings_propagate_for_all_accounts_and_stale_save_rejected(self):
        before=self.snapshot()['settings_version']
        payload={'family_name':'Shared family','nas_name':'Shared NAS','server_url':'https://bills.example.test','expected_version':before}
        self.assertEqual(self.post('/api/settings/',payload).status_code,200)
        self.assertEqual(self.post('/api/settings/',payload).status_code,409)
        for member in [self.member,self.other]:
            self.client.force_login(member)
            self.assertEqual(self.snapshot()['nas_name'],'Shared NAS')
            self.assertNotEqual(self.client.get('/api/reachable/').json()['settings_version'],before)
            self.assertEqual(self.post('/api/settings/',payload).status_code,403)
        self.assertEqual(SiteSettings.objects.count(),1)

    def test_payer_scope_is_explicit_and_payment_attribution_retained(self):
        Payment.objects.create(bill=self.bill,amount='1',paid_date=timezone.localdate(),recorded_by=self.member,request_key=uuid.uuid4())
        self.assertEqual(self.assign().status_code,200)
        self.schedule.refresh_from_db(); self.bill.refresh_from_db()
        self.assertEqual(self.schedule.responsible_id,self.member.pk)
        self.assertEqual(self.bill.responsible_id,self.other.pk)
        self.assertEqual(Payment.objects.get().recorded_by_id,self.member.pk)
        self.assertEqual(self.assign(scope='future').status_code,200)
        materialize_recurring(date(2028,1,31))
        self.assertEqual(set(Bill.objects.values_list('responsible_id',flat=True)),{self.other.pk})
        event=AuditEvent.objects.filter(entity_type='bill',action='update').first()
        self.assertEqual(event.actor_id,self.admin.pk)

    def test_inactive_unknown_or_stale_payer_is_rejected(self):
        User.objects.filter(pk=self.other.pk).update(is_active=False)
        self.assertEqual(self.assign().status_code,404)
        self.assertEqual(self.assign(payer=999999).status_code,404)
        self.assertEqual(self.assign(payer=self.member.pk,expected_version='old').status_code,409)
        self.assertEqual(Bill.objects.get(pk=self.bill.pk).responsible_id,self.member.pk)

    def test_profile_and_deletion_logs_survive_account_removal(self):
        with audit_transaction(self.admin,'admin'):
            self.other.first_name='Fictional'; self.other.last_name='Tester'; self.other.email='qa@example.test'; self.other.username='renamed'; self.other.save()
            target_id=self.other.pk
            self.other.delete()
        events=AuditEvent.objects.filter(entity_type='account',entity_id=str(target_id),action__in=['update','delete'])
        self.assertEqual(events.count(),2)
        changed=events.get(action='update')
        self.assertEqual(changed.after['email'],'qa@example.test')
        self.assertEqual(changed.before['username'],'another-payer')
        self.assertEqual(events.get(action='delete').before['first_name'],'Fictional')
        self.assertNotIn('password',json.dumps(list(events.values('before','after'))))
        self.assertEqual(self.client.get('/api/audit/', {'entity_type':'account','search':'qa@example.test'}).json()['total'],2)

    def test_profile_audit_failure_rolls_back_account_changes(self):
        with unavailable_audit_storage():
            with self.assertRaises(IntegrityError), transaction.atomic(), audit_transaction(self.admin,'admin'):
                User.objects.filter(pk=self.other.pk).update(email='not-committed@example.test')
        self.other.refresh_from_db()
        self.assertEqual(self.other.email,'')

    def test_normal_sql_profile_change_is_audited_without_inventing_actor(self):
        with connection.cursor() as cursor:
            cursor.execute('UPDATE auth_user SET first_name=%s WHERE id=%s',['SQL profile',self.other.pk])
        event=AuditEvent.objects.filter(entity_type='account',entity_id=str(self.other.pk),action='update').get()
        self.assertEqual(event.after['first_name'],'SQL profile')
        self.assertIsNone(event.actor_id)
        self.assertEqual(event.source,'database')

    def test_referenced_account_deactivation_preserves_history(self):
        with self.assertRaises(ProtectedError), transaction.atomic(): self.member.delete()
        with audit_transaction(self.admin,'admin'):
            User.objects.filter(pk=self.member.pk).update(is_active=False)
        snapshot=self.snapshot()
        self.assertEqual(snapshot['bills'][0]['responsible'],'payer')
        self.assertNotIn(self.member.pk,[m['id'] for m in snapshot['members']])

    def test_audit_failure_rolls_back_removal_and_payer_changes(self):
        with unavailable_audit_storage():
            self.assertEqual(self.assign().status_code,409)
            self.assertEqual(self.lifecycle('remove').status_code,409)
        self.assertFalse(Bill.objects.get(pk=self.bill.pk).removed)
        self.assertEqual(Bill.objects.get(pk=self.bill.pk).responsible_id,self.member.pk)

    def test_admin_edit_and_deletion_require_current_record_version(self):
        url=f'/admin/auth/user/{self.other.pk}/change/'
        page=self.client.get(url)
        self.assertContains(page,'admin-review.js')
        token=page.context['record_version']
        User.objects.filter(pk=self.other.pk).update(first_name='Changed elsewhere')
        self.assertEqual(self.client.post(url,{'_record_version':token,'username':'overwritten'}).status_code,409)
        delete=f'/admin/auth/user/{self.other.pk}/delete/'
        page=self.client.get(delete)
        self.assertContains(page,'_record_version')
        self.assertEqual(self.client.post(delete,{'post':'yes'}).status_code,409)
        self.assertEqual(self.client.post(delete,{'post':'yes','_record_version':page.context['record_version']}).status_code,302)
        self.assertFalse(User.objects.filter(pk=self.other.pk).exists())
