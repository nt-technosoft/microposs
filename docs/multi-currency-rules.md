# Multi-Currency Rules

## Operating Rules

1. `Money` in the system is always `amount + currency`.
2. Cash and procurement balances are native per-currency. No implicit conversion.
3. Currency conversion happens only via explicit `CurrencyExchange`.
4. `fx_rate` is stored on historical transactions, but in UI it should be auto-filled by default from the rate table and edited only when the factual deal rate differs.

## Contract / Partnership Rules

1. Every partnership procurement has a `contract.currency`. This is the valuation currency for contract math.
2. Partner capital shares are recalculated from factual contributions using historical valuation in `contract.currency`.
3. Historical market moves after contribution do not rewrite partner capital shares.
4. Current-rate snapshots may be shown in reports, but they are not the contractual source of truth.

## Reporting Rules

1. `Balance` is shown native per-currency by default.
2. `P&L` and `Cash Flow` are reporting views and may use historical functional currency values.
3. Any consolidated single-currency snapshot must be explicitly labeled with:
   - target currency
   - rate date
   - rate source

## Guardrails

1. If a procurement needs `UZS` but the balance has only `USD`, the system must require an explicit exchange step.
2. Receive/close validations are performed per-currency, not by a merged equivalent amount.
3. Mixed-currency leftover balances must not be auto-settled by current-rate guesswork.
