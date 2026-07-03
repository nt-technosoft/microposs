import api from './client'

export type WorkspaceStatus = 'OPEN' | 'PARTIALLY_RECEIVED' | 'RECEIVED' | 'CLOSED' | 'CANCELLED'
export type WorkspaceFundingSource = 'OWN_FUNDS' | 'PARTNERSHIP'
export type WorkspaceSettlementType = 'PREPAID' | 'AT_RECEIPT' | 'PARTIAL' | 'DEFERRED' | 'INSTALLMENT' | 'ON_SALE'
export type WorkspaceSectionKey = 'overview' | 'source' | 'items' | 'settlement' | 'capital' | 'receive' | 'history'
export type WorkspaceFlowStepKey =
  | 'purchase_intent'
  | 'supplier_settlement'
  | 'funding'
  | 'payment_obligation'
  | 'goods_receipt'
  | 'history'
export type WorkspaceActionKey =
  | 'UPDATE_SOURCE'
  | 'UPDATE_ITEMS'
  | 'UPDATE_EXPENSES'
  | 'SPLIT_ITEM'
  | 'UPDATE_SETTLEMENT'
  | 'CREATE_INVESTMENT_AGREEMENT'
  | 'LINK_INVESTMENT_AGREEMENT'
  | 'RECORD_CAPITAL_CONTRIBUTION'
  | 'ALLOCATE_CAPITAL'
  | 'CONVERT_CAPITAL_POOL'
  | 'PAY_COSTS'
  | 'RESOLVE_OVERPAYMENT'
  | 'PAY_SUPPLIER_PAYABLE'
  | 'GENERATE_INSTALLMENT_SCHEDULE'
  | 'RECEIVE_BATCH'
  | 'AMEND_ITEMS'
  | 'AMEND_EXPENSES'
  | 'REVERSE_BATCH'
  | 'VIEW_HISTORY'
  | 'AMEND_SETTLEMENT'
  | 'RETURN_CONSIGNMENT'
  | 'CLOSE_WORKSPACE'
  | 'CANCEL_WORKSPACE'

export interface WorkspaceReadinessState {
  ok: boolean
  severity: 'ok' | 'info' | 'warning' | 'blocked'
  message: string | null
  missing: string[]
}

export interface ProcurementWorkspacePayload {
  id: number
  status: WorkspaceStatus
  display: {
    title: string
    subtitle: string | null
    created_at: string
    updated_at: string
    primary_currency: string
    next_action: {
      key: WorkspaceActionKey | string | null
      label: string | null
      reason: string | null
    }
  }
  flow: {
    current_step: WorkspaceFlowStepKey
    next_action: WorkspaceActionKey | string | null
    steps: Array<{
      key: WorkspaceFlowStepKey
      title: string
      status: 'ready' | 'blocked' | 'complete' | 'locked'
      readiness_keys: string[]
      primary_actions: Array<WorkspaceActionKey | string>
      blocked_reason: string | null
    }>
  }
  policy: {
    funding_source: WorkspaceFundingSource | string | null
    settlement_type: WorkspaceSettlementType | string | null
    allowed_settlements: Array<WorkspaceSettlementType | string>
    visible_sections: WorkspaceSectionKey[]
    locked_sections: Record<string, string | null>
    allowed_actions: Array<WorkspaceActionKey | string>
    blocked_reasons: Array<{ code: string; message: string }>
  }
  readiness: Record<string, WorkspaceReadinessState>
  sections: Array<{
    key: WorkspaceSectionKey
    title: string
    visible: boolean
    locked: boolean
    locked_reason: string | null
    readiness_key: string | null
  }>
  documents: {
    procurement: {
      id: number
      status: WorkspaceStatus
      primary_currency: string
      supplier_id: number | null
      supplier_name: string | null
      notes: string
      opened_at: string
      closed_at: string | null
    }
    source: {
      funding_source: WorkspaceFundingSource | string | null
      supplier_required: boolean
      supplier_id: number | null
      investment_agreement_required: boolean
      investment_agreement_id: number | null
    }
    items: Array<{
      id: number
      product_variant_id: number
      product_variant_name: string
      quantity: string
      unit_purchase_price: string
      currency: string
      fx_rate: string
      lifecycle_state: string
      payment_state: string
      received_quantity: string
      remaining_quantity: string
      locked_reason: string | null
      goods_ownership: 'OWNED' | 'CONSIGNED'
      estimated_allocated_expense_uzs?: string
      estimated_landed_cost_per_unit_uzs?: string
      estimated_landed_cost_per_unit?: string
      actual_allocated_expense_uzs?: string
      actual_landed_cost_per_unit_uzs?: string
      actual_landed_cost_per_unit?: string
    }>
    expenses: Array<{
      id: number
      expense_type: string
      amount: string
      currency: string
      fx_rate: string
      allocation_method: string
      target_item_ids: number[]
      lifecycle_state: string
      payment_state: string
      locked_reason: string | null
    }>
    settlement: {
      id: number
      type: WorkspaceSettlementType | string
      currency_of_obligation: string
      fx_rate_at_obligation: string
      total_amount_due: string
      paid_amount: string
      remaining_amount: string
      deadline_date: string | null
      consignment_mode: string | null
      notes: string
      schedule: Array<{
        id: number
        sequence_number: number
        due_date: string
        amount: string
        currency: string
        status: string
        paid_at: string | null
        paid_amount: string
      }>
    } | null
    payables: Array<{
      id: number
      supplier_id: number
      supplier_name: string | null
      original_amount: string
      paid_amount: string
      remaining_amount: string
      currency: string
      status: string
      due_date: string | null
    }>
    payments: Array<{
      id: number
      target_type: string
      target_id: number
      source_type: string
      source_id: number
      amount: string
      currency: string
      fx_rate: string
      status: string
      paid_at: string
      journal_entry_id: number | null
    }>
    payment_status: {
      obligation_by_currency: Record<string, string>
      paid_by_currency: Record<string, string>
      remaining_by_currency: Record<string, string>
      state: 'unpaid' | 'underpaid' | 'paid_full' | 'overpaid'
      // backward-compat single-currency fields (null when mixed currency)
      obligation_amount: string | null
      paid_amount: string | null
      delta: string | null
      currency: string | null
    }
    investment: {
      agreement_id: number
      agreement_label: string
      opened_at: string
      legal_mode: string | null
      reconciliation_mode: 'FACTUAL' | 'AGREED'
      currency: string
      planned_budget: string
      investor_shares: InvestorPoolShares | null
      pool: {
        cash_account_id: number
        currency: string
        balance: string
      } | null
      currency_pools: Array<{
        currency: string
        cash_account_id: number
        balance: string
        is_base: boolean
      }>
      partners: Array<{
        partner_id: number
        partner_name: string
        role: string
        planned_capital_share: string
        profit_share: string
      }>
      contributions: Array<{
        id: number
        partner_id: number
        amount: string
        currency: string
        fx_rate: string
        date: string
        notes: string
      }>
      allocations: Array<{
        id: number
        procurement_id: number
        partner_id: number
        direction: string
        amount: string
        currency: string
        fx_rate: string
        date: string
        notes: string
      }>
      available_by_partner: Record<string, Record<string, string>>
    } | null
    receive_batches: Array<{
      id: number
      received_at: string
      warehouse_id: number
      warehouse_name: string
      status: string
      inventory_total_uzs: string
      lines: Array<{
        id: number
        item_id: number
        lot_id: number
        product_variant_id: number
        product_variant_name: string
        quantity: string
        quantity_planned: string
        quantity_received: string
        discrepancy_reason: string
        unit_purchase_price_uzs: string
        allocated_expense_uzs: string
        landed_cost_per_unit_uzs: string
      }>
      expenses: Array<{
        id: number
        expense_id: number
        expense_type: string
        allocated_amount_uzs: string
      }>
      capital_snapshot: unknown | null
      journal_entry_id: number | null
    }>
    lots_preview: unknown[]
  }
  summaries: {
    items_total_uzs: string
    expenses_total_uzs: string
    payables_total: string
    receive_batches_count: number
  }
  history: Array<{
    kind: string
    date: string
    title: string
    document_id: number
    reason?: string
  }>
}

