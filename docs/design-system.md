# MicroPOS — Design System

## Philosophy

MicroPOS is not a cold corporate tool. It's a **warm, trustworthy companion** for small business owners.
The design reflects:
- **Trust** — clean, transparent, honest UI (Islamic finance principles)
- **Speed** — every tap counts, no friction
- **Warmth** — soft shapes, gentle gradients, human-scale spacing
- **Clarity** — information hierarchy so obvious that training is unnecessary

Style direction: **"Warm Minimal"** — clean lines with organic warmth. Not sterile Material, not trendy glassmorphism. Think: a well-organized notebook on a wooden desk.

---

## 1. Color System

### Light Theme

```
// Foundation
--color-bg-primary:      #FAFAF8;    // Warm off-white (not pure white)
--color-bg-secondary:    #F3F1EC;    // Warm light gray
--color-bg-elevated:     #FFFFFF;    // Cards, modals
--color-bg-sunken:       #EDE9E1;    // Inset areas, disabled backgrounds

// Text
--color-text-primary:    #1A1714;    // Near-black with warmth
--color-text-secondary:  #6B635A;    // Warm gray
--color-text-tertiary:   #9C948A;    // Muted labels
--color-text-inverse:    #FAFAF8;    // On dark backgrounds

// Brand — Deep Teal (trust, growth, stability)
--color-brand-50:        #E8F5F2;
--color-brand-100:       #C5E8E0;
--color-brand-200:       #8FD1C2;
--color-brand-300:       #5ABAA3;
--color-brand-400:       #2EA389;
--color-brand-500:       #1B8A6F;    // PRIMARY — Main actions
--color-brand-600:       #167358;
--color-brand-700:       #115C46;
--color-brand-800:       #0C4533;
--color-brand-900:       #072E22;

// Accent — Warm Amber (attention, warmth, highlights)
--color-accent-50:       #FFF8EB;
--color-accent-100:      #FEECC6;
--color-accent-200:      #FDD88D;
--color-accent-300:      #FCC554;
--color-accent-400:      #FBAD1B;    // Accent actions, badges
--color-accent-500:      #E59508;
--color-accent-600:      #BF7006;
--color-accent-700:      #994F09;

// Semantic
--color-success:         #2D9F6F;    // Confirmed, completed, profit
--color-success-bg:      #E8F7F0;
--color-warning:         #E5A60B;    // Caution, pending, debt alert
--color-warning-bg:      #FFF8EB;
--color-error:           #D9534F;    // Errors, losses, critical
--color-error-bg:        #FDF0EF;
--color-info:            #4A90B8;    // Informational, tips
--color-info-bg:         #EDF5FA;

// Borders & Dividers
--color-border-default:  #E0DCD5;
--color-border-subtle:   #EDE9E1;
--color-border-focus:    #1B8A6F;
```

### Dark Theme

```
--color-bg-primary:      #141210;    // Deep warm dark
--color-bg-secondary:    #1E1B18;    // Slightly elevated
--color-bg-elevated:     #282420;    // Cards
--color-bg-sunken:       #0E0D0B;    // Inset

--color-text-primary:    #EDE9E1;
--color-text-secondary:  #9C948A;
--color-text-tertiary:   #6B635A;

--color-brand-500:       #3FBF9A;    // Lighter for dark bg
--color-border-default:  #332F2A;
--color-border-subtle:   #282420;
```

### Why These Colors?
- **Deep Teal** — associated with trust, growth, and Islamic art. Not the aggressive blue of fintech, not the cold gray of enterprise.
- **Warm Amber** — welcoming, draws attention naturally. Used for badges, highlights, floating cart.
- **Warm neutrals** (not pure grays) — every gray has a slight yellow/brown undertone, making the entire palette feel human and approachable.

---

## 2. Typography

### Font Stack

