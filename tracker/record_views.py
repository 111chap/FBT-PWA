"""Text-only parent changes never recalculate or recreate financial records."""
from django.http import JsonResponse
from django.db import transaction
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST
from .models import Bill, Loan, Recurrence
from .views import api, body, text, label
from .privacy import visible, require_manage
from .versions import bill_version, loan_version, recurrence_version
from .audit import correction_reason
from .idempotency import idempotent


@require_POST
@api
@idempotent
def description(request, kind, record_id):
    model = {'bill': Bill, 'loan': Loan, 'recurrence': Recurrence}.get(kind)
    if model is None:
        raise ValidationError('Choose a valid record.')
    data = body(request)
    if data.get('confirmed') is not True:
        raise ValidationError('Review and confirm the description change.')
    value = text(data, 'description', 500)
    reason = label(data, 'reason', 500)
    with transaction.atomic():
        obj = visible(model, request.user).select_for_update().get(pk=record_id)
        require_manage(request.user, obj)
        if model is Bill and (obj.loan_id or obj.recurrence_id):
            raise ValidationError('Edit the shared description on the loan or monthly schedule. Installment notes stay separate.')
        current = bill_version(obj) if model is Bill else loan_version(obj, obj.bills.filter(removed=False)) if model is Loan else recurrence_version(obj)
        if data.get('expected_version') != current:
            return JsonResponse({'error': 'This record changed. Refresh and review again.'}, status=409)
        correction_reason(reason)
        field = 'notes' if model is Bill else 'description'
        setattr(obj, field, value)
        obj.save(update_fields=[field])
    return JsonResponse({'ok': True})
