/**
 * Shared enums matching backend choices.
 */

export enum ReceiptType {
  BUSINESS_OWNED = 'BUSINESS_OWNED',
  MUDARABA = 'MUDARABA',
  MUSHARAKA = 'MUSHARAKA',
  SUPPLIER_PURCHASE = 'SUPPLIER_PURCHASE',
  CONSIGNMENT = 'CONSIGNMENT',
}

export enum ReceiptStatus {
  DRAFT = 'draft',
  CONFIRMED = 'confirmed',
}

export enum SaleStatus {
  DRAFT = 'draft',
  COMPLETED = 'completed',
  RETURNED = 'returned',
}

export enum PaymentMethod {
  CASH = 'CASH',
  CARD = 'CARD',
  TRANSFER = 'TRANSFER',
  CREDIT = 'CREDIT',
  CASH_LEGACY = 'cash',
  CARD_LEGACY = 'card',
  CREDIT_LEGACY = 'credit',
}

export enum PricingMode {
  ALWAYS_ASK = 'ALWAYS_ASK',
  EDITABLE = 'EDITABLE',
  FIXED = 'FIXED',
  ASK_EACH_SALE = 'ALWAYS_ASK',
  DEFAULT_EDITABLE = 'EDITABLE',
  FIXED_LOCKED = 'FIXED',
}

export enum UserRole {
  OWNER = 'owner',
  CASHIER = 'cashier',
  WAREHOUSE = 'warehouse',
  INVESTOR = 'investor',
  PLATFORM_ADMIN = 'platform_admin',
}

export enum ProcurementType {
  OWN_FUNDS = 'OWN_FUNDS',
  PARTNERSHIP = 'PARTNERSHIP',
  MUSHARAKA = 'MUSHARAKA',
  DISTRIBUTOR = 'DISTRIBUTOR',
}

export enum ProcurementStatus {
  OPEN = 'OPEN',
  PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED',
  RECEIVED = 'RECEIVED',
  CLOSED = 'CLOSED',
  CANCELLED = 'CANCELLED',
}

export enum ContractType {
  MUDARABA = 'MUDARABA',
  MUSHARAKA = 'MUSHARAKA',
}

export enum ContractStatus {
  ACTIVE = 'active',
  CLOSED = 'closed',
}

export enum RiskEventType {
  WRITEOFF = 'writeoff',
  DAMAGE = 'damage',
  LOSS = 'loss',
  RETURN = 'return',
  STOCK_MISMATCH = 'stock_mismatch',
  ADJUSTMENT = 'adjustment',
  CASH_MISMATCH = 'cash_mismatch',
}

export enum ReturnCondition {
  GOOD = 'good',
  DAMAGED = 'damaged',
}
