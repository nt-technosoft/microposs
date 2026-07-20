# Design

> Visual system for Sherik. Seeded from product vision (not scanned from current
> code — the existing UI is explicitly not the target system). Re-run
> `/impeccable document` once target components exist to capture real tokens.

> **E31 scope:** deep emerald, warm neutrals, typography and semantic colors are
> the starting visual basis. This document does not prescribe information
> architecture, navigation, layout, breakpoints or component composition;
> those decisions follow the active workflow and E31 acceptance criteria.

## Theme

**Light primary.** Operational, daytime use: owner glancing in the morning,
cashier ringing sales under bright retail lighting all day, warehouse receiving
stock. Long sessions, data-heavy screens, readability first. A dark surface is
reserved for focused analytics / investor zones later — never a default "because
tools look cool dark".

Mood: **calm confidence.** Quiet, precise, trustworthy. The surface recedes so
numbers and state lead.

## Color

OKLCH throughout. Reduce chroma toward lightness extremes. Never `#000`/`#fff`.
All neutrals tinted toward the brand green hue (~162) so the whole surface feels
of one family.

**Color strategy: Committed.** Deep green is the brand carrier, not a ≤10%
accent — it holds primary actions, active nav, key surfaces. Used with restraint
elsewhere so it stays meaningful.

### Primary — deep emerald / pine (brand)

Mature, deep, slightly cool green. Trust + growth, never bright "halal-green".

```
--green-50:  oklch(0.97 0.012 165);
--green-100: oklch(0.94 0.022 165);
--green-200: oklch(0.88 0.040 165);
--green-300: oklch(0.80 0.060 165);
--green-400: oklch(0.66 0.085 165);
--green-500: oklch(0.55 0.098 165);
--green-600: oklch(0.47 0.098 165);  /* primary action */
--green-700: oklch(0.40 0.085 165);  /* hover / pressed */
--green-800: oklch(0.32 0.065 165);
--green-900: oklch(0.24 0.045 165);
```

### Neutrals — green-tinted (chroma ~0.006, hue 165)

```
--bg:        oklch(0.99 0.004 165);  /* app background, warm off-white */
--surface:   oklch(1.00 0.000 165);  /* raised surface */
--neutral-50:  oklch(0.975 0.005 165);
--neutral-100: oklch(0.95 0.006 165);
--neutral-200: oklch(0.90 0.006 165);  /* hairlines, borders */
--neutral-300: oklch(0.82 0.006 165);
--neutral-400: oklch(0.68 0.007 165);  /* disabled, placeholder */
--neutral-500: oklch(0.55 0.008 165);  /* secondary text */
--neutral-600: oklch(0.44 0.008 165);
--neutral-700: oklch(0.35 0.008 165);
--neutral-800: oklch(0.26 0.007 165);
--neutral-900: oklch(0.18 0.006 165);  /* primary text */
```

### Accent — warm sand (secondary, contrast to green)

Warmth of money; separates brand-green from data-positive-green. Used sparingly
for highlight / secondary CTA / attention.

```
--accent-400: oklch(0.82 0.090 75);
--accent-500: oklch(0.76 0.120 72);  /* accent */
--accent-600: oklch(0.68 0.130 68);  /* hover */
```

### Semantic (data) — distinct from brand hue, never color-only

Always paired with sign/icon/label (color-blind safety + bright-light legibility).

```
--positive: oklch(0.62 0.150 145);  /* profit / in — warmer success green, distinct from brand 165 */
--negative: oklch(0.56 0.120 35);   /* loss / out — calm terracotta, NOT alarm red */
--warning:  oklch(0.76 0.130 75);   /* attention — amber */
--info:     oklch(0.60 0.080 235);  /* neutral info — muted blue */
```

### Usage rules

- Profit/positive uses `--positive` + `▲`/icon, never the brand green (avoid conflating "brand" with "money up").
- Loss is terracotta, not red — this is a calm product; red is reserved for true destructive confirmation.
- One accent per view at most. Don't decorate.

## Typography

Modern neutral grotesque. Must cover **Cyrillic (ru) + Latin (uz/en)** and ship
excellent **tabular figures** (this is a numbers product).

