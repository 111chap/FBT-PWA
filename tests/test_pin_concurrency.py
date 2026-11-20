import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import connection, close_old_connections
from django.test import TransactionTestCase, Client, override_settings
from django.utils import timezone
from tracker.models import PinCredential, PinDevice
from tracker.security import digest


@skipUnless(connection.vendor=='postgresql','Concurrency requires PostgreSQL row locks.')
@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class PinConcurrencyTests(TransactionTestCase):
    def test_parallel_guesses_share_persistent_account_cooldown(self):
        user=get_user_model().objects.create_user('concurrent-pin-fixture',password='Fictional-passphrase-42!')
        PinCredential.objects.create(user=user,pin_hash=make_password('839274'))
        token=secrets.token_urlsafe(32)
        PinDevice.objects.create(user=user,verifier=digest(token),password_stamp=digest(user.password),expires_at=timezone.now()+timedelta(days=1))
        barrier=Barrier(2)
        def guesses(index):
            close_old_connections()
            try:
                client=Client();client.cookies['fbt_pin_device']=token
                barrier.wait(timeout=10)
                return [client.post('/login/pin/',{'pin':'482975'},secure=True,REMOTE_ADDR=f'192.0.2.{index}').status_code for _ in range(3)]
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(guesses,[1,2]))
        self.assertEqual(results,[[200]*3,[200]*3])
        credential=PinCredential.objects.get(user=user)
        self.assertEqual(credential.strikes,1)
        self.assertGreater(credential.blocked_until,timezone.now())
        client=Client();client.cookies['fbt_pin_device']=token
        self.assertEqual(client.post('/login/pin/',{'pin':'839274'},secure=True,REMOTE_ADDR='192.0.2.99').status_code,200)
        self.assertNotIn('_auth_user_id',client.session)
