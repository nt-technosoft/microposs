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
      currency: string
      planned_budget: string
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
  balances: Record<string, string>
  partners_count: number
  investor_names: string[]
  operator_names: string[]
  investor_shares: { capital_percent: number; profit_percent: number } | null
  procurements_count: number
  notes: string
}

export interface InvestmentAgreementDetail extends InvestmentAgreementListItem {
  loss_rule: string
  reconciliation_mode: 'FACTUAL' | 'AGREED'
  default_advance_repayment_mode: 'LUMP' | 'FROM_PROFIT'
  client_request_id: string | null
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
    role: string
    planned_capital_share: string
    planned_profit_share: string
    contributed_amount: string
    withdrawn_amount: string
    allocated_amount: string
    returned_amount: string
    available_amount: string
  }>
  history: Array<{
    id: string
    kind: string
    date: string
    title: string
    partner_id: number | null
    partner_name: string | null
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
  reconciliation_mode?: 'FACTUAL' | 'AGREED'
  default_advance_repayment_mode?: 'LUMP' | 'FROM_PROFIT'
  partners?: AgreementPartnerPayload[]
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
  default_advance_repayment_mode?: 'LUMP' | 'FROM_PROFIT'
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

export interface CapitalAdvanceRecord {
  id: number
  agreement: number
  batch: number
  debtor: number
  debtor_name: string
  creditor: number | null
  creditor_name: string
  principal: string
  currency: string
  repayment_mode: 'LUMP' | 'FROM_PROFIT'
  status: 'OUTSTANDING' | 'PARTIAL' | 'SETTLED' | 'CANCELLED'
  outstanding_balance: string
  settled_amount: string
}

export interface AdvanceSettlePayload {
  advance_id: number
  amount: string
  source: 'CASH' | 'FROM_PROFIT'
  from_account_id?: number | null
  client_request_id?: string
}

export async function fetchAgreementAdvances(id: number): Promise<CapitalAdvanceRecord[]> {
  const { data } = await api.get<CapitalAdvanceRecord[]>(`/api/v1/partnerships/agreements/${id}/advances/`)
  return Array.isArray(data) ? data : (data as { results?: CapitalAdvanceRecord[] }).results ?? []
}

export async function settleAgreementAdvance(
  id: number,
  payload: AdvanceSettlePayload,
): Promise<CapitalAdvanceRecord> {
  const { data } = await api.post<CapitalAdvanceRecord>(
    `/api/v1/partnerships/agreements/${id}/settle-advance/`,
    payload,
  )
  return data
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
