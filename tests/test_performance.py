"""Fictional load fixture; no access to the developer's QA database."""
import json
import os
import shutil
import subprocess
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import skipUnless
import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from tracker.models import Bill, Loan, Payment


@skipUnless(os.getenv('FBT_BROWSER_TESTS')=='1','Enable the real browser suite.')
@override_settings(SECURE_SSL_REDIRECT=False,SESSION_COOKIE_SECURE=False,CSRF_COOKIE_SECURE=False,ALLOWED_HOSTS=['localhost','127.0.0.1','testserver'])
class PerformanceTests(StaticLiveServerTestCase):
    def test_large_household(self):
        admin=get_user_model().objects.create_superuser('qa-admin',password='Fictional-QA-passphrase-123!')
        loan=Loan.objects.create(title='Fictional household loan',total='12000',installments=120,created_by=admin)
        bills=Bill.objects.bulk_create([Bill(title=f'Power {i:04}',amount=Decimal('100'),due_date=date(2027,1,31),responsible=admin,created_by=admin,loan=loan if i<120 else None) for i in range(2000)])
        Payment.objects.bulk_create([Payment(bill=bill,amount=Decimal('100'),paid_date=date(2026,1,1),recorded_by=admin,request_key=uuid.uuid4()) for bill in bills[1000:]])
        self.client.force_login(admin)
        with CaptureQueriesContext(connection) as queries:
            start=time.perf_counter();response=self.client.get('/api/snapshot/');elapsed=(time.perf_counter()-start)*1000
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.json()['bills']),2000)
        self.assertLessEqual(len(queries),10,'Snapshot queries must not grow with each bill/payment.')
        result={'bills':2000,'payments':1000,'snapshotQueries':len(queries),'snapshotBytes':len(response.content),'serverMs':round(elapsed,2),'database':connection.vendor}
        output=Path(settings.BASE_DIR)/'tmp/browser-qa';output.mkdir(parents=True,exist_ok=True)
        (output/f"server-performance-{os.getenv('FBT_BENCHMARK_LABEL','current')}.json").write_text(json.dumps(result,indent=2))
        command=[shutil.which('node'),str(settings.BASE_DIR/'tests/browser-performance.cjs'),self.live_server_url]
        browser=subprocess.run(command,cwd=settings.BASE_DIR,text=True,encoding='utf-8',capture_output=True,timeout=120)
        self.assertEqual(browser.returncode,0,browser.stdout+'\n'+browser.stderr)