export interface ProcurementWorkspaceCreatePayload {
  funding_source?: WorkspaceFundingSource
  primary_currency?: string
  supplier_id?: number | null
  investment_agreement_id?: number | null
  agreement_id?: number | null
  notes?: string
  client_request_id?: string
}

export async function fetchProcurementWorkspaces(params?: {
  status?: string
  funding_source?: string
}, signal?: AbortSignal): Promise<ProcurementWorkspacePayload[]> {
  const { data } = await api.get<ProcurementWorkspacePayload[] | { results?: ProcurementWorkspacePayload[] }>(
    '/api/v1/procurement-workspaces/',
    { params, signal },
  )
  return Array.isArray(data) ? data : data.results ?? []
}

export async function fetchProcurementWorkspace(
  id: number,
  signal?: AbortSignal,
): Promise<ProcurementWorkspacePayload> {
  const { data } = await api.get<ProcurementWorkspacePayload>(`/api/v1/procurement-workspaces/${id}/`, { signal })
  return data
}

export async function createProcurementWorkspace(
  payload: ProcurementWorkspaceCreatePayload,
): Promise<ProcurementWorkspacePayload> {
  const { data } = await api.post<ProcurementWorkspacePayload>('/api/v1/procurement-workspaces/', payload)
  return data
}

export async function runProcurementWorkspaceAction<TPayload extends Record<string, unknown>>(
  id: number,
  action: WorkspaceActionKey,
  payload: TPayload,
): Promise<ProcurementWorkspacePayload> {
  const { data } = await api.post<ProcurementWorkspacePayload>(
    `/api/v1/procurement-workspaces/${id}/actions/${action}/`,
    {
      client_request_id: crypto.randomUUID(),
      payload,
    },
  )
  return data
}

export interface ProcurementListItem {
  id: number
  procurement_type: string
  status: string
  opened_at: string
  received_at: string | null
  supplier: number | null
  supplier_name: string | null
  agreement: number | null
  agreement_label: string | null
  items_count: number
  is_receive_ready: boolean
  receive_status: string
  receive_message: string
  total_amount: string
  notes: string
}

export interface ProcurementDetail {
  id: number
  procurement_type: string
  status: string
  opened_at: string
  received_at: string | null
  closed_at: string | null
  supplier: number | null
  supplier_name: string | null
  agreement: number | null
  agreement_label: string | null
  notes: string
  client_request_id: string | null
  items: Array<{
    id: number
    product_variant: number
    product_variant_name: string
    quantity: string
    unit_purchase_price: string
    currency: string
    fx_rate: string
    status: string
  }>
  expenses: Array<{
    id: number
    expense_type: string
    amount: string
    currency: string
    fx_rate: string
    allocation_method: string
    notes: string
    status: string
    target_item_ids: number[]
  }>
  contract: {
    id: number
    mudaraba_ratio: string
    loss_rule: string
    planned_budget: string
    currency: string
    partners: Array<{
      id: number
      partner: number
      partner_name: string
      role: string
      planned_capital_share: string
      profit_share: string
    }>
  } | null
  balance: {
    balances: Record<string, string>
    is_zero: boolean
    contributions: Array<{
      id: number
      partner: number
      partner_name: string
      partner_role: string
      amount: string
      currency: string
      fx_rate: string
      date: string
      notes: string
    }>
    withdrawals: Array<{
      id: number
      procurement?: number | null
      paid_from_account?: number | null
      partner: number | null
      partner_name: string | null
      partner_role: string | null
      amount: string
      currency: string
      fx_rate: string
      date: string
      reason: string
    }>
    participant_totals: Array<{
      partner_id: number
      partner_name: string
      role: string
      contract_currency: string
      planned_capital_share: string
      planned_profit_share: string
      contributed_amount: string
      withdrawn_amount: string
      net_capital: string
      actual_capital_share: string
    }>
    history: Array<{
      id: string
      kind: 'CONTRIBUTION' | 'WITHDRAWAL' | 'EXCHANGE'
      date: string
      title: string
      partner_id: number | null
      partner_name: string | null
      partner_role: string | null
      amount: string
      currency: string
      secondary_amount: string | null
      secondary_currency: string | null
      fx_rate: string
      note: string
    }>
    exchanges: Array<{
      id: number
      from_currency: string
      from_amount: string
      to_currency: string
      to_amount: string
      rate: string
      date: string
      notes: string
    }>
  }
  terms: {
    id: number
    type: string
    currency_of_obligation: string
    fx_rate_at_obligation: string
    total_amount_due: string
    paid_amount: string
    remaining_amount: string
    status: string
    deadline_date: string | null
    consignment_agreement: number | null
    notes: string
    schedule: Array<{
      id: number
      sequence_number: number
      due_date: string
      amount: string
      currency: string
      status: string
      paid_at: string | null
      paid_amount: string
    }>
  } | null
  receive_batches: ReceiveBatch[]
  receive_plan: ReceivePlan
  cost_preview: {
    message: string
    reallocation_pending: boolean
    receive_basis: {
      items_count: number
      expenses_count: number
      total_expenses_uzs: string
      lines: Array<{
        item_id: number
        product_variant_id: number
        product_variant_name: string
        status: string
        quantity: string
        unit_purchase_price_uzs: string
        allocated_expense_uzs: string
        landed_cost_per_unit_uzs: string
      }>
    }
    if_all_current_lines_paid: {
      items_count: number
      expenses_count: number
      total_expenses_uzs: string
      lines: Array<{
        item_id: number
        product_variant_id: number
        product_variant_name: string
        status: string
        quantity: string
        unit_purchase_price_uzs: string
        allocated_expense_uzs: string
        landed_cost_per_unit_uzs: string
      }>
    }
  }
}

