"""
Core models — foundation for all MicroPOS domain models.
"""

import secrets

from django.db import models
from django.utils import timezone

from .managers import SoftDeleteManager
from .exceptions import ImmutableRecordError


class BaseModel(models.Model):
    """Abstract base with timestamps and soft-delete."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at', 'updated_at'])

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=['deleted_at', 'updated_at'])

    @property
    def is_deleted(self):
        return self.deleted_at is not None


class TenantModel(BaseModel):
    """Abstract base for all tenant-scoped business models."""

    tenant = models.ForeignKey(
        'core.Business',
        on_delete=models.PROTECT,
        related_name='%(app_label)s_%(class)s_set',
        db_index=True,
    )

    class Meta:
        abstract = True


IMMUTABLE_STATUSES = frozenset({'confirmed', 'completed', 'closed', 'received'})


class ImmutableMixin:
    """
    Mixin for models that become immutable after reaching certain statuses.
    Model must have a `status` field.
    """

    def save(self, *args, **kwargs):
        if self.pk:
            original = self.__class__.objects.get(pk=self.pk)
            original_status = str(getattr(original, 'status', '')).strip().lower()
            if original_status in IMMUTABLE_STATUSES:
                raise ImmutableRecordError(
                    f"Cannot modify {self.__class__.__name__} "
                    f"in status '{original.status}'"
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if hasattr(self, 'status'):
            current_status = str(getattr(self, 'status', '')).strip().lower()
            if current_status in IMMUTABLE_STATUSES:
                raise ImmutableRecordError(
                    f"Cannot delete {self.__class__.__name__} "
                    f"in status '{self.status}'"
                )
        self.soft_delete()


class Business(BaseModel):
    """Tenant — represents a business entity."""

    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='owned_businesses',
    )
    currency = models.CharField(max_length=3, default='UZS')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'core_business'
        verbose_name_plural = 'businesses'

    def __str__(self):
        return self.name


class UserPreference(BaseModel):
    """Per-user product preferences that should survive across devices."""

    class Locale(models.TextChoices):
        RU = 'ru', 'Русский'
        UZ = 'uz', "O'zbekcha"
        EN = 'en', 'English'

    user = models.OneToOneField(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='micropos_preferences',
    )
    locale = models.CharField(max_length=8, choices=Locale.choices, default=Locale.RU)

    class Meta:
        db_table = 'core_user_preference'

    def __str__(self):
        return f"{self.user_id}: {self.locale}"


class InvestmentProfile(BaseModel):
    """Global investor identity, independent from any single business tenant."""

    user = models.OneToOneField(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='investment_profile',
        null=True,
        blank=True,
    )
    display_name = models.CharField(max_length=255)
    public_slug = models.SlugField(max_length=96, unique=True, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'core_investment_profile'
        indexes = [
            models.Index(fields=['is_active', 'display_name']),
        ]

    def __str__(self):
        return self.display_name


class Partner(TenantModel):
    """
    Abstract business partner — supertype for investors and operators.
    Participates in InvestmentContract for Procurement-level partnerships.
    """

    class Role(models.TextChoices):
        INVESTOR = 'INVESTOR', 'Инвестор'
        OPERATOR = 'OPERATOR', 'Оператор'

    role = models.CharField(max_length=20, choices=Role.choices)
    display_name = models.CharField(max_length=255)
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='partner_profiles',
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'core_partner'
        indexes = [
            models.Index(fields=['tenant', 'role', 'is_active']),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.role})"


def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)


class BusinessInvestorRelation(TenantModel):
    """Explicit visibility/access link between a business and an investor partner."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Ожидает'
        ACTIVE = 'ACTIVE', 'Активен'
        REVOKED = 'REVOKED', 'Отозван'
        BLOCKED = 'BLOCKED', 'Заблокирован'

    class Source(models.TextChoices):
        MANUAL = 'MANUAL', 'Вручную'
        INVITE = 'INVITE', 'Инвайт'

    partner = models.ForeignKey(
        Partner,
        on_delete=models.PROTECT,
        related_name='investor_relations',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MANUAL,
    )
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='created_investor_relations',
        null=True,
        blank=True,
    )
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'core_business_investor_relation'
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'partner'],
                name='uq_business_investor_relation',
            ),
        ]
        indexes = [
            models.Index(fields=['tenant', 'status'], name='core_busine_tenant__77b141_idx'),
            models.Index(fields=['partner', 'status'], name='core_busine_partner_053bdb_idx'),
        ]


