# MicroPOS — Excel to Domain Mapping (Iteration 1)

## Import Order
`MALUMOTLAR -> opening balances -> SOTIB OLISH -> STOCK TRANSFER -> SOTUV -> TUSHUM -> XARAJAT -> PUL AYRIBOSHLASH`

## Sheet Mapping

| Sheet | Primary fields | Domain target | Transform | Validation / Invariants |
|---|---|---|---|---|
| `MALUMOTLAR` | `TRADE CREDITOR`, `MIJOZLAR`, `MAHSULOTLAR`, `OMBOR`, photo url | `Supplier`, `Customer`, `Product(+Variant)`, `Location`, `ProductCharacteristic(source_photo_url)` | Normalized names, idempotent upsert | Master rows are idempotent by name + tenant |
| `SOTIB OLISH` | `SANA`, `ISM`, `MAHSULOT`, `SONI`, `MAHSULOT NARXI`, `PUL BIRLIGI`, `KURS`, `TO'LOV MUDDATI` | `Receipt` + `ReceiptLine` + `Lot` via `confirm_receipt()` | Currency -> UZS functional amount | Receipt confirm immutability, journal/outbox on confirm |
| `STOCK TRANSFER` | `SANA`, `MAHSULOT`, `SONI`, `KIRIM`, `CHIQIM` | `transfer_lot()` over active lots (FIFO order) | Split/multi-lot move when needed | Move changes location only; participants unchanged |
| `SOTUV` | `SOTUV SANASI`, `MIJOZ`, `MAHSULOT`, `JAMI DONA`, `SOTUV NARXI`, `VALYUTA`, `KURS`, `OMBOR`, `TO'LOV MUDDATI` | `create_sale()` | Unit price normalized to UZS; payment method mapping | `SaleLine -> Lot`, FIFO, credit requires customer, journal/outbox |
| `TUSHUM` | `SANA`, `MIJOZ`, `MIQDOR`, `VALYUTA`, `KURS`, `TO'LOV TURI` | `record_customer_payment()` | Amount normalized to UZS | Decreases `Customer.outstanding_balance`, journal/outbox |
| `XARAJAT` | `SANA`, `CREDITOR`, `MIQDOR`, `VALYUTA`, `KURS`, `QAYERDAN TO'LOV QILINDI` | Supplier case: `record_supplier_payment()`, else journal expense entry | Amount normalized to UZS | AP payment updates supplier debt; journal integrity |
| `PUL AYRIBOSHLASH` | `SANA`, `KIRIM`, `KIRIM MIQDORI`, `CHIQIM`, `CHIQIM MIQDORI`, `VALYUTA (CHIQUVCHI)`, `KURS` | FX journal transfer entry | Outgoing amount -> UZS functional amount | Balanced journal entry required |

## Posting Behavior
- If `POSTED` exists and not marked (`✅/TRUE/1`), row is staged and marked `skipped`.
- If `POSTED` is absent, row is treated as operational by default.

## Account Mapping (Iteration 1)
- Cash-like SOM accounts -> `1000`.
- USD/Bank/Card/Plastic accounts -> `1010`.
- Imported non-supplier expense debit -> `5300`.
- Opening cash balancing credit -> `3000`.

## Staging / Idempotency
- Every row is staged in `core_excel_import_row`.
- Idempotency anchor: `row_fingerprint` + `source_sheet`.
- Re-import behavior: already-applied fingerprints are `skipped`.

## Notes on Derived Sheets
`KASSA`, `OMBOR`, `QARZDORLAR`, `YETKAZIB BERUVCHILARDAN QARZ`, `FOYDA TAQSIMOTI`:
- not loaded into operational tables,
- used as expected-control for reconcile mode / manual UAT checks.
