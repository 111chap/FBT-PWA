"""Administrator corrections; mutations and reasoned audit events share one commit."""
import uuid
from decimal import Decimal
from functools import wraps
from django.db import transaction
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import Bill, Loan, Payment, Recurrence
from .audit import correction_reason
from .idempotency import idempotent
from .versions import bill_version, loan_version, payment_version
from .views import api, body, label, text, money, parsed_date, User


def allocation(total,bills):
    """Keep paid installments; split the remaining agreement over open installments."""
    if total==sum((b.amount for b in bills),Decimal('0')):
        return [b.amount for b in bills]
    paid=[b.paid for b in bills]
    eligible=[i for i,b in enumerate(bills) if b.amount>paid[i]]
    if not eligible:eligible=[len(bills)-1]
    result=[max(value,Decimal('.01')) for value in paid]
    minimum=sum(result,Decimal('0'))
    if total<minimum:
        raise ValidationError(f'The agreement must be at least PHP {minimum:.2f}. Correct or delete payments/installments first.')
    cents=int((total-minimum)*100);each=cents//len(eligible)
    for position,index in enumerate(eligible):
        result[index]+=Decimal(each+(cents%len(eligible) if position==len(eligible)-1 else 0))/100
    return result


def administrator(view):
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        with transaction.atomic():
            actor=User.objects.select_for_update().get(pk=request.user.pk)
            if not actor.is_active or not actor.is_superuser:return JsonResponse({'error':'Only the family administrator can correct financial records.'},status=403)
            return view(request,*args,**kwargs)
    return wrapped


def stale():
    return JsonResponse({'error':'This record or its related records changed. Refresh and review the correction again.'},status=409)


def lock_bill(bill_id):
    target=Bill.objects.get(pk=bill_id)
    loan=Loan.objects.select_for_update().get(pk=target.loan_id,removed=False) if target.loan_id else None
    if target.recurrence_id:Recurrence.objects.select_for_update().get(pk=target.recurrence_id)
    bill=Bill.objects.select_for_update().get(pk=bill_id,removed=False)
    return bill,loan


def reconcile(loan):
    bills=list(Bill.objects.filter(loan=loan,removed=False))
    if bills:
        loan.total=money(str(sum((b.amount for b in bills),Decimal('0'))));loan.installments=len(bills)
    else:loan.removed=True
    loan.save(update_fields=['total','installments','removed'])


@require_POST
@api
@administrator
@idempotent
def correct(request,kind,record_id):
    data=body(request)
    uuid.UUID(str(data['request_key']))
    if data.get('confirmed') is not True:raise ValidationError('Review and confirm this correction first.')
    reason=label(data,'reason',500)
    action=data.get('action')
    if kind not in ('bill','loan','payment') or action not in ('edit','delete'):raise ValidationError('Choose a valid record and correction action.')
    with transaction.atomic():
        if kind=='loan':
            loan=Loan.objects.select_for_update().get(pk=record_id,removed=False)
            bills=list(Bill.objects.select_for_update().filter(loan=loan,removed=False).order_by('pk').prefetch_related('payments'))
            if not bills or data.get('expected_version')!=loan_version(loan,bills):return stale()
            correction_reason(reason)
            if action=='delete':
                for bill in bills:bill.removed=True;bill.save(update_fields=['removed'])
                loan.removed=True;loan.save(update_fields=['removed'])
            else:
                total=money(data['total']);title=label(data,'title',100)
                if total==loan.total and title==loan.title:raise ValidationError('No loan changes to save.')
                plan=allocation(total,bills)
                for bill,amount in zip(bills,plan):
                    if amount!=bill.amount:bill.amount=amount;bill.save(update_fields=['amount'])
                loan.title=title;loan.total=total;loan.installments=len(bills);loan.save(update_fields=['title','total','installments'])
        else:
            payment=Payment.objects.get(pk=record_id,removed=False) if kind=='payment' else None
            bill,loan=lock_bill(payment.bill_id if payment else record_id)
            if loan:
                siblings=list(Bill.objects.filter(loan=loan,removed=False).prefetch_related('payments'))
                if data.get('expected_loan_version')!=loan_version(loan,siblings):return stale()
            if kind=='payment':
                payment=Payment.objects.select_for_update().get(pk=record_id,removed=False)
                if data.get('expected_version')!=payment_version(payment) or data.get('expected_bill_version')!=bill_version(bill):return stale()
                correction_reason(reason)
                if action=='delete':payment.removed=True;payment.save(update_fields=['removed'])
                else:
                    amount=money(data['amount']);paid_date=parsed_date(data['paid_date'])
                    if paid_date>timezone.localdate():raise ValidationError('A payment cannot be dated in the future.')
                    if bill.paid-payment.amount+amount>bill.amount:raise ValidationError('The corrected payment would exceed the bill amount.')
                    if amount==payment.amount and paid_date==payment.paid_date:raise ValidationError('No payment changes to save.')
                    payment.amount=amount;payment.paid_date=paid_date;payment.save(update_fields=['amount','paid_date'])
            else:
                if data.get('expected_version')!=bill_version(bill):return stale()
                correction_reason(reason)
                if action=='delete':bill.removed=True;bill.save(update_fields=['removed'])
                else:
                    amount=money(data['amount'])
                    if amount<bill.paid:raise ValidationError('Correct or delete recorded payments before reducing this bill below its paid amount.')
                    payer=int(data['responsible'])
                    new=(label(data,'title',100),amount,parsed_date(data['due_date']),label(data,'category',40),text(data,'notes',500),payer)
                    if new==(bill.title,bill.amount,bill.due_date,bill.category,bill.notes,bill.responsible_id):raise ValidationError('No bill changes to save.')
                    if payer!=bill.responsible_id:bill.responsible=User.objects.get(pk=payer,is_active=True)
                    bill.title,bill.amount,bill.due_date,bill.category,bill.notes,_=new
                    bill.save(update_fields=['title','amount','due_date','category','notes','responsible'])
                if loan:reconcile(loan)
    return JsonResponse({'ok':True})
