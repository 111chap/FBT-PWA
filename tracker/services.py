import calendar
import ipaddress
import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Bill, Recurrence, ReminderDelivery, PushSubscription, WorkerHeartbeat
from .audit import audited


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0 or amount > Decimal('9999999999.99') or amount != amount.quantize(Decimal('.01')):
            raise ValueError
        return amount
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError('Enter a positive amount with at most two decimal places.')


def next_month(value, anchor):
    year, month = (value.year + 1, 1) if value.month == 12 else (value.year, value.month + 1)
    return date(year, month, min(anchor, calendar.monthrange(year, month)[1]))


def validate_server_url(value):
    parts = urlsplit(value)
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/') or not parts.hostname:
        raise ValidationError('Enter only the home server address, without a path or sign-in details.')
    if parts.scheme != 'https' and not (settings.DEBUG and parts.scheme == 'http' and parts.hostname in ('localhost', '127.0.0.1')):
        raise ValidationError('Use an HTTPS address. HTTP is allowed only for local development.')
    try:
        parts.port
    except ValueError:
        raise ValidationError('The server port is invalid.')
    return value.rstrip('/')


def validate_push_endpoint(endpoint):
    # An explicit provider allowlist prevents subscriptions from becoming an SSRF proxy.
    parts = urlsplit(endpoint)
    host = parts.hostname or ''
    allowed = host == 'fcm.googleapis.com' or host == 'updates.push.services.mozilla.com' or host.endswith('.push.apple.com') or host == 'web.push.apple.com' or host.endswith('.notify.windows.com')
    if parts.scheme != 'https' or not allowed or parts.username or parts.password or parts.port not in (None, 443):
        raise ValidationError('This push provider is not supported. Use Safari, Chrome, Firefox, or Edge.')
    return endpoint


def push_ready():
    return bool(settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY and settings.VAPID_SUBJECT)


def send_push(subscription, title, body):
    from pywebpush import webpush
    validate_push_endpoint(subscription.endpoint)
    webpush(subscription_info={'endpoint': subscription.endpoint, 'keys': subscription.keys}, data=json.dumps({'title': title, 'body': body, 'url': '/app/'}), vapid_private_key=settings.VAPID_PRIVATE_KEY, vapid_claims={'sub': settings.VAPID_SUBJECT}, timeout=10)


@audited('worker')
def materialize_recurring(today=None):
    today = today or timezone.localdate()
    for pk in Recurrence.objects.values_list('pk', flat=True):
        with transaction.atomic():
            recurrence = Recurrence.objects.select_for_update().get(pk=pk)
            if not recurrence.active or recurrence.removed:
                continue
            count = 0
            while recurrence.next_due <= today + timedelta(days=30) and count < 24:
                Bill.objects.get_or_create(recurrence=recurrence, due_date=recurrence.next_due, defaults={'owner_id': recurrence.owner_id, 'visibility': recurrence.visibility, 'title': recurrence.title, 'amount': recurrence.amount, 'category': recurrence.category, 'responsible': recurrence.responsible, 'created_by': recurrence.created_by})
                recurrence.next_due = next_month(recurrence.next_due, recurrence.anchor_day)
                count += 1
            recurrence.save(update_fields=['next_due'])


@audited('worker')
def deliver_reminders(now=None):
    now = now or timezone.now()
    local = timezone.localtime(now)
    if not push_ready() or local.hour < 9 or local.hour >= 20:
        return
    # Also serialize direct/manual invocations, not just the worker command.
    WorkerHeartbeat.objects.get_or_create(name='reminder-dispatch')
    WorkerHeartbeat.objects.select_for_update().get(name='reminder-dispatch')
    for bill in Bill.objects.filter(removed=False, due_date__lte=local.date() + timedelta(days=7)).prefetch_related('payments'):
        days=(bill.due_date-local.date()).days
        if days>0 and days not in (7,3,1):
            continue
        if bill.balance <= 0 or (bill.loan_id and bill.loan.removed) or (bill.recurrence_id and (not bill.recurrence.active or bill.recurrence.removed)):
            continue
        for subscription in PushSubscription.objects.filter(user__is_active=True):
            from .privacy import visible
            if not visible(Bill, subscription.user).filter(pk=bill.pk).exists():
                continue
            delivery, _ = ReminderDelivery.objects.get_or_create(bill=bill, subscription=subscription, day=local.date())
            if delivery.delivered_at or delivery.attempts >= 3:
                continue
            delivery.attempts += 1
            delivery.save(update_fields=['attempts'])
            # Fresh balance check immediately before dispatch.
            if Bill.objects.get(pk=bill.pk).balance <= 0 or not visible(Bill, subscription.user).filter(pk=bill.pk,removed=False).exists() or (bill.recurrence_id and not Recurrence.objects.filter(pk=bill.recurrence_id,active=True,removed=False).exists()):
                continue
            try:
                milestone = f'due in {days} days' if days in (7,3) else 'due tomorrow' if days==1 else 'due today' if days==0 else 'overdue'
                send_push(subscription, f'A payment is {milestone}', 'Open Family Bill Tracker on your home network to review your authorized payments.')
                delivery.delivered_at = timezone.now()
                delivery.save(update_fields=['delivered_at'])
            except Exception as error:
                response = getattr(error, 'response', None)
                if response is not None and response.status_code in (404, 410):
                    subscription.delete()
