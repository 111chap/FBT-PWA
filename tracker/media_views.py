import uuid
from django.http import JsonResponse, FileResponse
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from .models import Bill, Payment, MediaAsset, PaymentQR, ReceiptRevision, PrivacyAccess
from .views import api, body, label
from .privacy import visible, current_grant, require_manage
from .audit import audit_transaction, correction_reason
from .versions import version, payment_version
from .media import stage, open_verified, eligible_receipt, finalize


def qr_version(config):
    return version([str(config.asset_id or ''), config.recipient])


@require_POST
@api
def upload(request):
    if request.content_type != 'multipart/form-data' or len(request.FILES.getlist('image')) != 1:
        raise ValidationError('Select exactly one receipt or QR image.')
    purpose=request.POST.get('purpose')
    if purpose not in ('receipt','qr'):
        raise ValidationError('Choose a receipt or household QR image.')
    if purpose=='qr' and not request.user.is_superuser:
        return JsonResponse({'error':'Only the administrator can upload the household QR.'},status=403)
    bill=visible(Bill,request.user).get(pk=int(request.POST['bill_id']),removed=False) if purpose=='receipt' else None
    asset=stage(request.FILES['image'],request.user,purpose,bill)
    return JsonResponse({'id':str(asset.pk),'size':asset.size,'width':asset.width,'height':asset.height,'url':f'/api/media/{asset.pk}/'},status=201)


@require_GET
@api
def image(request, asset_id):
    asset=MediaAsset.objects.select_related('bill','uploaded_by').get(pk=asset_id)
    with audit_transaction(request.user):
        if asset.purpose=='qr':
            if not asset.finalized and request.user.is_superuser and asset.uploaded_by_id==request.user.pk:
                pass
            elif not PaymentQR.objects.filter(pk=1,asset=asset).exists():
                # A replaced QR may never be presented as the current destination.
                return JsonResponse({'error':'This QR was replaced or removed. Open Pay using QR again.'},status=404)
        elif not asset.finalized:
            if asset.uploaded_by_id!=request.user.pk or not visible(Bill,request.user).filter(pk=asset.bill_id).exists():
                return JsonResponse({'error':'This image is unavailable.'},status=404)
        elif not visible(Bill,request.user).filter(pk=asset.bill_id).exists():
            grant=current_grant(request)
            if not grant:
                return JsonResponse({'error':'This image is unavailable.'},status=404)
            target=asset.bill.loan or asset.bill.recurrence or asset.bill
            if target.owner_id:
                PrivacyAccess.objects.create(grant=grant,owner_id=target.owner_id,action='receipt-viewed',record_type='bill',record_id=asset.bill_id)
        stream=open_verified(asset)
        extension=asset.storage_name.rsplit('.',1)[-1]
        response=FileResponse(stream,content_type={'jpg':'image/jpeg','png':'image/png','webp':'image/webp'}[extension],as_attachment=request.GET.get('download')=='1',filename=asset.storage_name)
        response['Cache-Control']='no-store, private'
        response['X-Content-Type-Options']='nosniff'
        return response


@require_GET
@api
def qr_status(request):
    config=PaymentQR.objects.filter(pk=1).first() or PaymentQR()
    return JsonResponse({'configured':bool(config.asset_id),'recipient':config.recipient,'version':qr_version(config),'url':f'/api/media/{config.asset_id}/' if config.asset_id else ''})


@require_POST
@api
def configure_qr(request):
    if not request.user.is_superuser:
        return JsonResponse({'error':'Only the administrator can change the household QR.'},status=403)
    data=body(request)
    if data.get('confirmed') is not True:
        raise ValidationError('Review and confirm the household QR change.')
    with transaction.atomic():
        PaymentQR.objects.get_or_create(pk=1)
        config=PaymentQR.objects.select_for_update().get(pk=1)
        if data.get('expected_version')!=qr_version(config):
            return JsonResponse({'error':'The household QR changed. Refresh it and review again.'},status=409)
        correction_reason(label(data,'reason',500))
        if data.get('action')=='remove':
            config.asset=None;config.recipient=''
        elif data.get('action')=='replace':
            from datetime import timedelta
            try:
                asset=MediaAsset.objects.select_for_update().get(pk=uuid.UUID(str(data['asset_id'])),purpose='qr',uploaded_by=request.user,finalized=False,created_at__gte=timezone.now()-timedelta(hours=24))
            except (ValueError,MediaAsset.DoesNotExist):
                raise ValidationError('Upload a fresh household QR image.')
            recipient=label(data,'recipient',100)
            finalize(asset)
            config.asset=asset;config.recipient=recipient
        else:
            raise ValidationError('Choose Replace or Remove.')
        config.save()
    return JsonResponse({'ok':True})


@require_GET
@api
def evidence(request,payment_id):
    payment=Payment.objects.select_related('bill','receipt').get(pk=payment_id)
    with audit_transaction(request.user):
        if not visible(Bill,request.user).filter(pk=payment.bill_id).exists():
            grant=current_grant(request)
            if not grant:return JsonResponse({'error':'This record is unavailable.'},status=404)
            owner=(payment.bill.loan or payment.bill.recurrence or payment.bill).owner_id
            if owner:PrivacyAccess.objects.create(grant=grant,owner_id=owner,action='evidence-viewed',record_type='bill',record_id=payment.bill_id)
        revisions=list(payment.receipt_revisions.select_related('asset','actor').order_by('-id'))
        return JsonResponse({'payment_id':payment.pk,'version':payment_version(payment),'legacy':not payment.receipt_required,'current':str(payment.receipt_id or ''),'images':[{'id':str(r.asset_id),'url':f'/api/media/{r.asset_id}/','uploaded_at':r.asset.created_at.isoformat(),'reason':r.reason} for r in revisions]})


@require_POST
@api
def replace_evidence(request,payment_id):
    data=body(request)
    if data.get('confirmed') is not True:raise ValidationError('Review and confirm receipt replacement.')
    with transaction.atomic():
        payment=visible(Payment,request.user).select_for_update().get(pk=payment_id)
        require_manage(request.user,payment)
        if data.get('expected_version')!=payment_version(payment):
            return JsonResponse({'error':'The payment changed. Refresh and review the replacement.'},status=409)
        reason=label(data,'reason',500);correction_reason(reason)
        asset=eligible_receipt(data.get('asset_id'),payment.bill,request.user)
        # No physical evidence is overwritten or removed. Prior revisions remain reviewable.
        asset.finalized=True;asset.save(update_fields=['finalized'])
        payment.receipt=asset;payment.receipt_required=True
        payment.save(update_fields=['receipt','receipt_required'])
        finalize(asset,'loan' if payment.bill.loan_id else payment.bill.bill_type,payment.pk)
        ReceiptRevision.objects.create(payment=payment,asset=asset,actor=request.user,reason=reason)
    return JsonResponse({'ok':True})
