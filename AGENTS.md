# MicroPOS — Project Instructions

## Overview
MicroPOS — mobile-first POS platform for small retail businesses with Islamic partnership financing support (Mudaraba, Musharaka), consignment trading, and multi-location inventory.

## Architecture
- **Monorepo**: `backend/` (Django) + `frontend/` (Vue.js 3)
- **Backend**: Python 3.12 / Django 5.x / DRF / PostgreSQL 16 / Redis / Celery
- **Frontend**: Vue.js 3 + TypeScript + Pinia + Vue Router + Vite

## Key Business Rules (NEVER violate)
1. Products appear ONLY through Receipt (except initial inventory)
2. Receipt.status = confirmed -> immutable forever
3. SaleLine always references Lot (not ProductVariant directly)
4. FIFO by default for lot selection
5. sum(profit_ratio of all participants) == 1.0
6. capital_ratio is auto-calculated from capital_amount
7. Credit sale requires customer_id
8. InvestorContract closes only if no active Lots remain
9. Moving Lot changes only location, not participants/shares
10. JournalEntry created automatically for every financial operation
11. All significant operations write OutboxEvent
12. Physical delete() forbidden for Sale, Receipt, JournalEntry, Lot

## Backend Conventions
- All models inherit `core.BaseModel` (soft-delete, timestamps)
- Domain apps don't import each other's models for business logic
- Cross-domain communication: services layer + OutboxEvent
- ForeignKey across domains is allowed
- Service layer pattern: `services.py` in each app
- All POST endpoints for financial ops accept `client_request_id` (idempotency)
- Multi-tenant: `tenant_id` on all business data models
- Immutable financial records after confirmed/completed status

## Frontend Conventions
- Mobile-first, responsive (375px -> 768px -> 1024px -> 1440px)
- Vue 3 Composition API + `<script setup>` syntax
- Pinia stores per domain
- API layer in `src/api/` with typed clients
- Components: `src/components/` (shared) + `src/modules/<domain>/components/`
- Design tokens in CSS custom properties
- Lucide icons (no emojis as structural icons)
- All animations 150-300ms, respect prefers-reduced-motion
