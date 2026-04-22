# Production Smoke Checklist

Короткий чек после deploy и после `bootstrap_deploy_baseline`.

## 1. Auth

- открыть `/login`
- войти `owner / Owner123!`
- проверить, что `POST /api/v1/auth/token/` и `GET /api/v1/auth/me/` -> `200`

## 2. Core screens

- `/sales` открывается без `400/401/405`
- `/products` показывает каталог
- `/reports` открывается без красных API ошибок
- `/admin/` отвечает

## 3. Inventory / transfer

- `/stock/transfers` открывается
- есть `ASOSIY` и `DOKON`
- список товаров для transfer не пустой

## 4. Investor baseline

- войти `investor / Investor123!`
- `/api/v1/investors/dashboard/` -> `200`
- dashboard не весь в нулях
- `/api/v1/investors/procurements/` содержит хотя бы один procurement

## 5. Static / media

- `GET /static/...` отвечает `200`
- если есть загруженные фото, `GET /media/...` отвечает `200`

## 6. Domain routing

- `POST /api/v1/auth/token/` не должен попадать во frontend nginx
- если видишь `405 nginx`, значит сломан Dokploy path routing
