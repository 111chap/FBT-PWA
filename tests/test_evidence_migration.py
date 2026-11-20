from datetime import date
import uuid
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError
from django.test import TransactionTestCase
from tracker.audit import trigger_status


class EvidenceMigrationTests(TransactionTestCase):
    def test_legacy_payments_and_conflicting_installment_notes_survive_upgrade(self):
        old=[('tracker','0006_privacy_pin_bill_types')];latest=[('tracker','0007_notes_receipts_and_qr')]
        try:
            executor=MigrationExecutor(connection);executor.migrate(old);apps=executor.loader.project_state(old).apps
            user=apps.get_model('auth','User').objects.create(username='evidence-migration-fixture')
            loan=apps.get_model('tracker','Loan').objects.create(title='Historical fixture',total='200',installments=2,created_by_id=user.pk,owner_id=user.pk)
            ids=[]
            for i in (1,2):
                bill=apps.get_model('tracker','Bill').objects.create(title=f'Historical installment {i}',amount='100',due_date=date(2026,i,1),created_by_id=user.pk,responsible_id=user.pk,owner_id=user.pk,loan_id=loan.pk,notes=f'Conflicting individual note {i}',bill_type='loan')
                apps.get_model('tracker','Payment').objects.create(bill_id=bill.pk,amount='100',paid_date=date(2026,i,1),recorded_by_id=user.pk,request_key=uuid.uuid4());ids.append(bill.pk)
            before=apps.get_model('tracker','AuditEvent').objects.count()
            executor=MigrationExecutor(connection);executor.migrate(latest);apps=executor.loader.project_state(latest).apps
            self.assertEqual(apps.get_model('tracker','AuditEvent').objects.count(),before)
            self.assertEqual(apps.get_model('tracker','Loan').objects.get(pk=loan.pk).description,'')
            self.assertEqual(list(apps.get_model('tracker','Bill').objects.filter(pk__in=ids).order_by('id').values_list('notes',flat=True)),['Conflicting individual note 1','Conflicting individual note 2'])
            self.assertTrue(all(not p.receipt_required and p.receipt_id is None for p in apps.get_model('tracker','Payment').objects.all()))
            self.assertEqual(trigger_status()['state'],'healthy')
            apps.get_model('tracker','Loan').objects.filter(pk=loan.pk).update(description='New shared note')
            apps.get_model('tracker','Loan').objects.filter(pk=loan.pk).update(description='')
            with self.assertRaises(IrreversibleError):MigrationExecutor(connection).migrate(old)
        finally:MigrationExecutor(connection).migrate(latest)
