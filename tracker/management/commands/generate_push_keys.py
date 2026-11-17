import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Generate VAPID settings. Keep the private key in .env only.'

    def handle(self, *args, **kwargs):
        key = ec.generate_private_key(ec.SECP256R1())
        private = key.private_numbers().private_value.to_bytes(32, 'big')
        public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b'=').decode()
        self.stdout.write(f'VAPID_PRIVATE_KEY={encode(private)}\nVAPID_PUBLIC_KEY={encode(public)}')
