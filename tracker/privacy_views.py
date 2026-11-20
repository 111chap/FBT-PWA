"""Explicit, short-lived emergency reads and owner-controlled sharing."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from .audit import audit_transaction, correction_reason
from .models import Bill, Loan, Recurrence, EmergencyGrant, PrivacyAccess
from .privacy import visible, current_grant, end_grant
from .security import password_check
from .versions import bill_version, loan_version, recurrence_version
from .views import api, body, label, snapshot


@require_POST
@api
def emergency(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Only an administrator can request emergency access.'}, status=403)
    data = body(request)
    if data.get('action') == 'exit':
        end_grant(current_grant(request))
        request.session.pop('emergency_grant', None)
        return JsonResponse({'ok': True})
    reason = label(data, 'reason', 500)
    if data.get('confirmed') is not True:
        raise ValidationError('Confirm emergency visibility first.')
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        if not password_check(request, user, data.get('password', '')):
            return JsonResponse({'ok': False, 'error': 'Password verification failed or is temporarily limited. Wait 15 minutes after repeated attempts.'})
        end_grant(current_grant(request))
        grant = EmergencyGrant.objects.create(actor=user, reason=reason, expires_at=timezone.now()+timedelta(minutes=10))
        owners = set()
        for model in (Bill, Loan, Recurrence):
            owners.update(model.objects.filter(visibility='private').exclude(owner=user).exclude(owner=None).values_list('owner_id', flat=True))
        for owner_id in owners:
            PrivacyAccess.objects.create(grant=grant, owner_id=owner_id, action='activated')
        request.session['emergency_grant'] = grant.pk
        request.session.cycle_key()
        return JsonResponse({'ok': True, 'expires_at': grant.expires_at.isoformat()})


@require_GET
@api
def emergency_records(request):
    with audit_transaction(request.user):
        grant = current_grant(request)
        if not grant:
            return JsonResponse({'error': 'Emergency access is inactive or expired.'}, status=403)
        for model, kind in ((Bill, 'bill'), (Loan, 'loan'), (Recurrence, 'recurrence')):
            for obj in model.objects.filter(visibility='private').exclude(owner=request.user).exclude(owner=None):
                PrivacyAccess.objects.create(grant=grant, owner_id=obj.owner_id, action='viewed', record_type=kind, record_id=obj.pk)
        response = snapshot(request, emergency=True)
        import json
        payload = json.loads(response.content)
        payload['emergency_expires_at'] = grant.expires_at.isoformat()
        payload['emergency_reason'] = grant.reason
        return JsonResponse(payload)


@require_GET
@api
def access_history(request):
    events = PrivacyAccess.objects.select_related('grant__actor').order_by('-pk')
    if not request.user.is_superuser:
        events = events.filter(owner=request.user)
    number = int(request.GET.get('page', 1))
    if number < 1:
        raise ValidationError('Choose a valid access history page.')
    paginator = Paginator(events, 50)
    page = paginator.get_page(number)
    return JsonResponse({'page': page.number, 'pages': paginator.num_pages, 'events': [{'id': e.pk, 'owner_id': e.owner_id, 'administrator': e.grant.actor.username,
        'action': e.action, 'reason': e.grant.reason, 'record_type': e.record_type, 'record_id': e.record_id,
        'at': e.occurred_at.isoformat()} for e in page]})


@require_POST
@api
def visibility(request):
    data = body(request)
    models = {'bill': Bill, 'loan': Loan, 'recurrence': Recurrence}
    model = models.get(data.get('kind'))
    target = data.get('visibility')
    if model is None or target not in ('private', 'family') or data.get('confirmed') is not True:
        raise ValidationError('Review and confirm Private or Family visibility.')
    reason = label(data, 'reason', 500)
    with transaction.atomic():
        obj = visible(model, request.user).select_for_update().get(pk=int(data['id']))
        if obj.owner_id != request.user.pk:
            return JsonResponse({'error': 'Only the owner can change sharing.'}, status=403)
        if isinstance(obj, Bill) and (obj.loan_id or obj.recurrence_id):
            raise ValidationError('Change sharing for the entire loan or monthly schedule.')
        version = bill_version(obj) if model is Bill else loan_version(obj, obj.bills.filter(removed=False)) if model is Loan else recurrence_version(obj)
        if data.get('expected_version') != version:
            return JsonResponse({'error': 'This record changed. Refresh and review sharing again.'}, status=409)
        if obj.visibility == target:
            raise ValidationError('Sharing has not changed.')
        correction_reason(reason)
        obj.visibility = target
        fields = ['visibility']
        if model is Recurrence and target == 'private':
            obj.responsible = request.user
            fields.append('responsible')
        if model is Bill and target == 'private':
            obj.responsible = request.user
            fields.append('responsible')
        obj.save(update_fields=fields)
        if model in (Loan, Recurrence):
            for bill in Bill.objects.select_for_update().filter(**{'loan' if model is Loan else 'recurrence': obj}).order_by('pk'):
                bill.owner_id = obj.owner_id
                bill.visibility = target
                if target == 'private':
                    bill.responsible = request.user
                bill.save(update_fields=['owner', 'visibility', 'responsible'])
    return JsonResponse({'ok': True})
