# WGT-005 / Ledger Timeline

## Purpose
Показать последовательность ledger entries и связанных событий по procurement/investor flow понятным образом на mobile.

## Used in screens
- procurement detail
- investor dashboard/detail
- payout history contexts

## Planned role in PR-11
Новый domain widget для partner/investor trust and transparency.

## Required behavior
- chronological entries
- visible entry type semantics (capital in/out, profit accrued, reversed, loss, dividend)
- exact amount/currency
- link to related operation when available

## States
- loading
- empty timeline
- populated timeline
- filtered view (optional later)

## Mobile behavior
- timeline/cards first, not dense tables
- color may help, but text labels must carry meaning on their own