export interface ReceivePlan {
  status: string
  message: string
  balances: Record<string, string>
  missing_spend: Record<string, string>
  received_items_count: number
  received_expenses_count: number
  pending_paid_items_count: number
  pending_paid_expenses_count: number
  draft_items_count: number
  draft_expenses_count: number
  pending_paid_items: Array<{
    id: number
    product_variant_id: number
    product_variant_name: string
    quantity: string
    unit_purchase_price: string
    currency: string
    fx_rate: string
    status: string
  }>
  receive_batches: ReceiveBatch[]
  will_finish_procurement: boolean
  batch_capital_preview: ReceiveBatchCapitalPreview | null
  suggested_withdrawals: Array<{
    partner_id: number
    partner_name: string
    currency: string
    amount: string
    target_net_capital: string
    actual_net_capital: string
  }>
}

export interface ReceiveBatchCapitalPreview {
  currency: string
  required_amount: string
  status: string
  message: string
  partners: Array<{
    partner_id: number
    partner_name: string
    role: string
    available_amount: string
    amount: string
    capital_share: string
    profit_share: string
  }>
}

export interface ReceiveCapitalAllocationPayload {
  partner_id: number
  amount: string | number
}

export interface ReceiveBatch {
  id: number
  warehouse: number
  warehouse_name: string
  received_at: string
  items_count: number
  total_inventory_uzs: string
  lines: Array<{
    id: number
    item: number
    lot: number
    product_variant_name: string
    quantity: string
    unit_purchase_price_uzs: string
    allocated_expense_uzs: string
    landed_cost_per_unit_uzs: string
  }>
  expenses: Array<{
    id: number
    expense: number
    expense_type: string
    allocated_amount_uzs: string
  }>
  capital_allocations: Array<{
    id: number
    partner: number
    partner_name: string
    role: string
    amount_contract_currency: string
    capital_share: string
    profit_share: string
  }>
}

export interface ProcurementLedger {
  procurement_id: number
  partners: Array<{
    id: number
    partner: number
    partner_name: string
    entries: Array<{
      id: number
      date: string
      amount: string
      currency: string
      entry_type: string
      source_ref: string
    }>
  }>
}

export interface ProcurementContributionPayload {
  partner_id: number
  amount: string | number
  currency?: string
  fx_rate?: string | number
  notes?: string
}

export interface ProcurementWithdrawalPayload {
  partner_id?: number | null
  procurement_id?: number | null
  from_account_id?: number | null
  amount: string | number
  currency?: string
  fx_rate?: string | number
  reason?: string
}

export interface ProcurementBalanceExchangePayload {
  from_currency: string
  from_amount: string | number
  to_currency: string
  rate: string | number
  notes?: string
}

export interface AgreementPartnerPayload {
  partner_id: number
  role: string
  planned_capital_share: string | number
  profit_share: string | number
}

export interface InvestorPoolShares {
  capital_amount: string
  profit_share: string
  capital_percent: number
  profit_percent: number
  investors_count: number
}

export interface InvestmentAgreementListItem {
  id: number
  status: string
  opened_at: string
  closed_at: string | null
  supplier: number | null
  supplier_name: string | null
  planned_budget: string
  currency: string
  mudaraba_ratio: string
  reconciliation_mode?: 'FACTUAL' | 'AGREED'
  balances: Record<string, string>
  partners_count: number
  investor_names: string[]
  operator_names: string[]
  investor_shares: InvestorPoolShares | null
  procurements_count: number
  notes: string
  current_terms?: number | AgreementTermsVersion | null
}

export interface PayoutPolicy {
  review_interval_days: number
  minimum_available_amount: string
  minimum_days_between_payouts: number
  reserve_amount: string
  grace_period_days: number
  allow_partial: boolean
}

export interface AgreementTermsVersion {
  id: number
  version: number
  effective_at: string
  review_at: string | null
  offline_agreed_at: string | null
  offline_agreement_reference: string
  notes: string
  payout_policy: PayoutPolicy
}

