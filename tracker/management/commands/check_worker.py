from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from tracker.models import WorkerHeartbeat


class Command(BaseCommand):
    def handle(self, *args, **options):
        if not WorkerHeartbeat.objects.filter(name='reminders', updated_at__gte=timezone.now() - timedelta(minutes=3)).exists():
            raise CommandError('Reminder worker heartbeat is missing or stale.')
        self.stdout.write('Worker heartbeat is current.')
