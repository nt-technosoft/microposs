/**
 * Domain model interfaces matching backend models.
 */

import type {
  ReceiptType, ReceiptStatus, SaleStatus, PaymentMethod,
  PricingMode, ContractType, ContractStatus, RiskEventType,
  ReturnCondition,
} from './enums'

// === Base ===

export interface BaseModel {
  id: number
  created_at: string
  updated_at: string
}

export interface CurrencyTrace {
  operation_currency: string
  operation_amount: string | null
  fx_rate_snapshot: string | null
  functional_amount_uzs: string | null
}

// === Catalog ===

export interface Category extends BaseModel {
  name: string
  parent?: number | null
  parent_id?: number | null
  default_pricing_mode: PricingMode
  sort_order: number
  products_count?: number
  template_attributes?: CategoryAttributeTemplate[]
  template_characteristics?: CategoryCharacteristicTemplate[]
}

export interface CategoryAttributeTemplate {
  id: number
  category?: number
  attribute_id: number
  attribute_name?: string
  is_variant_generating: boolean
}

export interface CategoryCharacteristicTemplate {
  id: number
  category?: number
  name: string
  default_value: string
  sort_order: number
}

export interface AttributeValue {
  id: number
  value: string
  sort_order: number
}

export interface Attribute extends BaseModel {
  name: string
  values: AttributeValue[]
}

export interface ProductVariant extends BaseModel {
  product?: number
  product_id?: number
  product_name?: string
  category_id?: number | null
  category_name?: string | null
  sku: string
  display_sku?: string
  price: string | null
  effective_price: string
  is_active: boolean
  attribute_values: Array<{
    attribute_name: string
    value: string
  }>
  stock_quantity?: number
  total_stock_all_locations?: number
  stock_at_location?: number | null
  stock_by_location?: StockByLocation[]
  availability_state?: StockAvailabilityState
}

export type StockAvailabilityState = 'in_shop' | 'warehouse_only' | 'out_of_stock'

export interface StockByLocation {
  warehouse_id: number
  warehouse_name: string
  warehouse_kind: 'SHOP' | 'STORAGE' | 'shop' | 'storage' | string
  quantity: number
}

export interface ProductCharacteristic {
  id?: number
  name: string
  value: string
}

export interface Product extends BaseModel {
  name: string
  category: Category | null
  category_name?: string | null
  description: string
  photo_url?: string | null
  base_price: string | null
  pricing_mode: PricingMode
  has_variants: boolean
  is_active: boolean
  display_sku?: string
  variants_count?: number
  total_stock?: number
  total_stock_all_locations?: number
  stock_at_location?: number | null
  stock_by_location?: StockByLocation[]
  availability_state?: StockAvailabilityState
  variants: ProductVariant[]
  characteristics?: ProductCharacteristic[]
}

export interface DiscountReason extends BaseModel {
  name: string
  is_default: boolean
  is_active?: boolean
}

// === Inventory / Warehouses ===

export interface Warehouse extends BaseModel {
  name: string
  kind: 'shop' | 'storage'
  address?: string
  location_type?: 'warehouse' | 'store'
  is_active: boolean
}

export interface Location extends Warehouse {
  location_type: 'warehouse' | 'store'
}

export interface LotStock {
  id: number
  warehouse: number
  warehouse_name: string
  quantity_remaining: number
}

export interface Lot extends BaseModel {
  id: number
  receipt?: number | null
  procurement_item?: number | null
  product_variant: ProductVariant
  product_variant_name?: string
  quantity_initial: number
  quantity_remaining: number
  unit_purchase_price: string
  landed_cost_per_unit: string
  contract_snapshot?: Record<string, unknown>
  is_active: boolean
  stocks?: LotStock[]
}

export interface StockMovement extends BaseModel {
  lot: number
  movement_type: string
  quantity: number
  from_location?: number | null
  from_location_name?: string | null
  to_location?: number | null
  to_location_name?: string | null
  lot_product_name?: string
  lot_procurement_id?: number | null
  lot_receipt_id?: number | null
  lot_received_at?: string | null
  lot_landed_cost_per_unit?: string | null
  reference_type?: string | null
  reference_id?: number | null
  notes?: string
}

export interface ReceiptLine extends BaseModel {
  product_variant: ProductVariant
  quantity: number
  cost_per_unit: string
  total_cost: string
}

export interface ReceiptParticipant {
  participant_type: 'business' | 'investor'
  entity_id: number
  capital_amount: string
  capital_ratio: string
  profit_ratio: string
}

export interface Receipt extends BaseModel {
  receipt_type: ReceiptType
  status: ReceiptStatus
  date: string
  destination: Location
  supplier_id: number | null
  operation_currency?: string
  operation_amount?: string | null
  fx_rate_snapshot?: string | null
  functional_amount_uzs?: string | null
  lines: ReceiptLine[]
  participants: ReceiptParticipant[]
  notes: string
}

// === Sales ===

