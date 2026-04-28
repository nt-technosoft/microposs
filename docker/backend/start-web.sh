#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py collectstatic --noinput

FX_SYNC_BASE="${FX_SYNC_BASE_CURRENCY:-USD}"
FX_SYNC_QUOTE="${FX_SYNC_QUOTE_CURRENCY:-UZS}"
FX_SYNC_TZ="${FX_SYNC_TIMEZONE:-Asia/Tashkent}"
FX_SYNC_RUN_HOUR="${FX_SYNC_HOUR:-8}"
FX_SYNC_RUN_MINUTE="${FX_SYNC_MINUTE:-5}"
FX_SYNC_OVERWRITE="${FX_SYNC_OVERWRITE_MANUAL:-false}"
SCHEDULE_OVERWRITE_FLAG="--no-overwrite-manual"
SYNC_OVERWRITE_FLAG=""
if [ "$FX_SYNC_OVERWRITE" = "true" ] || [ "$FX_SYNC_OVERWRITE" = "True" ] || [ "$FX_SYNC_OVERWRITE" = "1" ]; then
  SCHEDULE_OVERWRITE_FLAG="--overwrite-manual"
  SYNC_OVERWRITE_FLAG="--overwrite-manual"
fi

python manage.py setup_fx_rate_schedule \
  --timezone "$FX_SYNC_TZ" \
  --hour "$FX_SYNC_RUN_HOUR" \
  --minute "$FX_SYNC_RUN_MINUTE" \
  --base-currency "$FX_SYNC_BASE" \
  --quote-currency "$FX_SYNC_QUOTE" \
  "$SCHEDULE_OVERWRITE_FLAG"

python manage.py sync_exchange_rates \
  --base-currency "$FX_SYNC_BASE" \
  --quote-currency "$FX_SYNC_QUOTE" \
  $SYNC_OVERWRITE_FLAG

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-1}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile -
