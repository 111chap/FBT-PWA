"""Opaque optimistic-concurrency versions, safe to include in a snapshot."""
import hashlib
import json
from decimal import Decimal


def version(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def bill_version(bill):
    return version([bill.owner_id, bill.visibility, bill.bill_type, bill.title, bill.category, bill.notes, bill.loan_id, bill.recurrence_id, str(Decimal(bill.amount).quantize(Decimal('.01'))), bill.due_date, bill.responsible_id,
                    bill.removed, [(p.pk, p.amount, p.paid_date, p.removed) for p in sorted(bill.payments.all(), key=lambda p:p.pk)]])


def recurrence_version(recurrence):
    return version([recurrence.owner_id, recurrence.visibility, recurrence.title, str(Decimal(recurrence.amount).quantize(Decimal('.01'))), recurrence.category,
                    recurrence.anchor_day, recurrence.active, recurrence.removed, recurrence.responsible_id, recurrence.next_due])


def settings_version(site):
    return version([site.family_name, site.nas_name, site.server_url])


def payment_version(payment):
    return version([payment.pk,payment.bill_id,payment.amount,payment.paid_date,payment.recorded_by_id,payment.removed])


def loan_version(loan,bills):
    return version([loan.owner_id, loan.visibility, loan.title,loan.total,loan.installments,loan.removed,
                    [(b.pk,bill_version(b)) for b in sorted(bills,key=lambda b:b.pk)]])
