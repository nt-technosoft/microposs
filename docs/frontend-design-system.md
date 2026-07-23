# Frontend Design System

> Scope of this file: **stack, file map, source-of-truth hierarchy.**
> The *design intent* lives in `DESIGN.md`/`PRODUCT.md`; the *redesign method*
> lives in `.agents/skills/microposs-frontend-design/SKILL.md`. This file does
> not restate either (one source per rule). Active redesign epic: **E10**
> (`docs/roadmap/E10-frontend-redesign.md`).

## Source of truth

- **`PRODUCT.md` / `DESIGN.md`** — design intent (canon). What the design *is*:
  users, tone, anti-references, color/type/spacing/motion. `DESIGN.md` is OKLCH
  "calm confidence" (deep-emerald hue 165, numbers-first).
- **`.agents/skills/microposs-frontend-design/SKILL.md`** — how the agent works:
  redesign method, responsive rules, migration rules.
- **This file** — stack + file map (below).
- **`tokens.css`** — the *runtime mechanism*, not a rival to `DESIGN.md`. Its
  values are brought in line with `DESIGN.md`. New OKLCH tokens are additive;
  legacy `--color-*` HEX stay for un-migrated screens and are removed per
  screen as migration completes. Not a global visual reset.

## Stack

- Vue 3 + TypeScript + Vite.
- Tailwind CSS v4 (CSS-first: `@import "tailwindcss"` + `@theme inline` +
  `@source`, via `@tailwindcss/vite`). No JS config drives the build.
- **shadcn-vue = the styled wrapper layer built on Reka UI.** They are not two
  parallel component sources: Reka UI provides the headless behaviour/a11y
  primitives, shadcn-vue is the Tailwind-styled copy we vendor into
  `src/components/ui/` and customize. Treat shadcn-vue components as low-level
  primitives, composed into domain wrappers, not as the product design language
  by themselves.
- Lucide icons through `lucide-vue-next`.
- MicroPOS CSS tokens remain the visual source of truth at runtime; the OKLCH
  layer in `tokens.css` is the `DESIGN.md` canon.

## Files

- `frontend/src/assets/styles/tokens.css` — MicroPOS tokens (legacy `--color-*`
  HEX + E10 OKLCH canon) and the shadcn/Tailwind variable bridge.
- `frontend/src/assets/styles/tailwind.css` — Tailwind v4 import, `@source`,
  `@theme inline` (shadcn theme map + OKLCH utilities), base layer.
- `frontend/tailwind.config.cjs` — v3-style stub kept only for the shadcn-vue
  CLI; **not loaded by the build** (no `@config` directive). Do not rely on it.
- `frontend/components.json` — shadcn-vue registry/config.
- `frontend/src/components/ui/` — vendored shadcn-vue components.
- `frontend/src/lib/utils.ts` — `cn()` helper for class merging.
- `.mcp.json` — project MCP entry for `shadcn-vue`.
- `.agents/skills/shadcn-vue/` — shadcn-vue usage rules for Codex/other agents.

## Method & migration

See `.agents/skills/microposs-frontend-design/SKILL.md`. In short: workflow
before components; mobile-first not mobile-only; screen-by-screen migration,
no global reset; "preserve contract, rebuild presentation" per redesigned
screen (full method in the skill).

Useful commands:

```bash
cd frontend
npm run ui:info
npm run ui:add -- button
npm run mcp:shadcn
```

## Configured registries

`frontend/components.json` configures a small registry set:

- Built-in `@shadcn` — official shadcn-vue components and blocks.
- `@ai-elements-vue` — Vue AI/chat components; use only if an AI workflow is
  added to the product.

Do not add registries globally just to increase choice. Add a new registry only
when it provides a concrete component/pattern needed by an active screen.
