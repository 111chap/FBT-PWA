import csv
import hashlib
import hmac
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from functools import wraps
from pathlib import Path
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import connection, transaction, IntegrityError
from django.db.models import ProtectedError
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse, FileResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from .models import Bill, Loan, Payment, Recurrence, SiteSettings, LoginFailure, PushSubscription, WorkerHeartbeat, AuditEvent
from .services import money, next_month, validate_server_url, validate_push_endpoint, push_ready, send_push
from .audit import trigger_status
from .versions import loan_version, payment_version, bill_version, settings_version, recurrence_version
from .idempotency import idempotent

User = get_user_model()


def api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Sign in again to connect to your family server.'}, status=401)
        try:
            return view(request, *args, **kwargs)
        except ValidationError as error:
            return JsonResponse({'error': ' '.join(error.messages)}, status=400)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return JsonResponse({'error': 'Some details are invalid. Check the form and try again.'}, status=400)
        except (Bill.DoesNotExist, Loan.DoesNotExist, Payment.DoesNotExist, Recurrence.DoesNotExist, User.DoesNotExist):
            return JsonResponse({'error': 'This record is no longer available.'}, status=404)
        except IntegrityError:
            return JsonResponse({'error': 'This record was just changed by another request. Refresh before retrying.'}, status=409)
    return wrapped


def body(request):
    if len(request.body) > 12000:
        raise ValidationError('The request is too large.')
    value = json.loads(request.body)
    if not isinstance(value, dict):
        raise ValidationError('Send a form object.')
    return value


def text(data, key, limit, default=''):
    value = data.get(key, default)
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise ValidationError(f'Check the {key.replace("_", " ")} field (maximum {limit} characters).')
    return value.strip()


def label(data, key, limit, default=''):
    value = text(data, key, limit, default)
    if not value:
        raise ValidationError(f'Enter {key.replace("_", " ")}.')
    return value


def parsed_date(value):
    result = date.fromisoformat(value)
    if not 2000 <= result.year <= 2100:
        raise ValidationError('Use a date between 2000 and 2100.')
    return result


def home(request):
    return redirect('/app/' if request.user.is_authenticated else '/login/')


@require_GET
@ensure_csrf_cookie
def shell(request):
    # Public static shell only: personal data is fetched through authenticated APIs.
    return render(request, 'app.html')


def failure_key(value):
    return hashlib.sha256(value.casefold().encode()).hexdigest()


def throttled(key):
    return LoginFailure.objects.filter(key=key, created_at__gte=timezone.now() - timedelta(minutes=15)).count() >= 5


@require_http_methods(['GET', 'POST'])
@never_cache
def login_view(request):
    if not User.objects.exists():
        return redirect('/setup/')
    error = ''
    status_code = 200
    if request.method == 'POST':
        username = request.POST.get('username', '')[:150]
        key = failure_key('login:' + username)
        if throttled(key):
            error, status_code = 'Too many attempts. Please wait 15 minutes before trying again.', 429
        else:
            user = authenticate(request, username=username, password=request.POST.get('password', ''))
            if user is not None:
                LoginFailure.objects.filter(key=key).delete()
                login(request, user)
                return redirect('/app/')
            LoginFailure.objects.create(key=key)
            error = 'The username or password is incorrect.'
    return render(request, 'login.html', {'error': error}, status=status_code)


@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({'ok': True})


@require_http_methods(['GET', 'POST'])
@never_cache
def bootstrap(request):
    if User.objects.exists():
        return redirect('/login/')
    error = ''
    status_code = 200
    if request.method == 'POST':
        key = failure_key('bootstrap:' + request.META.get('REMOTE_ADDR', ''))
        if throttled(key):
            return render(request, 'bootstrap.html', {'error': 'Too many attempts. Wait 15 minutes.'}, status=429)
        token = request.POST.get('token', '')
        if not settings.FBT_SETUP_TOKEN or not hmac.compare_digest(token, settings.FBT_SETUP_TOKEN):
            LoginFailure.objects.create(key=key)
            error = 'The setup code did not match. Use FBT_SETUP_TOKEN from your .env file.'
        else:
            try:
                user = User(username=request.POST.get('username', '').strip())
                user.full_clean(exclude=['password', 'last_login', 'date_joined'])
                validate_password(request.POST.get('password', ''), user)
                family_name = request.POST.get('family_name', '').strip()
                if not family_name or len(family_name) > 80:
                    raise ValidationError('Enter a family name of up to 80 characters.')
                with transaction.atomic():
                    SiteSettings.objects.get_or_create(pk=1)
                    site = SiteSettings.objects.select_for_update().get(pk=1)
                    if User.objects.exists():
                        return redirect('/login/')
                    site.family_name = family_name
                    site.save()
                    user.set_password(request.POST['password'])
                    user.is_staff = user.is_superuser = True
                    user.save()
                login(request, user)
                return redirect('/app/#setup')
            except ValidationError as exception:
                error = ' '.join(exception.messages)
                status_code = 400
    return render(request, 'bootstrap.html', {'error': error}, status=status_code)


