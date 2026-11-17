"""Generate private NAS settings without overwriting an existing deployment."""
import argparse
import base64
import os
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization


def build_env(origin, contact):
    parts = urlsplit(origin)
    if parts.scheme != 'https' or not parts.hostname or parts.path not in ('', '/') or parts.username or parts.password or parts.query or parts.fragment or not re.fullmatch(r'[a-zA-Z0-9.-]+', parts.hostname):
        raise ValueError('Use an HTTPS origin with a hostname and no path, credentials, or query.')
    if not re.fullmatch(r'[^\s@=]+@[^\s@=]+\.[^\s@=]+', contact):
        raise ValueError('Enter a valid contact email.')
    parts.port  # Reject invalid ports.
    key = ec.generate_private_key(ec.SECP256R1())
    encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b'=').decode()
    private = key.private_numbers().private_value.to_bytes(32, 'big')
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return '\n'.join(['# Private configuration. Never commit this file.', f'DJANGO_SECRET_KEY={secrets.token_hex(40)}', f'POSTGRES_PASSWORD={secrets.token_hex(40)}', f'FBT_SETUP_TOKEN={secrets.token_hex(40)}', f'FBT_ALLOWED_HOSTS={parts.hostname},localhost,127.0.0.1', f'FBT_TRUSTED_ORIGINS=https://{parts.netloc}', 'FBT_TRUST_PROXY=1', 'FBT_DEBUG=0', f'VAPID_PRIVATE_KEY={encode(private)}', f'VAPID_PUBLIC_KEY={encode(public)}', f'VAPID_SUBJECT=mailto:{contact}', ''])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--contact', required=True)
    parser.add_argument('--output', type=Path, default=Path('.env'))
    args = parser.parse_args()
    try:
        content = build_env(args.origin, args.contact)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
        print('Private settings created. Read FBT_SETUP_TOKEN locally for first-time enrollment.')
    except (ValueError, FileExistsError) as error:
        parser.error(str(error))
