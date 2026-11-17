"""Real-browser regression suite, enabled in CI and with FBT_BROWSER_TESTS=1."""
import os
import shutil
import subprocess
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.conf import settings
from django.utils import timezone
from tracker.models import Bill, Recurrence


@skipUnless(os.getenv('FBT_BROWSER_TESTS') == '1', 'Set FBT_BROWSER_TESTS=1 to run real-browser checks.')
@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False, ALLOWED_HOSTS=['localhost','127.0.0.1','testserver'])
class BrowserWorkflowTests(StaticLiveServerTestCase):
    @override_settings(FBT_SETUP_TOKEN='fictional-first-run-code-123')
    def test_first_family_setup_requires_review_in_browser(self):
        result=subprocess.run([shutil.which('node'),str(settings.BASE_DIR/'tests/browser-bootstrap.cjs'),self.live_server_url],cwd=settings.BASE_DIR,text=True,encoding='utf-8',capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertEqual(get_user_model().objects.filter(username='qa-first-admin',is_superuser=True).count(),1)

    def test_review_roles_layout_and_offline(self):
        User=get_user_model()
        admin=User.objects.create_superuser('qa-admin',password='Fictional-QA-passphrase-123!')
        member=User.objects.create_user('qa-member',password='Fictional-QA-passphrase-123!')
        recurrence=Recurrence.objects.create(title='QA Internet',amount='100',next_due=timezone.localdate(),anchor_day=31,responsible=member,created_by=admin)
        Bill.objects.create(title='QA Internet',amount='100',due_date=timezone.localdate(),responsible=member,created_by=admin,recurrence=recurrence)
        result=subprocess.run([shutil.which('node'),str(settings.BASE_DIR/'tests/browser-workflows.cjs'),self.live_server_url],cwd=settings.BASE_DIR,text=True,encoding='utf-8',capture_output=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