@require_GET
def setup_guide(request):
    return FileResponse(open(settings.BASE_DIR / 'setup' / 'index.html', 'rb'), content_type='text/html')


@require_GET
def service_worker(request):
    response = FileResponse(open(settings.BASE_DIR / 'static' / 'sw.js', 'rb'), content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response


@require_GET
def liveness(request):
    return JsonResponse({'status': 'ok'})


@require_GET
@api
def reachable(request):
    site = SiteSettings.objects.filter(pk=1).first() or SiteSettings()
    return JsonResponse({'reachable': True, 'user_id': request.user.pk, 'settings_version': settings_version(site)})


@require_GET
@api
def snapshot(request):
    site = SiteSettings.objects.filter(pk=1).first() or SiteSettings()
    bills = []
    loan_bills = {}
    for bill in Bill.objects.filter(removed=False).select_related('responsible', 'created_by').prefetch_related('payments__recorded_by'):
        if bill.loan_id:loan_bills.setdefault(bill.loan_id,[]).append(bill)
        balance = bill.balance
        state = 'paid' if balance <= 0 else 'overdue' if bill.due_date < timezone.localdate() else 'partial' if bill.paid else 'upcoming'
        bills.append({'version': bill_version(bill), 'responsible_id': bill.responsible_id, 'recurrence_id': bill.recurrence_id, 'id': bill.pk, 'title': bill.title, 'amount': str(bill.amount), 'balance': str(balance), 'due_date': bill.due_date.isoformat(), 'category': bill.category, 'notes': bill.notes, 'responsible': bill.responsible.username, 'status': state, 'loan_id': bill.loan_id, 'recurring': bool(bill.recurrence_id), 'payments': [{'id':p.pk,'version':payment_version(p),'amount': str(p.amount), 'paid_date': p.paid_date.isoformat(), 'recorded_by': p.recorded_by.username, 'recorded_by_id': p.recorded_by_id} for p in bill.payments.all() if not p.removed]})
    return JsonResponse({'version': 1, 'synced_at': timezone.now().isoformat(), 'today': timezone.localdate().isoformat(), 'currency': 'PHP', 'settings_version': settings_version(site), 'recurrences': [{'id': r.pk, 'title': r.title, 'anchor_day': r.anchor_day, 'active': r.active, 'removed': r.removed, 'next_due': r.next_due.isoformat(), 'responsible_id': r.responsible_id, 'version': recurrence_version(r)} for r in Recurrence.objects.all()], 'family_name': site.family_name, 'nas_name': site.nas_name, 'server_url': site.server_url, 'user': {'id': request.user.pk, 'name': request.user.username, 'admin': request.user.is_superuser}, 'members': list(User.objects.filter(is_active=True).values('id', 'username')), 'bills': bills, 'loans': [{'id': loan.pk, 'title': loan.title, 'total': str(loan.total), 'installments': loan.installments,'version':loan_version(loan,loan_bills.get(loan.pk,[]))} for loan in Loan.objects.filter(removed=False)], 'vapid_public_key': settings.VAPID_PUBLIC_KEY if push_ready() else ''})


@require_POST
@api
@idempotent
def create_bill(request):
    data = body(request)
    amount = money(data['amount'])
    due = parsed_date(data['due_date'])
    title = label(data, 'title', 100)
    category = label(data, 'category', 40, 'Household')
    responsible = User.objects.get(pk=int(data.get('responsible', request.user.pk)), is_active=True)
    with transaction.atomic():
        recurrence = None
        if data.get('repeat_monthly') is True:
            recurrence = Recurrence.objects.create(title=title, amount=amount, category=category, next_due=next_month(due, due.day), anchor_day=due.day, responsible=responsible, created_by=request.user)
        bill = Bill.objects.create(title=title, amount=amount, due_date=due, category=category, notes=text(data, 'notes', 500), responsible=responsible, created_by=request.user, recurrence=recurrence)
    return JsonResponse({'id': bill.pk}, status=201)


@require_POST
@api
def record_payment(request, bill_id):
    data = body(request)
    amount = money(data['amount'])
    paid_date = parsed_date(data['paid_date'])
    if paid_date > timezone.localdate():
        raise ValidationError('A recorded payment cannot be dated in the future.')
    request_key = uuid.UUID(str(data['request_key']))
    with transaction.atomic():
        bill = Bill.objects.select_for_update().get(pk=bill_id)
        previous = Payment.objects.filter(request_key=request_key).first()
        if previous:
            if previous.bill_id == bill.pk and previous.recorded_by_id == request.user.pk and previous.amount == amount and previous.paid_date == paid_date:
                return JsonResponse({'id': previous.pk, 'already_recorded': True})
            return JsonResponse({'error': 'This payment reference has already been used.'}, status=409)
        if amount > bill.balance:
            return JsonResponse({'error': 'This exceeds the current unpaid balance. Refresh the bill and try again.'}, status=409)
        if bill.removed:
            raise ValidationError('This bill was removed. Refresh your records.')
        if data.get('expected_version') and data['expected_version'] != bill_version(bill):
            return JsonResponse({'error': 'This bill changed after review. Refresh and review the payment again.'}, status=409)
        payment = Payment.objects.create(bill=bill, amount=amount, paid_date=paid_date, recorded_by=request.user, request_key=request_key)
    return JsonResponse({'id': payment.pk}, status=201)


@require_POST
@api
@idempotent
def create_loan(request):
    data = body(request)
    title = label(data, 'title', 100)
    total = money(data['total'])
    count = int(data['installments'])
    if count < 1 or count > 120 or total < Decimal('.01') * count:
        raise ValidationError('Choose 1 to 120 installments, each worth at least PHP 0.01.')
    due = parsed_date(data['first_due'])
    anchor = due.day
    responsible = User.objects.get(pk=int(data.get('responsible', request.user.pk)), is_active=True)
    installment = (total / count).quantize(Decimal('.01'))
    # Round down so the final installment remains positive for very small loans.
    installment = (total // Decimal('.01') // count) * Decimal('.01')
    with transaction.atomic():
        loan = Loan.objects.create(title=title, total=total, installments=count, created_by=request.user)
        for index in range(count):
            amount = total - installment * (count - 1) if index == count - 1 else installment
            Bill.objects.create(title=f'{title[:85]} · {index + 1}/{count}', amount=amount, due_date=due, category='Loan', responsible=responsible, created_by=request.user, loan=loan)
            due = next_month(due, anchor)
    return JsonResponse({'id': loan.pk}, status=201)


@require_POST
@api
def update_settings(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Only the family administrator can change server settings.'}, status=403)
    data = body(request)
    SiteSettings.objects.get_or_create(pk=1)
    site = SiteSettings.objects.select_for_update().get(pk=1)
    if data.get('expected_version') and data['expected_version'] != settings_version(site):
        return JsonResponse({'error': 'Workspace details changed. Refresh and review them again.'}, status=409)
    site.family_name = label(data, 'family_name', 80)
    site.nas_name = label(data, 'nas_name', 80)
    url = text(data, 'server_url', 200)
    site.server_url = validate_server_url(url) if url else ''
    site.save()
    return JsonResponse({'ok': True, 'note': 'Address saved for guidance only. DNS, certificates, and allowed hosts must be configured on the NAS.'})


@require_POST
@api
def recurrence_action(request, recurrence_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Only the administrator can cancel or remove repeating bills.'}, status=403)
    data = body(request)
    with transaction.atomic():
        recurrence = Recurrence.objects.select_for_update().get(pk=recurrence_id)
        current = recurrence_version(recurrence)
        if data.get('expected_version') != current:
            return JsonResponse({'error': 'This schedule changed. Refresh and review again.'}, status=409)
        if data.get('action') not in ('cancel', 'remove'):
            raise ValidationError('Choose cancel or remove.')
        if data['action'] == 'remove':
            bills = list(Bill.objects.select_for_update().filter(recurrence=recurrence).order_by('pk'))
            if Payment.objects.filter(bill__in=bills).exists():
                raise ValidationError('This schedule has payments. Cancel it instead to retain financial history.')
            for bill in bills:
                bill.removed = True
                bill.save(update_fields=['removed'])
            recurrence.removed = True
        recurrence.active = False
        recurrence.save(update_fields=['active', 'removed'])
    return JsonResponse({'ok': True})


@require_POST
@api
def remove_bill(request, bill_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Only the administrator can remove a bill.'}, status=403)
    data = body(request)
    with transaction.atomic():
        bill = Bill.objects.select_for_update().get(pk=bill_id)
        if data.get('expected_version') != bill_version(bill):
            return JsonResponse({'error': 'This bill changed. Refresh and review again.'}, status=409)
        if bill.payments.exists() or bill.loan_id:
            raise ValidationError('Bills with payments and loan installments must be retained.')
        bill.removed = True
        bill.save(update_fields=['removed'])
    return JsonResponse({'ok': True})


@require_POST
@api
def reassign_payer(request, bill_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Only the administrator can reassign an existing bill.'}, status=403)
    data = body(request)
    with transaction.atomic():
        # Same lock order as the recurrence worker / lifecycle operation.
        target = Bill.objects.get(pk=bill_id)
        recurrence = Recurrence.objects.select_for_update().get(pk=target.recurrence_id) if target.recurrence_id else None
        bill = Bill.objects.select_for_update().get(pk=bill_id, removed=False)
        if data.get('expected_version') != bill_version(bill):
            return JsonResponse({'error': 'This bill changed. Refresh and review again.'}, status=409)
        payer = User.objects.select_for_update().get(pk=int(data['responsible']), is_active=True)
        scope = data.get('scope', 'current')
        if scope not in ('current', 'future') or (scope == 'future' and not recurrence):
            raise ValidationError('Choose a valid assignment scope.')
        if scope == 'future':
            if data.get('recurrence_version') != recurrence_version(recurrence):
                return JsonResponse({'error': 'The schedule changed. Refresh and review again.'}, status=409)
            if not recurrence.active or recurrence.removed:
                raise ValidationError('This schedule is no longer active.')
            recurrence.responsible = payer
            recurrence.save(update_fields=['responsible'])
        bill.responsible = payer
        bill.save(update_fields=['responsible'])
    return JsonResponse({'ok': True})


@require_GET
@api
def status(request):
    checks = [{'name': 'Web application', 'state': 'healthy', 'detail': 'Your signed-in request reached Django.'}]
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        checks.append({'name': 'Database', 'state': 'healthy', 'detail': 'A live database query succeeded.'})
    except Exception:
        checks.append({'name': 'Database', 'state': 'error', 'detail': 'Database query failed. Check the database container.'})
    heartbeat = WorkerHeartbeat.objects.filter(name='reminders').first()
    alive = heartbeat and timezone.now() - heartbeat.updated_at < timedelta(minutes=3)
    checks.append({'name': 'Reminder worker', 'state': 'healthy' if alive else 'error', 'detail': f'Last heartbeat: {heartbeat.updated_at.isoformat()} · {heartbeat.detail}' if heartbeat else 'No heartbeat yet. Start the worker container.'})
    checks.append({'name': 'Secure connection', 'state': 'healthy' if request.is_secure() else 'warning', 'detail': 'HTTPS is active.' if request.is_secure() else 'Local HTTP development. Phones need trusted HTTPS for offline installation and push.'})
    checks.append({'name': 'Push delivery', 'state': 'configured' if push_ready() else 'warning', 'detail': 'Keys configured. Use a device test to verify delivery.' if push_ready() else 'Push keys are missing. Add VAPID keys and restart app and worker.'})
    checks.append({'name': 'Your registered devices', 'state': 'configured' if PushSubscription.objects.filter(user=request.user).exists() else 'warning', 'detail': f'{PushSubscription.objects.filter(user=request.user).count()} notification subscription(s) for your account.'})
    checks.append({'name': 'Docker / NAS', 'state': 'manual', 'detail': 'Check Container Manager → Project → fbt. The app deliberately has no Docker-control access.'})
    checks.append({'name': 'Backup recovery', 'state': 'manual', 'detail': 'A backup is not verified until restored. Follow the backup and restore guide.'})
    checks.append(trigger_status())
    return JsonResponse({'checked_at': timezone.now().isoformat(), 'checks': checks})


@require_GET
@api
def export_bills(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="family-bills.csv"'
    writer = csv.writer(response)
    writer.writerow(['Bill', 'Due date', 'Amount PHP', 'Unpaid PHP', 'Primary payer'])
    for bill in Bill.objects.filter(removed=False).select_related('responsible').prefetch_related('payments'):
        safe_title = "'" + bill.title if bill.title.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else bill.title
        username = bill.responsible.username
        safe_user = "'" + username if username.startswith(('=', '+', '-', '@')) else username
        writer.writerow([safe_title, bill.due_date, bill.amount, bill.balance, safe_user])
    return response


@require_http_methods(['POST', 'DELETE'])
@api
def push_subscription(request):
    data = body(request)
    endpoint = label(data, 'endpoint', 1500)
    if request.method == 'DELETE':
        PushSubscription.objects.filter(endpoint=endpoint, user=request.user).delete()
        return JsonResponse({'ok': True})
    validate_push_endpoint(endpoint)
    keys = data['keys']
    if not isinstance(keys, dict) or not all(isinstance(keys.get(k), str) and 10 <= len(keys[k]) <= 200 for k in ('auth', 'p256dh')):
        raise ValidationError('The device subscription is incomplete.')
    existing = PushSubscription.objects.filter(endpoint=endpoint).first()
    if existing and existing.user_id != request.user.pk:
        return JsonResponse({'error': 'This device belongs to another account. Disable notifications in that account first.'}, status=409)
    PushSubscription.objects.update_or_create(endpoint=endpoint, defaults={'user': request.user, 'keys': {k: keys[k] for k in ('auth', 'p256dh')}})
    return JsonResponse({'ok': True}, status=201)


@require_POST
@api
def test_push(request):
    if not push_ready():
        return JsonResponse({'error': 'Ask the administrator to configure push keys first.'}, status=409)
    subscriptions = PushSubscription.objects.filter(user=request.user)
    if not subscriptions.exists():
        return JsonResponse({'error': 'Enable notifications on this device first.'}, status=409)
    try:
        for subscription in subscriptions:
            send_push(subscription, 'Your reminders are connected', 'This is a test from Family Bill Tracker.')
    except Exception:
        return JsonResponse({'error': 'Push service did not accept the test. Check worker logs and keys.'}, status=502)
    return JsonResponse({'ok': True, 'note': 'Push service accepted the test. Confirm that you received it on your phone.'})


@require_GET
@api
def audit_history(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Only the family administrator can review the full audit history.'}, status=403)
    events = AuditEvent.objects.all()
    search = request.GET.get('search', '').strip()
    if len(search) > 150:
        raise ValidationError('Use a shorter search term.')
    if search:
        events = events.filter(Q(label__icontains=search) | Q(actor_name__icontains=search) | Q(transaction_id__icontains=search) | Q(entity_id__iexact=search) | Q(reason__icontains=search) | Q(before__icontains=search) | Q(after__icontains=search))
    choices = {
        'entity_type': {'bill', 'payment', 'loan', 'recurrence', 'settings', 'account', 'access', 'device', 'reminder', 'system'},
        'action': {'insert', 'update', 'delete', 'started'},
        'source': {'app', 'admin', 'setup', 'worker', 'database', 'migration'},
    }
    for field, allowed in choices.items():
        value = request.GET.get(field, '')
        if value:
            if value not in allowed:
                raise ValidationError('Choose a valid audit filter.')
            events = events.filter(**{field: value})
    start = parsed_date(request.GET['from']) if request.GET.get('from') else None
    end = parsed_date(request.GET['to']) if request.GET.get('to') else None
    if start and end and start > end:
        raise ValidationError('The start date must be before the end date.')
    if start:
        events = events.filter(occurred_at__date__gte=start)
    if end:
        events = events.filter(occurred_at__date__lte=end)
    transaction_id = request.GET.get('transaction', '')
    if transaction_id:
        if len(transaction_id) > 64:
            raise ValidationError('Invalid transaction reference.')
        events = events.filter(transaction_id=transaction_id)
    page_number = int(request.GET.get('page', 1))
    if page_number < 1:
        raise ValidationError('Choose a valid page.')
    paginator = Paginator(events, 25)
    page = paginator.get_page(page_number)
    fields = ['id', 'occurred_at', 'actor_id', 'actor_name', 'transaction_id', 'source', 'action', 'entity_type', 'entity_id', 'entity_table', 'label', 'before', 'after', 'credentials_changed','reason']
    started = AuditEvent.objects.filter(action='started', entity_type='system').order_by('id').values_list('occurred_at', flat=True).first()
    return JsonResponse({'events': list(page.object_list.values(*fields)), 'page': page.number, 'pages': paginator.num_pages, 'total': paginator.count, 'has_next': page.has_next(), 'has_previous': page.has_previous(), 'logging_started_at': started})
