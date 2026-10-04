FROM node:22.23.0-bookworm-slim AS build
WORKDIR /src
RUN npm install --ignore-scripts --prefix /opt/npm npm@12.0.2
ENV PATH="/opt/npm/node_modules/.bin:${PATH}"
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine
ENV FEWIA_API_UPSTREAM=api:8000
ENV NGINX_ENVSUBST_FILTER="^FEWIA_API_UPSTREAM$"
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --chmod=755 docker-entrypoint.d/15-validate-api-upstream.sh /docker-entrypoint.d/15-validate-api-upstream.sh
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
