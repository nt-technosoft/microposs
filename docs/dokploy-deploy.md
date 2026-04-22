# Deploy in Dokploy

Новый рекомендуемый вариант для этого репо:

- `frontend` — только SPA-статика Vue
- `backend` — Django + Gunicorn
- `files` — отдельный nginx только для `/static` и `/media`
- `celery-worker` / `celery-beat` — фоновые процессы
- `redis` — внутренний сервис compose
- `postgres` — внешний Dokploy Database, подключение через `DATABASE_URL`

## Почему эта схема лучше

- Dokploy сам роутит по path, без лишнего reverse-proxy между `frontend` и `backend`
- `frontend` больше не проксирует API
- `static` и `media` отделены от SPA и API
- меньше runtime-магии и меньше шансов поймать плавающие `400`

## Что загрузить в Dokploy

1. Создать сервис типа **Docker Compose**
2. Использовать корневой [`docker-compose.yml`](/Users/aziztohirov/Desktop/Projects/microposs/docker-compose.yml)
3. Заполнить переменные по образцу [`dokploy.env.example`](/Users/aziztohirov/Desktop/Projects/microposs/dokploy.env.example)
4. В `Domains` задать один и тот же host для нескольких service/path pair

## Domains в Dokploy

Для домена `micropos.example.com` нужны такие entries:

1. `frontend` -> host `micropos.example.com` -> path `/` -> port `80`
2. `backend` -> host `micropos.example.com` -> path `/api` -> port `8000`
3. `backend` -> host `micropos.example.com` -> path `/admin` -> port `8000`
4. `files` -> host `micropos.example.com` -> path `/static` -> port `80`
5. `files` -> host `micropos.example.com` -> path `/media` -> port `80`

Для всех:

- `Internal Path` -> `/`
- `Strip Path` -> `OFF`
- `HTTPS` -> `ON`

## Обязательные переменные

- `SECRET_KEY`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
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

- Для этой схемы `VITE_API_URL` оставляй пустым
- `ALLOWED_HOSTS` должен содержать только домен приложения и локальные внутренние хосты по необходимости
- `CORS_ALLOWED_ORIGINS` и `CSRF_TRUSTED_ORIGINS` должны быть без trailing slash
