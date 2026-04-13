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
  CASH = 'cash',
  CARD = 'card',
  CREDIT = 'credit',
}

export enum PricingMode {
  ASK_EACH_SALE = 'ASK_EACH_SALE',
  DEFAULT_EDITABLE = 'DEFAULT_EDITABLE',
  FIXED_LOCKED = 'FIXED_LOCKED',
}

export enum UserRole {
  OWNER = 'owner',
  CASHIER = 'cashier',
  WAREHOUSE = 'warehouse',
  INVESTOR = 'investor',
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
