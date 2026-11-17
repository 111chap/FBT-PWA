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
from tracker.models import Bill, Recurrence, Loan, Payment
from datetime import date
import uuid


@skipUnless(os.getenv('FBT_BROWSER_TESTS') == '1', 'Set FBT_BROWSER_TESTS=1 to run real-browser checks.')
@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False, ALLOWED_HOSTS=['localhost','127.0.0.1','testserver'])
class BrowserWorkflowTests(StaticLiveServerTestCase):
    def test_toffee_theme_and_offline_font(self):
        admin=get_user_model().objects.create_superuser('qa-admin',password='Fictional-QA-passphrase-123!')
        loan=Loan.objects.create(title='Family bicycle',total='200',installments=2,created_by=admin)
        Bill.objects.create(title='Electricity',amount='90',due_date=timezone.localdate(),created_by=admin,responsible=admin)
        Bill.objects.create(title='Bicycle installment',amount='100',due_date=timezone.localdate(),created_by=admin,responsible=admin,loan=loan)
        paid=Bill.objects.create(title='Water',amount='30',due_date=timezone.localdate(),created_by=admin,responsible=admin)
        Payment.objects.create(bill=paid,amount='30',paid_date=timezone.localdate(),recorded_by=admin,request_key=uuid.uuid4())
        result=subprocess.run([shutil.which('node'),str(settings.BASE_DIR/'tests/browser-theme.cjs'),self.live_server_url],cwd=settings.BASE_DIR,text=True,encoding='utf-8',capture_output=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_guided_entry_paid_history_and_column_sorting(self):
        User=get_user_model()
        admin=User.objects.create_superuser('qa-admin',password='Fictional-QA-passphrase-123!')
        member=User.objects.create_user('qa-member',password='Fictional-QA-passphrase-123!')
        retired=User.objects.create_user('qa-retired',is_active=False)
        def bill(title,amount,payer,due=date(2027,1,31),loan=None):
            return Bill.objects.create(title=title,amount=amount,due_date=due,category='Loan' if loan else 'Water',responsible=payer,created_by=admin,loan=loan)
        def pay(target,amount,recorder,paid=date(2025,12,1)):
            Payment.objects.create(bill=target,amount=amount,paid_date=paid,recorded_by=recorder,request_key=uuid.uuid4())
        paid=bill('Sort fixture Delta','100',member,date(2026,1,31))
        pay(paid,'40',admin,date(2026,1,20));pay(paid,'60',member,date(2026,1,25))
        partial=bill('Sort fixture Alpha','200',member);pay(partial,'50',admin)
        bill('Sort fixture Beta','9',member)
        bill('Sort fixture Gamma','20',member,date(2020,1,1))
        loan=Loan.objects.create(title='Family car',total='50',installments=1,created_by=admin)
        pay(bill('Car · 1/1','50',retired,date(2026,2,28),loan),'50',admin,date(2026,2,1))
        for index in range(26): pay(bill(f'History utility {index:02}','10',admin),'10',admin)
        result=subprocess.run([shutil.which('node'),str(settings.BASE_DIR/'tests/browser-bill-views.cjs'),self.live_server_url],cwd=settings.BASE_DIR,text=True,encoding='utf-8',capture_output=True,timeout=150)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

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
