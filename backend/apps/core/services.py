"""
Core services — outbox event publishing, tenant utilities.
"""

import logging
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

from .models import (
    Business,
    BusinessRegistrationRequest,
    BusinessInvestorRelation,
    InvestmentProfile,
    InvestorInvite,
    OutboxEvent,
    Partner,
)


def publish_event(event_type: str, payload: dict, tenant_id: int) -> OutboxEvent:
    """Create an OutboxEvent and trigger its dispatch when the action commits.

    The originating domain action (sale, receive, payment, …) is what should
    drive its downstream effects to completion. We register an on_commit hook
    that runs the outbox processor: in dev (CELERY_TASK_ALWAYS_EAGER) it runs
    inline, in prod it enqueues to the worker. A scheduled poll, if present,
    stays as a backstop for anything missed.
    """
    event = OutboxEvent.objects.create(
        event_type=event_type,
        payload=payload,
        tenant_id=tenant_id,
    )

    def _trigger_dispatch() -> None:
        try:
            from apps.analytics.tasks import process_outbox_events
            process_outbox_events.delay()
        except Exception:
            # A dispatch hiccup (e.g. broker down) must never break the action
            # that produced the event; the backstop poll will pick it up.
            logger.warning('Outbox dispatch trigger failed', exc_info=True)

    transaction.on_commit(_trigger_dispatch)
    return event


def _investor_display_name(user, fallback: str = '') -> str:
    full_name = ''
    if hasattr(user, 'get_full_name'):
        full_name = user.get_full_name()
    return (fallback or full_name or getattr(user, 'username', '') or 'Investor').strip()


def get_or_create_investment_profile(user, display_name: str = '') -> InvestmentProfile:
    """Return the user's global investor identity, creating the MVP profile if needed."""
    if not getattr(user, 'is_authenticated', False):
        raise ValueError('Authenticated user is required for an investment profile.')
    profile, _created = InvestmentProfile.objects.get_or_create(
        user=user,
        defaults={
            'display_name': _investor_display_name(user, display_name),
            'is_active': True,
        },
    )
    updates = []
    if display_name and profile.display_name != display_name:
        profile.display_name = display_name
        updates.append('display_name')
    if not profile.is_active:
        profile.is_active = True
        updates.append('is_active')
    if updates:
        profile.save(update_fields=[*updates, 'updated_at'])
    return profile


def _operator_display_name(*, first_name: str = '', last_name: str = '', business_name: str = '') -> str:
    full_name = ' '.join(part for part in [first_name.strip(), last_name.strip()] if part).strip()
    return full_name or business_name.strip() or 'Owner'


def create_business_registration_request(
    *,
    username: str,
    password: str,
    first_name: str,
    last_name: str,
    phone: str,
    business_name: str,
) -> BusinessRegistrationRequest:
    normalized_username = username.strip()
    if User.objects.filter(username=normalized_username).exists():
        raise ValueError('Пользователь с таким логином уже существует.')
    if BusinessRegistrationRequest.objects.filter(
        username=normalized_username,
        status=BusinessRegistrationRequest.Status.PENDING,
    ).exists():
        raise ValueError('Заявка с таким логином уже ожидает подтверждения.')

    registration_request = BusinessRegistrationRequest.objects.create(
        username=normalized_username,
        password_hash=make_password(password),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        phone=phone.strip(),
        business_name=business_name.strip(),
    )
    publish_event(
        event_type='business.registration_request_created',
        payload={
            'request_id': registration_request.pk,
            'username': registration_request.username,
            'business_name': registration_request.business_name,
        },
        tenant_id=0,
    )
    return registration_request


def approve_business_registration_request(
    *,
    request_id: int,
    reviewed_by: User,
) -> BusinessRegistrationRequest:
    with transaction.atomic():
        registration_request = (
            BusinessRegistrationRequest.objects
            .select_for_update()
            .get(pk=request_id)
        )
        if registration_request.status != BusinessRegistrationRequest.Status.PENDING:
            raise ValueError('Подтверждать можно только заявку в статусе ожидания.')
        if User.objects.filter(username=registration_request.username).exists():
            raise ValueError('Пользователь с таким логином уже существует.')

        owner_group, _ = Group.objects.get_or_create(name='owner')
        user = User.objects.create(
            username=registration_request.username,
            first_name=registration_request.first_name,
            last_name=registration_request.last_name,
            is_active=True,
            password=registration_request.password_hash,
        )
        user.groups.add(owner_group)

        business = Business.objects.create(
            name=registration_request.business_name,
            owner=user,
            currency='UZS',
            is_active=True,
        )
        Partner.objects.create(
            tenant=business,
            role=Partner.Role.OPERATOR,
            display_name=_operator_display_name(
                first_name=registration_request.first_name,
                last_name=registration_request.last_name,
                business_name=registration_request.business_name,
            ),
            user=user,
            is_active=True,
        )

        registration_request.status = BusinessRegistrationRequest.Status.APPROVED
        registration_request.rejection_reason = ''
        registration_request.reviewed_by = reviewed_by
        registration_request.reviewed_at = timezone.now()
        registration_request.approved_user = user
        registration_request.approved_business = business
        registration_request.save(update_fields=[
            'status',
            'rejection_reason',
            'reviewed_by',
            'reviewed_at',
            'approved_user',
            'approved_business',
            'updated_at',
        ])

        publish_event(
            event_type='business.registration_request_approved',
            payload={
                'request_id': registration_request.pk,
                'business_id': business.pk,
                'user_id': user.pk,
            },
            tenant_id=business.pk,
        )

    return registration_request


def reject_business_registration_request(
    *,
    request_id: int,
    reviewed_by: User,
    rejection_reason: str = '',
) -> BusinessRegistrationRequest:
    with transaction.atomic():
        registration_request = (
            BusinessRegistrationRequest.objects
            .select_for_update()
            .get(pk=request_id)
        )
        if registration_request.status != BusinessRegistrationRequest.Status.PENDING:
            raise ValueError('Отклонять можно только заявку в статусе ожидания.')

        registration_request.status = BusinessRegistrationRequest.Status.REJECTED
        registration_request.rejection_reason = rejection_reason.strip()
        registration_request.reviewed_by = reviewed_by
        registration_request.reviewed_at = timezone.now()
        registration_request.save(update_fields=[
            'status',
            'rejection_reason',
            'reviewed_by',
            'reviewed_at',
            'updated_at',
        ])

        publish_event(
            event_type='business.registration_request_rejected',
            payload={
                'request_id': registration_request.pk,
                'reason': registration_request.rejection_reason,
            },
            tenant_id=0,
        )

    return registration_request


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
