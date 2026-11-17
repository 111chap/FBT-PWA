import json
import uuid
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import connection, transaction, IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone
from tracker.audit import audit_transaction
from tracker.models import AuditEvent, Bill, Payment, Loan

User = get_user_model()


@contextmanager
def unavailable_audit_storage():
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute("CREATE FUNCTION fbt_test_reject_audit_fn() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Audit unavailable' USING ERRCODE='23514'; END; $$")
            cursor.execute('CREATE TRIGGER fbt_test_reject_audit BEFORE INSERT ON tracker_auditevent FOR EACH ROW EXECUTE FUNCTION fbt_test_reject_audit_fn()')
        else:
            cursor.execute("CREATE TRIGGER fbt_test_reject_audit BEFORE INSERT ON tracker_auditevent BEGIN SELECT RAISE(ABORT, 'Audit unavailable'); END")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                cursor.execute('DROP TRIGGER fbt_test_reject_audit ON tracker_auditevent')
                cursor.execute('DROP FUNCTION fbt_test_reject_audit_fn()')
            else:
                cursor.execute('DROP TRIGGER fbt_test_reject_audit')


@override_settings(SECURE_SSL_REDIRECT=False)
class AuditTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('reviewer', password='long-test-admin-passphrase-123')
        self.member = User.objects.create_user('family', password='long-test-member-passphrase-123')
        self.bill = Bill.objects.create(title='Audit test electricity', amount='1000.00', due_date=timezone.localdate(), responsible=self.member, created_by=self.admin)
        self.client.force_login(self.admin)

    def post(self, path, payload):
        return self.client.post(path, json.dumps(payload), content_type='application/json')

    def payment(self, amount='100.00', key=None):
        return self.post(f'/api/bills/{self.bill.pk}/payments/', {'amount':amount, 'paid_date':timezone.localdate().isoformat(), 'request_key':key or str(uuid.uuid4())})

    def test_payment_and_log_have_correct_actor_and_safe_snapshot(self):
        self.assertEqual(self.payment().status_code,201)
        payment=Payment.objects.get()
        event=AuditEvent.objects.get(entity_type='payment',entity_id=str(payment.pk),action='insert')
        self.assertEqual(event.actor_id,self.admin.pk)
        self.assertEqual(event.actor_name,'reviewer')
        self.assertEqual(event.source,'app')
        self.assertEqual(event.after['bill_id'],self.bill.pk)
        self.assertIsNone(event.before)
        self.assertEqual(len(event.transaction_id),32)

    def test_loan_and_all_installments_share_one_transaction(self):
        response=self.post('/api/loans/', {'title':'Audited loan','total':'1000.00','installments':3,'first_due':'2027-01-31'})
        self.assertEqual(response.status_code,201)
        event=AuditEvent.objects.get(entity_type='loan',entity_id=str(response.json()['id']))
        related=AuditEvent.objects.filter(transaction_id=event.transaction_id)
        self.assertEqual(related.count(),4)
        self.assertEqual(set(related.values_list('entity_type',flat=True)),{'loan','bill'})
        self.assertEqual(set(related.values_list('actor_id',flat=True)),{self.admin.pk})

    def test_failed_installment_rolls_back_loan_bills_and_logs(self):
        before=AuditEvent.objects.count()
        create=Bill.objects.create
        calls=0
        def failing_create(**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:
                raise ValueError('Simulated installment failure')
            return create(**kwargs)
        with patch('tracker.views.Bill.objects.create',side_effect=failing_create):
            response=self.post('/api/loans/',{'title':'Must roll back','total':'900','installments':3,'first_due':'2027-01-01'})
        self.assertEqual(response.status_code,400)
        self.assertFalse(Loan.objects.exists())
        self.assertEqual(Bill.objects.count(),1)
        self.assertEqual(AuditEvent.objects.count(),before)

    def test_audit_storage_failure_prevents_payment_commit(self):
        before=AuditEvent.objects.count()
        with unavailable_audit_storage():
            self.assertEqual(self.payment().status_code,409)
        self.assertEqual(Payment.objects.count(),0)
        self.assertEqual(AuditEvent.objects.count(),before)

    def test_rejected_payment_creates_no_committed_event(self):
        before=AuditEvent.objects.count()
        self.assertEqual(self.payment('1200.00').status_code,409)
        self.assertEqual(AuditEvent.objects.count(),before)

    def test_payment_retry_does_not_duplicate_audit_event(self):
        key=str(uuid.uuid4())
        self.payment(key=key)
        self.payment(key=key)
        self.assertEqual(AuditEvent.objects.filter(entity_type='payment').count(),1)

    def test_raw_sql_update_is_audited_without_fabricated_actor(self):
        self.payment()
        with connection.cursor() as cursor:
            cursor.execute('UPDATE tracker_bill SET notes=%s WHERE id=%s',['Changed outside the app',self.bill.pk])
        event=AuditEvent.objects.get(entity_type='bill',entity_id=str(self.bill.pk),action='update')
        self.assertEqual(event.before['notes'],'')
        self.assertEqual(event.after['notes'],'Changed outside the app')
        self.assertIsNone(event.actor_id)
        self.assertEqual(event.source,'database')
        self.assertEqual(event.actor_name,'Database / unknown actor')

    def test_raw_sql_overpayment_is_rejected_by_database(self):
        self.payment('900.00')
        before=AuditEvent.objects.count()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payment.objects.create(bill=self.bill,amount='200.00',paid_date=timezone.localdate(),recorded_by=self.admin,request_key=uuid.uuid4())
        self.assertEqual(Payment.objects.count(),1)
        self.assertEqual(AuditEvent.objects.count(),before)

    def test_lowering_bill_below_payments_is_rejected_by_database(self):
        self.payment('900.00')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Bill.objects.filter(pk=self.bill.pk).update(amount='800.00')
        self.bill.refresh_from_db()
        self.assertEqual(str(self.bill.amount),'1000.00')

    def test_row_delete_retains_before_snapshot(self):
        pk=self.bill.pk
        self.bill.delete()
        event=AuditEvent.objects.get(entity_type='bill',entity_id=str(pk),action='delete')
        self.assertEqual(event.before['title'],'Audit test electricity')
        self.assertIsNone(event.after)

    def test_password_change_is_flagged_without_password_or_hash(self):
        old_hash=self.member.password
        with audit_transaction(self.admin,'admin'):
            self.member.set_password('new-test-only-secret-passphrase-123')
            self.member.save()
        event=AuditEvent.objects.get(entity_type='account',entity_id=str(self.member.pk),action='update')
        self.assertTrue(event.credentials_changed)
        serialized=json.dumps({'before':event.before,'after':event.after})
        for value in ('password',old_hash,self.member.password,'new-test-only-secret-passphrase-123'):
            self.assertNotIn(value,serialized)

    def test_actual_django_admin_password_change_has_actor(self):
        url=f'/admin/auth/user/{self.member.pk}/password/'
        token=self.client.get(url).context['record_version']
        response=self.client.post(url,{'password1':'Another-test-passphrase-123!','password2':'Another-test-passphrase-123!','usable_password':'true','_record_version':token})
        self.assertEqual(response.status_code,302)
        event=AuditEvent.objects.get(entity_type='account',entity_id=str(self.member.pk),action='update')
        self.assertTrue(event.credentials_changed)
        self.assertEqual(event.actor_id,self.admin.pk)
        self.assertEqual(event.source,'admin')

    def test_group_membership_changes_are_audited(self):
        group=Group.objects.create(name='Family helpers')
        with audit_transaction(self.admin,'admin'):
            self.member.groups.add(group)
        event=AuditEvent.objects.get(entity_table='auth_user_groups',action='insert')
        self.assertEqual(event.after['user_id'],self.member.pk)
        self.assertEqual(event.after['group_id'],group.pk)

    def test_last_login_only_updates_are_not_business_changes(self):
        before=AuditEvent.objects.filter(entity_type='account').count()
        User.objects.filter(pk=self.member.pk).update(last_login=timezone.now())
        self.assertEqual(AuditEvent.objects.filter(entity_type='account').count(),before)

    def test_nested_rollback_keeps_only_committed_outer_events(self):
        with audit_transaction(self.admin,'app') as reference:
            Bill.objects.filter(pk=self.bill.pk).update(notes='Committed')
            try:
                with audit_transaction(self.member,'admin'):
                    Bill.objects.filter(pk=self.bill.pk).update(notes='Rolled back')
                    raise ValueError('Rollback inner savepoint')
            except ValueError:
                pass
        events=AuditEvent.objects.filter(transaction_id=reference)
        self.assertEqual(events.count(),1)
        self.assertEqual(events.get().after['notes'],'Committed')

    def test_audit_history_is_admin_only_and_no_store(self):
        response=self.client.get('/api/audit/')
        self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response['Cache-Control'])
        self.client.force_login(self.member)
        self.assertEqual(self.client.get('/api/audit/').status_code,403)
        self.client.logout()
        self.assertEqual(self.client.get('/api/audit/').status_code,401)

    def test_review_filters_transaction_reference_and_pagination(self):
        self.payment()
        event=AuditEvent.objects.get(entity_type='payment')
        response=self.client.get('/api/audit/',{'entity_type':'payment','action':'insert','search':'reviewer','transaction':event.transaction_id,'from':timezone.localdate().isoformat(),'to':timezone.localdate().isoformat()})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['total'],1)
        self.assertEqual(response.json()['events'][0]['id'],event.pk)
        self.assertEqual(response.json()['page'],1)
        self.assertEqual(response.json()['pages'],1)

    def test_review_rejects_invalid_filters_and_mutations(self):
        for query in ({'page':'-1'},{'from':'invalid'},{'entity_type':'secret'},{'from':'2027-12-01','to':'2027-01-01'}):
            self.assertEqual(self.client.get('/api/audit/',query).status_code,400)
        self.assertEqual(self.post('/api/audit/',{}).status_code,405)

    def test_audit_records_cannot_be_edited_or_deleted_through_orm(self):
        event=AuditEvent.objects.first()
        with self.assertRaises(ValidationError): AuditEvent.objects.filter(pk=event.pk).update(label='Forged')
        with self.assertRaises(ValidationError): AuditEvent.objects.filter(pk=event.pk).delete()
        with self.assertRaises(ValidationError): event.delete()
        event.label='Forged'
        with self.assertRaises(ValidationError): event.save()

    def test_offline_snapshot_does_not_include_global_audit_records(self):
        response=self.client.get('/api/snapshot/').json()
        self.assertNotIn('events',response)
        self.assertNotIn('audit',response)

    def test_reading_snapshot_does_not_create_settings_or_audit_changes(self):
        from tracker.models import SiteSettings
        self.assertFalse(SiteSettings.objects.exists())
        before=AuditEvent.objects.count()
        self.assertEqual(self.client.get('/api/snapshot/').status_code,200)
        self.assertFalse(SiteSettings.objects.exists())
        self.assertEqual(AuditEvent.objects.count(),before)

    def test_health_checks_actual_audit_trigger_presence(self):
        from tracker.audit import trigger_status
        self.assertEqual(trigger_status()['state'],'healthy')
        with connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
                cursor.execute('ALTER TABLE tracker_bill DISABLE TRIGGER fbt_audit_tracker_bill_insert')
            else:
                cursor.execute('DROP TRIGGER fbt_audit_tracker_bill_insert')
        self.assertEqual(trigger_status()['state'],'error')
