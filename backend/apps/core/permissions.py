"""Role-based permissions for MicroPOS."""

from rest_framework.permissions import BasePermission

ROLE_OWNER = 'owner'
ROLE_CASHIER = 'cashier'
ROLE_WAREHOUSE = 'warehouse'
ROLE_INVESTOR = 'investor'

KNOWN_ROLES = {
    ROLE_OWNER,
    ROLE_CASHIER,
    ROLE_WAREHOUSE,
    ROLE_INVESTOR,
}


def _group_names(user) -> set[str]:
    if not getattr(user, 'is_authenticated', False):
        return set()
    return {
        name.strip().lower()
        for name in user.groups.values_list('name', flat=True)
        if isinstance(name, str)
    }


def _coerce_tenant_id(raw_value) -> int | None:
    if raw_value in (None, ''):
        return None
    try:
        tenant_id = int(raw_value)
    except (TypeError, ValueError):
        return None
    return tenant_id if tenant_id > 0 else None


def _user_has_tenant_access(user, tenant_id: int | None) -> bool:
    if tenant_id is None or not getattr(user, 'is_authenticated', False):
        return False

    if user.is_superuser or user.is_staff:
        return True

    if hasattr(user, 'owned_businesses') and user.owned_businesses.filter(id=tenant_id, is_active=True).exists():
        return True

    from apps.core.models import BusinessInvestorRelation, Partner

    if Partner.objects.filter(
        user_id=user.id,
        tenant_id=tenant_id,
        is_active=True,
        role=Partner.Role.OPERATOR,
    ).exists():
        return True

    return BusinessInvestorRelation.objects.filter(
        tenant_id=tenant_id,
        status=BusinessInvestorRelation.Status.ACTIVE,
        partner__user_id=user.id,
        partner__is_active=True,
        partner__role=Partner.Role.INVESTOR,
    ).exists()


def resolve_tenant_id_for_user(user, header_tenant_id=None) -> int | None:
    if not getattr(user, 'is_authenticated', False):
        return _coerce_tenant_id(header_tenant_id)

    explicit_candidates = [
        _coerce_tenant_id(getattr(user, 'active_tenant_id', None)),
        _coerce_tenant_id(header_tenant_id),
    ]
    for candidate in explicit_candidates:
        if _user_has_tenant_access(user, candidate):
            return candidate

    tenant_id = None
    if hasattr(user, 'owned_businesses'):
        owned_business_id = (
            user.owned_businesses
            .filter(is_active=True)
            .order_by('id')
            .values_list('id', flat=True)
            .first()
        )
        tenant_id = _coerce_tenant_id(owned_business_id)

    if tenant_id is None:
        from apps.core.models import BusinessInvestorRelation, Partner

        partner_tenant_id = (
            BusinessInvestorRelation.objects
            .filter(
                partner__user_id=user.id,
                partner__is_active=True,
                partner__role=Partner.Role.INVESTOR,
                status=BusinessInvestorRelation.Status.ACTIVE,
            )
            .order_by('id')
            .values_list('tenant_id', flat=True)
            .first()
        )
        if partner_tenant_id is None:
            partner_tenant_id = (
                Partner.objects
                .filter(user_id=user.id, is_active=True, role=Partner.Role.OPERATOR)
                .order_by('id')
                .values_list('tenant_id', flat=True)
                .first()
            )
        tenant_id = _coerce_tenant_id(partner_tenant_id)

    if tenant_id is None and (user.is_superuser or user.is_staff):
        from apps.core.models import Business

        system_business_id = (
            Business.objects
            .filter(is_active=True)
            .order_by('id')
            .values_list('id', flat=True)
            .first()
        )
        tenant_id = _coerce_tenant_id(system_business_id)

    if tenant_id is None:
        group_names = _group_names(user)
        if (
            ROLE_INVESTOR in group_names
            and ROLE_OWNER not in group_names
            and ROLE_CASHIER not in group_names
            and ROLE_WAREHOUSE not in group_names
        ):
            return None

    if tenant_id is None:
        from apps.core.models import Business

        active_ids = list(
            Business.objects
            .filter(is_active=True)
            .order_by('id')
            .values_list('id', flat=True)[:2]
        )
        if len(active_ids) == 1:
            tenant_id = _coerce_tenant_id(active_ids[0])

    return tenant_id


