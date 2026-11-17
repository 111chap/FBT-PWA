import time
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import connection, transaction, close_old_connections
from django.utils import timezone
from tracker.models import WorkerHeartbeat, LoginFailure
from tracker.services import materialize_recurring, deliver_reminders


class Command(BaseCommand):
    help = 'Run the single reminder scheduler and publish a real heartbeat.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        while True:
            try:
                WorkerHeartbeat.objects.get_or_create(name='reminders')
                with transaction.atomic():
                    # The lock prevents two deployed workers from scheduling concurrently.
                    WorkerHeartbeat.objects.select_for_update().get(name='reminders')
                    materialize_recurring()
                    deliver_reminders()
                    LoginFailure.objects.filter(created_at__lt=timezone.now() - timedelta(days=1)).delete()
                    WorkerHeartbeat.objects.filter(name='reminders').update(updated_at=timezone.now(), detail='Schedule checked successfully')
            except Exception:
                self.stderr.write('Worker cycle failed. Check database connectivity and configuration.')
                if options['once']:
                    raise
            if options['once']:
                break
            close_old_connections()
            time.sleep(60)
