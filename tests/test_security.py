import json
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from tracker.models import Bill, Payment, SiteSettings, PushSubscription, LoginFailure
from tests.media_helpers import receipt
from tracker.services import validate_push_endpoint, validate_server_url

User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class SecurityTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', password='test-only-LongPass!123')
        self.member = User.objects.create_user('member', password='test-only-LongPass!456')
        self.bill = Bill.objects.create(title='Electricity', amount='2500.00', due_date=timezone.localdate(), responsible=self.member, created_by=self.admin)

    def post(self, path, value):
        return self.client.post(path, data=json.dumps(value), content_type='application/json')

    def test_private_endpoints_require_authentication(self):
        for path in ('/api/snapshot/', '/api/status/', '/api/export/', '/api/reachable/'):
            self.assertEqual(self.client.get(path).status_code, 401, path)
        self.assertEqual(self.post('/api/bills/', {}).status_code, 401)
        self.assertEqual(self.post('/api/loans/', {}).status_code, 401)
        self.assertEqual(self.post('/api/push/', {}).status_code, 401)

    def test_csrf_blocks_forged_payments_and_settings(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        for path in (f'/api/bills/{self.bill.pk}/payments/', '/api/settings/', '/logout/'):
            self.assertEqual(client.post(path, '{}', content_type='application/json').status_code, 403)
        self.assertEqual(Payment.objects.count(), 0)

    def test_login_and_bootstrap_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/login/', {'username':'admin','password':'test-only-LongPass!123'}).status_code,403)
        self.assertEqual(client.post('/setup/', {}).status_code,403)

    def test_family_member_cannot_reassign_server(self):
        self.client.force_login(self.member)
        response = self.post('/api/settings/', {'family_name':'Changed','nas_name':'Changed','server_url':'https://evil.example'})
        self.assertEqual(response.status_code,403)

    def test_disabled_member_cannot_access_family_records(self):
        self.client.force_login(self.member)
        self.member.is_active = False
        self.member.save()
        self.assertEqual(self.client.get('/api/snapshot/').status_code,401)

    def test_all_active_family_members_share_records(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get('/api/snapshot/').json()['bills'][0]['title'],'Electricity')

    def test_no_personal_data_or_secrets_in_public_shell(self):
        self.bill.title = 'Private invoice 5291'
        self.bill.save()
        content = self.client.get('/app/').content.decode()
        for secret in ('Private invoice 5291', '2500.00', settings.SECRET_KEY, 'test-only-LongPass!123'):
            self.assertNotIn(secret,content)

    def test_authenticated_responses_not_browser_cacheable(self):
        self.client.force_login(self.admin)
        for path in ('/api/snapshot/','/api/status/','/api/export/'):
            response = self.client.get(path)
            self.assertIn('no-store',response.headers['Cache-Control'])
            self.assertIn("script-src 'self'",response.headers['Content-Security-Policy'])
            self.assertEqual(response.headers['X-Frame-Options'],'DENY')

    def test_login_rate_limit_persists_in_database(self):
        for _ in range(5):
            self.client.post('/login/',{'username':'admin','password':'wrong'})
        other_client = Client()
        response = other_client.post('/login/',{'username':'admin','password':'test-only-LongPass!123'})
        self.assertEqual(response.status_code,429)
        self.assertFalse('_auth_user_id' in other_client.session)

    def test_setup_is_closed_after_first_user(self):
        self.assertRedirects(self.client.get('/setup/'),'/login/')
        self.assertEqual(User.objects.count(),2)

    def test_rejects_server_urls_with_credentials_paths_or_http(self):
        with override_settings(DEBUG=False):
            for url in ('http://nas.local','https://user:pass@nas.local','https://nas.local/path','javascript:alert(1)','https://nas.local/?token=secret'):
                with self.assertRaises(ValidationError,msg=url): validate_server_url(url)

    def test_push_endpoints_cannot_target_private_network_or_unknown_hosts(self):
        for url in ('http://127.0.0.1:5000','https://192.168.1.1/','https://fcm.googleapis.com.evil.example/','https://evil.example/','https://user:pass@fcm.googleapis.com/','https://fcm.googleapis.com:444/'):
            with self.assertRaises(ValidationError,msg=url): validate_push_endpoint(url)

    def test_existing_push_device_cannot_be_claimed_by_another_account(self):
        endpoint='https://fcm.googleapis.com/fcm/send/test-device'
        PushSubscription.objects.create(user=self.admin,endpoint=endpoint,keys={'p256dh':'a'*50,'auth':'b'*24})
        self.client.force_login(self.member)
        response=self.post('/api/push/',{'endpoint':endpoint,'keys':{'p256dh':'a'*50,'auth':'b'*24}})
        self.assertEqual(response.status_code,409)
        self.assertEqual(PushSubscription.objects.get().user,self.admin)

    def test_unsubscribe_cannot_remove_another_users_device(self):
        subscription=PushSubscription.objects.create(user=self.admin,endpoint='https://fcm.googleapis.com/fcm/send/test',keys={})
        self.client.force_login(self.member)
        self.client.delete('/api/push/',json.dumps({'endpoint':subscription.endpoint}),content_type='application/json')
        self.assertTrue(PushSubscription.objects.filter(pk=subscription.pk).exists())

    def test_csv_formula_injection_is_neutralized(self):
        self.bill.title='=HYPERLINK("https://evil.example")'
        self.bill.save()
        self.client.force_login(self.member)
        text=self.client.get('/api/export/').content.decode()
        self.assertIn("'=HYPERLINK",text)

    def test_login_form_does_not_render_unescaped_user_input(self):
        self.client.force_login(self.member)
        self.bill.title='<img src=x onerror=alert(1)>'
        self.bill.save()
        # JSON transports raw text; the frontend inserts user values through escaping/textContent.
        response=self.client.get('/api/snapshot/')
        self.assertEqual(response['Content-Type'],'application/json')
        self.assertIn("script-src 'self'",response['Content-Security-Policy'])

    def test_malformed_and_oversized_json_are_rejected(self):
        self.client.force_login(self.member)
        for content in ('null','[]','{bad json',json.dumps({'title':'x'*13000})):
            self.assertEqual(self.client.post('/api/bills/',content,content_type='application/json').status_code,400)

    def test_money_rejects_negative_nan_and_fractional_cents(self):
        self.client.force_login(self.member)
        for amount in ('-1','0','NaN','Infinity','1.001','10000000000'):
            response=self.post('/api/bills/',{'title':'Invalid','amount':amount,'due_date':'2026-11-20'})
            self.assertEqual(response.status_code,400,amount)

    def test_logout_invalidates_server_session(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post('/logout/').status_code,200)
        self.assertEqual(self.client.get('/api/snapshot/').status_code,401)

    def test_csrf_token_allows_real_same_origin_payment(self):
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.member)
        client.get('/app/')
        response=client.post(f'/api/bills/{self.bill.pk}/payments/',json.dumps({'receipt_id':str(receipt(self.bill,self.member).pk),'amount':'100.00','paid_date':timezone.localdate().isoformat(),'request_key':str(uuid.uuid4())}),content_type='application/json',HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code,201)