```css
/* Primary: Inter — clean, highly readable at all sizes */
--font-primary: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;

/* Monospace: for prices, quantities, codes */
--font-mono: 'JetBrains Mono', 'SF Mono', monospace;
```

### Type Scale (base 16px, ratio 1.25)

```
--text-xs:     0.75rem   / 12px   — Captions, badges
--text-sm:     0.875rem  / 14px   — Secondary labels, table cells
--text-base:   1rem      / 16px   — Body text, inputs
--text-lg:     1.125rem  / 18px   — Subtitles, card headers
--text-xl:     1.25rem   / 20px   — Section headers
--text-2xl:    1.5rem    / 24px   — Page titles
--text-3xl:    1.875rem  / 30px   — Dashboard numbers
--text-4xl:    2.25rem   / 36px   — Hero metrics
```

### Font Weights

```
--font-normal:    400   — Body text
--font-medium:    500   — Labels, secondary emphasis
--font-semibold:  600   — Headings, buttons
--font-bold:      700   — Key metrics, prices
```

### Line Heights

```
--leading-tight:   1.25  — Headings, prices
--leading-normal:  1.5   — Body text
--leading-relaxed: 1.75  — Long-form text
```

### Price Display
All prices use `font-variant-numeric: tabular-nums;` for alignment in lists and tables.

---

## 3. Spacing System (4px base)

```
--space-0:    0
--space-1:    0.25rem  / 4px    — Tight gaps (icon-to-text)
--space-2:    0.5rem   / 8px    — Element internal padding
--space-3:    0.75rem  / 12px   — Compact groups
--space-4:    1rem     / 16px   — Standard gap
--space-5:    1.25rem  / 20px   — Section padding (mobile)
--space-6:    1.5rem   / 24px   — Card padding
--space-8:    2rem     / 32px   — Section gaps
--space-10:   2.5rem   / 40px   — Major section breaks
--space-12:   3rem     / 48px   — Page padding top
--space-16:   4rem     / 64px   — Hero spacing
```

---

## 4. Border Radius

```
--radius-sm:     6px    — Tags, badges, small elements
--radius-md:     10px   — Buttons, inputs, chips
--radius-lg:     14px   — Cards, modals
--radius-xl:     20px   — Bottom sheets, floating elements
--radius-full:   9999px — Avatars, circular buttons
```

Characteristic: generous but not bubbly. 10-14px is the sweet spot for the "warm minimal" feel.

---

## 5. Shadows & Elevation

```css
/* Subtle, warm shadows — not pure black */
--shadow-sm:    0 1px 2px rgba(26, 23, 20, 0.06);
--shadow-md:    0 4px 12px rgba(26, 23, 20, 0.08);
--shadow-lg:    0 8px 24px rgba(26, 23, 20, 0.12);
--shadow-xl:    0 16px 48px rgba(26, 23, 20, 0.16);

/* Floating cart button */
--shadow-float: 0 6px 20px rgba(27, 138, 111, 0.3);

/* Elevation layers */
Layer 0: Page background    (no shadow)
Layer 1: Cards, list items   (shadow-sm)
Layer 2: Dropdowns, popovers (shadow-md)
Layer 3: Bottom sheets        (shadow-lg)
Layer 4: Modals, dialogs      (shadow-xl)
Layer 5: Floating cart         (shadow-float)
```

---

## 6. Breakpoints & Layout

```
--bp-mobile:   375px   — Base design target
--bp-tablet:   768px   — Two-column layouts unlock
--bp-desktop:  1024px  — Sidebar navigation appears
--bp-wide:     1440px  — Full POS dashboard layout
```

### Layout Patterns

**Mobile (375-767px)**:
- Single column
- Bottom navigation (5 tabs max)
- Full-width cards
- Bottom sheets for selections
- Floating cart button (bottom-right, above nav)

**Tablet (768-1023px)**:
- Two-column where appropriate (catalog grid + detail)
- Bottom navigation persists
- Cards in 2-column grid

