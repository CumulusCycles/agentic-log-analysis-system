# Stage 1 — React frontend build
FROM node:22-alpine AS frontend

RUN corepack enable
WORKDIR /build

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts

COPY frontend ./
RUN pnpm run build


# Stage 2 — Backend TS build
FROM node:22-alpine AS backend

RUN corepack enable
WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts

COPY tsconfig.json ./
COPY src ./src
RUN pnpm run build


# Stage 3 — Production node_modules (no devDeps)
FROM node:22-alpine AS prod-deps

RUN corepack enable
WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --prod --ignore-scripts


# Stage 4 — runtime
FROM node:20-alpine AS runtime

WORKDIR /app
# node:20-alpine already ships with a `node` user at UID 1000 — use it so we
# match the FNOL non-root convention without colliding with the prebuilt UID.
RUN mkdir -p /app/logs && chown -R node:node /app

COPY --from=backend    --chown=node:node /app/dist          ./dist
COPY --from=prod-deps  --chown=node:node /app/node_modules  ./node_modules
COPY --from=frontend   --chown=node:node /build/dist        ./frontend/dist
COPY --chown=node:node package.json ./

ENV NODE_ENV=production

USER node
EXPOSE 3000

CMD ["node", "dist/server.js"]