class InvestorInvite(TenantModel):
    """Invite link for attaching an investor user to a business."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Ожидает'
        ACCEPTED = 'ACCEPTED', 'Принят'
        REVOKED = 'REVOKED', 'Отозван'
        EXPIRED = 'EXPIRED', 'Истёк'

    token = models.CharField(
        max_length=96,
        unique=True,
        default=generate_invite_token,
        db_index=True,
    )
    email = models.EmailField(blank=True, default='')
    display_name = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    invited_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='sent_investor_invites',
    )
    accepted_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='accepted_investor_invites',
        null=True,
        blank=True,
    )
    relation = models.ForeignKey(
        BusinessInvestorRelation,
        on_delete=models.SET_NULL,
        related_name='invites',
        null=True,
        blank=True,
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'core_investor_invite'
        indexes = [
            models.Index(fields=['tenant', 'status'], name='core_invest_tenant__be25c0_idx'),
            models.Index(fields=['expires_at'], name='core_invest_expires_77dcd2_idx'),
        ]

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()


class BusinessRegistrationRequest(BaseModel):
    """Public request for creating a new business account on the platform."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Ожидает'
        APPROVED = 'APPROVED', 'Подтверждена'
        REJECTED = 'REJECTED', 'Отклонена'

    username = models.CharField(max_length=150, db_index=True)
    password_hash = models.CharField(max_length=128)
    first_name = models.CharField(max_length=150, blank=True, default='')
    last_name = models.CharField(max_length=150, blank=True, default='')
    phone = models.CharField(max_length=32, blank=True, default='')
    business_name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    rejection_reason = models.CharField(max_length=255, blank=True, default='')
    reviewed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='reviewed_business_registration_requests',
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_user = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='approved_business_registration_requests',
        null=True,
        blank=True,
    )
    approved_business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name='registration_requests',
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'core_business_registration_request'
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['username', 'status']),
        ]


class OutboxEvent(BaseModel):
    """
    Outbox pattern — stores domain events for async processing.
    Celery workers poll for unprocessed events.
    """

    event_type = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField()
    processed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')
    attempts = models.PositiveIntegerField(default=0)
    tenant_id = models.IntegerField(db_index=True)

    class Meta:
        db_table = 'core_outbox_event'
        indexes = [
            models.Index(
                fields=['processed_at', 'tenant_id'],
                name='idx_outbox_unprocessed',
                condition=models.Q(processed_at__isnull=True),
            ),
        ]

    def __str__(self):
        return f"{self.event_type} (tenant={self.tenant_id})"

    def mark_processed(self):
        self.processed_at = timezone.now()
        self.failed_at = None
        self.last_error = ''
        self.save(update_fields=['processed_at', 'failed_at', 'last_error', 'updated_at'])

    def mark_failed(self, error_message: str):
        self.failed_at = timezone.now()
        self.last_error = error_message[:2000]
        self.attempts = self.attempts + 1
        self.save(update_fields=['failed_at', 'last_error', 'attempts', 'updated_at'])


class ExcelImportBatch(TenantModel):
    """
    Import batch metadata for Excel/Sheets alignment pipeline.
    """

    class Mode(models.TextChoices):
        DRY_RUN = 'dry-run', 'Dry run'
        LOAD_MASTER = 'load-master', 'Load master'
        LOAD_TRANSACTIONS = 'load-transactions', 'Load transactions'
        RECONCILE = 'reconcile', 'Reconcile'

    class Status(models.TextChoices):
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    source_kind = models.CharField(max_length=50, default='json')
    source_ref = models.CharField(max_length=500, blank=True, default='')
    mode = models.CharField(max_length=40, choices=Mode.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    totals = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'core_excel_import_batch'
        indexes = [
            models.Index(fields=['tenant', 'mode', 'status']),
            models.Index(fields=['tenant', 'created_at']),
        ]

    def __str__(self):
        return f"ExcelImportBatch #{self.pk} ({self.mode})"


class ExcelImportRow(TenantModel):
    """
    Staging row with parse/apply status and source traceability.
    """

    class Status(models.TextChoices):
        STAGED = 'staged', 'Staged'
        PARSED = 'parsed', 'Parsed'
        APPLIED = 'applied', 'Applied'
        FAILED = 'failed', 'Failed'
        SKIPPED = 'skipped', 'Skipped'

    class FailureCategory(models.TextChoices):
        PARSE = 'parse', 'Parse'
        MAPPING = 'mapping', 'Mapping'
        DOMAIN = 'domain', 'Domain'
        OTHER = 'other', 'Other'

    batch = models.ForeignKey(
        ExcelImportBatch,
        on_delete=models.CASCADE,
        related_name='rows',
    )
    source_sheet = models.CharField(max_length=100, db_index=True)
    source_row_id = models.CharField(max_length=64)
    row_fingerprint = models.CharField(max_length=64, db_index=True)
    raw_payload = models.JSONField()
    normalized_payload = models.JSONField(null=True, blank=True)
    parse_errors = models.JSONField(default=list, blank=True)
    failure_category = models.CharField(
        max_length=20,
        choices=FailureCategory.choices,
        blank=True,
        default='',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.STAGED,
        db_index=True,
    )
    target_model = models.CharField(max_length=120, blank=True, default='')
    target_id = models.IntegerField(null=True, blank=True)

    # Canonical operation money trace for audit/reconciliation.
    operation_currency = models.CharField(max_length=3, default='UZS')
    operation_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fx_rate_snapshot = models.DecimalField(
        max_digits=16,
        decimal_places=6,
        null=True,
        blank=True,
    )
    functional_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Functional amount in UZS.',
    )

    class Meta:
        db_table = 'core_excel_import_row'
        unique_together = [('batch', 'source_sheet', 'source_row_id')]
        indexes = [
            models.Index(fields=['tenant', 'source_sheet', 'row_fingerprint']),
            models.Index(fields=['batch', 'status']),
            models.Index(fields=['tenant', 'status', 'created_at']),
        ]

    def __str__(self):
        return (
            f"ExcelImportRow #{self.pk} "
            f"{self.source_sheet}:{self.source_row_id} "
            f"({self.status})"
        )