@override_settings(SECURE_SSL_REDIRECT=False, FBT_SETUP_TOKEN='test-one-time-secret-code')
class FirstRunTests(TestCase):
    def test_wrong_token_cannot_claim_instance(self):
        self.client.post('/setup/',{'token':'wrong','family_name':'Test','username':'owner','password':'A-long-private-passphrase-123'})
        self.assertFalse(User.objects.exists())

    def test_strong_password_and_correct_token_bootstrap_once(self):
        response=self.client.post('/setup/',{'token':'test-one-time-secret-code','family_name':'Test Family','username':'owner','password':'A-long-private-passphrase-123'})
        self.assertEqual(response.status_code,302)
        self.assertTrue(User.objects.get().is_superuser)
        self.assertEqual(SiteSettings.objects.get().family_name,'Test Family')
        self.client.post('/setup/',{'token':'test-one-time-secret-code','family_name':'Other','username':'intruder','password':'Another-long-private-pass-123'})
        self.assertEqual(User.objects.count(),1)

    def test_bootstrap_rejects_weak_password(self):
        response=self.client.post('/setup/',{'token':'test-one-time-secret-code','family_name':'Test','username':'owner','password':'123'})
        self.assertEqual(response.status_code,400)
        self.assertFalse(User.objects.exists())
