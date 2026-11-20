from datetime import date
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError
from django.test import TransactionTestCase
from tracker.audit import trigger_status


class PrivacyMigrationTests(TransactionTestCase):
    def test_legacy_records_stay_family_and_keep_history_and_balances(self):
        old=[('tracker','0005_financial_corrections')]
        latest=[('tracker','0006_privacy_pin_bill_types')]
        try:
            executor=MigrationExecutor(connection);executor.migrate(old)
            apps=executor.loader.project_state(old).apps
            user=apps.get_model('auth','User').objects.create(username='migration-private-fixture')
            loan=apps.get_model('tracker','Loan').objects.create(title='Historical agreement',total='10',installments=1,created_by_id=user.pk)
            bill=apps.get_model('tracker','Bill').objects.create(title='Historical installment',amount='10',due_date=date(2026,1,1),created_by_id=user.pk,responsible_id=user.pk,loan_id=loan.pk)
            utility=apps.get_model('tracker','Bill').objects.create(title='Non-repeating historical utility',amount='20',due_date=date(2026,1,1),created_by_id=user.pk,responsible_id=user.pk)
            before=apps.get_model('tracker','AuditEvent').objects.count()
            executor=MigrationExecutor(connection);executor.migrate(latest)
            apps=executor.loader.project_state(latest).apps
            upgraded=apps.get_model('tracker','Bill').objects.get(pk=bill.pk)
            self.assertEqual((upgraded.owner_id,upgraded.visibility,upgraded.bill_type),(user.pk,'family','loan'))
            self.assertEqual(apps.get_model('tracker','Bill').objects.get(pk=utility.pk).bill_type,'utilities')
            self.assertEqual(apps.get_model('tracker','AuditEvent').objects.count(),before)
            self.assertEqual(trigger_status()['state'],'healthy')
            apps.get_model('tracker','Bill').objects.filter(pk=bill.pk).update(visibility='private')
            with self.assertRaises(IrreversibleError):MigrationExecutor(connection).migrate(old)
            # A later share must not make a downgrade expose private audit history.
            apps.get_model('tracker','Bill').objects.filter(pk=bill.pk).update(visibility='family')
            with self.assertRaises(IrreversibleError):MigrationExecutor(connection).migrate(old)
            self.assertEqual(trigger_status()['state'],'healthy')
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_database_rejects_private_records_without_owner_and_repeating_one_time(self):
        from tracker.models import Bill, Recurrence
        from django.contrib.auth import get_user_model
        user=get_user_model().objects.create(username='constraint-fixture')
        fields={'title':'Fixture','amount':'10','due_date':date(2026,1,1),'created_by':user,'responsible':user}
        with self.assertRaises(IntegrityError), transaction.atomic():
            Bill.objects.create(**fields,visibility='private')
        recurrence=Recurrence.objects.create(title='Fixture schedule',amount='10',next_due=date(2026,1,1),anchor_day=1,created_by=user,responsible=user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Bill.objects.create(**fields,bill_type='one-time',recurrence=recurrence)
