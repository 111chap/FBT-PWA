import base64
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from django.test import SimpleTestCase
from tools.make_env import build_env
from py_vapid import Vapid


class SetupConfigurationTests(SimpleTestCase):
    def test_generated_credentials_are_random_and_keys_match(self):
        parse = lambda value: dict(line.split('=',1) for line in value.splitlines() if line and not line.startswith('#'))
        first=parse(build_env('https://bills.example.com','admin@example.com'))
        second=parse(build_env('https://bills.example.com','admin@example.com'))
        for field in ('DJANGO_SECRET_KEY','POSTGRES_PASSWORD','FBT_SETUP_TOKEN','VAPID_PRIVATE_KEY'):
            self.assertNotEqual(first[field],second[field])
        self.assertGreaterEqual(len(first['DJANGO_SECRET_KEY']),50)
        key=Vapid.from_string(first['VAPID_PRIVATE_KEY'])
        from cryptography.hazmat.primitives import serialization
        public=key.public_key.public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        self.assertEqual(base64.urlsafe_b64encode(public).rstrip(b'=').decode(),first['VAPID_PUBLIC_KEY'])
        self.assertEqual(first['FBT_DEBUG'],'0')
        self.assertEqual(first['FBT_TRUSTED_ORIGINS'],'https://bills.example.com')

    def test_configuration_rejects_injected_values_and_insecure_origin(self):
        for origin in ('http://nas.local','https://user:secret@nas.local','https://nas.local/path','https://nas.local/?secret=1'):
            with self.assertRaises(ValueError): build_env(origin,'admin@example.com')
        with self.assertRaises(ValueError): build_env('https://nas.local','admin@example.com\nFBT_DEBUG=1')
