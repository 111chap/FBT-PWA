"""Attach attribution to database triggers without separating logs from their writes."""
from contextlib import contextmanager
from contextvars import ContextVar
import uuid
from functools import wraps
from django.db import connection, transaction
from .models import AuditContext

_current = ContextVar('fbt_audit_transaction', default=None)
FIELDS = ('actor_id', 'actor_name', 'transaction_id', 'source')
AUDITED_TABLES = ('tracker_bill', 'tracker_payment', 'tracker_loan', 'tracker_recurrence', 'tracker_sitesettings', 'auth_user', 'auth_user_groups', 'auth_user_user_permissions', 'auth_group', 'auth_group_permissions', 'tracker_pushsubscription', 'tracker_reminderdelivery')


def trigger_status():
    expected = {f'fbt_audit_{table}_{action}' for table in AUDITED_TABLES for action in ('insert', 'update', 'delete')}
    expected |= {'fbt_payment_balance', 'fbt_bill_balance'} if connection.vendor == 'postgresql' else {'fbt_payment_balance_insert', 'fbt_payment_balance_update', 'fbt_bill_balance'}
    try:
        with connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                cursor.execute("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgenabled <> 'D'")
            else:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
            installed = {row[0] for row in cursor.fetchall()}
        missing = expected - installed
        return {'name': 'Audit logging', 'state': 'error' if missing else 'healthy', 'detail': f'{len(missing)} required audit or balance trigger(s) missing. Ask the administrator to check migrations.' if missing else 'Audit and balance triggers are installed. Changes and logs share the same database commit.'}
    except Exception:
        return {'name': 'Audit logging', 'state': 'error', 'detail': 'Audit trigger status could not be checked.'}


def audited(source):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with audit_transaction(source=source):
                return function(*args, **kwargs)
        return wrapped
    return decorate


@contextmanager
def audit_transaction(actor=None, source='app'):
    # Nested operations keep the outer reference and roll back to their own savepoint.
    if _current.get() is not None:
        with transaction.atomic():
            yield _current.get()
        return
    values = {'actor_id': actor.pk if actor and actor.is_authenticated else None,
              'actor_name': actor.username if actor and actor.is_authenticated else 'System',
              'transaction_id': uuid.uuid4().hex, 'source': source}
    token = _current.set(values['transaction_id'])
    try:
        with transaction.atomic():
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    for key in FIELDS:
                        cursor.execute('SELECT set_config(%s, %s, true)', [f'fbt.audit_{key}', str(values[key] or '')])
            else:
                # This first write takes SQLite's writer lock before a balance is read.
                AuditContext.objects.get_or_create(pk=1)
                AuditContext.objects.filter(pk=1).update(**values)
            try:
                yield values['transaction_id']
            finally:
                if not connection.needs_rollback:
                    if connection.vendor == 'postgresql':
                        with connection.cursor() as cursor:
                            for key in FIELDS:
                                cursor.execute('SELECT set_config(%s, %s, true)', [f'fbt.audit_{key}', ''])
                    else:
                        AuditContext.objects.filter(pk=1).update(actor_id=None, actor_name='', transaction_id='', source='')
    finally:
        _current.reset(token)


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return self.get_response(request)
        actor = request.user if request.user.is_authenticated else None
        source = 'admin' if request.path.startswith('/admin/') else 'setup' if request.path == '/setup/' else 'app'
        with audit_transaction(actor, source):
            response = self.get_response(request)
            # A view may translate an exception into a 4xx response. Never commit its partial writes.
            if response.status_code >= 400:
                transaction.set_rollback(True)
            return response
