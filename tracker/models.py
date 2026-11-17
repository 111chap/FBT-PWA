from decimal import Decimal
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


class Loan(models.Model):
    title = models.CharField(max_length=100)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    installments = models.PositiveSmallIntegerField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class Recurrence(models.Model):
    title = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=40, default='Household')
    next_due = models.DateField()
    anchor_day = models.PositiveSmallIntegerField()
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')


class Bill(models.Model):
    title = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    category = models.CharField(max_length=40, default='Household')
    notes = models.CharField(max_length=500, blank=True)
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='assigned_bills')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_bills')
    loan = models.ForeignKey(Loan, null=True, blank=True, on_delete=models.PROTECT, related_name='bills')
    recurrence = models.ForeignKey(Recurrence, null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date', 'id']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='bill_positive_amount'), models.UniqueConstraint(fields=['recurrence', 'due_date'], name='unique_recurring_occurrence')]

    @property
    def paid(self):
        return sum((p.amount for p in self.payments.all()), Decimal('0.00'))

    @property
    def balance(self):
        return Decimal(self.amount) - self.paid


class Payment(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_date = models.DateField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    request_key = models.UUIDField(unique=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='payment_positive_amount')]


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


class AuditContext(models.Model):
    """SQLite transaction context; written and cleared within the same write transaction."""
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
