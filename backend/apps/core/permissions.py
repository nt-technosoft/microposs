"""Role-based permissions for MicroPOS."""

from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """Full access — business owner."""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request.user, 'role', None) == 'owner'
        )


class IsCashier(BasePermission):
    """Sales-only access."""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request.user, 'role', None) in ('owner', 'cashier')
        )


class IsWarehouse(BasePermission):
    """Inventory management access."""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request.user, 'role', None) in ('owner', 'warehouse')
        )


class IsInvestor(BasePermission):
    """Investor cabinet access."""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and getattr(request.user, 'role', None) == 'investor'
        )
