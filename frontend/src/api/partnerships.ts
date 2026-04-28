import api from './client'

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
  procurements_count: number
  notes: string
}

export interface InvestmentAgreementDetail extends InvestmentAgreementListItem {
  loss_rule: string
  client_request_id: string | null
  partners: Array<{
    id: number
    partner: number
    partner_name: string
    role: string
    planned_capital_share: string
    profit_share: string
  }>
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
    partner: number
    partner_name: string
    partner_role: string
    amount: string
    currency: string
    fx_rate: string
    date: string
    reason: string
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
    notes: string
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
  mudaraba_ratio: string | number
  planned_budget: string | number
  currency?: string
  notes?: string
  partners: AgreementPartnerPayload[]
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
): Promise<ProcurementDetail & { items_count: number }> {
  const { data } = await api.post<ProcurementDetail & { items_count: number }>(
    `/api/v1/partnerships/procurements/${id}/receive/`,
    {
      destination_warehouse_id,
      ...(item_ids?.length ? { item_ids } : {}),
      ...(capital_allocations?.length ? { capital_allocations } : {}),
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
