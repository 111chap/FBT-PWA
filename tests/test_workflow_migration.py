from datetime import date
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from tracker.audit import trigger_status


class FamilyWorkflowMigrationTests(TransactionTestCase):
    def test_upgrade_preserves_rows_history_and_all_triggers(self):
        old=[('tracker','0003_audit_triggers')]
        latest=[('tracker','0004_family_workflows')]
        executor=MigrationExecutor(connection)
        try:
            executor.migrate(old)
            apps=executor.loader.project_state(old).apps
            user=apps.get_model('auth','User').objects.create(username='migration-family')
            bill=apps.get_model('tracker','Bill').objects.create(title='Retained bill',amount='100',due_date=date(2028,1,31),responsible_id=user.pk,created_by_id=user.pk)
            before=apps.get_model('tracker','AuditEvent').objects.count()
            executor=MigrationExecutor(connection); executor.migrate(latest)
            apps=executor.loader.project_state(latest).apps
            self.assertFalse(apps.get_model('tracker','Bill').objects.get(pk=bill.pk).removed)
            self.assertEqual(apps.get_model('tracker','AuditEvent').objects.count(),before)
            self.assertEqual(trigger_status()['state'],'healthy')
            apps.get_model('auth','User').objects.filter(pk=user.pk).update(email='migration@example.test')
            event=apps.get_model('tracker','AuditEvent').objects.order_by('-id').first()
            self.assertEqual(event.after['email'],'migration@example.test')
        finally:
            MigrationExecutor(connection).migrate(latest)
