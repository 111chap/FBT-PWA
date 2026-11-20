"""Server-verified opt-in PINs bound to revocable, password-enrolled devices."""
import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.hashers import make_password, check_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from .audit import _current
from .models import PinCredential, PinDevice, PinNetwork, AuditEvent, LoginFailure

COOKIE = 'fbt_pin_device'
DAYS = 30
User = get_user_model()


def digest(value):
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def event(user, action):
    AuditEvent.objects.create(actor_id=user.pk if user else None, actor_name=user.username if user else 'Sign-in',
        transaction_id=_current.get() or secrets.token_hex(16), source='app', action='update',
        entity_type='access', entity_id=str(user.pk) if user else '', entity_table='security', label=action)


def password_check(request, user, password):
    # Caller locks the account, serializing re-authentication attempts.
    key = digest('reauth:' + str(user.pk))
    recent = LoginFailure.objects.filter(key=key, created_at__gte=timezone.now()-timedelta(minutes=15))
    if recent.count() >= 5:
        return False
    if not user.is_active or not user.check_password(password):
        LoginFailure.objects.create(key=key)
        event(user, 'Password re-authentication failed')
        return False
    LoginFailure.objects.filter(key=key).delete()
    return True


def valid_pin(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{6,8}', value):
        raise ValidationError('Choose a PIN containing 6 to 8 digits.')
    if len(set(value)) < 3 or value in '01234567890123456789' or value in '98765432109876543210' or value in ('123123', '121212', '112233', '654321', '12345678', '87654321'):
        raise ValidationError('Choose a less predictable PIN; avoid repeated digits and sequences.')
    return value


def trusted(request):
    token = request.COOKIES.get(COOKIE, '')
    if not 30 <= len(token) <= 100:
        return None
    device = PinDevice.objects.filter(verifier=digest(token), revoked=False, expires_at__gt=timezone.now(), user__is_active=True).select_related('user').first()
    if not device or not hmac.compare_digest(device.password_stamp, digest(device.user.password)):
        return None
    return device


def https_required(request):
    return request.is_secure() or (settings.DEBUG and request.get_host().split(':')[0] in ('localhost', '127.0.0.1', 'testserver'))


@require_http_methods(['GET', 'POST'])
def pin_login(request):
    device = trusted(request)
    error = ''
    if request.method == 'POST':
        if not https_required(request):
            return render(request, 'pin-login.html', {'error': 'PIN sign-in needs a trusted HTTPS connection.'})
        now = timezone.now()
        # Network limit is additional, generous, and never affects password fallback.
        network_key = digest('pin-network:' + request.META.get('REMOTE_ADDR', ''))
        with transaction.atomic():
            PinNetwork.objects.get_or_create(key=network_key)
            network = PinNetwork.objects.select_for_update().get(key=network_key)
            if now-network.window_start >= timedelta(minutes=15):
                network.attempts = 0
                network.window_start = now
            network.attempts += 1
            network.save()
            if not device or network.attempts > 60:
                event(None, 'PIN sign-in unavailable or network limited')
            else:
                user = User.objects.select_for_update().filter(pk=device.user_id).first()
                # Re-check credentials after acquiring locks, including concurrent revocation.
                device = trusted(request) if user else None
                credential = PinCredential.objects.filter(user=user).first() if user else None
                if device and credential and credential.pin_hash and (not credential.blocked_until or credential.blocked_until <= now):
                    pin = request.POST.get('pin', '')
                    matched = bool(re.fullmatch(r'[0-9]{6,8}', pin)) and check_password(pin, credential.pin_hash)
                    if matched:
                        credential.failures = credential.strikes = 0
                        credential.blocked_until = None
                        credential.save()
                        request.session.flush()  # Never inherit an emergency grant or another account.
                        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                        event(user, 'PIN sign-in succeeded')
                        return redirect('/app/')
                    credential.failures += 1
                    if credential.failures >= 5:
                        credential.strikes += 1
                        credential.failures = 0
                        credential.blocked_until = now + timedelta(minutes=min(15 * 2 ** min(credential.strikes-1, 5), 240))
                    credential.save()
                    event(user, 'PIN sign-in failed or throttled')
                else:
                    event(user, 'PIN sign-in unavailable or throttled')
        # 200 is intentional: the audit middleware must commit failed-attempt counters.
        error = 'PIN sign-in is unavailable or the details did not match. After repeated attempts, wait at least 15 minutes, or use your password.'
    return render(request, 'pin-login.html', {'error': error, 'enrolled': bool(device), 'account_name': device.user.username if device else ''})


@require_POST
def pin_settings(request):
    from .views import body
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Sign in first.'}, status=401)
    if request.session.get('emergency_grant'):
        from .privacy import current_grant
        if current_grant(request):
            return JsonResponse({'error': 'Exit emergency visibility before changing PIN settings.'}, status=403)
    if not https_required(request):
        return JsonResponse({'error': 'Use trusted HTTPS for PIN settings.'}, status=400)
    try:
        data = body(request)
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if not password_check(request, user, data.get('password', '')):
                return JsonResponse({'ok': False, 'error': 'Password verification failed or is temporarily limited. Wait 15 minutes after repeated attempts.'})
            action = data.get('action')
            if data.get('confirmed') is not True or action not in ('enable', 'disable', 'enroll', 'revoke'):
                raise ValidationError('Review and confirm a valid PIN action.')
            credential, _ = PinCredential.objects.get_or_create(user=user)
            if action == 'enable':
                pin = valid_pin(data.get('pin'))
                if pin != data.get('pin_confirmation'):
                    raise ValidationError('The PINs do not match.')
                credential.pin_hash = make_password(pin)
                credential.failures = credential.strikes = 0
                credential.blocked_until = None
                credential.save()
                PinDevice.objects.filter(user=user).update(revoked=True)
            elif action == 'disable':
                credential.pin_hash = ''
                credential.save(update_fields=['pin_hash'])
                PinDevice.objects.filter(user=user).update(revoked=True)
            elif action == 'revoke':
                PinDevice.objects.filter(user=user).update(revoked=True)
            if action in ('enable', 'enroll'):
                if not credential.pin_hash:
                    raise ValidationError('Enable a PIN first.')
                # A browser has one enrolled account; switching invalidates its old credential.
                PinDevice.objects.filter(verifier=digest(request.COOKIES.get(COOKIE, ''))).update(revoked=True)
                token = secrets.token_urlsafe(32)
                PinDevice.objects.create(user=user, verifier=digest(token), password_stamp=digest(user.password), expires_at=timezone.now()+timedelta(days=DAYS))
            event(user, 'PIN ' + action + ' confirmed')
            request.session.cycle_key()
            response = JsonResponse({'ok': True})
            if action in ('enable', 'enroll'):
                response.set_cookie(COOKIE, token, max_age=DAYS*86400, secure=True, httponly=True, samesite='Strict', path='/')
            else:
                response.delete_cookie(COOKIE, samesite='Strict')
            return response
    except (ValidationError, ValueError, TypeError, KeyError) as exc:
        return JsonResponse({'error': ' '.join(exc.messages) if isinstance(exc, ValidationError) else 'Check your PIN settings.'}, status=400)
