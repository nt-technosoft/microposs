FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci

COPY frontend ./

ARG VITE_API_URL=
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

FROM nginx:1.27-alpine

COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker/frontend/40-render-nginx.sh /docker-entrypoint.d/40-render-nginx.sh
RUN chmod +x /docker-entrypoint.d/40-render-nginx.sh
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
