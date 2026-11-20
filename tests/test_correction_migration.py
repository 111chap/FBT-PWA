from datetime import date
import uuid
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError
from django.test import TransactionTestCase
from tracker.audit import trigger_status


class CorrectionMigrationTests(TransactionTestCase):
    def test_upgrade_retains_paid_records_and_refuses_lossy_downgrade(self):
        old=[('tracker','0004_family_workflows')];latest=[('tracker','0005_financial_corrections')]
        try:
            executor=MigrationExecutor(connection);executor.migrate(old);apps=executor.loader.project_state(old).apps
            user=apps.get_model('auth','User').objects.create(username='migration-correction')
            bill=apps.get_model('tracker','Bill').objects.create(title='Paid migration fixture',amount='100',due_date=date(2026,1,1),responsible_id=user.pk,created_by_id=user.pk)
            payment=apps.get_model('tracker','Payment').objects.create(bill_id=bill.pk,amount='100',paid_date=date(2026,1,1),recorded_by_id=user.pk,request_key=uuid.uuid4())
            count=apps.get_model('tracker','AuditEvent').objects.count()
            executor=MigrationExecutor(connection);executor.migrate(latest);apps=executor.loader.project_state(latest).apps
            self.assertEqual(apps.get_model('tracker','AuditEvent').objects.count(),count)
            self.assertFalse(apps.get_model('tracker','Payment').objects.get(pk=payment.pk).removed)
            self.assertEqual(trigger_status()['state'],'healthy')
            apps.get_model('tracker','Payment').objects.filter(pk=payment.pk).update(removed=True)
            with self.assertRaises(IrreversibleError):MigrationExecutor(connection).migrate(old)
            self.assertTrue(apps.get_model('tracker','Payment').objects.get(pk=payment.pk).removed)
            self.assertEqual(trigger_status()['state'],'healthy')
        finally:MigrationExecutor(connection).migrate([('tracker','0006_privacy_pin_bill_types')])
