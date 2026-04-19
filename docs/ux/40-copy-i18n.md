# Copy and i18n Rules

## Purpose
Снизить drift по текстам и не допускать hardcoded strings в новых PR-10/11 flows.

## Rules
- Все новые role-facing тексты проходят через i18n layer.
- В spec фиксируются user-facing labels для критических действий и состояний.
- Тексты ошибок должны объяснять причину и следующий шаг.
- Терминология должна отражать vacuum-model: `Procurement`, `Receive`, `Receivable`, `Ledger`, `Dividend`, а не legacy vocabulary там, где модель уже переосмыслена.

## UX copy style
- коротко
- понятно
- без двусмысленностей
- без перегруза финансовым жаргоном там, где можно объяснить проще

## Critical examples
- balance blocked before receive
- credit requires customer
- return resolution meaning
- pending payout meaning