export interface InvestmentAgreementDetail extends InvestmentAgreementListItem {
  loss_rule: string
  reconciliation_mode: 'FACTUAL' | 'AGREED'
  client_request_id: string | null
  current_terms: AgreementTermsVersion | null
  partners: Array<{
    id: number
    partner: number
    partner_name: string
    role: string
    planned_capital_share: string
    profit_share: string
  }>
  commitments: Array<{
    id: number
    partner: number
    partner_name: string
    partner_role: string
    amount: string
    currency: string
    fx_rate: string
    fx_rate_source?: string
    fx_rate_date?: string | null
    date: string
    source: string
    confirmation_status: string
    created_by: number | null
    created_by_name: string
    actor_partner: number | null
    actor_partner_name: string | null
    notes: string
    client_request_id: string | null
  }>
  contributions: Array<{
    id: number
    partner: number
    partner_name: string
    partner_role: string
    amount: string
    currency: string
    fx_rate: string
    fx_rate_source?: string
    fx_rate_date?: string | null
    date: string
    source: string
    confirmation_status: string
    created_by: number | null
    created_by_name: string
    actor_partner: number | null
    actor_partner_name: string | null
    notes: string
    client_request_id: string | null
  }>
  withdrawals: Array<{
    id: number
    procurement: number | null
    paid_from_account: number | null
    partner: number
    partner_name: string
    partner_role: string
    amount: string
    currency: string
    fx_rate: string
    date: string
    source: string
    confirmation_status: string
    created_by: number | null
    created_by_name: string
    actor_partner: number | null
    actor_partner_name: string | null
    reason: string
    client_request_id: string | null
  }>
  allocations: Array<{
    id: number
    procurement: number
    partner: number
    partner_name: string
    partner_role: string
    direction: string
    amount: string
    currency: string
    fx_rate: string
    date: string
    source: string
    confirmation_status: string
    created_by: number | null
    created_by_name: string
    actor_partner: number | null
    actor_partner_name: string | null
    notes: string
    client_request_id: string | null
  }>
  events: Array<{
    id: number
    event_type: string
    occurred_at: string
    actor_user: number | null
    actor_user_name: string
    actor_partner: number | null
    actor_partner_name: string | null
    source: string
    related_model: string
    related_id: number | null
    payload: Record<string, unknown>
  }>
  procurements: ProcurementListItem[]
  participant_totals: Array<{
    partner_id: number
    partner_name: string
    display_name?: string
    role: string
    planned_capital_share: string
    planned_profit_share: string
    contributed_amount: string
    gross_contributed_amount?: string
    withdrawn_amount: string
    pool_withdrawn_amount?: string
    proceeds_withdrawn_amount?: string
    allocated_amount: string
    returned_amount: string
    available_amount: string
    withdrawable_amount?: string
  }>
  history: Array<{
    id: string
    kind: string
    return_kind?: 'FROM_POOL' | 'FROM_PROCEEDS'
    date: string
    title: string
    partner_id: number | null
    partner_name: string | null
    display_name?: string | null
    partner_role: string | null
    amount: string
    currency: string
    procurement_id: number | null
    note: string
  }>
}

export interface InvestmentAgreementCreatePayload {
  client_request_id?: string
  supplier_id?: number | null
  mudaraba_ratio?: string | number
  planned_budget?: string | number
  investor_partner_id?: number
  investor_planned_amount?: string | number
  investor_capital_percent?: string | number
  investor_profit_percent?: string | number
  currency?: string
  notes?: string
  review_at?: string | null
  offline_agreed_at?: string | null
  offline_agreement_reference?: string
  payout_policy?: Partial<PayoutPolicy>
  reconciliation_mode?: 'FACTUAL' | 'AGREED'
  partners?: AgreementPartnerPayload[]
}

export interface PayoutObligation {
  id: number
  agreement: number | null
  fund: number | null
  recipient: number
  recipient_name: string
  procurement: number | null
  kind: 'PROFIT' | 'CAPITAL_RETURN'
  amount: string
  paid_amount: string
  currency: string
  due_at: string
  status: 'PENDING' | 'RECORDED' | 'CONFIRMED' | 'DISPUTED' | 'WAIVED'
  recorded_at: string | null
  confirmed_at: string | null
  dividend_payment: number | null
  capital_withdrawal: number | null
  notes: string
  settlements: Array<{
    id: number
    amount: string
    settled_at: string
    evidence: string
    dividend_payment: number | null
    capital_withdrawal: number | null
  }>
}

export interface FundMemberPosition {
  id: number
  member: number
  partner: number
  partner_name: string
  currency: string
  capital_share: string
  paid_in: string
  deployed: string
  available: string
  provisional_profit_uzs: string
  capital_return_available_uzs: string
  profit_available_uzs: string
  manager_fee_accrued_uzs: string
  computed_at: string
}

export interface FundApplication {
  id: number
  fund: number
  partner: number
  partner_name: string
  requested_amount: string
  approved_amount: string
  currency: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED'
  message: string
  decided_at: string | null
  decided_by: number | null
  created_at: string
}

export interface FundApplicationApprovalPreview {
  fund_id: number
  currency: string
  target_amount: string | null
  active_approved_amount: string
  batch_approved_amount: string
  after_approved_amount: string
  exceeds_target: boolean
  rows: Array<{
    application_id: number
    partner_id: number
    partner_name: string
    requested_amount: string
    approved_amount: string
    currency: string
  }>
}

export interface InvestmentFund {
  id: number
  name: string
  status: 'DRAFT' | 'RAISING' | 'DEPLOYED' | 'CLOSED'
  visibility: 'PRIVATE_INVITE' | 'PUBLIC_LISTING'
  invite_token: string | null
  invite_path: string
  manager_partner: number
  manager_partner_name: string
  holder_partner: number
  holder_partner_name: string
  capital_account: number
  currency: string
  target_amount: string | null
  min_contribution_amount: string
  opened_at: string
  closed_at: string | null
  current_terms: (AgreementTermsVersion & { manager_profit_share: string }) | null
  members: Array<{ id: number; partner: number; partner_name: string; status: 'ACTIVE' | 'EXITED' | 'REMOVED'; approved_amount: string; confirmed_amount: string; joined_at: string; exited_at: string | null }>
  applications: FundApplication[]
  contributions: Array<{ id: number; member: number; partner: number; partner_name: string; amount: string; currency: string; date: string }>
  deployments: Array<{ id: number; agreement: number; agreement_label: string; agreement_contribution: number; amount: string; currency: string; date: string }>
  member_exits: Array<{ id: number; member: number; partner: number; partner_name: string; reason: string; refund_amount: string; currency: string; refunded_at: string }>
  positions: FundMemberPosition[]
  position: {
    currency: string
    paid_in: string
    deployed: string
    available: string
    provisional_profit_uzs: string
    capital_return_available_uzs: string
    profit_available_uzs: string
    manager_fee_accrued_uzs: string
    computed_at: string
  } | null
}