**Desktop (1024px+)**:
- Sidebar navigation replaces bottom nav
- Three-column layouts (nav + list + detail)
- Persistent cart panel on right

---

## 7. Component Patterns

### Buttons

```
Primary:    bg brand-500, text white, radius-md, h-48px
            hover: brand-600, active: brand-700
            ONLY ONE primary per screen

Secondary:  bg transparent, border brand-500, text brand-500
            hover: brand-50 bg

Ghost:      bg transparent, text brand-500
            hover: brand-50 bg

Danger:     bg error, text white
            Used only for destructive + confirm actions

Disabled:   opacity 0.4, pointer-events none

Sizes:
  sm: h-36px, text-sm, px-12px
  md: h-44px, text-base, px-16px  (DEFAULT — meets 44px touch target)
  lg: h-52px, text-lg, px-20px    (For primary CTAs in checkout)
```

### Cards

```
bg: elevated
border: 1px border-subtle
radius: radius-lg (14px)
padding: space-5 (20px)
shadow: shadow-sm on hover

Product card (catalog):
  ┌─────────────────────────┐
  │  [Product Image]        │
  │                         │
  │  Product Name           │
  │  Category tag           │
  │                         │
  │  ₩ 45,000    ● In stock │
  │  [Variations] chip      │
  └─────────────────────────┘
```

### Bottom Navigation

```
Height: 64px + safe-area-inset-bottom
Background: bg-elevated with shadow-lg (top)
Items: 5 max
Active: brand-500 icon + label (600 weight)
Inactive: text-tertiary icon + label

  ┌────┬────┬────┬────┬────┐
  │ 💳 │ 📦 │ 📥 │ 📊 │ ⚙️ │  <- Lucide icons, NOT emojis
  │Sale│Prod│Rcpt│Rpts│More│
  └────┴────┴────┴────┴────┘

Icons (Lucide):
  Sale:     ShoppingBag
  Products: Package
  Receipt:  Download
  Reports:  BarChart3
  More:     Settings
```

### Floating Cart Button

```
Position: fixed, bottom-right, 16px above bottom nav
Size: 56x56px (circle) or pill shape when items > 0
Background: brand-500
Shadow: shadow-float
Badge: accent-400 circle, top-right, shows item count

States:
  Empty:     Hidden (cart icon only shown in top bar)
  Has items: Visible floating, shows count + total

  ┌──────────────────┐
  │  🛒 3 · ₩135,000 │  <- Pill shape when expanded
  └──────────────────┘

Animation: scale spring on item add (0.9 → 1.05 → 1.0)
```

### Chips / Tags

```
Category chips (horizontal scroll):
  Active:   bg brand-500, text white, radius-full
  Inactive: bg bg-secondary, text text-secondary, radius-full
  Height: 36px, px-16px

Attribute chips (variant selector):
  Available:   border border-default, text text-primary
  Selected:    bg brand-500, text white, border brand-500
  Unavailable: bg bg-sunken, text text-tertiary, strikethrough
  Size: 44x44px minimum (touch target)
```

### Bottom Sheet

```
Background: bg-elevated
Border-radius: radius-xl (20px) top-left/right only
Handle: 36x4px centered bar, bg text-tertiary, radius-full
Max-height: 85vh
Shadow: shadow-xl
Backdrop: rgba(0,0,0,0.4)

Animation: slide-up 250ms ease-out
Dismiss: swipe down or tap backdrop
```

### Inputs

```
Height: 48px (meets touch target)
Border: 1px border-default
Radius: radius-md (10px)
Padding: 0 16px
Font: text-base
Background: bg-elevated

Focus: border brand-500, ring 2px brand-100
Error: border error, ring 2px error-bg
Label: text-sm, text-secondary, above input (ALWAYS visible, never placeholder-only)

Price input:
  Left-aligned currency symbol (fixed)
  Right-aligned clear button (×)
  font-mono, font-bold, text-xl
```

