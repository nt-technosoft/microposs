# WGT-010 / Confirm and Error Patterns

## Purpose
Единый паттерн для destructive confirmations, blocked-state explanations и actionable error recovery.

## Used in screens
- return flow
- finance actions
- payout actions
- procurement receive block
- session closing and other risky operations

## Required behavior
- explain cause, not only show generic failure
- when possible, suggest next action
- confirm destructive actions before irreversible effect
- keep copy concise and role-appropriate

## UX rules
- no vague 'something went wrong' for critical flows
- confirmation copy should state what changes and what cannot be undone
- on mobile, dialogs/bottom sheets must remain readable and easy to dismiss or confirm intentionally
