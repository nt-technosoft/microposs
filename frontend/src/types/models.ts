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

// === Catalog ===

export interface Category extends BaseModel {
  name: string
  parent_id: number | null
  default_pricing_mode: PricingMode
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
  sku: string
  price: string | null
  effective_price: string
  is_active: boolean
  attribute_values: Array<{
    attribute_name: string
    value: string
  }>
  stock_quantity?: number
}

export interface Product extends BaseModel {
  name: string
  category: Category | null
  description: string
  base_price: string | null
  pricing_mode: PricingMode
  has_variants: boolean
  is_active: boolean
  variants: ProductVariant[]
}

export interface DiscountReason extends BaseModel {
  name: string
  is_default: boolean
}

// === Inventory ===

export interface Location extends BaseModel {
  name: string
  location_type: 'warehouse' | 'store'
  is_active: boolean
}

export interface Lot extends BaseModel {
  receipt_id: number
  product_variant: ProductVariant
  location: Location
  quantity_initial: number
  quantity_remaining: number
  cost_per_unit: string
  is_active: boolean
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
  lines: ReceiptLine[]
  participants: ReceiptParticipant[]
  notes: string
}

// === Sales ===

export interface CartItem {
  product_variant: ProductVariant
  product_name: string
  lot_id: number | null
  quantity: number
  unit_price: string
  base_price: string
  discount_reason_id: number | null
}

export interface SaleLine extends BaseModel {
  lot_id: number
  product_variant: ProductVariant
  quantity: number
  unit_price: string
  base_price: string
  price_changed: boolean
  discount_reason: DiscountReason | null
  cost_per_unit: string
}

export interface Sale extends BaseModel {
  status: SaleStatus
  payment_method: PaymentMethod
  customer_id: number | null
  total_amount: string
  total_cogs: string
  lines: SaleLine[]
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

export interface InvestorSummary {
  total_invested: string
  in_stock_value: string
  total_sold_revenue: string
  total_profit: string
  total_losses: string
  turnover_ratio: string
  business_owes: string
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
  opening_cash: string
  expected_cash: string | null
  actual_cash: string | null
  cash_difference: string | null
  opened_at: string
  closed_at: string | null
}