export interface AgreementAllocationPreview {
  agreement_id: number
  procurement_id: number
  required: Record<string, string>
  agreement_balances: Record<string, string>
  suggestions: Array<{
    partner_id: number
    partner_name: string
    role: string
    currency: string
    available: string
    target_amount: string
    amount: string
  }>
}

export interface ProcurementContractPayload {
  mudaraba_ratio: string
  planned_budget: string
  currency: string
  reconciliation_mode?: 'FACTUAL' | 'AGREED'
  partners: Array<{
    partner_id: number
    role: string
    planned_capital_share: string
    profit_share: string
  }>
}

export interface ProcurementUpsertPayload {
  client_request_id?: string
  procurement_type: string
  supplier_id?: number | null
  agreement_id?: number | null
  notes?: string
  items?: Array<{
    id?: number
    product_variant_id: number
    quantity: number
    unit_purchase_price: number
    currency?: string
    fx_rate?: string
    goods_ownership?: 'OWNED' | 'CONSIGNED'
  }>
  expenses?: Array<{
    id?: number
    expense_type: string
    amount: number
    currency?: string
    fx_rate?: string
    allocation_method?: string
    notes?: string
    target_item_ids?: number[]
  }>
  contract?: ProcurementContractPayload
  terms?: {
    type: string
    currency_of_obligation?: string
    fx_rate_at_obligation?: string | number
    total_amount_due: string | number
    paid_amount?: string | number
    deadline_date?: string | null
    consignment_agreement_id?: number | null
    notes?: string
  } | null
  schedule?: Array<{
    sequence_number?: number
    due_date: string
    amount: string | number
    currency?: string
  }>
}

export interface CapitalPositionRow {
  partner_id: number
  partner_name: string
  role: string
  deployed: string
  paid_in: string
  net: string
  owed: string
  withdrawable: string
  deployed_uzs?: string
  capital_recovered_uzs?: string
  remaining_inventory_capital_uzs?: string
  liability_capital_recovered_uzs?: string
  provisional_profit_uzs?: string
  loss_uzs?: string
  partner_liability_loss_uzs?: string
  capital_returned_uzs?: string
  dividends_paid_uzs?: string
  capital_return_available_uzs?: string
  provisional_profit_available_uzs?: string
  negative_position_uzs?: string
  currency: string
}

export interface ProcurementVenturePosition {
  partner_id: number
  partner_name: string
  role: string
  deployed_uzs: string
  capital_recovered_uzs: string
  remaining_inventory_capital_uzs: string
  liability_capital_recovered_uzs: string
  provisional_profit_uzs: string
  loss_uzs: string
  partner_liability_loss_uzs: string
  capital_returned_uzs: string
  dividends_paid_uzs: string
  capital_return_available_uzs: string
  provisional_profit_available_uzs: string
  negative_position_uzs: string
}

export interface ProcurementVentureSummary {
  procurement_id: number
  agreement_id: number | null
  currency: 'UZS' | string
  positions: ProcurementVenturePosition[]
  totals: Omit<ProcurementVenturePosition, 'partner_id' | 'partner_name' | 'role'>
  has_active_lots?: boolean
  audit_warnings?: Array<{
    code: string
    message: string
    line_ids?: number[]
  }>
}

export interface AgreementVentureSummary {
  agreement_id: number
  currency: 'UZS' | string
  positions: ProcurementVenturePosition[]
  procurements: Array<{
    procurement_id: number
    status: string
    capital_return_available_uzs: string
  }>
}

export interface AgreementPayoutPreview {
  allowed: boolean
  payout_type: 'CAPITAL_RETURN' | 'PROFIT' | string
  partner_id: number | null
  procurement_id: number | null
  amount: string
  currency: string
  fx_rate: string
  fx_rate_source: string
  fx_rate_date: string | null
  functional_amount_uzs: string
  available_uzs: string
  blocking_reasons: string[]
}

export interface ProcurementVentureSettlement {
  id: number
  procurement_id: number
  settlement_type: 'CONSTRUCTIVE' | 'FINAL'
  settled_at: string
  inventory_value_uzs: string
  reserve_uzs: string
  totals: Record<string, string>
  partner_positions: Record<string, Record<string, string>>
  notes: string
}

export interface SettlePartnerCapitalPayload {
  partner_id: number
  amount: string
  source: 'CASH' | 'FROM_PROFIT'
  from_account_id?: number | null
  client_request_id?: string
}

export async function fetchCapitalPositions(id: number): Promise<CapitalPositionRow[]> {
  const { data } = await api.get<CapitalPositionRow[]>(`/api/v1/partnerships/agreements/${id}/capital-positions/`)
  return Array.isArray(data) ? data : (data as { results?: CapitalPositionRow[] }).results ?? []
}

export async function settlePartnerCapital(
  id: number,
  payload: SettlePartnerCapitalPayload,
): Promise<CapitalPositionRow[]> {
  const { data } = await api.post<CapitalPositionRow[]>(
    `/api/v1/partnerships/agreements/${id}/settle-partner-capital/`,
    payload,
  )
  return Array.isArray(data) ? data : (data as { results?: CapitalPositionRow[] }).results ?? []
}

export interface AgreementProfitRow {
  procurement_id: number
  partner_id: number
  partner_name: string
  role: string
  pending: string
}

export interface PayDividendPayload {
  partner_id: number
  procurement_id: number
  amount: string
  currency?: string
  paid_from_account_id: number
}

export async function fetchAgreementProfitSummary(id: number): Promise<AgreementProfitRow[]> {
  const { data } = await api.get<AgreementProfitRow[]>(`/api/v1/partnerships/agreements/${id}/profit-summary/`)
  return Array.isArray(data) ? data : (data as { results?: AgreementProfitRow[] }).results ?? []
}

export async function payDividend(payload: PayDividendPayload): Promise<{ id: number; amount: string }> {
  const { data } = await api.post('/api/v1/partnerships/dividends/', payload)
  return data
}

export async function fetchInvestmentAgreements(): Promise<InvestmentAgreementListItem[]> {
  const { data } = await api.get<InvestmentAgreementListItem[]>('/api/v1/partnerships/agreements/')
  return Array.isArray(data) ? data : (data as { results?: InvestmentAgreementListItem[] }).results ?? []
}

