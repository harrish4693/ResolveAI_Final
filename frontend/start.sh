#!/bin/sh
set -e

echo "[STARTUP] Starting ResolveAI V2 Frontend SSR server on port 3000..."
export NITRO_PORT=3000
export NITRO_HOST=127.0.0.1

node .output/server/index.mjs &
NODE_PID=$!

cleanup() {
    echo "[SHUTDOWN] Stopping frontend processes..."
    kill -TERM "$NODE_PID" 2>/dev/null || true
    if [ -n "$NGINX_PID" ]; then
        kill -TERM "$NGINX_PID" 2>/dev/null || true
    fi
    exit 0
}

trap cleanup TERM INT QUIT

echo "[STARTUP] Waiting for SSR server to become healthy..."
attempts=0
max_attempts=30
while ! curl -s -f http://127.0.0.1:3000/ > /dev/null 2>&1; do
    if ! kill -0 "$NODE_PID" 2>/dev/null; then
        echo "ERROR: Node SSR server process ($NODE_PID) died during initialization."
        exit 1
    fi
    attempts=$((attempts + 1))
    if [ "$attempts" -ge "$max_attempts" ]; then
        echo "ERROR: SSR server failed to respond within 15 seconds."
        kill -9 "$NODE_PID" 2>/dev/null || true
        exit 1
    fi
    sleep 0.5
done

echo "[STARTUP] SSR server is active. Starting Nginx gateway on port 8080..."
nginx -g "daemon off;" &
NGINX_PID=$!

# Continuously monitor both processes. If either crashes, kill the survivor and exit 1.
while true; do
    if ! kill -0 "$NODE_PID" 2>/dev/null; then
        echo "ERROR: Node SSR process ($NODE_PID) terminated unexpectedly."
        kill -TERM "$NGINX_PID" 2>/dev/null || true
        exit 1
    fi
    if ! kill -0 "$NGINX_PID" 2>/dev/null; then
        echo "ERROR: Nginx gateway process ($NGINX_PID) terminated unexpectedly."
        kill -TERM "$NODE_PID" 2>/dev/null || true
        exit 1
    fi
    sleep 2
done
