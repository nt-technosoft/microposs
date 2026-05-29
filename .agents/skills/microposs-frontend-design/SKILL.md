---
name: microposs-frontend-design
description: Project frontend workflow for MicroPOS/Sherik POS UI design and redesign. Use when creating, redesigning, or reviewing app screens, especially procurement, sales, reports, finance, inventory, navigation, mobile/desktop responsive behavior, Tailwind/shadcn-vue usage, or design-system decisions.
---

# MicroPOS Frontend Design

Use this skill for any frontend screen design, redesign, or UI implementation in
MicroPOS / Sherik POS.

## Stack

- Vue 3 + TypeScript + Vite.
- Tailwind CSS v4 as the utility layer (CSS-first config).
- **shadcn-vue = styled wrappers built on Reka UI** (not two parallel sources):
  Reka = headless behaviour/a11y primitives, shadcn-vue = the Tailwind-styled
  copy vendored into `src/components/ui/`. Use as low-level primitives.
- Lucide icons through `lucide-vue-next`.
- MicroPOS CSS tokens remain the visual source of truth. Design intent canon
  is `DESIGN.md` (OKLCH "calm confidence"); `tokens.css` is the runtime
  mechanism aligned to it.

## Workflow

1. Start from the business workflow and the most common user path.
2. Design mobile-first, but never mobile-only.
3. Pick shadcn-vue primitives only after the workflow is clear.
4. Compose primitives into domain wrappers instead of scattering raw shadcn-vue
   everywhere.
5. Verify on mobile and desktop viewports before treating a screen as done.

## Redesign method — "preserve contract, rebuild presentation"

When redesigning an existing screen (not greenfield), logic is an asset to
keep; markup and scoped CSS are a liability to replace. Do NOT edit the old
template in place (you inherit its layout decisions), and do NOT rip the logic
out (you risk re-deriving business rules and breaking Key Business Rules).

1. **Extract & freeze the contract.** Per block: business rules, data
   inputs/outputs, states (loading / empty / error / edge), events emitted,
   props consumed, invariants. Write it down. This is what must not be lost.
2. **IA-first shape.** Re-derive the screen's composition from the workflow
   (mobile + desktop). The existing component decomposition served the OLD UX,
   so it is not sacred: old blocks may survive, merge, split, or die. Sketch
   2-3 layout directions, pick one, before touching blocks.
3. **Rebuild per-block.** Keep the `<script setup>` logic (composables, state
   derivation, API, events); rebuild `<template>` + `<style scoped>` on
   shadcn-vue/Tailwind + domain wrappers against `DESIGN.md`. One block at a
   time, not the whole page at once.
4. **Verify.** Mobile + desktop widths, every state, and contrast of
   brand-green (hue 165) vs positive-green (hue 145) in dense data.

## Responsive Rules

- Mobile is the primary design target for data entry and quick operational work.
- Desktop must be planned for data-heavy screens: procurement, sales/POS,
  reports, finance, inventory and supplier/payable flows.
- Do not stretch mobile cards into desktop. Use split workspace layouts where
  they improve scanning and repeated action.
- Keep one business state model per screen; adapt layout by viewport.
- Navigation is currently bottom-nav-first across authenticated app screens
  until a dedicated desktop shell is designed.

## Design-System Rules

- Use existing shared components first.
- Use shadcn-vue primitives for new or redesigned sections.
- Use domain wrappers for repeated app patterns, for example stage panels,
  amount summaries, line selectors, payment sheets and action bars.
- Keep colors semantic: `primary`, `muted`, `destructive`, `background`,
  `foreground`, or MicroPOS token variables. Do not introduce raw ad hoc
  palettes.
- Use lucide icons for tool/action buttons.
- Avoid decorative dashboard-card grids for operational workflows.

## Migration Rules

- Migrate screen-by-screen and workflow-by-workflow.
- Do not run a global visual reset while legacy screens are active.
- Avoid mixing old and new primitives inside the same small interaction except
  as a temporary bridge during a focused migration.
- Remove obsolete scoped CSS only after the section has fully moved to the new
  approach.

