# Stage deploy checklist

Перед stage/prod-like деплоем:

```bash
DJANGO_SETTINGS_MODULE=config.settings.production backend/.venv/bin/python backend/manage.py check --deploy
npm --prefix frontend run type-check
npm --prefix frontend run build
```

Обязательные правила:

- Базу stage не очищать без отдельного решения.
- `SECRET_KEY` на сервере должен быть реальным длинным секретом, не placeholder.
- `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`, secure cookies и SSL redirect должны идти из Dokploy env.
- Логин в браузере не должен быть предзаполнен. Dev-prefill допускается только через `VITE_ENABLE_LOGIN_PREFILL=true`.
- Команды demo/Excel seed/reset в `DEBUG=False` требуют явный confirm-флаг и не должны запускаться автоматически.
- `/admin/` и `/api/docs/` на stage можно оставить открытыми, но бизнес-операции всё равно требуют JWT/роль.

После деплоя вручную проверить:

- вход существующих owner/investor/cashier;
- сохранность текущих Excel demo-данных;
- страницы `/reports`, `/sales/history`, `/procurements`, `/investor`;
- CBU FX sync в логах backend/celery.
