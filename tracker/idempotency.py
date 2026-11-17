"""Optional request keys protect app creation retries, within the audit transaction."""
import hashlib
import json
import uuid
from functools import wraps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from .models import MutationReceipt


def idempotent(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if len(request.body) > 12000:
            raise ValidationError('The request is too large.')
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValidationError('Send a form object.')
        key = data.get('request_key')
        if not key:
            return view(request, *args, **kwargs)
        key = uuid.UUID(str(key))
        digest = hashlib.sha256((request.path + json.dumps(data, sort_keys=True)).encode()).hexdigest()
        with transaction.atomic():
            # Serializes keys per actor, including simultaneous first submissions.
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            prior = MutationReceipt.objects.filter(key=key).first()
            if prior:
                if prior.actor_id != request.user.pk or prior.digest != digest:
                    return JsonResponse({'error': 'This request reference has already been used.'}, status=409)
                return JsonResponse(prior.result, status=200)
            response = view(request, *args, **kwargs)
            if response.status_code < 300:
                MutationReceipt.objects.create(key=key, actor=request.user, digest=digest, result=json.loads(response.content))
            return response
    return wrapped
