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
from tracker.models import Bill, Recurrence, Loan, Payment, SiteSettings
from datetime import date
import uuid


@skipUnless(os.getenv('FBT_BROWSER_TESTS') == '1', 'Set FBT_BROWSER_TESTS=1 to run real-browser checks.')
@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False, ALLOWED_HOSTS=['localhost','127.0.0.1','testserver'])
class BrowserWorkflowTests(StaticLiveServerTestCase):
    def test_remaining_notes_receipts_qr_and_totals(self):
        get_user_model().objects.create_superuser('qa-admin',password='Fictional-QA-passphrase-123!')
        result=subprocess.run([shutil.which('node'),str(settings.BASE_DIR/'tests/browser-remaining-features.cjs'),self.live_server_url],cwd=settings.BASE_DIR,text=True,encoding='utf-8',capture_output=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    @override_settings(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https'))
    def test_privacy_pin_and_one_time_bill_mobile(self):
        admin=get_user_model().objects.create_superuser('qa-admin',password='Fictional-QA-passphrase-123!')
        member=get_user_model().objects.create_user('qa-member',password='Fictional-QA-passphrase-123!')
        Bill.objects.create(title='Private fictional school fee',amount='100',due_date=timezone.localdate(),owner=member,visibility='private',created_by=member,responsible=member)
        Bill.objects.create(title='Shared fictional water',amount='100',due_date=timezone.localdate(),owner=admin,visibility='family',created_by=admin,responsible=admin)
        with self.settings(CSRF_TRUSTED_ORIGINS=[self.live_server_url]):
            result=subprocess.run([shutil.which('node'),str(settings.BASE_DIR/'tests/browser-privacy-pin.cjs'),self.live_server_url],cwd=settings.BASE_DIR,text=True,encoding='utf-8',capture_output=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_mobile_navigation_geometry_and_readable_header(self):
        get_user_model().objects.create_superuser('qa-admin', password='Fictional-QA-passphrase-123!')
        SiteSettings.objects.create(family_name='A fictional household with a longer display name')
        result = subprocess.run([shutil.which('node'), str(settings.BASE_DIR/'tests/browser-mobile-navigation.cjs'), self.live_server_url], cwd=settings.BASE_DIR, text=True, encoding='utf-8', capture_output=True, timeout=150)
        self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)

    def test_public_themes_and_modification_buttons(self):
        admin=get_user_model().objects.create_superuser('qa-admin',password='Fictional-QA-passphrase-123!')
        loan=Loan.objects.create(title='Fictional repayment',total='100',installments=1,created_by=admin)
        for title,parent,paid in [('Unpaid utility',None,False),('Paid utility',None,True),('Loan installment',loan,False)]:
            bill=Bill.objects.create(title=title,amount='100',due_date=timezone.localdate(),responsible=admin,created_by=admin,loan=parent)
            if paid:Payment.objects.create(receipt_required=False,bill=bill,amount='100',paid_date=timezone.localdate(),recorded_by=admin,request_key=uuid.uuid4())
        result=subprocess.run([shutil.which('node'),str(settings.BASE_DIR/'tests/browser-ui-consistency.cjs'),self.live_server_url],cwd=settings.BASE_DIR,text=True,encoding='utf-8',capture_output=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_admin_financial_corrections(self):
        admin=get_user_model().objects.create_superuser('qa-admin',password='Fictional-QA-passphrase-123!')
        member=get_user_model().objects.create_user('qa-member',password='Fictional-QA-passphrase-123!')
        loan=Loan.objects.create(title='Paid bicycle',total='200',installments=2,created_by=admin)
        for title,amount,parent,paid in [('Paid water','100',None,True),('Bike 1','100',loan,True),('Bike 2','100',loan,True),('Electricity','90',None,False)]:
            bill=Bill.objects.create(title=title,amount=amount,due_date=timezone.localdate(),responsible=member,created_by=admin,loan=parent)
            if paid:Payment.objects.create(receipt_required=False,bill=bill,amount=amount,paid_date=timezone.localdate(),recorded_by=member,request_key=uuid.uuid4())
        result=subprocess.run([shutil.which('node'),str(settings.BASE_DIR/'tests/browser-corrections.cjs'),self.live_server_url],cwd=settings.BASE_DIR,text=True,encoding='utf-8',capture_output=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_profile_and_responsive_matrix(self):
        admin=get_user_model().objects.create_superuser('qa-admin',password='Fictional-QA-passphrase-123!')
        get_user_model().objects.create_user('qa-member-with-a-long-display-name-for-layout-checks',password='Fictional-QA-passphrase-123!')
        SiteSettings.objects.update_or_create(pk=1,defaults={'family_name':'A fictional family with a long workspace name for responsive layout checks'})
        Bill.objects.create(title='A fictional household utility with a long descriptive title for mobile cards',amount='100',due_date=timezone.localdate(),responsible=admin,created_by=admin)
        for index in range(35):
            loan=Loan.objects.create(title=f'Fictional loan {index:02}',total='100',installments=1,created_by=admin)
            Bill.objects.create(title=f'Loan installment {index:02}',amount='100',due_date=timezone.localdate(),responsible=admin,created_by=admin,loan=loan)
        result=subprocess.run([shutil.which('node'),str(settings.BASE_DIR/'tests/browser-profile-responsive.cjs'),self.live_server_url],cwd=settings.BASE_DIR,text=True,encoding='utf-8',capture_output=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_toffee_theme_and_offline_font(self):
        admin=get_user_model().objects.create_superuser('qa-admin',password='Fictional-QA-passphrase-123!')
        loan=Loan.objects.create(title='Family bicycle',total='200',installments=2,created_by=admin)
        Bill.objects.create(title='Electricity',amount='90',due_date=timezone.localdate(),created_by=admin,responsible=admin)
        Bill.objects.create(title='Bicycle installment',amount='100',due_date=timezone.localdate(),created_by=admin,responsible=admin,loan=loan)
        paid=Bill.objects.create(title='Water',amount='30',due_date=timezone.localdate(),created_by=admin,responsible=admin)
        Payment.objects.create(receipt_required=False,bill=paid,amount='30',paid_date=timezone.localdate(),recorded_by=admin,request_key=uuid.uuid4())
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
            Payment.objects.create(receipt_required=False,bill=target,amount=amount,paid_date=paid,recorded_by=recorder,request_key=uuid.uuid4())
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
