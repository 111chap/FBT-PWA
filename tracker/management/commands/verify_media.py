"""Run after an isolated restore, or to check NAS media integrity."""
from django.core.management.base import BaseCommand, CommandError
from tracker.models import MediaAsset
from tracker.media import open_verified, StorageUnavailable


class Command(BaseCommand):
    help='Verify every retained finalized image against the database size and SHA-256 manifest.'

    def handle(self,*args,**options):
        checked=failed=0
        for asset in MediaAsset.objects.filter(finalized=True).iterator():
            try:
                with open_verified(asset):pass
                checked+=1
            except StorageUnavailable:failed+=1
        if failed:raise CommandError(f'{failed} retained image(s) are missing or do not match the backup manifest. Do not use this restore.')
        self.stdout.write(f'Verified {checked} retained image(s). This does not authenticate external payments.')
