"""Production WSGI entry point for the loopback-bound NAS reverse proxy."""
import os
from waitress import serve
from config.wsgi import application

options = {'listen': '0.0.0.0:8000', 'threads': 4, 'max_request_body_size': 16384, 'expose_tracebacks': False}
if os.getenv('FBT_TRUST_PROXY') == '1':
    # Only DSM should reach the app through the loopback-bound Docker port.
    # Trust the scheme header, never forwarded host or client IP headers.
    options.update(trusted_proxy='*', trusted_proxy_headers={'x-forwarded-proto'})
serve(application, **options)
