FROM scratch AS npm-download
ADD --checksum=sha256:07fecbf753e2c3bc10ebeb3e9ed8738f6a0cc1292998b79e2e9f1dd2a5525e0c https://registry.npmjs.org/npm/-/npm-12.2.2.tgz /npm.tgz

FROM node:22-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee AS toolchain
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=bind,from=npm-download,source=/npm.tgz,target=/tmp/npm.tgz,ro \
    rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx \
    && mkdir -p /usr/local/lib/node_modules/npm \
    && tar -xzf /tmp/npm.tgz --strip-components=1 --no-same-owner -C /usr/local/lib/node_modules/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
RUN test "$(node --version)" = "v22.23.5" \
    && test "$(npm --version)" = "12.2.2" \
    && test "$(npx --version)" = "12.2.2" \
    && node -e 'const assert = require("node:assert/strict"); const npm = require("/usr/local/lib/node_modules/npm/package.json"); const semver = require("/usr/local/lib/node_modules/npm/node_modules/semver"); assert(semver.satisfies(process.version, npm.engines.node), "npm engines MUST support the pinned Node version");'

FROM toolchain AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine3.23@sha256:b3f2436575bd5be7386518084d842dac414ab4962712afa31e99e0942a56e3b2 AS runtime
USER root
RUN apk upgrade --no-cache
USER 101
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
