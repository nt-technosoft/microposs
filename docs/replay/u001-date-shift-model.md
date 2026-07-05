# U-001 date-shift replay model

Status: working projection, not yet a database import.

Purpose: make `U-001.xlsx` replayable through MicroPOS without synthetic debt,
by keeping the Excel economics but making implicit turnover decisions explicit.

## Source priority

- `FOYDA_TAQSIMOTI`: agreement economics, capital/profit shares, final P&L.
- `TUSHUM`: actual cash receipts and investor capital inflows.
- `XARAJAT`: cash payments for purchases, dividends and expenses.
- `SOTIB OLISH`: product/quantity/cost detail for inventory and FIFO.
- `SOTUV`: product sales detail; `TUSHUM` remains the cash source.

## Source totals used

| Metric | Amount |
|---|---:|
| Investor capital base | 84,850,000 UZS |
| Purchase payments | 257,021,600 UZS |
| Collected sales cash | 246,743,000 UZS |
| Revenue in P&L | 251,943,000 UZS |
| Cost of sales in P&L | 154,008,000 UZS |
| Gross profit in P&L | 97,935,000 UZS |
| Final profit in P&L | 96,769,350 UZS |
| Ending inventory at cost | 103,013,600 UZS |
| Ending cash | 8,663,750 UZS |

Important: capital rollover alone is not enough. Original capital plus recovered
cost of sold goods cannot explain ending inventory and all later purchases. The
Excel effectively keeps part of investor profit in turnover.

## Selected model

1. Initial capital: 60,450,000 UZS on 2025-11-01.
2. Second investor capital tranche: 24,400,000 UZS effective on 2026-03-15.
   Source row is 2026-03-23 for 2,000 USD, but the economic model uses the
   later 12,200 UZS/USD conversion visible in `PUL AYRIBOSHLASH` so the contract
   capital matches `FOYDA_TAQSIMOTI` total capital of 84,850,000 UZS.
3. Sales cash first releases recovered capital and investor profit share.
4. Before each purchase payment, use in order:
   - active agreement pool;
   - explicit `ROLL_OVER_CAPITAL` from recovered cost;
   - explicit investor `CAPITALIZE_PROFIT` if the pool still lacks money.
5. Business profit payouts to Uygun remain payouts, not hidden capital.
6. Physical product dates can remain close to `SOTIB OLISH`; the capital-funded
   purchase/payment chronology follows `XARAJAT`.

## Required date corrections

| Source | Original date | Effective date | Amount | Reason |
|---|---:|---:|---:|---|
| `TUSHUM` capital row, 2,000 USD | 2026-03-23 | 2026-03-15 | 24,400,000 UZS | Make the second tranche available before March turnover pressure. |
| `PUL AYRIBOSHLASH`, 2,000 USD conversion | 2026-03-24/25 | 2026-03-15 | 24,400,000 UZS | Same economic correction as the capital tranche. |
| `XARAJAT` row 58, contract 39 partial purchase payment | 2026-04-20 | 2026-04-21 | 1,530,000 UZS | Removes a small 104,703.90 UZS timing shortage; product/FIFO date can stay unchanged. |

Already accepted product-level corrections still apply separately: the `J82350`
sale typo is mapped to `82350`, and the earlier KURTKA/99620 post-factum
purchase-date issues should keep their existing smooth effective dates.

## Monthly model result

| Month | External capital | Sales cash | Purchase payments | Capital rollover | Investor profit capitalized | Dividend/expense cash out |
|---|---:|---:|---:|---:|---:|---:|
| 2025-11 | 60,450,000.00 | 33,176,000.00 | 78,320,000.00 | 16,535,848.78 | 1,334,151.22 | 0.00 |
| 2025-12 | 0.00 | 37,830,000.00 | 28,130,000.00 | 25,572,945.79 | 2,557,054.21 | 18,655,000.00 |
| 2026-01 | 0.00 | 18,820,000.00 | 14,600,000.00 | 11,534,791.68 | 3,065,208.32 | 4,885,000.00 |
| 2026-02 | 0.00 | 18,750,000.00 | 14,345,000.00 | 11,161,993.31 | 3,183,006.69 | 6,272,000.00 |
| 2026-03 | 24,400,000.00 | 50,115,000.00 | 63,974,600.00 | 32,199,233.16 | 7,375,366.84 | 12,260,000.00 |
| 2026-04 | 0.00 | 37,447,000.00 | 22,492,000.00 | 18,515,377.85 | 3,976,622.15 | 13,045,000.00 |
| 2026-05 | 0.00 | 42,065,000.00 | 28,140,000.00 | 28,140,000.00 | 0.00 | 10,825,000.00 |
| 2026-06 | 0.00 | 8,540,000.00 | 7,020,000.00 | 7,020,000.00 | 0.00 | 0.00 |

Totals:

- `ROLL_OVER_CAPITAL`: 150,680,190.56 UZS.
- Investor `CAPITALIZE_PROFIT`: 21,491,409.44 UZS.
- Timing deficits after the corrections: 0.
- Remaining recovered capital not reused: 149,147.60 UZS.
- Remaining investor profit share not capitalized: 7,282,689.11 UZS.
- Cash model ending balance: 8,629,400 UZS, close to Excel cash 8,663,750 UZS;
  the difference is explainable by the small FX/capital presentation mismatch.

## Profit capitalization events

| Date | Amount |
|---|---:|
| 2025-11-23 | 1,334,151.22 |
| 2025-12-04 | 58,347.48 |
| 2025-12-21 | 1,195,145.03 |
| 2025-12-28 | 1,303,561.70 |
| 2026-01-10 | 619,641.82 |
| 2026-01-25 | 2,445,566.50 |
| 2026-02-02 | 534,501.67 |
| 2026-02-10 | 402,527.48 |
| 2026-02-17 | 1,307,223.54 |
| 2026-02-25 | 938,754.00 |
| 2026-03-04 | 722,433.59 |
| 2026-03-14 | 2,103,467.81 |
| 2026-03-25 | 2,933,131.45 |
| 2026-03-31 | 1,616,333.99 |
| 2026-04-20 | 2,581,104.00 |
| 2026-04-21 | 1,395,518.15 |

## Implementation implication

This model is mathematically valid only if U-001 terms explicitly allow investor
profit capitalization. E23 intentionally blocks generic `CAPITALIZE_PROFIT`
without a terms/amendment rule. So before applying replay, U-001 needs either:

1. an explicit agreement terms rule/amendment allowing investor profit
   capitalization inside the same agreement; or
2. a founder-approved alternative treatment for the 21,491,409.44 UZS that does
   not pretend it was new external capital.

Recommendation: use option 1. It matches the real business story: the investor
did not add that money from outside; their earned profit stayed in turnover.