```
--font-sans: 'Inter', system-ui, sans-serif;       /* body, UI, data */
--font-mono: 'Geist Mono', ui-monospace, monospace; /* dense numeric / ledger contexts */
```

Headings: same family, weight + size contrast (no separate display face needed
for a product register). If a more distinct heading voice is wanted later,
`Geist` or `Hanken Grotesk` are safe lanes.

**Tabular numbers mandatory** on all money/quantity: `font-variant-numeric: tabular-nums`.

### Scale (1.25 ratio, base 16)

```
--text-xs:   0.75rem;  /* 12 — captions, meta */
--text-sm:   0.875rem; /* 14 — secondary, dense tables */
--text-base: 1rem;     /* 16 — body */
--text-lg:   1.25rem;  /* 20 — section titles */
--text-xl:   1.563rem; /* 25 — screen titles */
--text-2xl:  1.953rem; /* 31 — key figures */
--text-3xl:  2.441rem; /* 39 — hero numbers (rare) */
```

Weights: 400 body, 500 emphasis, 600 titles/actions, 700 key figures. Hierarchy
through weight+scale contrast (≥1.25), never flat. Body line length ≤ 70ch.

## Spacing & Layout

Task-adaptive: compact `<768px`, drawer `768–1279px`, desktop workspace
`>=1280px`. 4px base unit.

```
--space-1: 4px;  --space-2: 8px;  --space-3: 12px; --space-4: 16px;
--space-5: 24px; --space-6: 32px; --space-7: 48px; --space-8: 64px;
```

- **Varied rhythm**, not uniform padding everywhere — spacing creates hierarchy.
- **Cards sparingly.** Lists, tables, and grouped rows often read better unwrapped. Never nested cards.
- Don't wrap everything in a container. Most things don't need one.
- Tables and numeric blocks are first-class: right-align numbers, tabular figures, clear column rhythm.

## Radius & Elevation

Confident, not bubbly.

```
--radius-sm:  6px;   --radius-md: 10px;  --radius-lg: 14px;  --radius-full: 9999px;
```

Elevation through subtle layered shadows + the tinted neutral scale, not heavy
drop shadows. Glassmorphism only rare and purposeful, never default.

```
--shadow-sm: 0 1px 2px oklch(0.18 0.006 165 / 0.06);
--shadow-md: 0 2px 8px oklch(0.18 0.006 165 / 0.08);
--shadow-lg: 0 8px 24px oklch(0.18 0.006 165 / 0.10);
```

## Motion

Calm confidence: motion **confirms** an action, never entertains.

```
--ease-out: cubic-bezier(0.22, 1, 0.36, 1);  /* ease-out-quint */
--dur-fast: 150ms;  --dur-base: 220ms;  --dur-slow: 300ms;
```

- Ease-out exponential only. No bounce, no elastic.
- Never animate layout properties (use transform/opacity).
- Always respect `prefers-reduced-motion`.

## Components (direction, not spec)

- **Buttons:** primary = green-600 solid; secondary = neutral outline; tertiary = text. Min height 44px (retail touch). Sand accent reserved for one highlight action per view.
- **Money display:** dedicated component — tabular figures, currency in the obligation currency (no auto-conversion), sign + color for direction.
- **Tables / ledgers:** first-class. Right-aligned numbers, hairline rows (neutral-200), no zebra-by-default, sticky headers on long lists.
- **Inputs:** generous targets, clear focus ring (green-600), inline validation; calm error styling (terracotta text + icon, not red flood).
- **Navigation:** mobile bottom nav primary; side/top nav on wider viewports. Active state via green, not heavy fills.
- **Status / signals:** semantic color + icon + short label. Attention is earned and pointed, never ambient.
- **Avoid:** hero-metric template, identical card grids, side-stripe accent borders, gradient text.

## Anti-slop guardrails (enforced)

- No hero-metric template (big number + gradient + supporting stats row).
- No `background-clip: text` gradients. Emphasis via weight/size/color.
- No `border-left`/`border-right` colored accent stripes on cards/alerts.
- No identical icon+heading+text card grids repeated endlessly.
- Category-reflex check: must not read as "fintech → green dashboard by default". Depth of green + tinted neutrals + restraint keep it out of the cliché.