def ensure_request_tenant(request) -> int | None:
    header_tenant_id = request.headers.get('X-Tenant-ID')
    if getattr(request.user, 'is_authenticated', False):
        tenant_id = resolve_tenant_id_for_user(
            request.user,
            header_tenant_id=header_tenant_id,
        )
        request.tenant_id = tenant_id
        return tenant_id

    tenant_id = _coerce_tenant_id(getattr(request, 'tenant_id', None))
    if tenant_id is None:
        tenant_id = _coerce_tenant_id(header_tenant_id)
    request.tenant_id = tenant_id
    return tenant_id


def resolve_user_role(user, tenant_id: int | None = None) -> str | None:
    """
    Resolve role from the current auth model.

    Priority:
    1) user.role (if present on a custom user model)
    2) Django groups (owner/cashier/warehouse/investor)
    3) superuser/staff or business owner -> owner
    """
    if not getattr(user, 'is_authenticated', False):
        return None

    raw_role = getattr(user, 'role', None)
    if isinstance(raw_role, str):
        normalized = raw_role.strip().lower()
        if normalized in KNOWN_ROLES:
            return normalized

    from apps.core.models import BusinessInvestorRelation, Partner

    partner_query = Partner.objects.filter(user_id=user.id, is_active=True)
    if tenant_id is not None:
        partner_query = partner_query.filter(tenant_id=tenant_id)

    if partner_query.filter(role=Partner.Role.OPERATOR).exists():
        return ROLE_OWNER

    investor_partner_ids = partner_query.filter(
        role=Partner.Role.INVESTOR,
    ).values('id')
    investor_relation_query = BusinessInvestorRelation.objects.filter(
        partner_id__in=investor_partner_ids,
        status=BusinessInvestorRelation.Status.ACTIVE,
    )
    if tenant_id is not None:
        investor_relation_query = investor_relation_query.filter(tenant_id=tenant_id)
    if investor_relation_query.exists():
        return ROLE_INVESTOR

    group_names = _group_names(user)
    for role in (ROLE_OWNER, ROLE_CASHIER, ROLE_WAREHOUSE):
        if role in group_names:
            return role
    if ROLE_INVESTOR in group_names:
        if tenant_id is None or BusinessInvestorRelation.objects.filter(
            tenant_id=tenant_id,
            status=BusinessInvestorRelation.Status.ACTIVE,
            partner__user_id=user.id,
            partner__is_active=True,
            partner__role=Partner.Role.INVESTOR,
        ).exists():
            return ROLE_INVESTOR

    if user.is_superuser or user.is_staff:
        return ROLE_OWNER

    if hasattr(user, 'owned_businesses') and user.owned_businesses.exists():
        return ROLE_OWNER

    return None


class IsOwner(BasePermission):
    """Full access — business owner."""

    def has_permission(self, request, view):
        ensure_request_tenant(request)
        return (
            request.user.is_authenticated
            and resolve_user_role(request.user, request.tenant_id) == ROLE_OWNER
        )


class IsCashier(BasePermission):
    """Sales-only access."""

    def has_permission(self, request, view):
        ensure_request_tenant(request)
        role = resolve_user_role(request.user, request.tenant_id)
        return (
            request.user.is_authenticated
            and role in (ROLE_OWNER, ROLE_CASHIER)
        )


class IsCashierOrWarehouse(BasePermission):
    """Read access for sales/intake shared reference data."""

    def has_permission(self, request, view):
        ensure_request_tenant(request)
        role = resolve_user_role(request.user, request.tenant_id)
        return (
            request.user.is_authenticated
            and role in (ROLE_OWNER, ROLE_CASHIER, ROLE_WAREHOUSE)
        )


class IsWarehouse(BasePermission):
    """Inventory management access."""

    def has_permission(self, request, view):
        ensure_request_tenant(request)
        role = resolve_user_role(request.user, request.tenant_id)
        return (
            request.user.is_authenticated
            and role in (ROLE_OWNER, ROLE_WAREHOUSE)
        )


class IsInvestor(BasePermission):
    """Investor cabinet access."""

    def has_permission(self, request, view):
        ensure_request_tenant(request)
        return (
            request.user.is_authenticated
            and resolve_user_role(request.user, request.tenant_id) == ROLE_INVESTOR
        )
