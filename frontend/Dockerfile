FROM node:22.23.0-bookworm-slim AS build
WORKDIR /src
RUN npm install --ignore-scripts --prefix /opt/npm npm@12.0.2
ENV PATH="/opt/npm/node_modules/.bin:${PATH}"
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginx:stable-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