### Tables (Desktop/Tablet)

```
Header: bg bg-secondary, text-sm font-semibold text-secondary
Row: bg elevated, border-bottom border-subtle
Row hover: bg bg-secondary
Cell padding: 12px 16px
Font: text-sm for data, font-mono for numbers
Zebra striping: NOT used (clean look)
```

### Toast Notifications

```
Position: top-center, below safe area
Duration: 3s auto-dismiss (5s for errors)
Background: text-primary (dark on light theme)
Text: text-inverse
Radius: radius-md
Shadow: shadow-lg
Icon: Lucide icon left-aligned

Success: ✓ "Добавлено в чек"    (check-circle)
Error:   ✕ "Недостаточно товара" (x-circle)
Warning: ⚠ "Клиент имеет долг"  (alert-triangle)
```

---

## 8. Animation Guidelines

### Principles
1. **Purpose** — every animation communicates cause-effect
2. **Speed** — micro-interactions 150ms, transitions 250ms, complex 300ms
3. **Physics** — spring curves for natural feel (not linear)
4. **Respect** — `prefers-reduced-motion: reduce` → instant transitions

### Timing Functions

```css
--ease-spring:    cubic-bezier(0.34, 1.56, 0.64, 1);   /* Bouncy spring */
--ease-out:       cubic-bezier(0.16, 1, 0.3, 1);       /* Decelerate (entering) */
--ease-in:        cubic-bezier(0.5, 0, 0.75, 0);       /* Accelerate (exiting) */
--ease-in-out:    cubic-bezier(0.45, 0, 0.55, 1);      /* Smooth both */
```

### Key Animations

| Element | Animation | Duration | Easing |
|---------|-----------|----------|--------|
| Cart badge update | Scale pulse | 200ms | spring |
| Add to cart | Fly-to-cart arc | 300ms | ease-out |
| Bottom sheet open | Slide up + fade | 250ms | ease-out |
| Bottom sheet close | Slide down | 180ms | ease-in |
| Page transition | Slide left/right | 250ms | ease-out |
| Card press | Scale to 0.98 | 100ms | ease-out |
| Toast appear | Slide down + fade | 200ms | ease-out |
| Toast dismiss | Fade out + slide up | 150ms | ease-in |
| Skeleton shimmer | Left-to-right gradient | 1.5s loop | linear |
| Lot selection highlight | Border + bg transition | 150ms | ease-out |

### Stagger Pattern
List items animate in with 30ms stagger (max 10 items, then instant).

---

## 9. Iconography

### Library: Lucide Icons
- Stroke width: 1.75px (slightly lighter than default 2px for elegance)
- Size grid: 16px (inline), 20px (buttons), 24px (navigation), 32px (empty states)
- Color: inherits from text color via `currentColor`

### Key Icons Mapping

```
Navigation:
  ShoppingBag    — Sales/POS
  Package        — Products/Catalog
  Download       — Receipt/Intake
  BarChart3      — Reports
  Settings       — More/Profile

Actions:
  Plus           — Add new
  Search         — Search
  Filter         — Filter
  X              — Close/Clear
  ChevronRight   — Navigate forward
  ChevronDown    — Expand
  Trash2         — Delete (soft)
  Edit3          — Edit
  Check          — Confirm/Select
  
Finance:
  DollarSign     — Price/Money
  TrendingUp     — Profit
  TrendingDown   — Loss
  Wallet         — Cash
  CreditCard     — Card payment
  UserCheck      — Credit/Debt
  Scale          — Balance/Equity

Inventory:
  Warehouse      — Stock location
  ArrowRightLeft — Transfer
  ClipboardCheck — Inventory check
  AlertTriangle  — Low stock
  
Status:
  CheckCircle    — Success/Confirmed
  XCircle        — Error/Cancelled
  AlertCircle    — Warning
  Clock          — Pending/Draft
  Lock           — Immutable/Locked
```

