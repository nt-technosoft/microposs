#!/bin/sh
set -eu

export SERVER_NAME="${APP_DOMAIN:-_}"
export PROXY_HOST="${APP_DOMAIN:-\$host}"

envsubst '${SERVER_NAME} ${PROXY_HOST}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf
