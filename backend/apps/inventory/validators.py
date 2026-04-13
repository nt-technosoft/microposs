"""
Inventory validators — receipt participant ratio checks.
"""

from decimal import Decimal
from apps.core.exceptions import InvalidParticipantRatioError


def validate_participant_ratios(participants: list[dict]) -> None:
    """
    Validate that profit_ratio of all participants sums to 1.0.
    Also validates capital_amount > 0 for each participant.
    """
    if not participants:
        return

    total_profit_ratio = sum(
        Decimal(str(p['profit_ratio'])) for p in participants
    )

    if abs(total_profit_ratio - Decimal('1.0')) > Decimal('0.0001'):
        raise InvalidParticipantRatioError(
            f"Profit ratios must sum to 1.0, got {total_profit_ratio}"
        )

    total_capital = sum(
        Decimal(str(p['capital_amount'])) for p in participants
    )

    if total_capital <= 0:
        raise InvalidParticipantRatioError("Total capital must be positive")

    for p in participants:
        if Decimal(str(p['capital_amount'])) < 0:
            raise InvalidParticipantRatioError(
                "Capital amount cannot be negative"
            )