export async function fetchInvestmentAgreement(id: number): Promise<InvestmentAgreementDetail> {
  const { data } = await api.get<InvestmentAgreementDetail>(`/api/v1/partnerships/agreements/${id}/`)
  return data
}

export async function createInvestmentAgreement(payload: InvestmentAgreementCreatePayload): Promise<InvestmentAgreementDetail> {
  const { data } = await api.post<InvestmentAgreementDetail>('/api/v1/partnerships/agreements/', payload)
  return data
}

export async function fetchInvestmentFunds(): Promise<InvestmentFund[]> {
  const { data } = await api.get<InvestmentFund[]>('/api/v1/partnerships/funds/')
  return Array.isArray(data) ? data : (data as { results?: InvestmentFund[] }).results ?? []
}

export async function fetchInvestmentFund(id: number): Promise<InvestmentFund> {
  const { data } = await api.get<InvestmentFund>(`/api/v1/partnerships/funds/${id}/`)
  return data
}

export interface PartnershipActionQueueItem {
  id: string
  kind: 'FUND_APPLICATION' | 'PAYOUT_OBLIGATION' | 'CONTRACT_REVIEW' | 'DISPUTE'
  fund_id: number | null
  agreement_id?: number | null
  title: string
  subtitle: string
  created_at: string
}

export async function fetchPartnershipActionQueue(): Promise<PartnershipActionQueueItem[]> {
  const { data } = await api.get<PartnershipActionQueueItem[]>('/api/v1/partnerships/funds/action-queue/')
  return data
}

export async function createInvestmentFund(payload: {
  name: string
  manager_partner_id: number
  member_partner_ids?: number[]
  currency?: string
  target_amount?: string | number | null
  min_contribution_amount?: string | number
  visibility?: 'PRIVATE_INVITE' | 'PUBLIC_LISTING'
  manager_profit_share?: string | number
  review_at?: string | null
  offline_agreed_at?: string | null
  offline_agreement_reference?: string
  notes?: string
  payout_policy?: Partial<PayoutPolicy>
}): Promise<InvestmentFund> {
  const { data } = await api.post<InvestmentFund>('/api/v1/partnerships/funds/', payload)
  return data
}

export async function fetchInvestmentFundByInvite(token: string): Promise<InvestmentFund> {
  const { data } = await api.get<InvestmentFund>(`/api/v1/partnerships/funds/by-invite/${token}/`)
  return data
}

export async function submitFundApplication(id: number, payload: {
  partner_id: number
  requested_amount: string | number
  message?: string
}): Promise<FundApplication> {
  const { data } = await api.post<FundApplication>(`/api/v1/partnerships/funds/${id}/applications/`, payload)
  return data
}

export async function approveFundApplication(id: number, applicationId: number, payload: {
  approved_amount?: string | number | null
} = {}): Promise<FundApplication> {
  const { data } = await api.post<FundApplication>(`/api/v1/partnerships/funds/${id}/applications/${applicationId}/approve/`, payload)
  return data
}

export async function rejectFundApplication(id: number, applicationId: number): Promise<FundApplication> {
  const { data } = await api.post<FundApplication>(`/api/v1/partnerships/funds/${id}/applications/${applicationId}/reject/`)
  return data
}

export async function previewFundApplicationApprovals(id: number, payload: {
  approvals: Array<{ application_id: number; approved_amount?: string | number | null }>
}): Promise<FundApplicationApprovalPreview> {
  const { data } = await api.post<FundApplicationApprovalPreview>(`/api/v1/partnerships/funds/${id}/applications/approval-preview/`, payload)
  return data
}

export async function amendFundTerms(id: number, payload: {
  target_amount?: string | number | null
  min_contribution_amount?: string | number | null
  visibility?: 'PRIVATE_INVITE' | 'PUBLIC_LISTING' | null
  manager_profit_share?: string | number | null
  review_at?: string | null
  offline_agreed_at?: string | null
  offline_agreement_reference?: string
  notes?: string
  payout_policy?: Partial<PayoutPolicy>
}): Promise<AgreementTermsVersion & { manager_profit_share: string }> {
  const { data } = await api.post<AgreementTermsVersion & { manager_profit_share: string }>(`/api/v1/partnerships/funds/${id}/terms/`, payload)
  return data
}

export async function exitFundMember(id: number, payload: {
  partner_id: number
  reason: 'MEMBER_EXIT' | 'MANAGER_REMOVE'
  notes?: string
  client_request_id?: string
}): Promise<InvestmentFund['member_exits'][number]> {
  const { data } = await api.post<InvestmentFund['member_exits'][number]>(`/api/v1/partnerships/funds/${id}/member-exits/`, payload)
  return data
}

export async function addFundContribution(id: number, payload: {
  partner_id: number
  amount: string | number
  currency?: string
  fx_rate?: string | number | null
  from_cash_account_id?: number | null
  notes?: string
  client_request_id?: string
}): Promise<InvestmentFund['contributions'][number]> {
  const { data } = await api.post(`/api/v1/partnerships/funds/${id}/contributions/`, payload)
  return data
}

export async function deployFund(id: number, payload: {
  agreement_id: number
  amount: string | number
  notes?: string
  client_request_id?: string
}): Promise<InvestmentFund['deployments'][number]> {
  const { data } = await api.post(`/api/v1/partnerships/funds/${id}/deployments/`, payload)
  return data
}

export async function evaluateAgreementPayouts(id: number): Promise<PayoutObligation[]> {
  const { data } = await api.post<PayoutObligation[]>(`/api/v1/partnerships/agreements/${id}/evaluate-payouts/`)
  return data
}

export async function fetchAgreementPayoutObligations(id: number): Promise<PayoutObligation[]> {
  const { data } = await api.get<PayoutObligation[]>(`/api/v1/partnerships/agreements/${id}/payout-obligations/`)
  return data
}

export async function evaluateFundPayouts(id: number): Promise<PayoutObligation[]> {
  const { data } = await api.post<PayoutObligation[]>(`/api/v1/partnerships/funds/${id}/evaluate-payouts/`)
  return data
}

