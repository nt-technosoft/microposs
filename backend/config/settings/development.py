"""Development settings."""

from .base import *  # noqa: F401, F403

DEBUG = True

INSTALLED_APPS += ['debug_toolbar']  # noqa: F405

MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')  # noqa: F405

INTERNAL_IPS = ['127.0.0.1']

# Dev stability: do not keep persistent DB connections between requests.
DATABASES['default']['CONN_MAX_AGE'] = 0  # noqa: F405
DATABASES['default']['CONN_HEALTH_CHECKS'] = True  # noqa: F405

# Run Celery tasks synchronously in dev/test — no worker required.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