export interface CartItem {
  product_variant: ProductVariant
  product_name: string
  pricing_mode: PricingMode
  lot_id: number | null
  location_id?: number | null
  available_stock?: number | null
  quantity: number
  operation_currency?: 'UZS' | 'USD'
  operation_unit_price?: string
  fx_rate?: string
  unit_price: string
  base_price: string
  price_changed?: boolean
  discount_reason_id: number | null
}

export interface SaleLine extends BaseModel {
  lot_id?: number
  lot?: number
  product_variant: ProductVariant | {
    id?: number
    product_name?: string
    attribute_values?: Array<{
      attribute_name: string
      value: string
    }>
  } | number
  product_name?: string
  quantity: number
  unit_price: string
  operation_currency?: string
  operation_unit_price?: string | null
  fx_rate_snapshot?: string | null
  base_price: string
  price_changed: boolean
  discount_reason: DiscountReason | null
  cost_per_unit: string
  unit_purchase_price?: string
  unit_landed_cost?: string
  profit_distribution_snapshot?: Record<string, string>
  total?: string
  gross_profit?: string
}

export interface SalePayment {
  id: number
  date: string
  amount: string
  currency: string
  fx_rate: string
  functional_amount_uzs?: string
  method: PaymentMethod
  role: 'INCOMING' | 'REFUND'
  account_id?: number | null
}

export interface Sale extends BaseModel {
  status: SaleStatus
  payment_method?: PaymentMethod | string
  payment_methods?: string[]
  customer_id?: number | null
  customer?: number | null
  customer_name?: string | null
  location_name?: string
  operation_currency?: string
  operation_amount?: string | null
  fx_rate_snapshot?: string | null
  functional_amount_uzs?: string | null
  total_amount: string
  total_cogs: string
  purchase_cost?: string
  landed_cost?: string
  gross_profit?: string
  investor_profit?: string
  business_profit?: string
  margin_percent?: string
  markup_percent?: string
  lines: SaleLine[]
  lines_count?: number
  paid_total?: string
  payments?: SalePayment[]
  notes: string
}

export interface SaleReturnLine {
  sale_line_id: number
  quantity: number
  condition: ReturnCondition
}

// === Customers ===

export interface Customer extends BaseModel {
  name: string
  phone: string
  outstanding_balance: string
}

// === Investors ===

export interface InvestorContract extends BaseModel {
  investor_id: number
  investor_name: string
  contract_type: ContractType
  default_profit_ratio: string
  status: ContractStatus
  start_date: string
  final_settlement: string | null
}

export interface InvestorLedgerTotals {
  capital_in: string
  capital_out: string
  capital_net: string
  profit_accrued: string
  profit_reversed: string
  losses_incurred: string
  dividends_paid: string
  profit_pending_payout: string
}

export interface InvestorCapitalState {
  sold_cost_uzs: string
  in_stock_cost_uzs: string
  tracked_cost_uzs: string
  sold_revenue_uzs: string
  projected_revenue_uzs: string
  projected_partner_profit_uzs: string
}

export interface InvestorDashboardAggregate extends InvestorLedgerTotals {
  partner_id: number
  summary_currency: string
  functional_uzs: InvestorLedgerTotals
  by_currency: Record<string, InvestorLedgerTotals>
  capital_state: InvestorCapitalState
}

export interface InvestorProcurementListItem {
  id: number
  procurement_type: string
  status: string
  opened_at: string
  received_at: string | null
  supplier_name: string | null
}

export interface InvestorLedgerEntry {
  id: number
  date: string
  amount: string
  currency: string
  fx_rate: string
  functional_amount_uzs: string
  entry_type: string
  source_ref: string
}

export interface InvestorProcurementDetail {
  id: number
  procurement_type: string
  status: string
  opened_at: string
  received_at: string | null
  supplier_name: string | null
  notes: string
  investor_aggregate: InvestorDashboardAggregate
  capital_state: InvestorCapitalState
  investor_ledger: {
    partner_id: number
    partner_name: string
    entries: InvestorLedgerEntry[]
  }
}

// === Suppliers ===

export interface Supplier extends BaseModel {
  name: string
  phone: string
  outstanding_balance: string
}

// === Risk ===

export interface RiskEvent extends BaseModel {
  event_type: RiskEventType
  lot_id: number | null
  quantity: number
  monetary_impact: string
  affects_investor: boolean
  negligence: boolean
  reason: string
}

// === POS Session ===

export interface PosSession extends BaseModel {
  location: Location
  status: 'open' | 'closed'
  sales_count?: number
  cash_sales_total?: string
  cash_sales_by_currency?: Record<string, string>
  opening_cash: string
  expected_cash: string | null
  actual_cash: string | null
  cash_difference: string | null
  opening_cash_by_currency?: Record<string, string>
  expected_cash_by_currency?: Record<string, string>
  actual_cash_by_currency?: Record<string, string>
  cash_difference_by_currency?: Record<string, string>
  opened_at: string
  closed_at: string | null
}
