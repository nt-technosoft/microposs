# E14 — Capital Reconciliation (Inter-Partner Advances) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a partnership receive hold the *agreed* capital/profit shares even when actual contributions differ, recording the gap as an interest-free inter-partner advance through the agreement pool, settleable by cash or from the debtor's profit.

**Architecture:** A per-batch `share_basis` switch in the capital-snapshot resolver (`AGREED` = Path 2 default, `FACTUAL` = Path 1 = today). Under `AGREED`, the immutable batch snapshot pins agreed shares; the per-partner shortfall becomes a `CapitalAdvance` (debtor → creditor, pool-mediated) with append-only `CapitalAdvanceSettlement` events (source `CASH`|`FROM_PROFIT`). Shares never move after receive (Rule #14); only the advance balance moves. Loss follows the snapshot (agreed) share. Agreement close blocked while advances outstanding. Reversal cascades to the advance only when the batch is fully unsold.

**Tech Stack:** Django 5.1 / DRF / PostgreSQL; `apps.partnerships` (models, workspace.py services), `apps.finance` (journals, pool CashAccount), existing append-only `PartnerLedgerEntry` + immutable `ProcurementReceiveBatchCapitalAllocation`. Tests: `DJANGO_SETTINGS_MODULE=config.settings.development .venv/bin/python -m pytest apps/partnerships/ -q` from `backend/`.

**Reference spec:** `docs/roadmap/E14-capital-reconciliation-advances.md`

---

## File Structure

- `apps/partnerships/models.py` — add `CapitalAdvance`, `CapitalAdvanceSettlement`; add `ADVANCE_OUT`/`ADVANCE_REPAID` to `PartnerLedgerEntry.EntryType`.
- `apps/partnerships/migrations/00NN_capital_advance.py` — schema (no backfill; new receives only).
- `apps/partnerships/workspace.py` — `share_basis` in `_resolve_workspace_capital_snapshot`; advance creation in `receive_workspace_batch`; reversal handling in `reverse_workspace_receive_batch`; close guard.
- `apps/partnerships/advances.py` (NEW) — settlement service: `settle_capital_advance(...)`, `auto_settle_from_profit(...)`, balance/invariant helpers. Keeps `workspace.py` from growing further.
- `apps/partnerships/formulas.py` — loss allocation already uses snapshot; add assertion test only (no change expected).
- `apps/partnerships/views.py` + `urls.py` — settlement endpoint(s) with `client_request_id`.
- `apps/partnerships/tests/test_e14_*.py` — phase test modules.

---

## Phase 1 — Model + migration

### Task 1: `CapitalAdvance` + `CapitalAdvanceSettlement` models

**Files:**
- Modify: `apps/partnerships/models.py` (after `ProcurementReceiveBatchCapitalAllocation`, ~line 616; and `EntryType` ~line 988)
- Test: `apps/partnerships/tests/test_e14_models.py`

- [ ] **Step 1: Write failing test** (`test_e14_models.py`)

```python
import pytest
from decimal import Decimal
from apps.partnerships.models import CapitalAdvance, CapitalAdvanceSettlement, PartnerLedgerEntry

pytestmark = pytest.mark.django_db

def test_advance_defaults_outstanding_and_tracks_balance(agreement_two_partners, posted_batch):
    inv, biz = agreement_two_partners.investor, agreement_two_partners.operator
    adv = CapitalAdvance.objects.create(
        tenant=agreement_two_partners.tenant, agreement=agreement_two_partners.agreement,
        batch=posted_batch, debtor=inv, creditor=biz,
        principal=Decimal('1000.00'), currency='USD',
        repayment_mode=CapitalAdvance.RepaymentMode.LUMP,
    )
    assert adv.status == CapitalAdvance.Status.OUTSTANDING
    assert adv.outstanding_balance == Decimal('1000.00')

def test_settlement_is_append_only(advance_1000_usd):
    s = CapitalAdvanceSettlement.objects.create(
        tenant=advance_1000_usd.tenant, advance=advance_1000_usd,
        amount=Decimal('400.00'), source=CapitalAdvanceSettlement.Source.CASH,
    )
    with pytest.raises(Exception):
        s.amount = Decimal('1'); s.save()

def test_entrytypes_include_advance():
    assert PartnerLedgerEntry.EntryType.ADVANCE_OUT
    assert PartnerLedgerEntry.EntryType.ADVANCE_REPAID
```

- [ ] **Step 2: Run, verify import/attr failure**

Run: `.venv/bin/python -m pytest apps/partnerships/tests/test_e14_models.py -q`
Expected: FAIL (`ImportError: CapitalAdvance`).

- [ ] **Step 3: Add models + entry types**

```python
# models.py — extend PartnerLedgerEntry.EntryType
        ADVANCE_OUT = 'ADVANCE_OUT', 'Капитальный аванс (выдан)'
        ADVANCE_REPAID = 'ADVANCE_REPAID', 'Капитальный аванс (погашен)'

# models.py — new models (append-only, immutable balance recomputed from settlements)
class CapitalAdvance(TenantModel):
    """Interest-free inter-partner capital advance (qard) created when a Path-2
    receive holds agreed shares despite an under/over funding gap. Debtor under-
    contributed; creditor (or the pool) covered the shortfall."""

    class RepaymentMode(models.TextChoices):
        LUMP = 'LUMP', 'Единым платежом'
        FROM_PROFIT = 'FROM_PROFIT', 'Из прибыли'

    class Status(models.TextChoices):
        OUTSTANDING = 'OUTSTANDING', 'Не погашен'
        PARTIAL = 'PARTIAL', 'Частично погашен'
        SETTLED = 'SETTLED', 'Погашен'
        CANCELLED = 'CANCELLED', 'Аннулирован (реверс)'

    agreement = models.ForeignKey(InvestmentAgreement, on_delete=models.PROTECT, related_name='capital_advances')
    batch = models.ForeignKey(ProcurementReceiveBatch, on_delete=models.PROTECT, related_name='capital_advances')
    debtor = models.ForeignKey('core.Partner', on_delete=models.PROTECT, related_name='capital_advances_owed')
    creditor = models.ForeignKey('core.Partner', on_delete=models.PROTECT, null=True, blank=True, related_name='capital_advances_due')  # null = pool
    principal = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    repayment_mode = models.CharField(max_length=16, choices=RepaymentMode.choices, default=RepaymentMode.LUMP)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OUTSTANDING)
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_capital_advance'
        indexes = [models.Index(fields=['agreement']), models.Index(fields=['batch']), models.Index(fields=['status'])]

    @property
    def settled_amount(self) -> Decimal:
        from django.db.models import Sum
        total = self.settlements.aggregate(s=Sum('amount'))['s'] or Decimal('0')
        return Decimal(total).quantize(Decimal('0.01'))

    @property
    def outstanding_balance(self) -> Decimal:
        return (self.principal - self.settled_amount).quantize(Decimal('0.01'))


class CapitalAdvanceSettlement(TenantModel):
    """Append-only settlement event reducing an advance. Source = how it was paid."""

    class Source(models.TextChoices):
        CASH = 'CASH', 'Деньгами (пополнение/из баланса)'
        FROM_PROFIT = 'FROM_PROFIT', 'Из нераспределённой прибыли'

    advance = models.ForeignKey(CapitalAdvance, on_delete=models.PROTECT, related_name='settlements')
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    source = models.CharField(max_length=16, choices=Source.choices)
    date = models.DateTimeField(auto_now_add=True)
    source_ref = models.CharField(max_length=100, blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_capital_advance_settlement'
        indexes = [models.Index(fields=['advance'])]
        constraints = [models.UniqueConstraint(fields=['tenant', 'client_request_id'],
            condition=models.Q(client_request_id__isnull=False), name='uq_advance_settlement_idempotent')]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('CapitalAdvanceSettlement is append-only.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('CapitalAdvanceSettlement is append-only.')
```

- [ ] **Step 4: Make migration + run tests**

Run: `.venv/bin/python manage.py makemigrations partnerships && .venv/bin/python -m pytest apps/partnerships/tests/test_e14_models.py -q`
Expected: migration created; tests PASS. (Add fixtures `agreement_two_partners`, `posted_batch`, `advance_1000_usd` to `apps/partnerships/tests/conftest.py` — reuse existing agreement/receive factories already used by `test_e07_*`/`test_e11_*`.)

- [ ] **Step 5: Commit** — `feat(E14): CapitalAdvance + settlement models, advance ledger entry types`

---

## Phase 2 — Receive under Path 2 (pin agreed shares, create advances)

### Task 2: `share_basis` in the snapshot resolver

**Files:**
- Modify: `apps/partnerships/workspace.py:3851` (`_resolve_workspace_capital_snapshot`)
- Test: `apps/partnerships/tests/test_e14_receive.py`

Algorithm under `share_basis='AGREED'` (default for Path 2):
- `target_i = agreed_ratio_i * required`, where `agreed_ratio_i = AgreementPartner.planned_capital_share_i / Σ planned_capital_share`.
- `available_i` = `_procurement_capital_available_by_partner` (unchanged source).
- **Relax** the per-partner `amount <= available` check; require only `Σ available >= required` (pool funds the batch).
- Snapshot `amount_contract_currency = target_i`, `capital_share = agreed_ratio_i`, `profit_share = AgreementPartner.profit_share_i` (NOT `profit_shares_from_capital`).
- `shortfall_i = max(0, target_i − available_i)`; `surplus_i = max(0, available_i − target_i)`. Σ shortfall == Σ surplus (covered) — assert.
- Return advances spec: list of `{debtor, creditor, principal}` by pairing shortfalls to surpluses pro-rata (2-party → single pair; n-party → pro-rata split).

Under `share_basis='FACTUAL'`: unchanged (current code path), no advances.

- [ ] **Step 1: Failing test — Path 2 pins agreed shares + emits advance spec**

```python
def test_path2_pins_agreed_shares_and_reports_shortfall(agreement_70_30_profit_40_60):
    ctx = agreement_70_30_profit_40_60  # investor agreed 70% cap / 40% profit; only 66% available
    snap, rows, advances = _resolve_workspace_capital_snapshot(
        tenant_id=ctx.tenant_id, procurement=ctx.procurement,
        required_uzs=ctx.required_uzs, raw_allocations=None, received_at=ctx.now,
        required_base=ctx.required_usd, share_basis='AGREED',
    )
    inv_row = next(r for r in rows if r['partner_id'] == ctx.investor_id)
    assert inv_row['capital_share'] == Decimal('0.700000')
    assert inv_row['profit_share'] == Decimal('0.400000')
    assert len(advances) == 1
    assert advances[0]['debtor'] == ctx.investor_id
    assert advances[0]['creditor'] == ctx.operator_id
    assert advances[0]['principal'] == ctx.shortfall_usd  # e.g. 0.04 * required
```

- [ ] **Step 2: Run → FAIL** (resolver returns 2-tuple, no `share_basis`). 
- [ ] **Step 3: Implement** the `share_basis` branch + advances spec (return becomes 3-tuple `(snapshot, rows, advances)`; update the single caller in Step of Task 3). Keep `FACTUAL` returning `advances=[]`.
- [ ] **Step 4: Run → PASS** plus existing `test_e11_*`/`test_e07_*` snapshot tests still green (update their call sites to unpack 3-tuple, default `share_basis='FACTUAL'`).
- [ ] **Step 5: Commit** — `feat(E14): AGREED share_basis pins agreed shares, computes shortfalls`

### Task 3: persist advances on receive + ledger entries + journal

**Files:**
- Modify: `apps/partnerships/workspace.py:2239` (`receive_workspace_batch`) — accept `share_basis` (default `AGREED`), unpack advances, create `CapitalAdvance` rows, post ledger `ADVANCE_OUT` (debtor −, creditor +) and GL by agreed shares.
- Test: `apps/partnerships/tests/test_e14_receive.py`

- [ ] **Step 1: Failing test** — receiving Path 2 creates a `CapitalAdvance(OUTSTANDING)` with `principal == shortfall`, snapshot allocation `capital_share` = agreed, and pool cash fully consumed; `ProcurementReceiveBatchCapitalAllocation.capital_share` == agreed.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — after snapshot persist (`workspace.py:2388`), loop advances → `CapitalAdvance.objects.create(...)`; `PartnerLedgerEntry` ADVANCE_OUT for debtor (the borrowed portion completing capital) and matching creditor entry; GL credit equity by agreed shares (role-correct accounts per Rule #13: investor 3100/3110, operator 3000). Emit `OutboxEvent` `partnership.capital_advance_created`.
- [ ] **Step 4: Run → PASS** + full `apps/partnerships -q` green.
- [ ] **Step 5: Commit** — `feat(E14): persist inter-partner advances on Path-2 receive`

### Task 4: invariant — Path 1 unchanged, deltas net zero

- [ ] Test `test_path1_factual_creates_no_advance` (share_basis FACTUAL → 0 advances, shares follow actual).
- [ ] Test `test_advance_deltas_net_zero` (Σ debtor principals == Σ creditor claims for the batch).
- [ ] Run → PASS. Commit — `test(E14): Path-1 untouched + advance net-zero invariant`.

---

## Phase 3 — Settlement service

### Task 5: `settle_capital_advance` (CASH + FROM_PROFIT)

**Files:**
- Create: `apps/partnerships/advances.py`
- Test: `apps/partnerships/tests/test_e14_settlement.py`

Service signature:

```python
def settle_capital_advance(*, tenant_id: int, advance_id: int, amount: Decimal,
                           source: str, client_request_id=None, acting_user=None) -> CapitalAdvance:
    """Append one CapitalAdvanceSettlement, post ledger ADVANCE_REPAID + GL/cash moves,
    recompute status. Principal-only; never below zero. For FROM_PROFIT, amount must not
    exceed the debtor's undistributed profit balance in this agreement."""
```

Rules enforced (each its own test):
- [ ] `amount > 0` and `amount <= advance.outstanding_balance` (else ValueError).
- [ ] `source=CASH`: debtor pays into pool → creditor's locked principal is freed (pool cash routed to creditor / creditor withdrawal claim). Journal posted.
- [ ] `source=FROM_PROFIT`: `amount <= undistributed_profit(debtor, agreement)`; routes debtor's accrued-but-unpaid profit to creditor; principal-only.
- [ ] status transitions: partial → `PARTIAL`, full → `SETTLED`.
- [ ] idempotent on `client_request_id`.
- [ ] `creditor` never receives more than principal (no markup) — assert in a test with over-amount rejected.

- [ ] Steps: write each test → FAIL → implement helper incrementally → PASS. Commit per coherent group — `feat(E14): advance settlement (cash + from-profit), principal-only guards`.

### Task 6: auto-settle from profit on distribution

**Files:**
- Modify: profit-distribution path (where `PROFIT_ACCRUED`/`DIVIDEND_PAID` ledger entries are written — locate via `grep PROFIT_ACCRUED apps/partnerships`).
- Test: `test_e14_settlement.py::test_from_profit_toggle_auto_consumes_first_profit`

- [ ] Failing test: advance with `repayment_mode=FROM_PROFIT`; distribute profit to debtor → first amounts auto-create `CapitalAdvanceSettlement(source=FROM_PROFIT)` until principal cleared, remainder flows to debtor.
- [ ] Run → FAIL → implement hook calling `settle_capital_advance(source=FROM_PROFIT, ...)` bounded by the distribution amount → PASS.
- [ ] Commit — `feat(E14): auto-settle FROM_PROFIT advances on profit distribution`.

---

## Phase 4 — Close guard + reversal + pool invariant

### Task 7: block agreement close while advances outstanding

**Files:** Modify the agreement-close service (`grep -n "def .*close" apps/partnerships/workspace.py apps/partnerships/services.py`).
- [ ] Failing test: close with an OUTSTANDING/PARTIAL advance → ValueError `Cannot close: unsettled capital advances`.
- [ ] Implement guard (respect Rule #8 alongside the existing active-lot check). PASS. Commit.

### Task 8: reversal by batch state

**Files:** Modify `reverse_workspace_receive_batch` (`workspace.py:613`).
- [ ] Test `test_reverse_unsold_cancels_advance_and_refunds`: batch fully unsold → advance `CANCELLED` (append-only counter-entries), prior CASH settlements refunded.
- [ ] Test `test_reverse_partially_sold_keeps_advance`: any SaleLine references the batch's lots → advance untouched (`OUTSTANDING`/`PARTIAL` preserved); only unsold lots reversed.
- [ ] Implement: detect "fully unsold" via `SaleLine` referencing `batch` lots == 0; branch accordingly. PASS. Commit — `feat(E14): reversal cascades to advance only when fully unsold`.

### Task 9: extended pool invariant

- [ ] Test `test_pool_invariant_with_advances`: `pool.balance == Σ contributions − Σ pool payments`, advances do not break it (locked principal is pool cash until settled). Run full suite → PASS. Commit — `test(E14): pool balance invariant holds with advances`.

---

## Phase 5 — Frontend receive UI (FOUNDER-COLLABORATIVE — do not ship solo)

Backend endpoints first (Task 10), then UI tasks 11-13 are built/verified WITH the founder per the standing "receive-UI under founder control" rule.

### Task 10: settlement + advances API
- [ ] `GET /api/v1/partnerships/agreements/{id}/advances/` — outstanding advances for the agreement card.
- [ ] `POST .../advances/{id}/settle/` — `{amount, source, client_request_id}` → `settle_capital_advance`.
- [ ] Receive endpoint accepts `share_basis` (default `AGREED`) + per-advance `repayment_mode`.
- [ ] Serializer + view + url tests. Commit.

### Task 11-13 (with founder)
- [ ] T-11 Receive wizard "shares" step: Path 2 (default) / Path 1 toggle; on gap show debtor/amount + repayment-mode toggle. (`ReceiveBatchConfirmSheet.vue`)
- [ ] T-12 Agreement detail "Взаиморасчёты сторон" block + settle modal.
- [ ] T-13 Close-with-debt notification → settle modal.

---

## Phase 6 — Reports + ADR + live run

### Task 14: reports reflect advances as obligation
- [ ] Advance shown as obligation, not profit; profit routed to settlement flagged. Tests on report summary serializer. Commit.

### Task 15: ADR + docs
- [ ] ADR in `partnerships`/`finance` domain docs + E14 checkboxes. Commit.

### Task 16: live end-to-end run (FOUNDER verifies)
- [ ] Full Path-2 receive → advance → settle (cash + from-profit) → reports, via live stack. Founder verifies the receive UI run.

---

## Self-Review notes
- Spec coverage: US-1..7 → Tasks 2-4 (US-1/2/3/7), 5-6 (US-4), 7 (US-5 close), 8 (reversal states), 6+modal (US-5 post-facto from-profit). ✓
- Sharia invariants (interest-free, principal-only, loss by agreed snapshot): enforced in Task 5 guards + formulas test (Phase 2 Task 4 / loss uses snapshot). No UI badges (per decision). ✓
- Open technical detail (exact GL accounts for creditor-side claim) resolved during Task 3 against Rule #13 role-correct equity accounts.
