FROM node:24-alpine AS base
ENV NEXT_TELEMETRY_DISABLED=1
# Same version as packageManager in package.json.
RUN npm install -g pnpm@10.13.1

FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -S nodejs && adduser -S nextjs -G nodejs
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
# CHAT_API_BASE_URL, CHAT_API_INTERNAL_KEY and the DeepSeek settings are read
# at request time, so the same image runs anywhere; pass them at `docker run`.
CMD ["node", "server.js"]
