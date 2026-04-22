# Deploy in Dokploy

Короткий рабочий вариант для этого репо:

- `frontend` — собирает Vue и отдает статику через `nginx`
- `backend` — Django + Gunicorn
- `celery-worker` — фоновые задачи
- `celery-beat` — планировщик
- `redis` — внутренний сервис compose
- `postgres` — внешний сервис, подключается через `DATABASE_URL`

## Почему так

Для Dokploy это проще и надежнее:

- один публичный сервис — `frontend`
- один домен
- `nginx` проксирует `/api` и `/admin` в backend
- статика и media разнесены через volumes

## Что загрузить в Dokploy

1. Создать сервис типа **Docker Compose**
2. Использовать корневой [`docker-compose.yml`](/Users/aziztohirov/Desktop/Projects/microposs/docker-compose.yml)
3. Заполнить переменные окружения по образцу [`dokploy.env.example`](/Users/aziztohirov/Desktop/Projects/microposs/dokploy.env.example)
4. В `Domains` привязать домен к сервису `frontend`, порт `80`

## Важные замечания по Dokploy

Опирался на документацию Dokploy:

- Compose env через `.env` рядом с compose, но переменные не попадают в контейнер автоматически без `env_file` или `${VAR}`: [Docker Compose | Dokploy](https://docs.dokploy.com/docs/core/docker-compose)
- Для публичного домена Dokploy рекомендует управлять routing через UI, а не вручную через Traefik labels: [Domains | Dokploy](https://docs.dokploy.com/docs/core/docker-compose/domains)
- Для persistence лучше named volumes; абсолютные host paths использовать не стоит: [Docker Compose | Dokploy](https://docs.dokploy.com/docs/core/docker-compose)

## Обязательные переменные

- `SECRET_KEY`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `APP_DOMAIN`
- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`

## Что backend делает сам при старте

`backend` контейнер автоматически:

1. прогоняет `migrate`
2. делает `collectstatic`
3. создает/обновляет daily FX schedule
4. запускает `gunicorn`

## Что важно не ломать

- Если используешь один домен через `frontend`, оставляй `VITE_API_URL` пустым.
- Если решишь выносить API на отдельный домен, тогда уже нужно будет отдельно перенастроить `VITE_API_URL`, `CORS_ALLOWED_ORIGINS` и, возможно, `nginx.conf`.
