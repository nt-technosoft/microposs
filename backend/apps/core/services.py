"""
Core services — outbox event publishing, tenant utilities.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    Business,
    BusinessInvestorRelation,
    InvestorInvite,
    OutboxEvent,
    Partner,
)


def publish_event(event_type: str, payload: dict, tenant_id: int) -> OutboxEvent:
    """Create an OutboxEvent for async processing by Celery."""
    return OutboxEvent.objects.create(
        event_type=event_type,
        payload=payload,
        tenant_id=tenant_id,
    )


def _investor_display_name(user, fallback: str = '') -> str:
    full_name = ''
    if hasattr(user, 'get_full_name'):
        full_name = user.get_full_name()
    return (fallback or full_name or getattr(user, 'username', '') or 'Investor').strip()


def create_investor_invite(
    *,
    tenant_id: int,
    invited_by_id: int,
    email: str = '',
    display_name: str = '',
    expires_days: int = 14,
) -> InvestorInvite:
    business = Business.objects.get(pk=tenant_id, is_active=True)
    invite = InvestorInvite.objects.create(
        tenant=business,
        invited_by_id=invited_by_id,
        email=(email or '').strip().lower(),
        display_name=(display_name or '').strip(),
        expires_at=timezone.now() + timedelta(days=max(1, min(expires_days, 60))),
    )
    publish_event(
        event_type='investor.invite_created',
        payload={'invite_id': invite.pk, 'email': invite.email},
        tenant_id=tenant_id,
    )
    return invite


def accept_investor_invite(
    *,
    token: str,
    user,
    display_name: str = '',
) -> tuple[InvestorInvite, BusinessInvestorRelation]:
    with transaction.atomic():
        invite = InvestorInvite.objects.select_for_update().select_related('tenant').get(
            token=token,
        )
        if invite.status != InvestorInvite.Status.PENDING:
            raise ValueError('Invite is not pending.')
        if invite.is_expired:
            invite.status = InvestorInvite.Status.EXPIRED
            invite.save(update_fields=['status', 'updated_at'])
            raise ValueError('Invite has expired.')

        partner = Partner.objects.filter(
            tenant=invite.tenant,
            user_id=user.id,
            role=Partner.Role.INVESTOR,
        ).first()
        if partner is None:
            partner = Partner.objects.create(
                tenant=invite.tenant,
                user=user,
                role=Partner.Role.INVESTOR,
                display_name=_investor_display_name(user, display_name or invite.display_name),
                is_active=True,
            )
        else:
            updates = []
            if not partner.is_active:
                partner.is_active = True
                updates.append('is_active')
            if display_name and partner.display_name != display_name:
                partner.display_name = display_name
                updates.append('display_name')
            if updates:
                partner.save(update_fields=[*updates, 'updated_at'])

        relation, _ = BusinessInvestorRelation.objects.get_or_create(
            tenant=invite.tenant,
            partner=partner,
            defaults={
                'status': BusinessInvestorRelation.Status.ACTIVE,
                'source': BusinessInvestorRelation.Source.INVITE,
                'created_by_id': invite.invited_by_id,
            },
        )
        if relation.status != BusinessInvestorRelation.Status.ACTIVE:
            relation.status = BusinessInvestorRelation.Status.ACTIVE
            relation.source = BusinessInvestorRelation.Source.INVITE
            relation.save(update_fields=['status', 'source', 'updated_at'])

        invite.status = InvestorInvite.Status.ACCEPTED
        invite.accepted_by = user
        invite.accepted_at = timezone.now()
        invite.relation = relation
        invite.save(update_fields=[
            'status', 'accepted_by', 'accepted_at', 'relation', 'updated_at',
        ])

        publish_event(
            event_type='investor.invite_accepted',
            payload={
                'invite_id': invite.pk,
                'partner_id': partner.pk,
                'relation_id': relation.pk,
            },
            tenant_id=invite.tenant_id,
        )

    return invite, relation
