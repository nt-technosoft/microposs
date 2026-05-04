"""Safety helpers for management commands that can mutate production data."""

import sys

from django.conf import settings
from django.core.management.base import CommandError


def _running_under_pytest() -> bool:
    return any('pytest' in arg for arg in sys.argv)


def require_debug_or_confirmation(
    *,
    command_name: str,
    confirmed: bool,
    flag_name: str,
    action: str,
) -> None:
    allow_test_commands = getattr(
        settings,
        'ALLOW_UNSAFE_MANAGEMENT_COMMANDS_IN_TESTS',
        True,
    )
    if settings.DEBUG or confirmed or (allow_test_commands and _running_under_pytest()):
        return

    raise CommandError(
        f'Refusing to run {command_name} while DEBUG=False: {action}. '
        f'If this is intentional, re-run with {flag_name}.'
    )
