"""One access policy for snapshots, direct IDs, admin, exports and linked records."""
from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Subquery
from django.db.models.functions import Cast
from django.db.models import CharField
from django.utils import timezone
from .audit import audit_transaction
from .models import Bill, Loan, Recurrence, Payment, AuditEvent, EmergencyGrant, PrivacyAccess, MediaAsset, ReceiptRevision


def own_or_family(user, prefix=''):
    return Q(**{prefix + 'visibility': 'family'}) | Q(**{prefix + 'owner_id': user.pk})


def visible(model, user):
    if model is MediaAsset:
        result=model.objects.filter(bill__in=visible(Bill,user))
        return result | model.objects.filter(purpose='qr') if user.is_superuser else result
    if model is ReceiptRevision:
        return model.objects.filter(payment__in=visible(Payment,user))
    if model is Payment:
        return model.objects.filter(bill__in=visible(Bill, user))
    result = model.objects.filter(own_or_family(user))
    if model in (Loan, Recurrence):
        parent = 'loan' if model is Loan else 'recurrence'
        # Fail closed for malformed imports: a shared parent total must never
        # reveal a hidden private child, even when created outside normal APIs.
        hidden_children = Bill.objects.filter(visibility='private').exclude(owner=user).values(parent + '_id')
        result = result.exclude(pk__in=hidden_children.exclude(**{parent + '_id': None}))
    if model is Bill:
        # Also check parents: inconsistent imported children never bypass privacy.
        result = result.filter(Q(loan=None) | Q(loan__in=visible(Loan, user)))
        result = result.filter(Q(recurrence=None) | Q(recurrence__in=visible(Recurrence, user)))
    return result


def may_manage(user, obj):
    target = obj.bill if isinstance(obj, Payment) else obj
    if isinstance(target, Bill):
        target = target.loan or target.recurrence or target
    return (target.visibility == 'private' and target.owner_id == user.pk) or (target.visibility == 'family' and user.is_superuser)


def require_manage(user, obj):
    if not may_manage(user, obj):
        raise PermissionDenied('Only the owner or the administrator of a family record can change it.')


def creation_privacy(data, user):
    visibility = data.get('visibility', 'private')
    if visibility not in ('private', 'family'):
        raise ValidationError('Choose Private or Family.')
    return {'owner': user, 'visibility': visibility}


def end_grant(grant, action='deactivated'):
    if grant and not grant.ended_at:
        grant.ended_at = timezone.now()
        grant.save(update_fields=['ended_at'])
        for owner_id in grant.privacyaccess_set.values_list('owner_id', flat=True).distinct():
            PrivacyAccess.objects.create(grant=grant, owner_id=owner_id, action=action)


def current_grant(request):
    pk = request.session.get('emergency_grant')
    if not pk:
        return None
    with audit_transaction(request.user), transaction.atomic():
        grant = EmergencyGrant.objects.select_for_update().filter(pk=pk, actor=request.user, ended_at=None).first()
        if not grant or not request.user.is_active or not request.user.is_superuser or grant.expires_at <= timezone.now():
            end_grant(grant, 'expired')
            request.session.pop('emergency_grant', None)
            return None
        return grant


def audit_visible(user):
    allowed = Q()
    financial = ('bill', 'payment', 'loan', 'recurrence', 'attachment', 'evidence')
    for name, model in zip(financial, (Bill, Payment, Loan, Recurrence, MediaAsset, ReceiptRevision)):
        ids = visible(model, user).annotate(audit_id=Cast('pk', CharField())).values('audit_id')
        allowed |= Q(entity_type=name, entity_id__in=Subquery(ids))
    # Events can retain earlier private text after sharing. Never disclose that
    # historical snapshot to a different user in the ordinary audit screen.
    private_before = AuditEvent.objects.filter(before__visibility='private').exclude(before__owner_id=user.pk).values('pk')
    private_after = AuditEvent.objects.filter(after__visibility='private').exclude(after__owner_id=user.pk).values('pk')
    return AuditEvent.objects.filter(allowed | ~Q(entity_type__in=financial)).exclude(pk__in=private_before).exclude(pk__in=private_after)
