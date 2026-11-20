from decimal import Decimal
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class SiteSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    family_name = models.CharField(max_length=80, default='Our family')
    server_url = models.URLField(blank=True)
    nas_name = models.CharField(max_length=80, default='Family NAS')


class OwnedRecord(models.Model):
    # Family is the model default for legacy/imported records. API creation defaults Private.
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='+')
    visibility = models.CharField(max_length=7, choices=[('private', 'Private'), ('family', 'Family')], default='family')

    class Meta:
        abstract = True
        constraints = [models.CheckConstraint(condition=Q(visibility='family') | Q(visibility='private', owner__isnull=False), name='%(class)s_valid_privacy')]


class Loan(OwnedRecord):
    description = models.CharField(max_length=500, blank=True)
    removed = models.BooleanField(default=False)
    title = models.CharField(max_length=100)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    installments = models.PositiveSmallIntegerField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class Recurrence(OwnedRecord):
    description = models.CharField(max_length=500, blank=True)
    title = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=40, default='Household')
    next_due = models.DateField()
    anchor_day = models.PositiveSmallIntegerField()
    active = models.BooleanField(default=True)
    removed = models.BooleanField(default=False)
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')


class Bill(OwnedRecord):
    bill_type = models.CharField(max_length=9, choices=[('utilities', 'Utilities'), ('loan', 'Loan'), ('one-time', 'One-time bill')], default='utilities')
    title = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    category = models.CharField(max_length=40, default='Household')
    notes = models.CharField(max_length=500, blank=True)
    removed = models.BooleanField(default=False)
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='assigned_bills')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_bills')
    loan = models.ForeignKey(Loan, null=True, blank=True, on_delete=models.PROTECT, related_name='bills')
    recurrence = models.ForeignKey(Recurrence, null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date', 'id']
        constraints = [*OwnedRecord.Meta.constraints, models.CheckConstraint(condition=Q(bill_type__in=['utilities', 'loan', 'one-time']) & (~Q(bill_type='one-time') | Q(loan__isnull=True, recurrence__isnull=True)), name='valid_bill_type'), models.CheckConstraint(condition=Q(amount__gt=0), name='bill_positive_amount'), models.UniqueConstraint(fields=['recurrence', 'due_date'], name='unique_recurring_occurrence')]

    @property
    def paid(self):
        return sum((p.amount for p in self.payments.all() if not p.removed), Decimal('0.00'))

    @property
    def balance(self):
        return Decimal(self.amount) - self.paid


class Payment(models.Model):
    receipt_required = models.BooleanField(default=True)
    receipt = models.OneToOneField('MediaAsset', null=True, on_delete=models.PROTECT, related_name='payment')
    removed = models.BooleanField(default=False)
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_date = models.DateField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    request_key = models.UUIDField(unique=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='payment_positive_amount'), models.CheckConstraint(condition=Q(receipt_required=False) | Q(receipt__isnull=False), name='payment_evidence_required')]


class MediaAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purpose = models.CharField(max_length=7, choices=[('receipt', 'Receipt'), ('qr', 'QR')])
    finalized = models.BooleanField(default=False)
    bill = models.ForeignKey(Bill, null=True, on_delete=models.PROTECT, related_name='media_assets')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    storage_name = models.CharField(max_length=180, unique=True)
    sha256 = models.CharField(max_length=64)
    size = models.PositiveIntegerField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    created_at = models.DateTimeField(default=timezone.now)


class ReceiptRevision(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='receipt_revisions')
    asset = models.OneToOneField(MediaAsset, on_delete=models.PROTECT, related_name='revision')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now)


class PaymentQR(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    asset = models.ForeignKey(MediaAsset, null=True, on_delete=models.PROTECT)
    recipient = models.CharField(max_length=100, blank=True)


class WorkerHeartbeat(models.Model):
    name = models.CharField(max_length=30, primary_key=True)
    updated_at = models.DateTimeField(default=timezone.now)
    detail = models.CharField(max_length=120, default='Starting')


class PushSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    endpoint = models.URLField(max_length=1500, unique=True)
    keys = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class ReminderDelivery(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE)
    subscription = models.ForeignKey(PushSubscription, on_delete=models.CASCADE)
    day = models.DateField()
    delivered_at = models.DateTimeField(null=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['bill', 'subscription', 'day'], name='unique_daily_reminder')]


class LoginFailure(models.Model):
    key = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)


class EmergencyGrant(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    expires_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True)


class PrivacyAccess(models.Model):
    grant = models.ForeignKey(EmergencyGrant, on_delete=models.PROTECT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=20)
    record_type = models.CharField(max_length=12, blank=True)
    record_id = models.PositiveBigIntegerField(null=True)
    occurred_at = models.DateTimeField(default=timezone.now)


class PinCredential(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    pin_hash = models.CharField(max_length=256, blank=True)
    failures = models.PositiveIntegerField(default=0)
    strikes = models.PositiveIntegerField(default=0)
    blocked_until = models.DateTimeField(null=True)


class PinDevice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    verifier = models.CharField(max_length=64, unique=True)
    password_stamp = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)


class PinNetwork(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    attempts = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField(default=timezone.now)


class MutationReceipt(models.Model):
    key = models.UUIDField(primary_key=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    digest = models.CharField(max_length=64)
    result = models.JSONField()


class AuditContext(models.Model):
    """SQLite transaction context; written and cleared within the same write transaction."""
    reason = models.CharField(max_length=500, blank=True, default="")
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    actor_id = models.BigIntegerField(null=True)
    actor_name = models.CharField(max_length=150, blank=True)
    transaction_id = models.CharField(max_length=64, blank=True)
    source = models.CharField(max_length=30, blank=True)


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Audit history is read-only.')

    def delete(self):
        raise ValidationError('Audit history is read-only.')


class AuditEvent(models.Model):
    reason = models.CharField(max_length=500, blank=True, default="")
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    actor_id = models.BigIntegerField(null=True)
    actor_name = models.CharField(max_length=150)
    transaction_id = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=30)
    action = models.CharField(max_length=12)
    entity_type = models.CharField(max_length=30, db_index=True)
    entity_id = models.CharField(max_length=64)
    entity_table = models.CharField(max_length=64)
    label = models.CharField(max_length=180)
    before = models.JSONField(null=True)
    after = models.JSONField(null=True)
    credentials_changed = models.BooleanField(default=False)

    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ['-id']

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            raise ValidationError('Audit history is read-only.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Audit history is read-only.')
