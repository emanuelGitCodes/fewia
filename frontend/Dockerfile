FROM node:22.23.0-bookworm-slim@sha256:d9f850096136edbc402debdd8729579a288aac64574ada0ff4db26b6ae58b0b2 AS build
WORKDIR /src
RUN npm install --ignore-scripts --prefix /opt/npm npm@12.0.2
ENV PATH="/opt/npm/node_modules/.bin:${PATH}"
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03
ENV FEWIA_API_UPSTREAM=api:8000
ENV FEWIA_WEB_HOST_CHECK=off
ENV NGINX_ENVSUBST_FILTER="^FEWIA_API_UPSTREAM$"
RUN mkdir -p -m 755 /etc/nginx/templates
COPY --chmod=644 nginx.conf /etc/nginx/templates/default.conf.template
COPY --chmod=644 security-headers.conf /etc/nginx/security-headers.conf
COPY --chmod=755 docker-entrypoint.d/15-validate-api-upstream.sh /docker-entrypoint.d/15-validate-api-upstream.sh
COPY --chmod=755 docker-entrypoint.d/16-validate-host-check.sh /docker-entrypoint.d/16-validate-host-check.sh
COPY --chmod=755 docker-entrypoint.d/17-select-host-check.sh /docker-entrypoint.d/17-select-host-check.sh
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
