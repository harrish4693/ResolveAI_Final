# Multi-stage production build for ResolveAI V2 Frontend
# Stage 1: Build TanStack Start SSR application
FROM node:20-alpine AS builder

WORKDIR /app

# Install build dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy application source
COPY . .

# Build application with node-server Nitro preset
ENV NITRO_PRESET=node-server
RUN npm run build

# Stage 2: Production runtime with SSR and rootless Nginx reverse proxy
FROM node:20-alpine AS runner

WORKDIR /app

# Install Nginx and curl for healthchecks
RUN apk add --no-cache nginx curl

# Copy built artifacts and configurations
COPY --from=builder /app/.output ./.output
COPY nginx.conf /etc/nginx/nginx.conf
COPY start.sh ./start.sh

# Normalize script line-endings and set up non-root permissions
RUN sed -i 's/\r$//' ./start.sh && \
    chmod +x ./start.sh && \
    mkdir -p /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp /var/log/nginx && \
    chown -R node:node /app /tmp /var/log/nginx

USER node

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:8080/healthz || exit 1

CMD ["./start.sh"]