export async function fetchFundPayoutObligations(id: number): Promise<PayoutObligation[]> {
  const { data } = await api.get<PayoutObligation[]>(`/api/v1/partnerships/funds/${id}/payout-obligations/`)
  return data
}

export async function recordFundPayout(id: number, payload: {
  amount: string | number
  evidence?: string
  notes?: string
}): Promise<PayoutObligation> {
  const { data } = await api.post<PayoutObligation>(`/api/v1/partnerships/payout-obligations/${id}/record/`, payload)
  return data
}

export async function confirmFundPayout(id: number): Promise<PayoutObligation> {
  const { data } = await api.post<PayoutObligation>(`/api/v1/partnerships/payout-obligations/${id}/confirm/`)
  return data
}

export type ContractReviewResolution = 'CONTINUE' | 'ORDERLY_SALE' | 'WRITE_OFF' | 'BUYOUT' | 'DISPUTE'

export async function resolveAgreementReview(id: number, payload: {
  resolution: ContractReviewResolution
  notes?: string
  extension_until?: string | null
}): Promise<unknown> {
  const { data } = await api.post(`/api/v1/partnerships/agreements/${id}/review/`, payload)
  return data
}

export async function resolveFundReview(id: number, payload: {
  resolution: ContractReviewResolution
  notes?: string
  extension_until?: string | null
}): Promise<unknown> {
  const { data } = await api.post(`/api/v1/partnerships/funds/${id}/review/`, payload)
  return data
}

export async function addAgreementContribution(
  id: number,
  payload: ProcurementContributionPayload,
): Promise<InvestmentAgreementDetail['contributions'][number]> {
  const { data } = await api.post(`/api/v1/partnerships/agreements/${id}/contributions/`, payload)
  return data
}

export async function addAgreementWithdrawal(
  id: number,
  payload: Required<Pick<ProcurementWithdrawalPayload, 'partner_id'>> & ProcurementWithdrawalPayload,
): Promise<InvestmentAgreementDetail['withdrawals'][number]> {
  const { data } = await api.post(`/api/v1/partnerships/agreements/${id}/withdrawals/`, payload)
  return data
}

export async function fetchAgreementAllocationPreview(id: number, procurementId: number): Promise<AgreementAllocationPreview> {
  const { data } = await api.get<AgreementAllocationPreview>(
    `/api/v1/partnerships/agreements/${id}/allocation-preview/`,
    { params: { procurement_id: procurementId } },
  )
  return data
}

export async function createAgreementAllocations(
  id: number,
  payload: {
    procurement_id: number
    allocations: Array<{ partner_id: number; amount: string | number; currency?: string; fx_rate?: string | number; notes?: string }>
  },
): Promise<InvestmentAgreementDetail['allocations']> {
  const { data } = await api.post(`/api/v1/partnerships/agreements/${id}/allocations/`, payload)
  return data
}

export async function fetchProcurements(params?: {
  status?: string
  procurement_type?: string
}): Promise<ProcurementListItem[]> {
  const { data } = await api.get<ProcurementListItem[]>('/api/v1/partnerships/procurements/', { params })
  return Array.isArray(data) ? data : (data as { results?: ProcurementListItem[] }).results ?? []
}

export async function fetchProcurement(id: number): Promise<ProcurementDetail> {
  const { data } = await api.get<ProcurementDetail>(`/api/v1/partnerships/procurements/${id}/`)
  return data
}

export async function fetchProcurementVentureSummary(id: number): Promise<ProcurementVentureSummary> {
  const { data } = await api.get<ProcurementVentureSummary>(
    `/api/v1/partnerships/procurements/${id}/venture-summary/`,
  )
  return data
}

export async function fetchAgreementVentureSummary(id: number): Promise<AgreementVentureSummary> {
  const { data } = await api.get<AgreementVentureSummary>(
    `/api/v1/partnerships/agreements/${id}/venture-summary/`,
  )
  return data
}

// E17 close lifecycle — derived read-model (gates live on the backend).
export interface ClosePreview {
  status: string
  show_close: boolean
  closeable: boolean
  blocking_reasons: string[]
}

export async function fetchProcurementClosePreview(id: number): Promise<ClosePreview> {
  const { data } = await api.get<ClosePreview>(`/api/v1/partnerships/procurements/${id}/close-preview/`)
  return data
}

export async function closeProcurement(id: number, clientRequestId?: string): Promise<unknown> {
  const { data } = await api.post(
    `/api/v1/partnerships/procurements/${id}/close/`,
    clientRequestId ? { client_request_id: clientRequestId } : {},
  )
  return data
}

export interface RepayVentureDebtPayload {
  partner_id: number
  amount: string
  currency?: string
  paid_to_account_id: number
  client_request_id?: string
}

export async function repayVentureDebt(procurementId: number, payload: RepayVentureDebtPayload): Promise<unknown> {
  const { data } = await api.post(`/api/v1/partnerships/procurements/${procurementId}/repay-debt/`, payload)
  return data
}

export async function fetchAgreementClosePreview(id: number): Promise<ClosePreview> {
  const { data } = await api.get<ClosePreview>(`/api/v1/partnerships/agreements/${id}/close-preview/`)
  return data
}

export async function closeAgreement(id: number, clientRequestId?: string): Promise<{ status: string; closed_at: string | null }> {
  const { data } = await api.post<{ status: string; closed_at: string | null }>(
    `/api/v1/partnerships/agreements/${id}/close/`,
    clientRequestId ? { client_request_id: clientRequestId } : {},
  )
  return data
}

export async function previewAgreementPayout(
  id: number,
  payload: {
    partner_id: number
    procurement_id?: number | null
    payout_type: 'CAPITAL_RETURN' | 'PROFIT'
    amount: string | number
    currency?: string
    fx_rate?: string | number
    from_account_id?: number | null
  },
): Promise<AgreementPayoutPreview> {
  const { data } = await api.post<AgreementPayoutPreview>(
    `/api/v1/partnerships/agreements/${id}/payout-preview/`,
    payload,
  )
  return data
}