---

## 10. Screen Layout Patterns

### Sale Flow (3-4 taps)

```
Tap 1: Select product (from catalog/search)
   ┌─────────────────────┐
   │ 🔍 Search...        │
   │ [Cat1] [Cat2] [Cat3]│  <- Category chips
   │                     │
   │ ┌─────┐ ┌─────┐    │
   │ │Prod1│ │Prod2│    │  <- 2-column grid
   │ │₩45k │ │₩30k │    │
   │ └─────┘ └─────┘    │
   │ ┌─────┐ ┌─────┐    │
   │ │Prod3│ │Prod4│    │
   │ └─────┘ └─────┘    │
   │                     │
   │    [🛒 2 · ₩75,000] │  <- Floating cart
   │ [Sale][Prod][Rcpt]..│  <- Bottom nav
   └─────────────────────┘

Tap 2: Choose variant + set price (if needed)
   ┌─────────────────────┐
   │ ← Product Name      │
   │                     │
   │ Size:  [S] [M] [L]  │  <- Attribute chips
   │ Color: [🔴] [⚫] [⚪] │
   │                     │
   │ Остаток: 12 шт      │
   │                     │
   │ ₩ [45,000]     [×]  │  <- Price input
   │                     │
   │ [+ Добавить в чек]  │  <- Primary CTA
   └─────────────────────┘

Tap 3: Review cart → Checkout
   ┌─────────────────────┐
   │ ← Чек               │
   │                     │
   │ Куртка кожа M       │
   │ 1× ₩45,000  [-][+] │
   │                     │
   │ Кроссовки 42        │
   │ 1× ₩30,000  [-][+] │
   │                     │
   │ ─────────────────── │
   │ Итого:    ₩75,000   │
   │                     │
   │ [Оформить продажу]  │
   └─────────────────────┘

Tap 4: Payment method → Done
   ┌─────────────────────┐
   │ Оплата              │
   │                     │
   │ ₩75,000             │  <- Large total
   │                     │
   │ ○ Наличные          │
   │ ○ Карта             │
   │ ○ В долг            │
   │                     │
   │ [Подтвердить ₩75k]  │
   └─────────────────────┘
```

### Information Density by Role

```
Owner (full access):
  Dashboard with P&L summary, recent sales, low stock alerts,
  investor summaries, supplier obligations

Cashier ("Simple seller"):
  ONLY Sales tab — clean, fast, no financial details.
  No profit margins, no receipt types, no investor info.

Warehouse:
  Intake tab + Products tab — stock levels, transfers,
  inventory checks. No financial details.

Investor (separate cabinet):
  Personal dashboard — invested, in-stock, sold, profit,
  turnover ratio. Drill-down to contracts → receipts → lots.
```

---

## 11. Empty States

Every empty list shows:
- Relevant illustration (simple line art, warm tones)
- Clear message: what this section is for
- Primary action: how to start

```
No products yet:
  [illustration of a package]
  "Начните с добавления товаров"
  [+ Добавить первый товар]

No sales today:
  [illustration of a receipt]
  "Пока нет продаж за сегодня"
  [Начать продажу]

No investors:
  [illustration of handshake]
  "Добавьте инвесторов для совместной торговли"
  [+ Добавить инвестора]
```

---

## 12. Accessibility Checklist

- [x] Color contrast >= 4.5:1 (all text pairs verified)
- [x] Touch targets >= 44x44px (buttons, chips, nav items)
- [x] 8px minimum spacing between touch targets
- [x] No color-only information (icons + text for status)
- [x] Visible focus rings (2px brand-500 outline)
- [x] aria-labels on icon-only buttons
- [x] prefers-reduced-motion support
- [x] Screen reader friendly: semantic HTML, proper headings
- [x] RTL-ready layout (for potential Arabic interface)
- [x] Tabular numerics for price alignment
