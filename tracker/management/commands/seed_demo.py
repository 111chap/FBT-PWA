import os
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from tracker.models import Bill, SiteSettings


class Command(BaseCommand):
    help = 'Create fictional local-preview records; never runs in production.'

    def handle(self, *args, **kwargs):
        if not settings.DEBUG or settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3':
            raise CommandError('Demo data is available only in local SQLite development mode.')
        password = os.getenv('FBT_DEMO_PASSWORD')
        if not password or len(password) < 12:
            raise CommandError('Set FBT_DEMO_PASSWORD to a development-only password of at least 12 characters.')
        User = get_user_model()
        if User.objects.exclude(username__in=['demo', 'sam']).exists():
            raise CommandError('Refusing to mix demo data with existing family accounts.')
        owner, _ = User.objects.get_or_create(username='demo', defaults={'is_staff': True, 'is_superuser': True})
        owner.set_password(password)
        owner.save()
        member, _ = User.objects.get_or_create(username='sam')
        member.set_unusable_password()
        member.save()
        SiteSettings.objects.update_or_create(pk=1, defaults={'family_name': 'The Rivera family · Demo', 'nas_name': 'Our family Synology'})
        for title, amount, days, category, responsible in [('Electricity', '2840.50', 2, 'Utilities', owner), ('Home internet', '1699.00', 4, 'Internet', member), ('Water bill', '485.75', -2, 'Utilities', owner), ('Health insurance', '3200.00', 8, 'Insurance', member)]:
            Bill.objects.get_or_create(title=title, defaults={'amount': amount, 'due_date': timezone.localdate() + timedelta(days=days), 'category': category, 'responsible': responsible, 'created_by': owner})
        self.stdout.write('Fictional local demo records are ready. Sign in as demo using FBT_DEMO_PASSWORD.')
