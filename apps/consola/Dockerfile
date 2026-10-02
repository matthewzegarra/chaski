# syntax=docker/dockerfile:1.7
# Build context: repository root (pnpm workspace).
FROM node:22-alpine AS build
RUN npm install -g pnpm@12.3.4
WORKDIR /src
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY packages/shared/package.json packages/shared/
COPY apps/consola/package.json apps/consola/
RUN --mount=type=cache,id=pnpm,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --filter "@chaski/consola..."
COPY packages/shared packages/shared
COPY apps/consola apps/consola
RUN pnpm --filter @chaski/consola build

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY docker/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --chmod=755 docker/web/40-chaski-env.sh /docker-entrypoint.d/40-chaski-env.sh
COPY --from=build --chown=101:101 /src/apps/consola/dist /usr/share/nginx/html
USER 101
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
