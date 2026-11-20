from django.core.management.base import BaseCommand
from tracker.media import cleanup_unused
from tracker.audit import audit_transaction


class Command(BaseCommand):
    help='Remove abandoned staged uploads and unreferenced files older than 48 hours. Retained evidence is never removed.'

    def handle(self,*args,**options):
        with audit_transaction(source='worker'):cleanup_unused()
        self.stdout.write('Unused media cleanup completed.')
