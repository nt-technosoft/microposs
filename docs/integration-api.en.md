# Integration API (YesPos)

## Environment
| | |
|---|---|
| App | https://sherik.nt-technosoft.uz/ |
| Server (IP) | `84.247.166.45` |
| Key management (create/revoke) | https://sherik.nt-technosoft.uz/settings/integrations |
| Test user | `owner` / `Owner123!` |

## Base
```
https://sherik.nt-technosoft.uz/api/v1/integrations/yespos/v1/
```

## Headers
| Header | Value | When |
|---|---|---|
| `X-Integration-Key` | integration key `ssk_yespos_live_...` | always |
| `Content-Type` | `application/json` | for POST |
| `X-Request-Id` | unique request id | optional, for POST idempotency |

The key is created in the app: **Settings → Integrations → Add key** (shown once). Revoking a key makes it invalid immediately.

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| POST | `/sale` | Sale event |
| POST | `/inventory` | Inventory event |
| POST | `/agreement-link` | Agreement event |
| POST | `/{slug}` | Custom event (`slug`: `[a-z0-9-]`, ≤64) |
| GET | `/agreements` | List active investment agreements |

POST body is an arbitrary JSON object (stored as-is).

## How it works (current phase)
For now the endpoints only **accept** requests on the given paths and **store the full body** as-is on the server (raw). There is no processing or schema validation yet.

What we need from you: send the different request types to the matching paths (`/sale` — sales, `/inventory` — stock, `/agreement-link` — agreements, `/{slug}` — anything else). Once we have the real structure and formats of the data you send, we'll lock the contract and build the processing logic on top of it.

## Responses
| Code | Body | Meaning |
|---|---|---|
| 201 | `{"id": "...", "status": "received"}` | accepted |
| 200 | `{"status": "duplicate"}` | repeat of the same `X-Request-Id` |
| 400 | `{"detail": "..."}` | invalid `slug` (only for `/{slug}`) |
| 401 | `{"detail": "..."}` | missing/invalid/revoked key, or IP not allowed |

`GET /agreements` → array of objects: `id`, `title`, `investor_name`, `profit_ratio`, `capital_amount`, `currency`, `status`.

## Security
Send the key over HTTPS only. A per-key IP allowlist is supported. Never commit the key to Git/logs.