export async function createProcurementVentureSettlement(
  id: number,
  payload: {
    settlement_type: 'CONSTRUCTIVE' | 'FINAL'
    inventory_value_uzs?: string
    reserve_uzs?: string
    notes?: string
    client_request_id?: string
  },
): Promise<ProcurementVentureSettlement> {
  const { data } = await api.post<ProcurementVentureSettlement>(
    `/api/v1/partnerships/procurements/${id}/venture-settlements/`,
    payload,
  )
  return data
}

export async function receiveProcurement(
  id: number,
  destination_warehouse_id: number,
  item_ids?: number[],
  capital_allocations?: ReceiveCapitalAllocationPayload[],
  terms_payload?: Record<string, unknown> | null,
  schedule_payload?: Array<Record<string, unknown>>,
): Promise<ProcurementDetail & { items_count: number }> {
  const { data } = await api.post<ProcurementDetail & { items_count: number }>(
    `/api/v1/partnerships/procurements/${id}/receive/`,
    {
      destination_warehouse_id,
      ...(item_ids?.length ? { item_ids } : {}),
      ...(capital_allocations?.length ? { capital_allocations } : {}),
      ...(terms_payload ? { terms_payload } : {}),
      ...(schedule_payload?.length ? { schedule_payload } : {}),
    },
  )
  return data
}

export async function splitProcurementItem(
  id: number,
  payload: { item_id: number; quantity: string | number },
): Promise<ProcurementDetail> {
  const { data } = await api.post<ProcurementDetail>(`/api/v1/partnerships/procurements/${id}/split-item/`, payload)
  return data
}

export async function createConsignmentReturn(
  id: number,
  payload: {
    warehouse_id: number
    notes?: string
    client_request_id?: string
    lines: Array<{
      lot_id: number
      quantity: string | number
      disposition: 'RETURN_TO_SUPPLIER' | 'DISPOSE_SUPPLIER_LOSS' | 'DISPOSE_BUSINESS_LOSS' | 'CONVERT_TO_OWN'
      agreed_price_per_unit: string | number
      notes?: string
    }>
  },
): Promise<unknown> {
  const { data } = await api.post(`/api/v1/partnerships/procurements/${id}/consignment-return/`, payload)
  return data
}

export interface ProcurementTermsAmendment {
  id: number
  amended_at: string
  changed_by_user: number | null
  changed_by_user_name: string
  change_payload: {
    before?: Record<string, string>
    after?: Record<string, string>
  }
  reason: string
}

export async function fetchProcurementTermsAmendments(id: number): Promise<ProcurementTermsAmendment[]> {
  const { data } = await api.get<ProcurementTermsAmendment[]>(
    `/api/v1/partnerships/procurements/${id}/terms/amendments/`,
  )
  return data
}

export async function amendProcurementTerms(
  id: number,
  payload: { new_fields: Record<string, unknown>; reason?: string },
): Promise<{ amendment_id: number; change_payload: ProcurementTermsAmendment['change_payload']; amended_at: string }> {
  const { data } = await api.post(
    `/api/v1/partnerships/procurements/${id}/terms/amend/`,
    payload,
  )
  return data
}

export async function fetchProcurementLedger(id: number): Promise<ProcurementLedger> {
  const { data } = await api.get<ProcurementLedger>(`/api/v1/partnerships/procurements/${id}/ledger/`)
  return data
}

export async function fetchProcurementReceivePlan(id: number, item_ids?: number[]): Promise<ReceivePlan> {
  const { data } = await api.get<ReceivePlan>(
    `/api/v1/partnerships/procurements/${id}/receive-plan/`,
    { params: item_ids?.length ? { item_ids: item_ids.join(',') } : undefined },
  )
  return data
}

export async function addProcurementContribution(
  id: number,
  payload: ProcurementContributionPayload,
): Promise<{
  id: number
  partner: number
  amount: string
  currency: string
  fx_rate: string
  fx_rate_source?: string
  fx_rate_date?: string | null
  date: string
  notes: string
}> {
  const { data } = await api.post(`/api/v1/partnerships/procurements/${id}/contributions/`, payload)
  return data
}

export async function addProcurementWithdrawal(
  id: number,
  payload: ProcurementWithdrawalPayload,
): Promise<{
  id: number
  partner: number | null
  amount: string
  currency: string
  fx_rate: string
  fx_rate_source?: string
  fx_rate_date?: string | null
  date: string
  reason: string
}> {
  const { data } = await api.post(`/api/v1/partnerships/procurements/${id}/withdrawals/`, payload)
  return data
}

export async function createProcurementBalanceExchange(
  id: number,
  payload: ProcurementBalanceExchangePayload,
): Promise<{
  id: number
  from_currency: string
  from_amount: string
  to_currency: string
  to_amount: string
  rate: string
  date: string
  notes: string
}> {
  const { data } = await api.post(`/api/v1/partnerships/procurements/${id}/balance-exchanges/`, payload)
  return data
}

export async function createProcurement(payload: ProcurementUpsertPayload): Promise<ProcurementDetail> {
  const { data } = await api.post<ProcurementDetail>('/api/v1/partnerships/procurements/', payload)
  return data
}

export async function updateProcurement(id: number, payload: ProcurementUpsertPayload): Promise<ProcurementDetail> {
  const { data } = await api.put<ProcurementDetail>(`/api/v1/partnerships/procurements/${id}/`, payload)
  return data
}

export async function payProcurementItems(
  id: number,
  payload?: { item_ids?: number[]; reason?: string },
): Promise<{ count: number; status: string }> {
  const { data } = await api.post<{ count: number; status: string }>(`/api/v1/partnerships/procurements/${id}/pay-items/`, payload ?? {})
  return data
}

export async function updateProcurementExpenseTargets(
  id: number,
  payload: { expense_id: number; target_item_ids: number[] },
): Promise<ProcurementDetail['expenses'][number]> {
  const { data } = await api.post<ProcurementDetail['expenses'][number]>(
    `/api/v1/partnerships/procurements/${id}/expense-targets/`,
    payload,
  )
  return data
}

export async function payProcurementExpenses(
  id: number,
  payload?: { expense_ids?: number[]; reason?: string },
): Promise<{ count: number; status: string }> {
  const { data } = await api.post<{ count: number; status: string }>(`/api/v1/partnerships/procurements/${id}/pay-expenses/`, payload ?? {})
  return data
}
