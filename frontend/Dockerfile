# syntax=docker/dockerfile:1.7

# --------------------------------------------------------------------------- #
# deps — install exactly the lockfile, cached across source edits
# --------------------------------------------------------------------------- #
FROM node:22-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# --------------------------------------------------------------------------- #
# builder — compile the Next.js app
#
# NEXT_PUBLIC_* values are inlined into the browser bundle at build time, so
# they arrive as build args, not runtime environment. They describe how the
# *browser* reaches the API, which is why the default is the host-published
# backend port rather than the compose service name.
# --------------------------------------------------------------------------- #
FROM node:22-alpine AS builder

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_APP_NAME=BuildSEO
ARG NEXT_PUBLIC_API_TIMEOUT_MS=30000

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_APP_NAME=$NEXT_PUBLIC_APP_NAME \
    NEXT_PUBLIC_API_TIMEOUT_MS=$NEXT_PUBLIC_API_TIMEOUT_MS \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# --------------------------------------------------------------------------- #
# runtime — standalone server only, non-root
# --------------------------------------------------------------------------- #
FROM node:22-alpine AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=5175 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 buildseo \
    && adduser --system --uid 1001 --ingroup buildseo buildseo

WORKDIR /app

# `output: "standalone"` emits a self-contained server with only the modules it
# actually imports; static assets and the public folder are not included in it
# and are copied alongside.
COPY --from=builder --chown=buildseo:buildseo /app/.next/standalone ./
COPY --from=builder --chown=buildseo:buildseo /app/.next/static ./.next/static

# Never run application code as root.
USER buildseo

EXPOSE 5175

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -qO- http://127.0.0.1:5175/ >/dev/null 2>&1 || exit 1

CMD ["node", "server.js"]
